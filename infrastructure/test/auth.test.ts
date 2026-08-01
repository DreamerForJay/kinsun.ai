import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';

import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';

import { Auth } from '../lib/constructs/auth';
import { ElderlyCareStack } from '../lib/elderly-care-stack';

const CALLBACK_URL = 'https://staging.kinsun.example/auth/callback';
const LOGOUT_URL = 'https://staging.kinsun.example/signed-out';
const GOOGLE_CLIENT_ID = 'staging-client.apps.googleusercontent.com';
const GOOGLE_SECRET_NAME = 'kinsun/staging/google-oauth';

function createTemplate(withGoogleFederation: boolean): Template {
  const app = new cdk.App();
  const stack = new cdk.Stack(app, 'AuthTestStack', {
    env: { account: '111111111111', region: 'ap-northeast-1' },
  });

  new Auth(stack, 'Auth', {
    envName: 'staging',
    googleFederation: withGoogleFederation
      ? {
          clientId: GOOGLE_CLIENT_ID,
          clientSecret: cdk.SecretValue.secretsManager(GOOGLE_SECRET_NAME, {
            jsonField: 'clientSecret',
          }),
          domainPrefix: 'kinsun-staging-auth-test',
          callbackUrls: [CALLBACK_URL],
          logoutUrls: [LOGOUT_URL],
        }
      : undefined,
  });

  return Template.fromStack(stack);
}

describe('Auth', () => {
  it('rejects Google federation outside staging', () => {
    const app = new cdk.App();
    const stack = new cdk.Stack(app, 'ProductionAuthTestStack');

    assert.throws(
      () =>
        new Auth(stack, 'Auth', {
          envName: 'production',
          googleFederation: {
            clientId: GOOGLE_CLIENT_ID,
            clientSecret: cdk.SecretValue.secretsManager(GOOGLE_SECRET_NAME),
            domainPrefix: 'must-not-be-created',
            callbackUrls: [CALLBACK_URL],
            logoutUrls: [LOGOUT_URL],
          },
        }),
      /only for the staging environment/,
    );
  });

  it('preserves the legacy client and identity pool when Google is not configured', () => {
    const template = createTemplate(false);

    template.resourceCountIs('AWS::Cognito::UserPoolClient', 1);
    template.resourceCountIs('AWS::Cognito::IdentityPool', 1);
    template.resourceCountIs('AWS::Cognito::UserPoolIdentityProvider', 0);
    template.resourceCountIs('AWS::Cognito::UserPoolDomain', 0);
  });

  it('creates a secret-backed Google provider and code-only PKCE public client', () => {
    const template = createTemplate(true);

    template.resourceCountIs('AWS::Cognito::UserPoolClient', 2);
    template.resourceCountIs('AWS::Cognito::IdentityPool', 1);
    template.hasResourceProperties('AWS::Cognito::UserPoolIdentityProvider', {
      ProviderName: 'Google',
      ProviderType: 'Google',
      ProviderDetails: Match.objectLike({
        authorize_scopes: 'openid email profile',
        client_id: GOOGLE_CLIENT_ID,
      }),
      AttributeMapping: Match.objectLike({
        email: 'email',
        email_verified: 'email_verified',
        name: 'name',
      }),
    });
    template.hasResourceProperties('AWS::Cognito::UserPoolDomain', {
      Domain: 'kinsun-staging-auth-test',
    });
    template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
      ClientName: 'elderly-care-web-bff-staging',
      GenerateSecret: false,
      AllowedOAuthFlows: ['code'],
      AllowedOAuthFlowsUserPoolClient: true,
      AllowedOAuthScopes: ['openid', 'email', 'profile'],
      CallbackURLs: [CALLBACK_URL],
      LogoutURLs: [LOGOUT_URL],
      SupportedIdentityProviders: ['Google'],
      EnableTokenRevocation: true,
      PreventUserExistenceErrors: 'ENABLED',
      RefreshTokenRotation: {
        Feature: 'ENABLED',
        RetryGracePeriodSeconds: 10,
      },
    });

    const providers = template.findResources('AWS::Cognito::UserPoolIdentityProvider');
    const providerLogicalId = Object.keys(providers)[0];
    assert.ok(providerLogicalId);
    const provider = providers[providerLogicalId];
    assert.ok(provider);
    const providerSecret = provider.Properties.ProviderDetails.client_secret;
    assert.equal(typeof providerSecret, 'string');
    assert.match(providerSecret, /^\{\{resolve:secretsmanager:/);

    const synthesized = JSON.stringify(template.toJSON());
    assert.match(synthesized, /resolve:secretsmanager/);
    assert.equal(template.toJSON().Outputs, undefined);

    const clients = template.findResources('AWS::Cognito::UserPoolClient');
    const legacyClientLogicalId = Object.entries(clients).find(
      ([, resource]) => resource.Properties.ClientName === undefined,
    )?.[0];
    const identityPools = template.findResources('AWS::Cognito::IdentityPool');
    const identityPool = Object.values(identityPools)[0];
    assert.ok(legacyClientLogicalId);
    assert.ok(identityPool);
    assert.deepEqual(identityPool.Properties.CognitoIdentityProviders[0].ClientId, {
      Ref: legacyClientLogicalId,
    });
  });

  it('orders the web client after both the Google provider and managed-login domain', () => {
    const template = createTemplate(true);
    const providers = template.findResources('AWS::Cognito::UserPoolIdentityProvider');
    const domains = template.findResources('AWS::Cognito::UserPoolDomain');
    const clients = template.findResources('AWS::Cognito::UserPoolClient');
    const providerLogicalId = Object.keys(providers)[0];
    const domainLogicalId = Object.keys(domains)[0];
    const webClient = Object.values(clients).find(
      (resource) => resource.Properties.ClientName === 'elderly-care-web-bff-staging',
    );

    assert.ok(providerLogicalId);
    assert.ok(domainLogicalId);
    assert.ok(webClient);
    const dependencies = Array.isArray(webClient.DependsOn)
      ? webClient.DependsOn
      : [webClient.DependsOn];
    assert.ok(dependencies.includes(providerLogicalId));
    assert.ok(dependencies.includes(domainLogicalId));
  });
});
describe('ElderlyCareStack Google federation integration', () => {
  it('passes staging federation settings and outputs only public integration values', () => {
    const app = new cdk.App();
    const stack = new ElderlyCareStack(app, 'StagingIntegrationTestStack', {
      envName: 'staging',
      env: { account: '111111111111', region: 'us-west-2' },
      googleFederation: {
        clientId: GOOGLE_CLIENT_ID,
        clientSecret: cdk.SecretValue.secretsManager(GOOGLE_SECRET_NAME),
        domainPrefix: 'kinsun-staging-integration-test',
        callbackUrls: [CALLBACK_URL],
        logoutUrls: [LOGOUT_URL],
      },
    });
    const template = Template.fromStack(stack);

    template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
      ClientName: 'elderly-care-web-bff-staging',
      CallbackURLs: [CALLBACK_URL],
      LogoutURLs: [LOGOUT_URL],
    });
    template.hasOutput('WebBffClientId', {});
    template.hasOutput('CognitoOAuthDomain', {});
    template.hasOutput('GoogleOAuthRedirectUri', {});

    const serializedOutputs = JSON.stringify(template.toJSON().Outputs);
    assert.match(serializedOutputs, /oauth2\/idpresponse/);
    assert.doesNotMatch(
      serializedOutputs,
      /client_secret|secretsmanager|kinsun\/staging\/google-oauth/i,
    );
  });

  it('rejects parent-stack federation outside staging', () => {
    const app = new cdk.App();

    assert.throws(
      () =>
        new ElderlyCareStack(app, 'ProductionIntegrationTestStack', {
          envName: 'production',
          googleFederation: {
            clientId: GOOGLE_CLIENT_ID,
            clientSecret: cdk.SecretValue.secretsManager(GOOGLE_SECRET_NAME),
            domainPrefix: 'must-not-be-created',
            callbackUrls: [CALLBACK_URL],
            logoutUrls: [LOGOUT_URL],
          },
        }),
      /only for the staging stack/,
    );
  });
});
