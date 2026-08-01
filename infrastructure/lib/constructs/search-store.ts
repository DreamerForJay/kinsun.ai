import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as opensearchserverless from 'aws-cdk-lib/aws-opensearchserverless';
import { Construct } from 'constructs';

export interface SearchStoreProps {
  envName: string;
}

/**
 * OpenSearch Serverless collection backing hybrid (BM25 + kNN) retrieval.
 *
 * Holds the two indices declared in packages/backend/src/search/index-mappings.ts:
 *   - health-knowledge  (1024-dim knn_vector, matches amazon.titan-embed-text-v2:0)
 *   - memory-vectors    (1024-dim knn_vector)
 *
 * The indices themselves are NOT created here — packages/backend's IndexManager
 * creates them at runtime. This construct only provisions the collection and the
 * three policies AOSS requires before a collection can be reached:
 * encryption, network, and data access.
 *
 * Cost note: unlike the Lambda/DynamoDB resources in this stack, an AOSS
 * collection bills continuously for its minimum OCU allocation whether or not
 * any query is issued. Removing this construct is the way to stop that charge.
 */
export class SearchStore extends Construct {
  public readonly collection: opensearchserverless.CfnCollection;
  /** Collection name, needed by the data-access policy's resource patterns. */
  public readonly collectionName: string;

  private readonly accessPrincipals: string[] = [];
  private accessPolicy?: opensearchserverless.CfnAccessPolicy;

  constructor(scope: Construct, id: string, props: SearchStoreProps) {
    super(scope, id);

    // AOSS collection names: 3-32 chars, lowercase alphanumeric and hyphen.
    this.collectionName = `elderly-care-${props.envName}`.slice(0, 32);

    // AOSS refuses to create a collection that has no encryption policy, so
    // this must exist first. AWS-owned key (no CMK), matching DataStore's
    // deliberate "AWS-default encryption throughout" choice.
    const encryptionPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'EncryptionPolicy', {
      name: `${this.collectionName}-enc`.slice(0, 32),
      type: 'encryption',
      policy: JSON.stringify({
        Rules: [{ ResourceType: 'collection', Resource: [`collection/${this.collectionName}`] }],
        AWSOwnedKey: true,
      }),
    });

    // Public network access: the Lambdas in this stack are not VPC-attached,
    // so a VPC endpoint would make the collection unreachable from them.
    // Authorization is enforced by the data-access policy + SigV4, not by
    // network reachability.
    const networkPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'NetworkPolicy', {
      name: `${this.collectionName}-net`.slice(0, 32),
      type: 'network',
      policy: JSON.stringify([
        {
          Rules: [
            { ResourceType: 'collection', Resource: [`collection/${this.collectionName}`] },
            { ResourceType: 'dashboard', Resource: [`collection/${this.collectionName}`] },
          ],
          AllowFromPublic: true,
        },
      ]),
    });

    this.collection = new opensearchserverless.CfnCollection(this, 'Collection', {
      name: this.collectionName,
      // VECTORSEARCH enables the knn_vector field type the index mappings use.
      type: 'VECTORSEARCH',
      description: 'Health knowledge + memory vectors for hybrid retrieval',
    });
    this.collection.addDependency(encryptionPolicy);
    this.collection.addDependency(networkPolicy);
  }

  /** Collection endpoint, e.g. https://abc123.us-west-2.aoss.amazonaws.com */
  public get endpoint(): string {
    return this.collection.attrCollectionEndpoint;
  }

  /**
   * Grants a Lambda's execution role both halves of AOSS authorization, which
   * are independent and both required:
   *   1. IAM  — aoss:APIAccessAll on the collection
   *   2. AOSS data-access policy — index/document level permissions
   * Granting only the IAM half yields 403s that look like a missing policy.
   */
  public grantAccess(grantee: iam.IGrantable & { readonly role?: iam.IRole }): void {
    grantee.grantPrincipal.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ['aoss:APIAccessAll'],
        resources: [this.collection.attrArn],
      }),
    );

    const roleArn = grantee.role?.roleArn;
    if (roleArn) {
      this.accessPrincipals.push(roleArn);
      this.syncAccessPolicy();
    }
  }

  /**
   * AOSS allows only a limited number of access policies per collection, so all
   * grantees share a single policy that is rewritten as principals accumulate.
   */
  private syncAccessPolicy(): void {
    const policyDocument = JSON.stringify([
      {
        Rules: [
          {
            ResourceType: 'index',
            Resource: [`index/${this.collectionName}/*`],
            Permission: [
              'aoss:CreateIndex',
              'aoss:DeleteIndex',
              'aoss:UpdateIndex',
              'aoss:DescribeIndex',
              'aoss:ReadDocument',
              'aoss:WriteDocument',
            ],
          },
          {
            ResourceType: 'collection',
            Resource: [`collection/${this.collectionName}`],
            Permission: ['aoss:CreateCollectionItems', 'aoss:DescribeCollectionItems'],
          },
        ],
        Principal: this.accessPrincipals,
      },
    ]);

    if (!this.accessPolicy) {
      this.accessPolicy = new opensearchserverless.CfnAccessPolicy(this, 'AccessPolicy', {
        name: `${this.collectionName}-data`.slice(0, 32),
        type: 'data',
        policy: policyDocument,
      });
    } else {
      this.accessPolicy.policy = policyDocument;
    }
  }
}
