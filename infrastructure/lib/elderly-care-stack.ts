import * as cdk from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as eventTargets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdaEventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as lambdaNodejs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import * as path from 'node:path';
import { Api } from './constructs/api';
import { Auth } from './constructs/auth';
import { DataStore } from './constructs/data-store';
import { VoiceWorkflow } from './constructs/voice-workflow';

export interface ElderlyCareStackProps extends cdk.StackProps {
  envName: string;
}

export class ElderlyCareStack extends cdk.Stack {
  public readonly dataStore: DataStore;
  public readonly auth: Auth;
  public readonly api: Api;

  constructor(scope: Construct, id: string, props: ElderlyCareStackProps) {
    super(scope, id, props);

    this.dataStore = new DataStore(this, 'DataStore', { envName: props.envName });
    this.auth = new Auth(this, 'Auth', { envName: props.envName });

    // Workflow/component Lambda logs (ASR, Context Composer, Event Extractor,
    // Memory Manager, ...) all log here so CloudWatch Insights queries can
    // filter by traceId across every stage of a single interaction (J04).
    new logs.LogGroup(this, 'ApplicationLogs', {
      logGroupName: `/elderly-care/${props.envName}/application`,
      retention: logs.RetentionDays.THREE_MONTHS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const commonEnv = {
      DYNAMODB_TABLE_NAME: this.dataStore.table.tableName,
      DYNAMODB_GSI1_NAME: 'GSI1',
      DYNAMODB_GSI2_NAME: 'GSI2',
      COGNITO_USER_POOL_ID: this.auth.userPool.userPoolId,
      COGNITO_CLIENT_ID: this.auth.userPoolClient.userPoolClientId,
    };

    // REQUEST authorizer (H01) — verifies the Cognito ID token, resolves the
    // caller's authorized elder_ids from CG#/FM# mappings, and hands the
    // result to downstream handlers via the API Gateway authorizer context.
    const authorizerFn = new lambdaNodejs.NodejsFunction(this, 'AuthorizerFn', {
      runtime: lambda.Runtime.NODEJS_22_X,
      entry: path.join(__dirname, '../../packages/backend/src/auth/authorizer.ts'),
      handler: 'handler',
      environment: commonEnv,
      timeout: cdk.Duration.seconds(5),
      description: 'Lambda Authorizer: verifies Cognito JWT + resolves elder-scoped authorization context',
    });
    this.dataStore.table.grantReadData(authorizerFn);

    // --- REST API business-logic handlers (task 20) -------------------------
    // Multiple routes share one entry file (e.g. events.ts exports both
    // listEventsHandler and updateEventHandler) — `handler` picks the named
    // export, so no per-route file split is needed.
    const apiSrc = (file: string) => path.join(__dirname, `../../packages/backend/src/api/${file}`);

    const makeApiFn = (id: string, entry: string, exportName: string): lambdaNodejs.NodejsFunction => {
      const fn = new lambdaNodejs.NodejsFunction(this, id, {
        runtime: lambda.Runtime.NODEJS_22_X,
        entry,
        handler: exportName,
        environment: commonEnv,
        timeout: cdk.Duration.seconds(10),
      });
      this.dataStore.table.grantReadWriteData(fn);
      return fn;
    };

    const startConversationFn = makeApiFn('StartConversationFn', apiSrc('conversations.ts'), 'handler');
    const listEventsFn = makeApiFn('ListEventsFn', apiSrc('events.ts'), 'listEventsHandler');
    const updateEventFn = makeApiFn('UpdateEventFn', apiSrc('events.ts'), 'updateEventHandler');
    const listMemoriesFn = makeApiFn('ListMemoriesFn', apiSrc('memories.ts'), 'listMemoriesHandler');
    const confirmMemoryFn = makeApiFn('ConfirmMemoryFn', apiSrc('memories.ts'), 'confirmMemoryHandler');
    const rejectMemoryFn = makeApiFn('RejectMemoryFn', apiSrc('memories.ts'), 'rejectMemoryHandler');
    const deleteMemoryFn = makeApiFn('DeleteMemoryFn', apiSrc('memories.ts'), 'deleteMemoryHandler');
    const listSummariesFn = makeApiFn('ListSummariesFn', apiSrc('summaries.ts'), 'listSummariesHandler');
    const publishSummaryFn = makeApiFn('PublishSummaryFn', apiSrc('summary-publish.ts'), 'handler');
    const withdrawSummaryFn = makeApiFn('WithdrawSummaryFn', apiSrc('summary-withdraw.ts'), 'handler');
    const searchHealthFn = makeApiFn('SearchHealthFn', apiSrc('search.ts'), 'handler');
    const dashboardFn = makeApiFn('CaregiverDashboardFn', apiSrc('dashboard.ts'), 'handler');
    const getPersonaFn = makeApiFn('GetPersonaFn', apiSrc('persona.ts'), 'getPersonaHandler');
    const updatePersonaFn = makeApiFn('UpdatePersonaFn', apiSrc('persona.ts'), 'handler');
    const grantConsentFn = makeApiFn('GrantConsentFn', apiSrc('consent.ts'), 'grantHandler');
    const revokeConsentFn = makeApiFn('RevokeConsentFn', apiSrc('consent.ts'), 'revokeHandler');
    const reportsFn = makeApiFn('ReportsFn', apiSrc('reports.ts'), 'handler');

    // Bedrock (LLM + embeddings + guardrails) is only invoked from the
    // search path today; grant broadly since model/guardrail ARNs vary by
    // account and aren't known at synth time for a demo deployment.
    searchHealthFn.addToRolePolicy(
      new iam.PolicyStatement({ actions: ['bedrock:InvokeModel', 'bedrock:Converse'], resources: ['*'] }),
    );

    // --- Voice-interaction Step Functions workflow (task 25) ----------------
    const voiceWorkflow = new VoiceWorkflow(this, 'VoiceWorkflow', {
      envName: props.envName,
      table: this.dataStore.table,
      audioBucket: this.dataStore.audioBucket,
      exportsBucket: this.dataStore.exportsBucket,
      commonEnv,
    });

    // --- WebSocket handlers (connect/disconnect/control/audio) --------------
    const workflowSrc = (file: string) => path.join(__dirname, `../../packages/backend/src/workflow/handlers/${file}`);
    const wsEnv = { ...commonEnv, STATE_MACHINE_ARN: voiceWorkflow.stateMachine.attrArn };

    const makeWsFn = (id: string, file: string): lambdaNodejs.NodejsFunction => {
      const fn = new lambdaNodejs.NodejsFunction(this, id, {
        runtime: lambda.Runtime.NODEJS_22_X,
        entry: workflowSrc(file),
        handler: 'handler',
        environment: wsEnv,
        timeout: cdk.Duration.seconds(15),
      });
      this.dataStore.table.grantReadWriteData(fn);
      return fn;
    };

    // Async post-processing (event extraction + candidate memory
    // generation) — invoked fire-and-forget by the Router Lambda after
    // each turn, per design.md's "par 非同步處理" sequence-diagram branch.
    const postProcessingFn = new lambdaNodejs.NodejsFunction(this, 'PostProcessingFn', {
      runtime: lambda.Runtime.NODEJS_22_X,
      entry: path.join(__dirname, '../../packages/backend/src/workflow/stage-handlers/index.ts'),
      handler: 'postProcessingHandler',
      environment: commonEnv,
      timeout: cdk.Duration.seconds(30),
    });
    this.dataStore.table.grantReadWriteData(postProcessingFn);
    postProcessingFn.addToRolePolicy(new iam.PolicyStatement({ actions: ['bedrock:Converse'], resources: ['*'] }));

    const wsConnectFn = makeWsFn('WsConnectFn', 'connect.ts');
    const wsDisconnectFn = makeWsFn('WsDisconnectFn', 'disconnect.ts');
    const wsControlFn = makeWsFn('WsControlFn', 'control.ts');
    const wsAudioFn = makeWsFn('WsAudioFn', 'router.ts');
    wsAudioFn.addEnvironment('POST_PROCESSING_FUNCTION_NAME', postProcessingFn.functionName);
    postProcessingFn.grantInvoke(wsAudioFn);
    // CfnStateMachine (L1) has no grant* helpers, so the StartSyncExecution permission is explicit.
    wsAudioFn.addToRolePolicy(
      new iam.PolicyStatement({ actions: ['states:StartSyncExecution'], resources: [voiceWorkflow.stateMachine.attrArn] }),
    );
    for (const fn of [wsConnectFn, wsDisconnectFn, wsControlFn, wsAudioFn]) {
      fn.addToRolePolicy(
        new iam.PolicyStatement({ actions: ['execute-api:ManageConnections'], resources: [`arn:aws:execute-api:${this.region}:${this.account}:*/*/POST/@connections/*`] }),
      );
    }

    this.api = new Api(this, 'Api', {
      envName: props.envName,
      table: this.dataStore.table,
      authorizerFn,
      wsConnectFn,
      wsDisconnectFn,
      wsControlFn,
      wsAudioFn,
      restHandlers: {
        'POST /v1/conversations/start': startConversationFn,
        'GET /v1/elders/{elderId}/events': listEventsFn,
        'PUT /v1/events/{eventId}': updateEventFn,
        'GET /v1/elders/{elderId}/memories': listMemoriesFn,
        'PUT /v1/memories/{memoryId}/confirm': confirmMemoryFn,
        'PUT /v1/memories/{memoryId}/reject': rejectMemoryFn,
        'DELETE /v1/memories/{memoryId}': deleteMemoryFn,
        'GET /v1/elders/{elderId}/summaries': listSummariesFn,
        'PUT /v1/elders/{elderId}/summaries/{date}/publish': publishSummaryFn,
        'PUT /v1/elders/{elderId}/summaries/{date}/withdraw': withdrawSummaryFn,
        'POST /v1/search/health': searchHealthFn,
        'GET /v1/caregivers/{caregiverId}/dashboard': dashboardFn,
        'GET /v1/elders/{elderId}/reports': reportsFn,
        'GET /v1/elders/{elderId}/persona': getPersonaFn,
        'PUT /v1/elders/{elderId}/persona': updatePersonaFn,
        'POST /v1/consent/grant': grantConsentFn,
        'POST /v1/consent/revoke': revokeConsentFn,
      },
      // wsConnectFn etc. are wired in once the E2E integration task (25)
      // deploys the voice-interaction state machine — see Api's props.
    });

    // --- TTL cross-store cleanup (H03.3) -------------------------------------
    // Fires on every DynamoDB Streams record; the handler itself filters to
    // TTL-driven REMOVE events and fans the deletion out to S3/OpenSearch.
    const ttlCleanupFn = new lambdaNodejs.NodejsFunction(this, 'TtlCleanupFn', {
      runtime: lambda.Runtime.NODEJS_22_X,
      entry: path.join(__dirname, '../../packages/backend/src/retention/ttl-stream-handler.ts'),
      handler: 'handler',
      environment: { ...commonEnv, AUDIO_BUCKET_NAME: this.dataStore.audioBucket.bucketName },
      timeout: cdk.Duration.seconds(30),
    });
    this.dataStore.audioBucket.grantDelete(ttlCleanupFn);
    if (this.dataStore.table.tableStreamArn) {
      ttlCleanupFn.addEventSource(
        new lambdaEventSources.DynamoEventSource(this.dataStore.table, {
          startingPosition: lambda.StartingPosition.TRIM_HORIZON,
          batchSize: 25,
          retryAttempts: 3,
        }),
      );
    }

    // --- Daily summary generation (B02.1) ------------------------------------
    const summaryGeneratorFn = new lambdaNodejs.NodejsFunction(this, 'SummaryGeneratorFn', {
      runtime: lambda.Runtime.NODEJS_22_X,
      entry: path.join(__dirname, '../../packages/backend/src/summary/handler.ts'),
      handler: 'handler',
      environment: commonEnv,
      timeout: cdk.Duration.minutes(5),
    });
    this.dataStore.table.grantReadWriteData(summaryGeneratorFn);
    summaryGeneratorFn.addToRolePolicy(
      new iam.PolicyStatement({ actions: ['bedrock:Converse'], resources: ['*'] }),
    );
    new events.Rule(this, 'DailySummaryRule', {
      schedule: events.Schedule.cron({ hour: '20', minute: '0' }), // 20:00 UTC = 04:00 next day Taipei
      targets: [new eventTargets.LambdaFunction(summaryGeneratorFn)],
      description: 'Triggers SummaryGenerator once daily for every elder profile',
    });

    new cdk.CfnOutput(this, 'RestApiUrl', { value: this.api.restApi.url });
    new cdk.CfnOutput(this, 'WebSocketUrl', { value: this.api.webSocketStage.url });
    new cdk.CfnOutput(this, 'UserPoolId', { value: this.auth.userPool.userPoolId });
    new cdk.CfnOutput(this, 'UserPoolClientId', { value: this.auth.userPoolClient.userPoolClientId });
    new cdk.CfnOutput(this, 'TableName', { value: this.dataStore.table.tableName });
  }
}
