[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{12}$')]
    [string]$ExpectedAccountId,

    [Parameter(Mandatory = $true)]
    [ValidateSet('us-west-2')]
    [string]$Region,

    [string]$Profile = "",

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9._-]{0,39}$')]
    [string]$ConsentPolicyVersion,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^sha256:[a-f0-9]{64}$')]
    [string]$FrontendImageDigest,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^sha256:[a-f0-9]{64}$')]
    [string]$CoreApiImageDigest,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^sha256:[a-f0-9]{64}$')]
    [string]$MigrationImageDigest,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^sha256:[a-f0-9]{64}$')]
    [string]$AgentImageDigest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""

if ($null -eq (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI v2 was not found on PATH."
}

$globalArguments = @("--region", $Region, "--no-cli-pager")
if (-not [string]::IsNullOrWhiteSpace($Profile)) {
    $globalArguments += @("--profile", $Profile)
}

function Invoke-AwsJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = & aws @Arguments @globalArguments --output json 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI validation call failed. Refresh the approved credentials and verify ECR permissions."
    }
    try {
        return [string]::Join([Environment]::NewLine, @($output)) | ConvertFrom-Json
    }
    catch {
        throw "AWS CLI validation call returned invalid JSON."
    }
}

$identity = Invoke-AwsJson -Arguments @("sts", "get-caller-identity")
if ([string]$identity.Account -ne $ExpectedAccountId) {
    throw "AWS account mismatch. Refusing to validate release images."
}

$images = @(
    @{ Artifact = "frontend"; Repository = "kinsun/staging/frontend"; Digest = $FrontendImageDigest },
    @{ Artifact = "core-api"; Repository = "kinsun/staging/core-api"; Digest = $CoreApiImageDigest },
    @{ Artifact = "core-migration"; Repository = "kinsun/staging/core-migration"; Digest = $MigrationImageDigest },
    @{ Artifact = "agent-runtime"; Repository = "kinsun/staging/agent-runtime"; Digest = $AgentImageDigest }
)

foreach ($image in $images) {
    $imageId = "imageDigest=$($image.Digest)"
    $batch = Invoke-AwsJson -Arguments @(
        "ecr", "batch-get-image",
        "--repository-name", [string]$image.Repository,
        "--image-ids", $imageId,
        "--accepted-media-types",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json"
    )
    if (@($batch.failures).Count -ne 0 -or @($batch.images).Count -ne 1) {
        throw "The immutable digest for $($image.Artifact) does not exist in its expected repository."
    }

    $details = Invoke-AwsJson -Arguments @(
        "ecr", "describe-images",
        "--repository-name", [string]$image.Repository,
        "--image-ids", $imageId
    )
    $detail = @($details.imageDetails)[0]
    if (@($detail.imageTags).Count -eq 0) {
        throw "The $($image.Artifact) digest is untagged and is not a retained release artifact."
    }

    $scan = Invoke-AwsJson -Arguments @(
        "ecr", "describe-image-scan-findings",
        "--repository-name", [string]$image.Repository,
        "--image-id", $imageId
    )
    if ([string]$scan.imageScanStatus.status -ne "COMPLETE") {
        throw "ECR vulnerability scan is not complete for $($image.Artifact)."
    }
    $counts = $scan.imageScanFindings.findingSeverityCounts
    $critical = if ($null -ne $counts.PSObject.Properties["CRITICAL"]) { [int]$counts.CRITICAL } else { 0 }
    $high = if ($null -ne $counts.PSObject.Properties["HIGH"]) { [int]$counts.HIGH } else { 0 }
    if ($critical -ne 0 -or $high -ne 0) {
        throw "ECR scan found blocking HIGH or CRITICAL findings for $($image.Artifact)."
    }

    $manifest = ([string]@($batch.images)[0].imageManifest) | ConvertFrom-Json
    if ($null -eq $manifest.config -or [string]::IsNullOrWhiteSpace([string]$manifest.config.digest)) {
        throw "The $($image.Artifact) image must be a single linux/amd64 manifest, not an unresolved index."
    }
    $download = Invoke-AwsJson -Arguments @(
        "ecr", "get-download-url-for-layer",
        "--repository-name", [string]$image.Repository,
        "--layer-digest", [string]$manifest.config.digest
    )
    $configuration = Invoke-RestMethod -Method Get -Uri ([string]$download.downloadUrl)
    if ($configuration.os -ne "linux" -or $configuration.architecture -ne "amd64") {
        throw "Image platform mismatch for $($image.Artifact); linux/amd64 is required."
    }
    $artifactLabel = $configuration.config.Labels.PSObject.Properties["io.kinsun.artifact"]
    if ($null -eq $artifactLabel -or [string]$artifactLabel.Value -ne [string]$image.Artifact) {
        throw "Artifact label mismatch for $($image.Artifact)."
    }
    if ($image.Artifact -eq "frontend") {
        $consentLabel = $configuration.config.Labels.PSObject.Properties[
            "io.kinsun.consent-policy-version"
        ]
        if ($null -eq $consentLabel -or [string]$consentLabel.Value -ne $ConsentPolicyVersion) {
            throw "Frontend consent policy provenance label mismatch."
        }
    }

    Write-Host "ok    $($image.Artifact): digest, repository, tag, scan, platform, and label verified"
}

Write-Host ""
Write-Host "ECR release preflight passed. No ECS service was created or updated."
