import * as cdk from 'aws-cdk-lib';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdaNodejs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import * as path from 'node:path';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

export interface ApiProps {
  envName: string;
  table: dynamodb.ITable;
  /** Lambda Authorizer for REST — wired once packages/backend/src/auth/authorizer.ts exists (task 2). */
  authorizerFn?: lambda.IFunction;
  /** WebSocket $connect/$disconnect/audio/control handlers — wired in task 4 (Router Lambda). */
  wsConnectFn?: lambda.IFunction;
  wsDisconnectFn?: lambda.IFunction;
  wsAudioFn?: lambda.IFunction;
  wsControlFn?: lambda.IFunction;
  /** REST route handlers, keyed `METHOD /path` — wired progressively in task 20. */
  restHandlers?: Partial<Record<string, lambda.IFunction>>;
}

const REST_ROUTES = [
  'POST /v1/conversations/start',
  'GET /v1/elders/{elderId}/events',
  'PUT /v1/events/{eventId}',
  'GET /v1/elders/{elderId}/memories',
  'PUT /v1/memories/{memoryId}/confirm',
  'PUT /v1/memories/{memoryId}/reject',
  'DELETE /v1/memories/{memoryId}',
  'GET /v1/elders/{elderId}/summaries',
  'PUT /v1/elders/{elderId}/summaries/{date}/publish',
  'PUT /v1/elders/{elderId}/summaries/{date}/withdraw',
  'GET /v1/caregivers/{caregiverId}/dashboard',
  'POST /v1/search/health',
  'GET /v1/elders/{elderId}/reports',
  'GET /v1/elders/{elderId}/persona',
  'PUT /v1/elders/{elderId}/persona',
  'POST /v1/consent/grant',
  'POST /v1/consent/revoke',
] as const;

/**
 * API Gateway skeleton: REST for management operations, WebSocket for the
 * low-latency voice stream. Routes are declared per design.md §閘道層, but
 * each integration is optional so this construct can be stood up before its
 * backing Lambda exists — later tasks pass the real function in via props
 * and redeploy rather than rewriting this file.
 */
export class Api extends Construct {
  public readonly restApi: apigateway.RestApi;
  public readonly webSocketApi: apigwv2.WebSocketApi;
  public readonly webSocketStage: apigwv2.WebSocketStage;
  public readonly accessLogGroup: logs.LogGroup;

  constructor(scope: Construct, id: string, props: ApiProps) {
    super(scope, id);

    this.accessLogGroup = new logs.LogGroup(this, 'ApiAccessLogs', {
      logGroupName: `/elderly-care/${props.envName}/api-access`,
      retention: logs.RetentionDays.THREE_MONTHS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // --- REST API -----------------------------------------------------------
    this.restApi = new apigateway.RestApi(this, 'RestApi', {
      restApiName: `elderly-care-rest-${props.envName}`,
      deployOptions: {
        stageName: props.envName,
        accessLogDestination: new apigateway.LogGroupLogDestination(this.accessLogGroup),
        accessLogFormat: apigateway.AccessLogFormat.jsonWithStandardFields(),
        tracingEnabled: true,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
      },
    });

    const authorizer = props.authorizerFn
      ? new apigateway.RequestAuthorizer(this, 'LambdaAuthorizer', {
          handler: props.authorizerFn,
          identitySources: [apigateway.IdentitySource.header('Authorization')],
          resultsCacheTtl: cdk.Duration.minutes(5),
        })
      : undefined;

    const notImplemented = new lambdaNodejs.NodejsFunction(this, 'NotImplementedHandler', {
      runtime: lambda.Runtime.NODEJS_22_X,
      entry: path.join(__dirname, '../../lambda-stubs/not-implemented.ts'),
      handler: 'handler',
      description: 'Placeholder for REST routes not yet wired to a real handler',
    });

    for (const route of REST_ROUTES) {
      const [method, resourcePath] = route.split(' ') as [string, string];
      const resource = this.ensureResource(resourcePath);
      const fn = props.restHandlers?.[route] ?? notImplemented;
      resource.addMethod(method, new apigateway.LambdaIntegration(fn), {
        authorizer,
        authorizationType: authorizer ? apigateway.AuthorizationType.CUSTOM : apigateway.AuthorizationType.NONE,
      });
    }

    // --- WebSocket API (voice streaming) ------------------------------------
    const wsFallback = new lambdaNodejs.NodejsFunction(this, 'WsNotImplementedHandler', {
      runtime: lambda.Runtime.NODEJS_22_X,
      entry: path.join(__dirname, '../../lambda-stubs/not-implemented.ts'),
      handler: 'handler',
    });

    this.webSocketApi = new apigwv2.WebSocketApi(this, 'WebSocketApi', {
      apiName: `elderly-care-ws-${props.envName}`,
      connectRouteOptions: {
        integration: new apigwv2Integrations.WebSocketLambdaIntegration(
          'ConnectIntegration',
          props.wsConnectFn ?? wsFallback,
        ),
      },
      disconnectRouteOptions: {
        integration: new apigwv2Integrations.WebSocketLambdaIntegration(
          'DisconnectIntegration',
          props.wsDisconnectFn ?? wsFallback,
        ),
      },
    });

    this.webSocketApi.addRoute('audio', {
      integration: new apigwv2Integrations.WebSocketLambdaIntegration(
        'AudioIntegration',
        props.wsAudioFn ?? wsFallback,
      ),
    });
    this.webSocketApi.addRoute('control', {
      integration: new apigwv2Integrations.WebSocketLambdaIntegration(
        'ControlIntegration',
        props.wsControlFn ?? wsFallback,
      ),
    });

    this.webSocketStage = new apigwv2.WebSocketStage(this, 'WebSocketStage', {
      webSocketApi: this.webSocketApi,
      stageName: props.envName,
      autoDeploy: true,
    });
  }

  private resourceCache = new Map<string, apigateway.IResource>();

  private ensureResource(resourcePath: string): apigateway.IResource {
    const segments = resourcePath.split('/').filter(Boolean);
    let current: apigateway.IResource = this.restApi.root;
    let cacheKey = '';
    for (const segment of segments) {
      cacheKey += `/${segment}`;
      const cached = this.resourceCache.get(cacheKey);
      if (cached) {
        current = cached;
        continue;
      }
      const next = current.getResource(segment) ?? current.addResource(segment);
      this.resourceCache.set(cacheKey, next);
      current = next;
    }
    return current;
  }
}
