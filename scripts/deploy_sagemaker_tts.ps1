[CmdletBinding()]
param(
    [string]$Region = "us-west-2",
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{12}$')]
    [string]$ExpectedAccountId,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^arn:aws:iam::\d{12}:role/.+$')]
    [string]$ExecutionRoleArn,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/.+@sha256:[a-f0-9]{64}$')]
    [string]$ImageDigestUri,
    [string]$InstanceType = "ml.g4dn.xlarge",
    [switch]$AcceptCcByNcNonCommercialDemo,
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $AcceptCcByNcNonCommercialDemo.IsPresent) {
    throw "Owner approval for CC-BY-NC-4.0 non-commercial demo use is required."
}

$identity = aws sts get-caller-identity --region $Region --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $identity.Account -ne $ExpectedAccountId) {
    throw "AWS identity failed or account ID does not match."
}

$modelName = "kinsun-speech-tts-v1"
$configName = "kinsun-speech-tts-config-v1"
$endpointName = "kinsun-speech-tts-v1"

Write-Host "Region: $Region"
Write-Host "Account: $($identity.Account)"
Write-Host "Image digest: $ImageDigestUri"
Write-Host "Instance: $InstanceType"

if (-not $Execute.IsPresent) {
    Write-Host "Dry run only. Add -Execute to create AWS resources."
    exit 0
}

# Use an immutable image digest and enable Network Isolation.
aws sagemaker create-model `
    --region $Region `
    --model-name $modelName `
    --execution-role-arn $ExecutionRoleArn `
    --enable-network-isolation `
    --primary-container "Image=$ImageDigestUri"
if ($LASTEXITCODE -ne 0) { throw "CreateModel failed." }

# Do not configure Data Capture; request payloads may contain conversation text.
aws sagemaker create-endpoint-config `
    --region $Region `
    --endpoint-config-name $configName `
    --production-variants "VariantName=AllTraffic,ModelName=$modelName,InitialInstanceCount=1,InstanceType=$InstanceType"
if ($LASTEXITCODE -ne 0) { throw "CreateEndpointConfig failed." }

aws sagemaker create-endpoint `
    --region $Region `
    --endpoint-name $endpointName `
    --endpoint-config-name $configName
if ($LASTEXITCODE -ne 0) { throw "CreateEndpoint failed." }

Write-Host "Endpoint creation started: $endpointName"
Write-Host "Wait for InService, then smoke test with Synthetic text only."
