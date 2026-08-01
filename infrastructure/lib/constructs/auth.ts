import * as cdk from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import { Construct } from 'constructs';

export interface GoogleFederationProps {
  /** Google Web OAuth client ID. This value is not secret. */
  readonly clientId: string;
  /** Resolve this from Secrets Manager; never pass or output plaintext. */
  readonly clientSecret: cdk.SecretValue;
  /** Globally unique prefix for the Cognito managed-login domain. */
  readonly domainPrefix: string;
  /** Exact application callback URLs registered for this staging client. */
  readonly callbackUrls: readonly string[];
  /** Exact post-logout URLs registered for this staging client. */
  readonly logoutUrls: readonly string[];
}

export interface AuthProps {
  readonly envName: string;
  /**
   * Optional during the parent-stack migration. When supplied, creates the
   * staging Google federation resources without replacing the legacy client.
   */
  readonly googleFederation?: GoogleFederationProps;
}

/** Cognito User Pool with one group per role (H01) — Elder/Caregiver/Family/Admin. */
export class Auth extends Construct {
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;
  public readonly identityPool: cognito.CfnIdentityPool;
  public readonly googleIdentityProvider?: cognito.UserPoolIdentityProviderGoogle;
  public readonly userPoolDomain?: cognito.UserPoolDomain;
  public readonly webBffClient?: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: AuthProps) {
    super(scope, id);

    if (props.googleFederation && props.envName !== 'staging') {
      throw new Error('Google federation is enabled only for the staging environment');
    }

    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: `elderly-care-users-${props.envName}`,
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      standardAttributes: {
        email: { required: true, mutable: true },
      },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    this.userPoolClient = new cognito.UserPoolClient(this, 'UserPoolClient', {
      userPool: this.userPool,
      authFlows: { userSrp: true },
      generateSecret: false,
      accessTokenValidity: cdk.Duration.hours(1),
      idTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
    });

    if (props.googleFederation) {
      const federation = props.googleFederation;
      if (federation.callbackUrls.length === 0 || federation.logoutUrls.length === 0) {
        throw new Error('Google federation requires callback and logout URLs');
      }

      this.googleIdentityProvider = new cognito.UserPoolIdentityProviderGoogle(
        this,
        'GoogleIdentityProvider',
        {
          userPool: this.userPool,
          clientId: federation.clientId,
          clientSecretValue: federation.clientSecret,
          scopes: ['openid', 'email', 'profile'],
          attributeMapping: {
            email: cognito.ProviderAttribute.GOOGLE_EMAIL,
            emailVerified: cognito.ProviderAttribute.GOOGLE_EMAIL_VERIFIED,
            fullname: cognito.ProviderAttribute.GOOGLE_NAME,
            givenName: cognito.ProviderAttribute.GOOGLE_GIVEN_NAME,
            familyName: cognito.ProviderAttribute.GOOGLE_FAMILY_NAME,
            profilePicture: cognito.ProviderAttribute.GOOGLE_PICTURE,
          },
        },
      );

      this.userPoolDomain = this.userPool.addDomain('ManagedLoginDomain', {
        cognitoDomain: { domainPrefix: federation.domainPrefix },
      });

      this.webBffClient = new cognito.UserPoolClient(this, 'WebBffClient', {
        userPool: this.userPool,
        userPoolClientName: `elderly-care-web-bff-${props.envName}`,
        // Public authorization-code client: the caller must use PKCE S256.
        generateSecret: false,
        supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.GOOGLE],
        oAuth: {
          flows: {
            authorizationCodeGrant: true,
            implicitCodeGrant: false,
            clientCredentials: false,
          },
          scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
          callbackUrls: [...federation.callbackUrls],
          logoutUrls: [...federation.logoutUrls],
        },
        accessTokenValidity: cdk.Duration.hours(1),
        idTokenValidity: cdk.Duration.hours(1),
        refreshTokenValidity: cdk.Duration.days(30),
        enableTokenRevocation: true,
        refreshTokenRotationGracePeriod: cdk.Duration.seconds(10),
        preventUserExistenceErrors: true,
      });

      // CloudFormation otherwise has no reference from an app client's static
      // SupportedIdentityProviders value to the provider or managed-login domain.
      this.webBffClient.node.addDependency(this.googleIdentityProvider);
      this.webBffClient.node.addDependency(this.userPoolDomain);
    }

    // One group per UserRole (packages/shared/src/types/enums.ts) — the Lambda
    // Authorizer maps `cognito:groups` to AuthorizationContext.role.
    (['Elder', 'Caregiver', 'Family', 'Admin'] as const).forEach((role, index) => {
      new cognito.CfnUserPoolGroup(this, `${role}Group`, {
        userPoolId: this.userPool.userPoolId,
        groupName: role,
        precedence: index,
      });
    });

    this.identityPool = new cognito.CfnIdentityPool(this, 'IdentityPool', {
      identityPoolName: `elderly_care_identity_${props.envName}`,
      allowUnauthenticatedIdentities: false,
      cognitoIdentityProviders: [
        {
          clientId: this.userPoolClient.userPoolClientId,
          providerName: this.userPool.userPoolProviderName,
        },
      ],
    });
  }
}
