import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';

export interface CanonicalStagingFoundationStackProps extends cdk.StackProps {
  readonly environmentName?: 'staging';
}

/**
 * Asset-free foundation for the canonical Next.js BFF -> Python Core -> Agent Runtime topology.
 *
 * It deliberately creates no ECS service or task definition until all three deployable images
 * exist. Existing Cognito and OpenSearch Serverless resources remain externally managed.
 */
export class CanonicalStagingFoundationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CanonicalStagingFoundationStackProps = {}) {
    super(scope, id, props);

    const environmentName = props.environmentName ?? 'staging';
    new cdk.CfnRule(this, 'UsWest2Only', {
      assertions: [
        {
          assert: cdk.Fn.conditionEquals(cdk.Aws.REGION, 'us-west-2'),
          assertDescription: 'The staging foundation must be deployed in us-west-2.',
        },
      ],
    });

    const owner = new cdk.CfnParameter(this, 'Owner', {
      type: 'String',
      default: 'member-c',
      minLength: 1,
      description: 'Operational owner tag for the staging foundation.',
    });
    const expiresAt = new cdk.CfnParameter(this, 'ExpiresAt', {
      type: 'String',
      default: '2026-09-01',
      allowedPattern: '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$',
      constraintDescription: 'Use an ISO calendar date such as 2026-09-01.',
      description: 'Review or teardown date; this tag does not delete resources automatically.',
    });
    const cognitoUserPoolId = new cdk.CfnParameter(this, 'CognitoUserPoolId', {
      type: 'String',
      default: 'us-west-2_wJJJXdstg',
      allowedPattern: '^us-west-2_[A-Za-z0-9]+$',
      description: 'Existing externally managed Cognito user pool. This stack does not create it.',
    });
    const cognitoWebBffClientId = new cdk.CfnParameter(this, 'CognitoWebBffClientId', {
      type: 'String',
      default: '5gqrkek6hfn8ub2ba5nsdtup81',
      allowedValues: ['5gqrkek6hfn8ub2ba5nsdtup81'],
      minLength: 1,
      description: 'Existing kinsun-web-bff-staging Cognito app client ID.',
    });
    const cognitoDomain = new cdk.CfnParameter(this, 'CognitoDomain', {
      type: 'String',
      default: 'https://kinsun-ai-staging-0919-472612.auth.us-west-2.amazoncognito.com',
      allowedPattern: '^https://[a-z0-9-]+\\.auth\\.us-west-2\\.amazoncognito\\.com$',
      description: 'Existing Cognito managed-login origin without a trailing slash.',
    });
    const openSearchCollectionId = new cdk.CfnParameter(this, 'OpenSearchCollectionId', {
      type: 'String',
      default: 'e682tp81hza27g3cp378',
      allowedPattern: '^[a-z0-9]{3,40}$',
      description: 'Existing kinsun-rag-staging OpenSearch Serverless collection ID.',
    });
    const openSearchEndpoint = new cdk.CfnParameter(this, 'OpenSearchEndpoint', {
      type: 'String',
      default: 'https://e682tp81hza27g3cp378.aoss.us-west-2.on.aws',
      allowedPattern: '^https://[a-z0-9-]+\\.aoss\\.us-west-2\\.on\\.aws$',
      description: 'Existing kinsun-rag-staging collection endpoint.',
    });
    const openSearchIndex = new cdk.CfnParameter(this, 'OpenSearchIndex', {
      type: 'String',
      default: 'ltc-public-knowledge-staging-v1',
      minLength: 1,
      description: 'Existing staging RAG index; no index is created by this stack.',
    });
    const openSearchAlias = new cdk.CfnParameter(this, 'OpenSearchAlias', {
      type: 'String',
      default: 'ltc-public-knowledge-staging',
      minLength: 1,
      description: 'Existing staging RAG alias; no alias is created by this stack.',
    });

    cdk.Tags.of(this).add('Project', 'kinsun.ai');
    cdk.Tags.of(this).add('Environment', environmentName);
    cdk.Tags.of(this).add('DataClass', 'synthetic-only');
    cdk.Tags.of(this).add('ManagedBy', 'aws-cdk');
    // Parameter tokens are valid resource tags but cannot become CloudFormation stack tags at
    // synth time, so exclude only the stack pseudo-resource while retaining resource coverage.
    cdk.Tags.of(this).add('Owner', owner.valueAsString, {
      excludeResourceTypes: ['aws:cdk:stack'],
    });
    cdk.Tags.of(this).add('ExpiresAt', expiresAt.valueAsString, {
      excludeResourceTypes: ['aws:cdk:stack'],
    });

    const vpc = new ec2.Vpc(this, 'Vpc', {
      vpcName: `kinsun-${environmentName}`,
      ipAddresses: ec2.IpAddresses.cidr('10.42.0.0/16'),
      maxAzs: 2,
      natGateways: 1,
      enableDnsHostnames: true,
      enableDnsSupport: true,
      subnetConfiguration: [
        { name: 'edge-public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'app-private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: 'db-isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    const apiVpcLinkSecurityGroup = this.securityGroup(
      vpc,
      'ApiVpcLinkSecurityGroup',
      'API Gateway VPC Link ENIs; the application stack will attach it.',
    );
    const frontendSecurityGroup = this.securityGroup(vpc, 'FrontendSecurityGroup', 'Next.js BFF; no Internet ingress.');
    const coreSecurityGroup = this.securityGroup(vpc, 'CoreSecurityGroup', 'Python Core API; canonical internal peers only.');
    const agentSecurityGroup = this.securityGroup(vpc, 'AgentSecurityGroup', 'Agent Runtime; reachable only from Core.');
    const migrationSecurityGroup = this.securityGroup(vpc, 'MigrationSecurityGroup', 'One-off Alembic tasks; no ingress.');
    const databaseSecurityGroup = this.securityGroup(vpc, 'DatabaseSecurityGroup', 'Aurora PostgreSQL; Core and migration tasks only.');

    frontendSecurityGroup.addIngressRule(apiVpcLinkSecurityGroup, ec2.Port.tcp(3000), 'HTTP from API Gateway VPC Link');
    coreSecurityGroup.addIngressRule(frontendSecurityGroup, ec2.Port.tcp(8000), 'Core API from BFF');
    coreSecurityGroup.addIngressRule(agentSecurityGroup, ec2.Port.tcp(8000), 'Core callbacks from Agent Runtime');
    agentSecurityGroup.addIngressRule(coreSecurityGroup, ec2.Port.tcp(8001), 'Agent Runtime from Core');
    databaseSecurityGroup.addIngressRule(coreSecurityGroup, ec2.Port.tcp(5432), 'PostgreSQL from Core');
    databaseSecurityGroup.addIngressRule(migrationSecurityGroup, ec2.Port.tcp(5432), 'PostgreSQL from Alembic migration task');

    const cluster = new ecs.Cluster(this, 'Cluster', {
      vpc,
      clusterName: `kinsun-${environmentName}`,
      containerInsightsV2: ecs.ContainerInsights.ENABLED,
      enableFargateCapacityProviders: true,
      defaultCloudMapNamespace: {
        name: `${environmentName}.kinsun.internal`,
        useForServiceConnect: true,
      },
    });

    const repositories = {
      frontend: this.repository('FrontendRepository', `kinsun/${environmentName}/frontend`),
      core: this.repository('CoreRepository', `kinsun/${environmentName}/core-api`),
      migration: this.repository('MigrationRepository', `kinsun/${environmentName}/core-migration`),
      agent: this.repository('AgentRepository', `kinsun/${environmentName}/agent-runtime`),
    };

    const logGroups = ['frontend', 'core-api', 'agent-runtime', 'migration'].map(
      (serviceName) =>
        new logs.LogGroup(this, `${this.pascalCase(serviceName)}LogGroup`, {
          logGroupName: `/kinsun/${environmentName}/${serviceName}`,
          retention: logs.RetentionDays.ONE_WEEK,
          removalPolicy: cdk.RemovalPolicy.DESTROY,
        }),
    );
    const databaseLogGroup = new logs.LogGroup(this, 'AuroraPostgresqlLogGroup', {
      logGroupName: `/aws/rds/cluster/kinsun-${environmentName}-aurora-pg/postgresql`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const databaseEngine = rds.DatabaseClusterEngine.auroraPostgres({
      version: rds.AuroraPostgresEngineVersion.VER_16_8,
    });
    const databaseParameterGroup = new rds.ParameterGroup(this, 'AuroraParameterGroup', {
      engine: databaseEngine,
      description: 'Kinsun staging Aurora PostgreSQL 16 parameters',
      parameters: { 'rds.force_ssl': '1' },
    });
    const database = new rds.DatabaseCluster(this, 'Database', {
      clusterIdentifier: `kinsun-${environmentName}-aurora-pg`,
      engine: databaseEngine,
      writer: rds.ClusterInstance.serverlessV2('writer', {
        publiclyAccessible: false,
        enablePerformanceInsights: false,
      }),
      readers: [],
      credentials: rds.Credentials.fromGeneratedSecret('kinsun_admin', {
        secretName: `kinsun/${environmentName}/aurora/admin`,
      }),
      defaultDatabaseName: 'kinsun',
      parameterGroup: databaseParameterGroup,
      serverlessV2MinCapacity: 0,
      serverlessV2MaxCapacity: 1,
      serverlessV2AutoPauseDuration: cdk.Duration.minutes(15),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [databaseSecurityGroup],
      storageEncrypted: true,
      iamAuthentication: false,
      cloudwatchLogsExports: ['postgresql'],
      backup: { retention: cdk.Duration.days(1), preferredWindow: '19:00-19:30' },
      preferredMaintenanceWindow: 'sun:19:30-sun:20:00',
      copyTagsToSnapshot: true,
      deletionProtection: true,
      // This is the protected steady-state template. The initial staging bootstrap used a
      // reviewed create-only template with Delete/false, then switched to this policy only after
      // CloudFormation reached CREATE_COMPLETE so an incomplete empty cluster could roll back.
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT,
    });
    database.node.addDependency(databaseLogGroup);
    // A retained snapshot is not operationally recoverable without its generated credentials.
    // DatabaseCluster owns the generated Secret as its `Secret` child; `database.secret` is the
    // target attachment, so applying the policy there would leave the credential resource at
    // Delete. Keep this lookup fail-fast so a future CDK construct-tree change cannot silently
    // weaken the recovery policy.
    const generatedDatabaseSecret = database.node.tryFindChild('Secret');
    if (!(generatedDatabaseSecret instanceof secretsmanager.Secret)) {
      throw new Error('Aurora generated credential Secret was not found at Database/Secret.');
    }
    generatedDatabaseSecret.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);

    const oauthTransactionSecret = this.generatedSecret(
      'OauthTransactionSecret',
      `kinsun/${environmentName}/frontend/oauth-transaction`,
      'Next.js BFF OAuth transaction signing secret',
    );
    const familyInviteSecret = this.generatedSecret(
      'FamilyInviteSecret',
      `kinsun/${environmentName}/core/family-invite-hmac`,
      'Core family invitation-code HMAC secret',
    );
    const databaseRuntimeSecret = new secretsmanager.Secret(this, 'DatabaseRuntimeSecret', {
      secretName: `kinsun/${environmentName}/aurora/runtime`,
      description: 'Least-privilege Core API Aurora runtime credential',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: 'kinsun_app' }),
        generateStringKey: 'password',
        passwordLength: 64,
        excludePunctuation: true,
      },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    const executionRoles = {
      frontend: this.executionRole('FrontendExecutionRole', `kinsun-frontend-execution-${environmentName}`),
      core: this.executionRole('CoreExecutionRole', `kinsun-core-execution-${environmentName}`),
      agent: this.executionRole('AgentExecutionRole', `kinsun-agent-execution-${environmentName}`),
      migration: this.executionRole('MigrationExecutionRole', `kinsun-migration-execution-${environmentName}`),
    };
    oauthTransactionSecret.grantRead(executionRoles.frontend);
    familyInviteSecret.grantRead(executionRoles.core);
    // The long-lived Core task must never receive the Aurora administrator credential.
    databaseRuntimeSecret.grantRead(executionRoles.core);
    // The one-shot migration task applies Alembic as admin, then reconciles the runtime
    // LOGIN role to the separately generated credential before any Core service is enabled.
    database.secret?.grantRead(executionRoles.migration);
    databaseRuntimeSecret.grantRead(executionRoles.migration);

    const taskRoles = {
      frontend: this.taskRole('FrontendTaskRole', `kinsun-frontend-ecs-${environmentName}`),
      core: this.taskRole('CoreTaskRole', `kinsun-core-ecs-${environmentName}`),
      agent: this.taskRole('AgentTaskRole', `kinsun-agent-runtime-ecs-${environmentName}`),
      migration: this.taskRole('MigrationTaskRole', `kinsun-migration-ecs-${environmentName}`),
    };
    taskRoles.agent.addToPolicy(
      new iam.PolicyStatement({
        sid: 'InvokeConfiguredEmbeddingModel',
        actions: ['bedrock:InvokeModel'],
        resources: [
          `arn:${cdk.Aws.PARTITION}:bedrock:*::foundation-model/cohere.embed-v4:0`,
          `arn:${cdk.Aws.PARTITION}:bedrock:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:inference-profile/us.cohere.embed-v4:0`,
        ],
      }),
    );
    taskRoles.agent.addToPolicy(
      new iam.PolicyStatement({
        sid: 'OpenSearchServerlessDataPlane',
        actions: ['aoss:APIAccessAll'],
        resources: [
          cdk.Stack.of(this).formatArn({
            service: 'aoss',
            resource: 'collection',
            resourceName: openSearchCollectionId.valueAsString,
          }),
        ],
      }),
    );

    const externalConfiguration: Record<string, string> = {
      'cognito-user-pool-id': cognitoUserPoolId.valueAsString,
      'cognito-web-bff-client-id': cognitoWebBffClientId.valueAsString,
      'cognito-domain': cognitoDomain.valueAsString,
      'opensearch-collection-id': openSearchCollectionId.valueAsString,
      'opensearch-endpoint': openSearchEndpoint.valueAsString,
      'opensearch-index': openSearchIndex.valueAsString,
      'opensearch-alias': openSearchAlias.valueAsString,
    };
    for (const [key, value] of Object.entries(externalConfiguration)) {
      new ssm.StringParameter(this, `${this.pascalCase(key)}Parameter`, {
        parameterName: `/kinsun/${environmentName}/external/${key}`,
        stringValue: value,
        description: `Externally managed staging reference: ${key}`,
        tier: ssm.ParameterTier.STANDARD,
      });
    }

    this.output('VpcId', vpc.vpcId);
    this.output('PublicEdgeSubnetIds', cdk.Fn.join(',', vpc.publicSubnets.map((subnet) => subnet.subnetId)));
    this.output('PrivateAppSubnetIds', cdk.Fn.join(',', vpc.privateSubnets.map((subnet) => subnet.subnetId)));
    this.output('IsolatedDatabaseSubnetIds', cdk.Fn.join(',', vpc.isolatedSubnets.map((subnet) => subnet.subnetId)));
    this.output('EcsClusterName', cluster.clusterName);
    this.output('CloudMapNamespace', cluster.defaultCloudMapNamespace?.namespaceName ?? 'not-created');
    this.output('FrontendRepositoryUri', repositories.frontend.repositoryUri);
    this.output('CoreRepositoryUri', repositories.core.repositoryUri);
    this.output('MigrationRepositoryUri', repositories.migration.repositoryUri);
    this.output('AgentRepositoryUri', repositories.agent.repositoryUri);
    this.output('DatabaseEndpoint', database.clusterEndpoint.hostname);
    this.output('DatabasePort', database.clusterEndpoint.port.toString());
    // Keep DatabaseSecretArn as a compatibility alias for the already-deployed foundation.
    this.output('DatabaseSecretArn', database.secret?.secretArn ?? 'not-created');
    this.output('DatabaseAdminSecretArn', database.secret?.secretArn ?? 'not-created');
    this.output('DatabaseRuntimeSecretArn', databaseRuntimeSecret.secretArn);
    this.output('OauthTransactionSecretArn', oauthTransactionSecret.secretArn);
    this.output('FamilyInviteSecretArn', familyInviteSecret.secretArn);
    this.output('ApiVpcLinkSecurityGroupId', apiVpcLinkSecurityGroup.securityGroupId);
    this.output('FrontendSecurityGroupId', frontendSecurityGroup.securityGroupId);
    this.output('CoreSecurityGroupId', coreSecurityGroup.securityGroupId);
    this.output('AgentSecurityGroupId', agentSecurityGroup.securityGroupId);
    this.output('MigrationSecurityGroupId', migrationSecurityGroup.securityGroupId);
    this.output('DatabaseSecurityGroupId', databaseSecurityGroup.securityGroupId);
    this.output('FrontendTaskRoleArn', taskRoles.frontend.roleArn);
    this.output('CoreTaskRoleArn', taskRoles.core.roleArn);
    this.output('AgentTaskRoleArn', taskRoles.agent.roleArn);
    this.output('MigrationTaskRoleArn', taskRoles.migration.roleArn);
    this.output('AgentRuntimeAossDataPolicyName', 'kinsun-rag-staging-data');
    this.output('ApplicationLogGroups', cdk.Fn.join(',', logGroups.map((logGroup) => logGroup.logGroupName)));
  }

  private securityGroup(vpc: ec2.IVpc, id: string, description: string): ec2.SecurityGroup {
    return new ec2.SecurityGroup(this, id, { vpc, description, allowAllOutbound: true });
  }

  private repository(id: string, repositoryName: string): ecr.Repository {
    const repository = new ecr.Repository(this, id, {
      repositoryName,
      encryption: ecr.RepositoryEncryption.AES_256,
      imageScanOnPush: true,
      imageTagMutability: ecr.TagMutability.IMMUTABLE,
      emptyOnDelete: false,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    repository.addLifecycleRule({
      // Task definitions are pinned by digest. Expiring tagged releases by a
      // global image count would eventually break restarts and rollbacks.
      description: 'Remove only untagged build leftovers after fourteen days',
      tagStatus: ecr.TagStatus.UNTAGGED,
      maxImageAge: cdk.Duration.days(14),
      rulePriority: 1,
    });
    return repository;
  }

  private generatedSecret(id: string, secretName: string, description: string): secretsmanager.Secret {
    return new secretsmanager.Secret(this, id, {
      secretName,
      description,
      generateSecretString: { passwordLength: 64, excludePunctuation: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
  }

  private executionRole(id: string, roleName: string): iam.Role {
    return new iam.Role(this, id, {
      roleName,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
      ],
      description: 'Canonical staging ECS task execution role',
    });
  }

  private taskRole(id: string, roleName: string): iam.Role {
    return new iam.Role(this, id, {
      roleName,
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Canonical staging ECS application task role',
    });
  }

  private output(id: string, value: string): void {
    new cdk.CfnOutput(this, id, { value });
  }

  private pascalCase(value: string): string {
    return value
      .split(/[^A-Za-z0-9]+/)
      .filter(Boolean)
      .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
      .join('');
  }
}
