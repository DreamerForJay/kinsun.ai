#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { ElderlyCareStack } from '../lib/elderly-care-stack';

const app = new cdk.App();
const envName = app.node.tryGetContext('envName') ?? process.env.ENV_NAME ?? 'dev';
const agentRuntimeBaseUrl =
  app.node.tryGetContext('agentRuntimeBaseUrl') ?? process.env.AGENT_RUNTIME_BASE_URL;

const contextOrEnvironment = (contextKey: string, environmentKey: string): unknown =>
  app.node.tryGetContext(contextKey) ?? process.env[environmentKey];

const requiredString = (value: unknown, settingName: string): string => {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${settingName} is required when staging Google federation is configured`);
  }
  return value.trim();
};

const configuredUrls = (value: unknown, settingName: string): string[] => {
  const values = Array.isArray(value) ? value : typeof value === 'string' ? value.split(',') : [];
  const urls = values.map((entry) => requiredString(entry, settingName));
  if (urls.length === 0) {
    throw new Error(`${settingName} must contain at least one exact URL`);
  }
  for (const value of urls) {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol)) {
      throw new Error(`${settingName} only supports HTTP(S) URLs`);
    }
    const isLoopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname.toLowerCase());
    if (url.protocol !== 'https:' && !isLoopback) {
      throw new Error(`${settingName} requires HTTPS except for loopback development URLs`);
    }
  }
  return urls;
};

const googleClientId = contextOrEnvironment('googleOAuthClientId', 'GOOGLE_OAUTH_CLIENT_ID');
const googleClientSecretId = contextOrEnvironment(
  'googleOAuthClientSecretId',
  'GOOGLE_OAUTH_CLIENT_SECRET_ID',
);
const cognitoDomainPrefix = contextOrEnvironment('cognitoDomainPrefix', 'COGNITO_DOMAIN_PREFIX');
const oauthCallbackUrls = contextOrEnvironment('oauthCallbackUrls', 'COGNITO_CALLBACK_URLS');
const oauthLogoutUrls = contextOrEnvironment('oauthLogoutUrls', 'COGNITO_LOGOUT_URLS');
const googleSettings = [
  googleClientId,
  googleClientSecretId,
  cognitoDomainPrefix,
  oauthCallbackUrls,
  oauthLogoutUrls,
];
const hasAnyGoogleSetting = googleSettings.some((value) => value !== undefined);

if (hasAnyGoogleSetting && envName !== 'staging') {
  throw new Error('Google federation is enabled only for the staging stack');
}

const googleFederation = hasAnyGoogleSetting
  ? {
      clientId: requiredString(googleClientId, 'googleOAuthClientId/GOOGLE_OAUTH_CLIENT_ID'),
      // The referenced secret must contain only the Google OAuth client secret.
      // CloudFormation resolves it at deployment; synth output never contains plaintext.
      clientSecret: cdk.SecretValue.secretsManager(
        requiredString(
          googleClientSecretId,
          'googleOAuthClientSecretId/GOOGLE_OAUTH_CLIENT_SECRET_ID',
        ),
      ),
      domainPrefix: requiredString(
        cognitoDomainPrefix,
        'cognitoDomainPrefix/COGNITO_DOMAIN_PREFIX',
      ),
      callbackUrls: configuredUrls(oauthCallbackUrls, 'oauthCallbackUrls/COGNITO_CALLBACK_URLS'),
      logoutUrls: configuredUrls(oauthLogoutUrls, 'oauthLogoutUrls/COGNITO_LOGOUT_URLS'),
    }
  : undefined;

// Region is pinned, not defaulted from CDK_DEFAULT_REGION — the `cdk` CLI
// itself injects that env var (falling back to us-east-1 when no AWS
// profile/credentials are configured at all), which would silently outrank
// a `??` fallback here. Every deploy of this app goes to us-west-2.
new ElderlyCareStack(app, `ElderlyCareStack-${envName}`, {
  envName,
  agentRuntimeBaseUrl,
  googleFederation,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-west-2',
  },
  tags: { project: 'elderly-care-ai-companion', env: envName },
});
