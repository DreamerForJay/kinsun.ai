#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { CanonicalStagingFoundationStack } from '../lib/canonical-staging-foundation-stack';

const app = new cdk.App();

new CanonicalStagingFoundationStack(app, 'KinsunCanonicalStagingFoundation', {
  // Pin the physical stack identity. Omitting stackName would allow a routine
  // `cdk deploy` to create a second foundation beside the protected stack.
  stackName: 'kinsun-staging-foundation-v1',
  environmentName: 'staging',
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-west-2',
  },
  // This hard-fails synthesis if a future change adds a file or Docker asset. The resulting
  // template can be uploaded through CloudFormation Console without a CDK bootstrap stack.
  synthesizer: new cdk.BootstraplessSynthesizer(),
  description: 'Kinsun canonical staging foundation (no application services and no legacy backend)',
});
