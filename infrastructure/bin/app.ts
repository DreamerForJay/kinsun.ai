#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { ElderlyCareStack } from '../lib/elderly-care-stack';

const app = new cdk.App();
const envName = app.node.tryGetContext('envName') ?? process.env.ENV_NAME ?? 'dev';
const agentRuntimeBaseUrl =
  app.node.tryGetContext('agentRuntimeBaseUrl') ?? process.env.AGENT_RUNTIME_BASE_URL;

// Region is pinned, not defaulted from CDK_DEFAULT_REGION — the `cdk` CLI
// itself injects that env var (falling back to us-east-1 when no AWS
// profile/credentials are configured at all), which would silently outrank
// a `??` fallback here. Every deploy of this app goes to us-west-2.
new ElderlyCareStack(app, `ElderlyCareStack-${envName}`, {
  envName,
  agentRuntimeBaseUrl,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-west-2',
  },
  tags: { project: 'elderly-care-ai-companion', env: envName },
});
