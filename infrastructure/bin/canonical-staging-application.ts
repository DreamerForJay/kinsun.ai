#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { CanonicalStagingApplicationStack } from '../lib/canonical-staging-application-stack';

const app = new cdk.App();

new CanonicalStagingApplicationStack(app, 'KinsunCanonicalStagingApplication', {
  // Keep application ownership unambiguous and prevent an accidental second
  // stack when operators use the repository's deploy command.
  stackName: 'kinsun-staging-application-v1',
  environmentName: 'staging',
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-west-2',
  },
  // Runtime stacks reference immutable images that already exist in ECR. Keep synthesis
  // asset-free so CloudFormation can review the complete change without hidden uploads.
  synthesizer: new cdk.BootstraplessSynthesizer(),
  description: 'Kinsun canonical staging application runtime (initially scaled to zero)',
});
