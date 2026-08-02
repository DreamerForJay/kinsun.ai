import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { CanonicalStagingApplicationStack } from '../lib/canonical-staging-application-stack';

const synthesizedTemplate = (): Template => {
  const app = new cdk.App();
  const stack = new CanonicalStagingApplicationStack(app, 'TestCanonicalStagingApplication', {
    environmentName: 'staging',
    env: { region: 'us-west-2' },
    privateSubnetAvailabilityZones: ['us-west-2a', 'us-west-2b'],
  });
  return Template.fromStack(stack);
};

test('creates a private three-service runtime that starts scaled to zero', () => {
  const template = synthesizedTemplate();

  template.resourceCountIs('AWS::ECS::TaskDefinition', 4);
  template.resourceCountIs('AWS::ECS::Service', 3);
  template.resourceCountIs('AWS::ApiGatewayV2::Api', 1);
  template.resourceCountIs('AWS::ApiGatewayV2::VpcLink', 1);
  template.resourceCountIs('AWS::ElasticLoadBalancingV2::LoadBalancer', 1);

  template.hasResourceProperties('AWS::ElasticLoadBalancingV2::LoadBalancer', {
    Scheme: 'internal',
    Type: 'application',
  });
  template.hasResourceProperties('AWS::ECS::Service', {
    DesiredCount: { Ref: 'ServiceDesiredCount' },
    LaunchType: 'FARGATE',
    EnableExecuteCommand: false,
    NetworkConfiguration: {
      AwsvpcConfiguration: Match.objectLike({ AssignPublicIp: 'DISABLED' }),
    },
    ServiceConnectConfiguration: Match.objectLike({ Enabled: true }),
  });
  const parameters = template.toJSON().Parameters as Record<
    string,
    { AllowedValues?: Array<string | number>; Default?: string | number }
  >;
  const serviceDesiredCount = parameters.ServiceDesiredCount;
  assert.ok(serviceDesiredCount);
  assert.equal(serviceDesiredCount.Default, 0);
  assert.deepEqual(serviceDesiredCount.AllowedValues, ['0', '1']);
  assert.equal(parameters.ConsentPolicyVersion?.Default, 'demo-consent-v1');
});

test('uses immutable digests and runtime-only secret injection', () => {
  const template = synthesizedTemplate();
  const document = template.toJSON() as {
    Parameters: Record<string, { AllowedPattern?: string; NoEcho?: boolean }>;
    Resources: Record<string, { Type: string; Properties?: Record<string, unknown> }>;
  };

  for (const name of [
    'FrontendImageDigest',
    'CoreApiImageDigest',
    'MigrationImageDigest',
    'AgentImageDigest',
  ]) {
    assert.equal(document.Parameters[name]?.AllowedPattern, '^sha256:[a-f0-9]{64}$');
  }
  for (const name of [
    'DatabaseAdminSecretArn',
    'DatabaseRuntimeSecretArn',
    'OauthTransactionSecretArn',
    'FamilyInviteSecretArn',
  ]) {
    assert.equal(document.Parameters[name]?.NoEcho, true);
  }
  assert.equal(document.Parameters.DatabaseSecretArn, undefined);

  const taskDefinitions = Object.values(document.Resources).filter(
    (resource) => resource.Type === 'AWS::ECS::TaskDefinition',
  );
  assert.equal(taskDefinitions.length, 4);
  for (const taskDefinition of taskDefinitions) {
    const containers = taskDefinition.Properties?.ContainerDefinitions as Array<Record<string, unknown>>;
    assert.equal(containers.length, 1);
    const container = containers[0];
    assert.ok(container);
    assert.equal(container.ReadonlyRootFilesystem, true);
    assert.match(JSON.stringify(container.Image), /@/);
    assert.doesNotMatch(JSON.stringify(containers), /ACCESS_KEY|SECRET_ACCESS_KEY|GOOGLE.*SECRET/i);
  }

  const migration = taskDefinitions.find((taskDefinition) =>
    JSON.stringify(taskDefinition.Properties).includes('kinsun-staging-migration'),
  );
  assert.ok(migration);
  const migrationContainer = (migration.Properties?.ContainerDefinitions as Array<Record<string, unknown>>)[0];
  assert.ok(migrationContainer);
  assert.equal(migrationContainer.HealthCheck, undefined);
  assert.equal(migrationContainer.PortMappings, undefined);
  assert.match(JSON.stringify(migrationContainer.Image), /core-migration/);
  assert.match(JSON.stringify(migrationContainer.Secrets), /DatabaseAdminSecretArn/);
  assert.match(JSON.stringify(migrationContainer.Secrets), /DatabaseRuntimeSecretArn/);

  const core = taskDefinitions.find((taskDefinition) =>
    JSON.stringify(taskDefinition.Properties).includes('kinsun-staging-core'),
  );
  assert.ok(core);
  const coreContainer = (core.Properties?.ContainerDefinitions as Array<Record<string, unknown>>)[0];
  assert.ok(coreContainer);
  assert.match(JSON.stringify(coreContainer.HealthCheck), /127\.0\.0\.1:8000\/health/);
  assert.doesNotMatch(JSON.stringify(coreContainer.HealthCheck), /\/ready/);
  assert.match(JSON.stringify(coreContainer.Secrets), /DatabaseRuntimeSecretArn/);
  assert.doesNotMatch(JSON.stringify(coreContainer.Secrets), /DatabaseAdminSecretArn/);
  const coreEnvironment = JSON.stringify(coreContainer.Environment);
  assert.match(coreEnvironment, /DB_POOL_MODE.*null/);
  assert.match(coreEnvironment, /DB_CONNECT_TIMEOUT_SECONDS.*5/);
  assert.match(coreEnvironment, /DB_RECOVERY_TIMEOUT_SECONDS.*10/);
  assert.doesNotMatch(coreEnvironment, /DB_POOL_SIZE|DB_MAX_OVERFLOW/);
});

test('exposes only the BFF and does not recreate external or legacy services', () => {
  const template = synthesizedTemplate();

  template.hasResourceProperties('AWS::ApiGatewayV2::Integration', {
    ConnectionType: 'VPC_LINK',
    IntegrationType: 'HTTP_PROXY',
    IntegrationMethod: 'ANY',
  });
  template.hasResourceProperties('AWS::ElasticLoadBalancingV2::TargetGroup', {
    HealthCheckPath: '/health',
    TargetType: 'ip',
  });
  for (const resourceType of [
    'AWS::Cognito::UserPool',
    'AWS::Cognito::UserPoolClient',
    'AWS::DynamoDB::Table',
    'AWS::Lambda::Function',
    'AWS::OpenSearchServerless::Collection',
    'AWS::RDS::DBCluster',
  ]) {
    template.resourceCountIs(resourceType, 0);
  }

  const document = template.toJSON() as {
    Resources: Record<string, { Type: string; Properties?: Record<string, unknown> }>;
  };
  const services = Object.values(document.Resources).filter((resource) => resource.Type === 'AWS::ECS::Service');
  const loadBalancedServices = services.filter((resource) => resource.Properties?.LoadBalancers !== undefined);
  assert.equal(loadBalancedServices.length, 1);
  assert.match(JSON.stringify(loadBalancedServices[0]), /frontend/);

  const stage = Object.values(document.Resources).find((resource) => resource.Type === 'AWS::ApiGatewayV2::Stage');
  assert.ok(stage);
  const accessLog = JSON.stringify(stage.Properties?.AccessLogSettings);
  assert.doesNotMatch(accessLog, /authoriz|header|query|string|body|identity/i);
});
