import * as cdk from 'aws-cdk-lib';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';

export interface CanonicalStagingApplicationStackProps extends cdk.StackProps {
  readonly environmentName?: 'staging';
  readonly privateSubnetAvailabilityZones?: readonly [string, string];
}

interface RuntimeContainerProps {
  readonly taskDefinition: ecs.FargateTaskDefinition;
  readonly name: string;
  readonly repository: ecr.IRepository;
  readonly imageDigest: string;
  readonly containerPort: number;
  readonly portMappingName: string;
  readonly logGroup: logs.ILogGroup;
  readonly environment: Record<string, string>;
  readonly secrets?: Record<string, ecs.Secret>;
  readonly healthPath: string;
  readonly healthRuntime: 'node' | 'python';
}

/**
 * Asset-free staging application runtime.
 *
 * Images must already exist in the retained foundation ECR repositories. The
 * stack defaults every service to desiredCount=0 so schema migration and the
 * external Cognito callback update can finish before traffic is enabled.
 */
export class CanonicalStagingApplicationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CanonicalStagingApplicationStackProps = {}) {
    super(scope, id, props);

    const environmentName = props.environmentName ?? 'staging';
    const privateSubnetAvailabilityZones = props.privateSubnetAvailabilityZones ?? ['us-west-2a', 'us-west-2b'];
    new cdk.CfnRule(this, 'UsWest2Only', {
      assertions: [
        {
          assert: cdk.Fn.conditionEquals(cdk.Aws.REGION, 'us-west-2'),
          assertDescription: 'The staging application runtime must be deployed in us-west-2.',
        },
      ],
    });

    const owner = this.stringParameter('Owner', 'member-c', 'Operational owner tag for the staging application runtime.');
    const expiresAt = new cdk.CfnParameter(this, 'ExpiresAt', {
      type: 'String',
      default: '2026-09-01',
      allowedPattern: '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$',
      constraintDescription: 'Use an ISO calendar date such as 2026-09-01.',
      description: 'Review or teardown date; this tag does not delete resources automatically.',
    });

    const vpcId = this.requiredParameter('VpcId', 'AWS::EC2::VPC::Id', 'VpcId output from kinsun-staging-foundation-v1.');
    const privateSubnet1Id = this.requiredParameter(
      'PrivateSubnet1Id',
      'AWS::EC2::Subnet::Id',
      'First private application subnet from the foundation stack.',
    );
    const privateSubnet2Id = this.requiredParameter(
      'PrivateSubnet2Id',
      'AWS::EC2::Subnet::Id',
      'Second private application subnet from the foundation stack.',
    );
    const apiVpcLinkSecurityGroupId = this.securityGroupParameter('ApiVpcLinkSecurityGroupId');
    const frontendSecurityGroupId = this.securityGroupParameter('FrontendSecurityGroupId');
    const coreSecurityGroupId = this.securityGroupParameter('CoreSecurityGroupId');
    const agentSecurityGroupId = this.securityGroupParameter('AgentSecurityGroupId');
    const migrationSecurityGroupId = this.securityGroupParameter('MigrationSecurityGroupId');
    const clusterName = this.stringParameter('EcsClusterName', 'kinsun-staging', 'Existing foundation ECS cluster name.');
    const cloudMapNamespace = this.stringParameter(
      'CloudMapNamespace',
      'staging.kinsun.internal',
      'Existing foundation ECS Service Connect namespace.',
    );

    const databaseEndpoint = this.requiredParameter(
      'DatabaseEndpoint',
      'String',
      'Aurora writer endpoint from the foundation stack.',
    );
    const databasePort = new cdk.CfnParameter(this, 'DatabasePort', {
      type: 'Number',
      default: 5432,
      allowedValues: ['5432'],
      description: 'Aurora PostgreSQL port from the foundation stack.',
    });
    const databaseAdminSecretArn = this.arnParameter(
      'DatabaseAdminSecretArn',
      'Foundation Aurora administrator Secret ARN; migration task only.',
    );
    const databaseRuntimeSecretArn = this.arnParameter(
      'DatabaseRuntimeSecretArn',
      'Foundation least-privilege Core runtime Secret ARN.',
    );
    const oauthTransactionSecretArn = this.arnParameter(
      'OauthTransactionSecretArn',
      'Foundation frontend OAuth transaction secret ARN.',
    );
    const familyInviteSecretArn = this.arnParameter(
      'FamilyInviteSecretArn',
      'Foundation family invitation HMAC secret ARN.',
    );

    const frontendImageDigest = this.imageDigestParameter('FrontendImageDigest');
    const coreApiImageDigest = this.imageDigestParameter('CoreApiImageDigest');
    const migrationImageDigest = this.imageDigestParameter('MigrationImageDigest');
    const agentImageDigest = this.imageDigestParameter('AgentImageDigest');
    const bedrockEmbeddingModelId = new cdk.CfnParameter(this, 'BedrockEmbeddingModelId', {
      type: 'String',
      default: 'us.cohere.embed-v4:0',
      allowedValues: ['us.cohere.embed-v4:0'],
      description: 'Approved staging query-embedding inference profile ID.',
    });
    const desiredCount = new cdk.CfnParameter(this, 'ServiceDesiredCount', {
      type: 'Number',
      default: 0,
      allowedValues: ['0', '1'],
      description: 'Desired count for each staging service. Staging is capped at one task; keep 0 until all deployment gates pass.',
    });
    const consentPolicyVersion = new cdk.CfnParameter(this, 'ConsentPolicyVersion', {
      type: 'String',
      default: 'demo-consent-v1',
      allowedPattern: '^[a-z0-9][a-z0-9._-]{0,39}$',
      description: 'Synthetic staging consent policy compiled into the exact frontend release image.',
    });

    cdk.Tags.of(this).add('Project', 'kinsun.ai');
    cdk.Tags.of(this).add('Environment', environmentName);
    cdk.Tags.of(this).add('DataClass', 'synthetic-only');
    cdk.Tags.of(this).add('ManagedBy', 'aws-cdk');
    cdk.Tags.of(this).add('Owner', owner.valueAsString, { excludeResourceTypes: ['aws:cdk:stack'] });
    cdk.Tags.of(this).add('ExpiresAt', expiresAt.valueAsString, { excludeResourceTypes: ['aws:cdk:stack'] });

    const vpc = ec2.Vpc.fromVpcAttributes(this, 'FoundationVpc', {
      vpcId: vpcId.valueAsString,
      availabilityZones: [...privateSubnetAvailabilityZones],
      privateSubnetIds: [privateSubnet1Id.valueAsString, privateSubnet2Id.valueAsString],
    });
    const privateSubnets = vpc.selectSubnets({ subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS });
    const apiVpcLinkSecurityGroup = ec2.SecurityGroup.fromSecurityGroupId(
      this,
      'ApiVpcLinkSecurityGroup',
      apiVpcLinkSecurityGroupId.valueAsString,
      { mutable: false },
    );
    const frontendSecurityGroup = this.importSecurityGroup('FrontendSecurityGroup', frontendSecurityGroupId);
    const coreSecurityGroup = this.importSecurityGroup('CoreSecurityGroup', coreSecurityGroupId);
    const agentSecurityGroup = this.importSecurityGroup('AgentSecurityGroup', agentSecurityGroupId);
    const migrationSecurityGroup = this.importSecurityGroup('MigrationSecurityGroup', migrationSecurityGroupId);
    const cluster = ecs.Cluster.fromClusterAttributes(this, 'FoundationCluster', {
      clusterName: clusterName.valueAsString,
      vpc,
      hasEc2Capacity: false,
    });

    const repositories = {
      frontend: ecr.Repository.fromRepositoryName(this, 'FrontendRepository', `kinsun/${environmentName}/frontend`),
      core: ecr.Repository.fromRepositoryName(this, 'CoreRepository', `kinsun/${environmentName}/core-api`),
      migration: ecr.Repository.fromRepositoryName(
        this,
        'MigrationRepository',
        `kinsun/${environmentName}/core-migration`,
      ),
      agent: ecr.Repository.fromRepositoryName(this, 'AgentRepository', `kinsun/${environmentName}/agent-runtime`),
    };
    const logGroups = {
      frontend: logs.LogGroup.fromLogGroupName(this, 'FrontendLogGroup', `/kinsun/${environmentName}/frontend`),
      core: logs.LogGroup.fromLogGroupName(this, 'CoreLogGroup', `/kinsun/${environmentName}/core-api`),
      agent: logs.LogGroup.fromLogGroupName(this, 'AgentLogGroup', `/kinsun/${environmentName}/agent-runtime`),
      migration: logs.LogGroup.fromLogGroupName(this, 'MigrationLogGroup', `/kinsun/${environmentName}/migration`),
    };
    const roles = {
      frontendExecution: this.importRole('FrontendExecutionRole', `kinsun-frontend-execution-${environmentName}`),
      frontendTask: this.importRole('FrontendTaskRole', `kinsun-frontend-ecs-${environmentName}`),
      coreExecution: this.importRole('CoreExecutionRole', `kinsun-core-execution-${environmentName}`),
      coreTask: this.importRole('CoreTaskRole', `kinsun-core-ecs-${environmentName}`),
      agentExecution: this.importRole('AgentExecutionRole', `kinsun-agent-execution-${environmentName}`),
      agentTask: this.importRole('AgentTaskRole', `kinsun-agent-runtime-ecs-${environmentName}`),
      migrationExecution: this.importRole('MigrationExecutionRole', `kinsun-migration-execution-${environmentName}`),
      migrationTask: this.importRole('MigrationTaskRole', `kinsun-migration-ecs-${environmentName}`),
    };
    const databaseAdminSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      'DatabaseAdminSecret',
      databaseAdminSecretArn.valueAsString,
    );
    const databaseRuntimeSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      'DatabaseRuntimeSecret',
      databaseRuntimeSecretArn.valueAsString,
    );
    const oauthTransactionSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      'OauthTransactionSecret',
      oauthTransactionSecretArn.valueAsString,
    );
    const familyInviteSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      'FamilyInviteSecret',
      familyInviteSecretArn.valueAsString,
    );

    const cognitoUserPoolId = ssm.StringParameter.valueForStringParameter(
      this,
      `/kinsun/${environmentName}/external/cognito-user-pool-id`,
    );
    const cognitoWebClientId = ssm.StringParameter.valueForStringParameter(
      this,
      `/kinsun/${environmentName}/external/cognito-web-bff-client-id`,
    );
    const cognitoDomain = ssm.StringParameter.valueForStringParameter(
      this,
      `/kinsun/${environmentName}/external/cognito-domain`,
    );
    const openSearchEndpoint = ssm.StringParameter.valueForStringParameter(
      this,
      `/kinsun/${environmentName}/external/opensearch-endpoint`,
    );
    const openSearchIndex = ssm.StringParameter.valueForStringParameter(
      this,
      `/kinsun/${environmentName}/external/opensearch-index`,
    );
    const openSearchAlias = ssm.StringParameter.valueForStringParameter(
      this,
      `/kinsun/${environmentName}/external/opensearch-alias`,
    );

    const apiAccessLogs = new logs.LogGroup(this, 'ApiAccessLogs', {
      logGroupName: `/kinsun/${environmentName}/api-gateway`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const httpApi = new apigwv2.HttpApi(this, 'FrontendHttpApi', {
      apiName: `kinsun-${environmentName}-frontend`,
      createDefaultStage: false,
      description: 'Public HTTP entry point for the canonical Next.js BFF only.',
    });
    const publicOrigin = httpApi.apiEndpoint;

    const frontendTask = this.taskDefinition(
      'FrontendTask',
      roles.frontendExecution,
      roles.frontendTask,
      512,
      1024,
    );
    frontendTask.addVolume({ name: 'next-cache' });
    const frontendContainer = this.runtimeContainer({
      taskDefinition: frontendTask,
      name: 'frontend',
      repository: repositories.frontend,
      imageDigest: frontendImageDigest.valueAsString,
      containerPort: 3000,
      portMappingName: 'frontend-http',
      logGroup: logGroups.frontend,
      environment: {
        NODE_ENV: 'production',
        PORT: '3000',
        HOSTNAME: '0.0.0.0',
        CORE_API_INTERNAL_URL: 'http://core-api:8000',
        CORE_ONBOARDING_REDEEM_URL: 'http://core-api:8000/api/v1/onboarding/resolve',
        FRONTEND_ORIGIN: publicOrigin,
        COGNITO_OAUTH_DOMAIN: cognitoDomain,
        COGNITO_WEB_CLIENT_ID: cognitoWebClientId,
        COGNITO_CALLBACK_URL: `${publicOrigin}/backend/auth/callback`,
        COGNITO_LOGOUT_URL: `${publicOrigin}/sign-in`,
        NEXT_PUBLIC_CONSENT_POLICY_VERSION: consentPolicyVersion.valueAsString,
        NEXT_PUBLIC_WS_URL: '',
      },
      secrets: {
        COGNITO_OAUTH_TRANSACTION_SECRET: ecs.Secret.fromSecretsManager(oauthTransactionSecret),
      },
      healthPath: '/health',
      healthRuntime: 'node',
    });
    frontendContainer.addMountPoints({
      sourceVolume: 'next-cache',
      containerPath: '/app/packages/frontend/.next/cache',
      readOnly: false,
    });

    const coreTask = this.taskDefinition('CoreTask', roles.coreExecution, roles.coreTask, 512, 1024);
    this.runtimeContainer({
      taskDefinition: coreTask,
      name: 'core-api',
      repository: repositories.core,
      imageDigest: coreApiImageDigest.valueAsString,
      containerPort: 8000,
      portMappingName: 'core-api',
      logGroup: logGroups.core,
      environment: {
        APP_ENV: 'production',
        HOST: '0.0.0.0',
        PORT: '8000',
        DB_HOST: databaseEndpoint.valueAsString,
        DB_PORT: databasePort.valueAsString,
        DB_NAME: 'kinsun',
        DB_SSLMODE: 'require',
        DB_POOL_MODE: 'null',
        DB_CONNECT_TIMEOUT_SECONDS: '5',
        DB_RECOVERY_TIMEOUT_SECONDS: '10',
        COGNITO_AUTH_ENABLED: 'true',
        COGNITO_REGION: cdk.Aws.REGION,
        COGNITO_USER_POOL_ID: cognitoUserPoolId,
        COGNITO_APP_CLIENT_ID: cognitoWebClientId,
        AGENT_RUNTIME_URL: 'http://agent-runtime:8001',
        AGENT_RUNTIME_MODEL_ID: 'mock',
      },
      secrets: {
        DB_USERNAME: ecs.Secret.fromSecretsManager(databaseRuntimeSecret, 'username'),
        DB_PASSWORD: ecs.Secret.fromSecretsManager(databaseRuntimeSecret, 'password'),
        FAMILY_INVITATION_HMAC_SECRET: ecs.Secret.fromSecretsManager(familyInviteSecret),
      },
      // Container health is liveness only. A transient Aurora outage must not
      // cause ECS to restart an otherwise healthy API process in a loop.
      healthPath: '/health',
      healthRuntime: 'python',
    });

    const agentTask = this.taskDefinition('AgentTask', roles.agentExecution, roles.agentTask, 512, 1024);
    this.runtimeContainer({
      taskDefinition: agentTask,
      name: 'agent-runtime',
      repository: repositories.agent,
      imageDigest: agentImageDigest.valueAsString,
      containerPort: 8001,
      portMappingName: 'agent-runtime',
      logGroup: logGroups.agent,
      environment: {
        APP_ENV: 'staging',
        LOG_LEVEL: 'INFO',
        MODEL_PROVIDER: 'mock',
        CORE_API_BASE_URL: 'http://core-api:8000',
        AWS_REGION: cdk.Aws.REGION,
        BEDROCK_EMBEDDING_MODEL_ID: bedrockEmbeddingModelId.valueAsString,
        BEDROCK_EMBEDDING_DIMENSION: '1024',
        OPENSEARCH_HOST: openSearchEndpoint,
        OPENSEARCH_INDEX: openSearchIndex,
        OPENSEARCH_ALIAS: openSearchAlias,
        RAG_MODE: 'staging',
        RAG_EMBEDDING_CONFIG_PATH: '/app/config/rag/embedding.yaml',
        RAG_OPENSEARCH_INDEX_CONFIG_PATH: '/app/config/rag/opensearch-index-v1.json',
        RAG_HYBRID_NATURAL_CONFIG_PATH: '/app/config/rag/hybrid-natural-language.json',
        RAG_HYBRID_LEGAL_CONFIG_PATH: '/app/config/rag/hybrid-legal.json',
      },
      healthPath: '/health',
      healthRuntime: 'python',
    });

    const migrationTask = this.taskDefinition(
      'MigrationTask',
      roles.migrationExecution,
      roles.migrationTask,
      512,
      1024,
    );
    migrationTask.addContainer('migrationContainer', {
      containerName: 'migration',
      image: ecs.ContainerImage.fromRegistry(
        `${repositories.migration.repositoryUri}@${migrationImageDigest.valueAsString}`,
      ),
      essential: true,
      readonlyRootFilesystem: true,
      environment: {
        APP_ENV: 'production',
        DB_HOST: databaseEndpoint.valueAsString,
        DB_PORT: databasePort.valueAsString,
        DB_NAME: 'kinsun',
        DB_SSLMODE: 'require',
        DATABASE_DRIVER: 'postgresql+psycopg',
      },
      secrets: {
        DB_USERNAME: ecs.Secret.fromSecretsManager(databaseAdminSecret, 'username'),
        DB_PASSWORD: ecs.Secret.fromSecretsManager(databaseAdminSecret, 'password'),
        DB_RUNTIME_USERNAME: ecs.Secret.fromSecretsManager(databaseRuntimeSecret, 'username'),
        DB_RUNTIME_PASSWORD: ecs.Secret.fromSecretsManager(databaseRuntimeSecret, 'password'),
      },
      logging: ecs.LogDrivers.awsLogs({
        logGroup: logGroups.migration,
        streamPrefix: 'migration',
        mode: ecs.AwsLogDriverMode.NON_BLOCKING,
        maxBufferSize: cdk.Size.mebibytes(4),
      }),
    });

    const frontendService = this.service(
      'FrontendService',
      cluster,
      frontendTask,
      privateSubnets,
      frontendSecurityGroup,
      desiredCount.valueAsNumber,
      cloudMapNamespace.valueAsString,
      [],
    );
    const coreService = this.service(
      'CoreService',
      cluster,
      coreTask,
      privateSubnets,
      coreSecurityGroup,
      desiredCount.valueAsNumber,
      cloudMapNamespace.valueAsString,
      [{ portMappingName: 'core-api', dnsName: 'core-api', port: 8000 }],
    );
    const agentService = this.service(
      'AgentService',
      cluster,
      agentTask,
      privateSubnets,
      agentSecurityGroup,
      desiredCount.valueAsNumber,
      cloudMapNamespace.valueAsString,
      [{ portMappingName: 'agent-runtime', dnsName: 'agent-runtime', port: 8001 }],
    );

    const loadBalancer = new elbv2.ApplicationLoadBalancer(this, 'FrontendLoadBalancer', {
      vpc,
      internetFacing: false,
      securityGroup: apiVpcLinkSecurityGroup,
      vpcSubnets: privateSubnets,
      deletionProtection: false,
      loadBalancerName: `kinsun-${environmentName}-frontend`,
    });
    new ec2.CfnSecurityGroupIngress(this, 'VpcLinkToAlbIngress', {
      groupId: apiVpcLinkSecurityGroupId.valueAsString,
      ipProtocol: 'tcp',
      fromPort: 80,
      toPort: 80,
      sourceSecurityGroupId: apiVpcLinkSecurityGroupId.valueAsString,
      description: 'API Gateway VPC Link ENIs to the internal frontend ALB.',
    });
    const frontendTargetGroup = new elbv2.ApplicationTargetGroup(this, 'FrontendTargetGroup', {
      vpc,
      port: 3000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        path: '/health',
        healthyHttpCodes: '200',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
      },
      deregistrationDelay: cdk.Duration.seconds(15),
    });
    frontendService.attachToApplicationTargetGroup(frontendTargetGroup);
    const listener = loadBalancer.addListener('HttpListener', {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
      open: false,
      defaultTargetGroups: [frontendTargetGroup],
    });
    const vpcLink = new apigwv2.VpcLink(this, 'FrontendVpcLink', {
      vpc,
      vpcLinkName: `kinsun-${environmentName}-frontend`,
      subnets: privateSubnets,
      securityGroups: [apiVpcLinkSecurityGroup],
    });
    const frontendIntegration = new apigwv2Integrations.HttpAlbIntegration('FrontendIntegration', listener, {
      vpcLink,
      method: apigwv2.HttpMethod.ANY,
      timeout: cdk.Duration.seconds(29),
    });
    httpApi.addRoutes({ path: '/', methods: [apigwv2.HttpMethod.ANY], integration: frontendIntegration });
    httpApi.addRoutes({ path: '/{proxy+}', methods: [apigwv2.HttpMethod.ANY], integration: frontendIntegration });
    new apigwv2.HttpStage(this, 'DefaultStage', {
      httpApi,
      stageName: '$default',
      autoDeploy: true,
      detailedMetricsEnabled: true,
      throttle: { burstLimit: 50, rateLimit: 25 },
      accessLogSettings: {
        destination: new apigwv2.LogGroupLogDestination(apiAccessLogs),
        format: apigateway.AccessLogFormat.custom(
          '{"requestId":"$context.requestId","routeKey":"$context.routeKey","status":"$context.status",' +
            '"integrationStatus":"$context.integrationStatus","responseLength":"$context.responseLength"}',
        ),
      },
    });

    coreService.node.addDependency(agentService);
    frontendService.node.addDependency(coreService);

    new cdk.CfnOutput(this, 'FrontendUrl', { value: publicOrigin });
    new cdk.CfnOutput(this, 'CognitoCallbackUrl', { value: `${publicOrigin}/backend/auth/callback` });
    new cdk.CfnOutput(this, 'CognitoLogoutUrl', { value: `${publicOrigin}/sign-in` });
    new cdk.CfnOutput(this, 'MigrationTaskDefinitionArn', { value: migrationTask.taskDefinitionArn });
    new cdk.CfnOutput(this, 'CoreTaskDefinitionArn', { value: coreTask.taskDefinitionArn });
    new cdk.CfnOutput(this, 'ConfiguredConsentPolicyVersion', {
      value: consentPolicyVersion.valueAsString,
    });
    new cdk.CfnOutput(this, 'MigrationNetworkSecurityGroupId', { value: migrationSecurityGroup.securityGroupId });
    new cdk.CfnOutput(this, 'PrivateSubnetIds', {
      value: `${privateSubnet1Id.valueAsString},${privateSubnet2Id.valueAsString}`,
    });
  }

  private requiredParameter(id: string, type: string, description: string): cdk.CfnParameter {
    return new cdk.CfnParameter(this, id, { type, description });
  }

  private stringParameter(id: string, defaultValue: string, description: string): cdk.CfnParameter {
    return new cdk.CfnParameter(this, id, {
      type: 'String',
      default: defaultValue,
      minLength: 1,
      description,
    });
  }

  private securityGroupParameter(id: string): cdk.CfnParameter {
    return this.requiredParameter(id, 'AWS::EC2::SecurityGroup::Id', `${id} output from the foundation stack.`);
  }

  private arnParameter(id: string, description: string): cdk.CfnParameter {
    return new cdk.CfnParameter(this, id, {
      type: 'String',
      allowedPattern: '^arn:[a-z0-9-]+:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:.+$',
      noEcho: true,
      description,
    });
  }

  private imageDigestParameter(id: string): cdk.CfnParameter {
    return new cdk.CfnParameter(this, id, {
      type: 'String',
      allowedPattern: '^sha256:[a-f0-9]{64}$',
      description: 'Immutable ECR sha256 digest. The image must already exist in the matching foundation repository.',
    });
  }

  private importSecurityGroup(id: string, parameter: cdk.CfnParameter): ec2.ISecurityGroup {
    return ec2.SecurityGroup.fromSecurityGroupId(this, id, parameter.valueAsString, { mutable: false });
  }

  private importRole(id: string, roleName: string): iam.IRole {
    return iam.Role.fromRoleName(this, id, roleName, { mutable: false });
  }

  private taskDefinition(
    id: string,
    executionRole: iam.IRole,
    taskRole: iam.IRole,
    cpu: number,
    memoryLimitMiB: number,
  ): ecs.FargateTaskDefinition {
    return new ecs.FargateTaskDefinition(this, id, {
      family: `kinsun-staging-${id.replace(/Task$/, '').toLowerCase()}`,
      cpu,
      memoryLimitMiB,
      executionRole,
      taskRole,
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.X86_64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });
  }

  private runtimeContainer(props: RuntimeContainerProps): ecs.ContainerDefinition {
    const healthCommand =
      props.healthRuntime === 'node'
        ? `node -e "fetch('http://127.0.0.1:${props.containerPort}${props.healthPath}').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"`
        : `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${props.containerPort}${props.healthPath}', timeout=4)"`;
    const container = props.taskDefinition.addContainer(`${props.name}Container`, {
      containerName: props.name,
      image: ecs.ContainerImage.fromRegistry(`${props.repository.repositoryUri}@${props.imageDigest}`),
      essential: true,
      readonlyRootFilesystem: true,
      environment: props.environment,
      secrets: props.secrets,
      logging: ecs.LogDrivers.awsLogs({
        logGroup: props.logGroup,
        streamPrefix: props.name,
        mode: ecs.AwsLogDriverMode.NON_BLOCKING,
        maxBufferSize: cdk.Size.mebibytes(4),
      }),
      healthCheck: {
        command: ['CMD-SHELL', healthCommand],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(30),
      },
    });
    container.addPortMappings({
      containerPort: props.containerPort,
      name: props.portMappingName,
      appProtocol: ecs.AppProtocol.http,
      protocol: ecs.Protocol.TCP,
    });
    return container;
  }

  private service(
    id: string,
    cluster: ecs.ICluster,
    taskDefinition: ecs.FargateTaskDefinition,
    privateSubnets: ec2.SubnetSelection,
    securityGroup: ec2.ISecurityGroup,
    desiredCount: number,
    namespace: string,
    services: ecs.ServiceConnectService[],
  ): ecs.FargateService {
    return new ecs.FargateService(this, id, {
      cluster,
      serviceName: `kinsun-staging-${id.replace(/Service$/, '').toLowerCase()}`,
      taskDefinition,
      desiredCount,
      assignPublicIp: false,
      vpcSubnets: privateSubnets,
      securityGroups: [securityGroup],
      enableExecuteCommand: false,
      circuitBreaker: { rollback: true },
      deploymentController: { type: ecs.DeploymentControllerType.ECS },
      minHealthyPercent: 100,
      maxHealthyPercent: 200,
      healthCheckGracePeriod: cdk.Duration.seconds(90),
      serviceConnectConfiguration: {
        namespace,
        services: services.length > 0 ? services : undefined,
      },
    });
  }
}
