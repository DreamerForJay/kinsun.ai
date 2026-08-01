import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export interface DataStoreProps {
  envName: string;
}

/**
 * Core data layer: single-table DynamoDB (see backend/src/db/keys.ts for the
 * PK/SK/GSI1/GSI2 scheme this table must match) plus the audio/knowledge/exports
 * S3 buckets. Uses AWS-default (not customer-managed KMS) encryption throughout
 * by design — no CMK is provisioned anywhere in this construct.
 */
export class DataStore extends Construct {
  public readonly table: dynamodb.Table;
  public readonly audioBucket: s3.Bucket;
  public readonly knowledgeBucket: s3.Bucket;
  public readonly exportsBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: DataStoreProps) {
    super(scope, id);

    // Single-table design — see design.md §DynamoDB Single-Table Design for the
    // full PK/SK/GSI key scheme (ELDER#, CG#, FM#, AUDIT# partitions).
    this.table = new dynamodb.Table(this, 'MainTable', {
      tableName: `elderly-care-main-${props.envName}`,
      partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'SK', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      // OLD_IMAGE so the TTL-cleanup stream Lambda (H03.3) can see what a
      // just-expired item contained (audioS3Key, memoryId, ...) to fan the
      // deletion out to S3/OpenSearch.
      stream: dynamodb.StreamViewType.OLD_IMAGE,
    });

    // GSI1: elderId + eventType -> date (event-type timelines)
    this.table.addGlobalSecondaryIndex({
      indexName: 'GSI1',
      partitionKey: { name: 'GSI1PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'GSI1SK', type: dynamodb.AttributeType.STRING },
    });

    // GSI2: elderId + reviewStatus -> date#eventId (review queues)
    this.table.addGlobalSecondaryIndex({
      indexName: 'GSI2',
      partitionKey: { name: 'GSI2PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'GSI2SK', type: dynamodb.AttributeType.STRING },
    });

    const commonBucketProps: Partial<s3.BucketProps> = {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    };

    // 90-day retention for raw audio, per design.md §資料保留政策.
    this.audioBucket = new s3.Bucket(this, 'AudioBucket', {
      bucketName: `elderly-care-audio-${props.envName}`,
      lifecycleRules: [{ id: 'expire-audio-90d', expiration: cdk.Duration.days(90) }],
      ...commonBucketProps,
    });

    // Knowledge-base documents are versioned/deactivated manually, not TTL'd.
    this.knowledgeBucket = new s3.Bucket(this, 'KnowledgeBucket', {
      bucketName: `elderly-care-knowledge-${props.envName}`,
      versioned: true,
      ...commonBucketProps,
    });

    this.exportsBucket = new s3.Bucket(this, 'ExportsBucket', {
      bucketName: `elderly-care-exports-${props.envName}`,
      lifecycleRules: [{ id: 'expire-exports-1y', expiration: cdk.Duration.days(365) }],
      ...commonBucketProps,
    });
  }
}
