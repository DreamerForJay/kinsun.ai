import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdaNodejs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import { Construct } from 'constructs';
import * as fs from 'node:fs';
import * as path from 'node:path';

export interface VoiceWorkflowProps {
  envName: string;
  table: dynamodb.ITable;
  audioBucket: s3.IBucket;
  exportsBucket: s3.IBucket;
  commonEnv: Record<string, string>;
}

const backendSrc = (file: string) => path.join(__dirname, `../../../packages/backend/src/${file}`);
const aslPath = backendSrc('workflow/asl/voice-interaction.asl.json');

/**
 * Voice-interaction Step Functions Express workflow (design.md §協調層).
 * Builds the 5 AI-processing stage Lambdas, then loads the ASL template
 * from packages/backend/src/workflow/asl/voice-interaction.asl.json and
 * substitutes its ${XxxFunctionArn} placeholders with the real function
 * ARNs via Fn::Sub — the ASL file is the single source of truth for the
 * state machine's control flow (see that file's own comment for the
 * ResultPath convention it relies on).
 */
export class VoiceWorkflow extends Construct {
  public readonly stateMachine: sfn.CfnStateMachine;

  constructor(scope: Construct, id: string, props: VoiceWorkflowProps) {
    super(scope, id);

    const makeStageFn = (fnId: string, exportName: string, extraEnv: Record<string, string> = {}): lambdaNodejs.NodejsFunction => {
      const fn = new lambdaNodejs.NodejsFunction(this, fnId, {
        projectRoot: path.join(__dirname, '../../..'),
        runtime: lambda.Runtime.NODEJS_22_X,
        entry: backendSrc('workflow/stage-handlers/index.ts'),
        handler: exportName,
        environment: { ...props.commonEnv, ...extraEnv },
        timeout: cdk.Duration.seconds(20),
        memorySize: 512,
      });
      props.table.grantReadWriteData(fn);
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel', 'bedrock:Converse', 'bedrock:ApplyGuardrail'],
          resources: ['*'],
        }),
      );
      return fn;
    };

    const asrFn = makeStageFn('AsrStageFn', 'asrStageHandler');
    asrFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['transcribe:StartStreamTranscription', 'sagemaker:InvokeEndpoint'],
        resources: ['*'],
      }),
    );

    const contextFn = makeStageFn('ContextStageFn', 'contextStageHandler');
    const llmFn = makeStageFn('LlmStageFn', 'llmStageHandler');
    const guardrailFn = makeStageFn('GuardrailStageFn', 'guardrailStageHandler');

    const ttsFn = makeStageFn('TtsStageFn', 'ttsStageHandler', { EXPORTS_BUCKET_NAME: props.exportsBucket.bucketName });
    ttsFn.addToRolePolicy(new iam.PolicyStatement({ actions: ['polly:SynthesizeSpeech', 'sagemaker:InvokeEndpoint'], resources: ['*'] }));
    props.exportsBucket.grantReadWrite(ttsFn);

    const aslTemplate = fs.readFileSync(aslPath, 'utf-8');
    const definitionString = cdk.Fn.sub(aslTemplate, {
      AsrFunctionArn: asrFn.functionArn,
      ContextFunctionArn: contextFn.functionArn,
      LlmFunctionArn: llmFn.functionArn,
      GuardrailFunctionArn: guardrailFn.functionArn,
      TtsFunctionArn: ttsFn.functionArn,
    });

    const logGroup = new logs.LogGroup(this, 'StateMachineLogs', {
      logGroupName: `/elderly-care/${props.envName}/voice-workflow`,
      retention: logs.RetentionDays.THREE_MONTHS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const executionRole = new iam.Role(this, 'StateMachineRole', {
      assumedBy: new iam.ServicePrincipal('states.amazonaws.com'),
    });
    for (const fn of [asrFn, contextFn, llmFn, guardrailFn, ttsFn]) {
      fn.grantInvoke(executionRole);
    }
    executionRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          'logs:CreateLogDelivery',
          'logs:GetLogDelivery',
          'logs:UpdateLogDelivery',
          'logs:DeleteLogDelivery',
          'logs:ListLogDeliveries',
          'logs:PutResourcePolicy',
          'logs:DescribeResourcePolicies',
          'logs:DescribeLogGroups',
        ],
        resources: ['*'],
      }),
    );

    this.stateMachine = new sfn.CfnStateMachine(this, 'StateMachine', {
      stateMachineName: `elderly-care-voice-interaction-${props.envName}`,
      stateMachineType: 'EXPRESS',
      definitionString,
      roleArn: executionRole.roleArn,
      loggingConfiguration: {
        level: 'ALL',
        includeExecutionData: true,
        destinations: [{ cloudWatchLogsLogGroup: { logGroupArn: logGroup.logGroupArn } }],
      },
    });
  }
}
