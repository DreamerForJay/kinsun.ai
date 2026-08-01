import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { test } from 'node:test';
import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { CanonicalStagingFoundationStack } from '../lib/canonical-staging-foundation-stack';

const synthesizedTemplate = (): Template => {
  const app = new cdk.App();
  const stack = new CanonicalStagingFoundationStack(app, 'TestCanonicalStagingFoundation', {
    environmentName: 'staging',
    env: { region: 'us-west-2' },
  });
  return Template.fromStack(stack);
};

test('creates only the canonical asset-free foundation', () => {
  const template = synthesizedTemplate();

  template.resourceCountIs('AWS::EC2::VPC', 1);
  template.resourceCountIs('AWS::EC2::NatGateway', 1);
  template.resourceCountIs('AWS::ECR::Repository', 4);
  template.resourceCountIs('AWS::ECS::Cluster', 1);
  template.resourceCountIs('AWS::ECS::Service', 0);
  template.resourceCountIs('AWS::ECS::TaskDefinition', 0);
  template.resourceCountIs('AWS::RDS::DBCluster', 1);
  template.resourceCountIs('AWS::RDS::DBInstance', 1);

  template.hasResourceProperties('AWS::RDS::DBCluster', {
    DatabaseName: 'kinsun',
    DeletionProtection: true,
    Engine: 'aurora-postgresql',
    EngineVersion: '16.8',
    ServerlessV2ScalingConfiguration: {
      MinCapacity: 0,
      MaxCapacity: 1,
      SecondsUntilAutoPause: 900,
    },
    StorageEncrypted: true,
  });
  const databaseClusters = template.findResources('AWS::RDS::DBCluster');
  const databaseCluster = Object.values(databaseClusters)[0] as {
    DeletionPolicy?: string;
    UpdateReplacePolicy?: string;
  };
  assert.equal(databaseCluster.DeletionPolicy, 'Snapshot');
  assert.equal(databaseCluster.UpdateReplacePolicy, 'Snapshot');
  template.hasResource('AWS::SecretsManager::Secret', {
    DeletionPolicy: 'Retain',
    UpdateReplacePolicy: 'Retain',
    Properties: Match.objectLike({ Name: 'kinsun/staging/aurora/admin' }),
  });
  template.hasResource('AWS::SecretsManager::Secret', {
    DeletionPolicy: 'Retain',
    UpdateReplacePolicy: 'Retain',
    Properties: Match.objectLike({
      Name: 'kinsun/staging/aurora/runtime',
      Description: 'Least-privilege Core API Aurora runtime credential',
      GenerateSecretString: {
        SecretStringTemplate: '{"username":"kinsun_app"}',
        GenerateStringKey: 'password',
        PasswordLength: 64,
        ExcludePunctuation: true,
      },
    }),
  });
  template.hasResourceProperties('AWS::RDS::DBInstance', {
    DBInstanceClass: 'db.serverless',
    PubliclyAccessible: false,
  });
  template.hasResourceProperties('AWS::ECR::Repository', {
    RepositoryName: 'kinsun/staging/core-migration',
  });
  const repositories = template.findResources('AWS::ECR::Repository');
  for (const repository of Object.values(repositories) as Array<{
    Properties?: { LifecyclePolicy?: { LifecyclePolicyText?: string } };
  }>) {
    const lifecyclePolicy = repository.Properties?.LifecyclePolicy?.LifecyclePolicyText ?? '';
    assert.match(lifecyclePolicy, /tagStatus.*untagged/i);
    assert.doesNotMatch(lifecyclePolicy, /imageCountMoreThan/i);
  }
});

test('separates Aurora administrator and runtime secret access', () => {
  const template = synthesizedTemplate();
  const resources = template.toJSON().Resources as Record<
    string,
    { Type: string; Properties?: Record<string, unknown> }
  >;

  const roleId = (roleName: string): string => {
    const match = Object.entries(resources).find(
      ([, resource]) =>
        resource.Type === 'AWS::IAM::Role' && resource.Properties?.RoleName === roleName,
    );
    assert.ok(match, `missing ${roleName}`);
    return match[0];
  };
  const policyForRole = (logicalRoleId: string): string => {
    const match = Object.values(resources).find((resource) => {
      if (resource.Type !== 'AWS::IAM::Policy') return false;
      const roles = resource.Properties?.Roles as Array<Record<string, string>> | undefined;
      return roles?.some((role) => role.Ref === logicalRoleId);
    });
    assert.ok(match, `missing inline policy for ${logicalRoleId}`);
    return JSON.stringify(match.Properties?.PolicyDocument);
  };

  const adminSecretId = Object.entries(resources).find(
    ([, resource]) =>
      resource.Type === 'AWS::SecretsManager::Secret' &&
      resource.Properties?.Name === 'kinsun/staging/aurora/admin',
  )?.[0];
  const adminSecretAttachmentId = Object.entries(resources).find(
    ([, resource]) => resource.Type === 'AWS::SecretsManager::SecretTargetAttachment',
  )?.[0];
  const runtimeSecretId = Object.entries(resources).find(
    ([, resource]) =>
      resource.Type === 'AWS::SecretsManager::Secret' &&
      resource.Properties?.Name === 'kinsun/staging/aurora/runtime',
  )?.[0];
  assert.ok(adminSecretId);
  assert.ok(adminSecretAttachmentId);
  assert.ok(runtimeSecretId);

  const corePolicy = policyForRole(roleId('kinsun-core-execution-staging'));
  assert.match(corePolicy, new RegExp(runtimeSecretId));
  assert.doesNotMatch(corePolicy, new RegExp(adminSecretId));
  assert.doesNotMatch(corePolicy, new RegExp(adminSecretAttachmentId));

  const migrationPolicy = policyForRole(roleId('kinsun-migration-execution-staging'));
  assert.match(migrationPolicy, new RegExp(runtimeSecretId));
  // CDK grants consumers the attached secret ARN, not the pre-attachment resource ARN.
  assert.match(migrationPolicy, new RegExp(adminSecretAttachmentId));

  const outputs = template.toJSON().Outputs as Record<string, unknown>;
  assert.ok(outputs.DatabaseAdminSecretArn);
  assert.ok(outputs.DatabaseRuntimeSecretArn);
});

test('does not recreate or deploy the rejected legacy backend', () => {
  const template = synthesizedTemplate();

  for (const resourceType of [
    'AWS::Cognito::UserPool',
    'AWS::DynamoDB::Table',
    'AWS::Lambda::Function',
    'AWS::OpenSearchServerless::Collection',
    'AWS::StepFunctions::StateMachine',
  ]) {
    template.resourceCountIs(resourceType, 0);
  }

  const parameters = template.toJSON().Parameters as Record<
    string,
    { AllowedValues?: string[]; Default?: string }
  >;
  assert.ok(parameters.CognitoUserPoolId);
  assert.ok(parameters.OpenSearchCollectionId);
  const cognitoWebBffClientId = parameters.CognitoWebBffClientId;
  assert.ok(cognitoWebBffClientId);
  assert.equal(cognitoWebBffClientId.Default, '5gqrkek6hfn8ub2ba5nsdtup81');
  assert.deepEqual(cognitoWebBffClientId.AllowedValues, ['5gqrkek6hfn8ub2ba5nsdtup81']);
  template.hasResourceProperties(
    'AWS::SSM::Parameter',
    Match.objectLike({ Name: '/kinsun/staging/external/cognito-user-pool-id' }),
  );
  template.hasResourceProperties('AWS::SSM::Parameter', {
    Name: '/kinsun/staging/external/cognito-web-bff-client-id',
    Value: { Ref: 'CognitoWebBffClientId' },
  });
});

test('canonical entrypoints pin the physical CloudFormation stack identities', () => {
  const foundationEntry = readFileSync(
    resolve(__dirname, '../bin/canonical-staging.ts'),
    'utf8',
  );
  const applicationEntry = readFileSync(
    resolve(__dirname, '../bin/canonical-staging-application.ts'),
    'utf8',
  );

  assert.match(foundationEntry, /stackName:\s*'kinsun-staging-foundation-v1'/);
  assert.match(applicationEntry, /stackName:\s*'kinsun-staging-application-v1'/);
});
