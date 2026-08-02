[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-f0-9]{7,40}$')]
    [string]$ReleaseId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9._-]{0,127}$')]
    [string]$ConsentPolicyVersion
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($null -eq $docker) {
    throw "Docker was not found on PATH."
}

$images = @(
    @{
        Artifact = "frontend"
        Dockerfile = "packages/frontend/Dockerfile"
        Context = "."
        Tag = "kinsun-staging-frontend:$ReleaseId"
        Extra = @(
            "--build-arg", "NEXT_PUBLIC_CONSENT_POLICY_VERSION=$ConsentPolicyVersion",
            "--build-arg", "NEXT_PUBLIC_WS_URL="
        )
    },
    @{
        Artifact = "core-api"
        Dockerfile = "services/core-api/Dockerfile.api"
        Context = "services/core-api"
        Tag = "kinsun-staging-core-api:$ReleaseId"
        Extra = @()
    },
    @{
        Artifact = "core-migration"
        Dockerfile = "services/core-api/Dockerfile"
        Context = "services/core-api"
        Tag = "kinsun-staging-core-migration:$ReleaseId"
        Extra = @()
    },
    @{
        Artifact = "agent-runtime"
        Dockerfile = "services/agent-runtime/Dockerfile"
        Context = "."
        Tag = "kinsun-staging-agent-runtime:$ReleaseId"
        Extra = @()
    }
)

Push-Location -LiteralPath $repositoryRoot
try {
    foreach ($image in $images) {
        $arguments = @(
            "build",
            "--platform", "linux/amd64",
            "--file", [string]$image.Dockerfile,
            "--tag", [string]$image.Tag,
            "--label", "io.kinsun.artifact=$($image.Artifact)"
        ) + $(
            if ($image.Artifact -eq "frontend") {
                @("--label", "io.kinsun.consent-policy-version=$ConsentPolicyVersion")
            }
            else {
                @()
            }
        ) + @($image.Extra) + @([string]$image.Context)

        & docker @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Docker build failed for $($image.Artifact)."
        }

        $inspectionOutput = & docker image inspect ([string]$image.Tag) 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Docker inspect failed for $($image.Artifact)."
        }
        $inspection = ([string]::Join([Environment]::NewLine, @($inspectionOutput)) | ConvertFrom-Json)[0]
        if ($inspection.Os -ne "linux" -or $inspection.Architecture -ne "amd64") {
            throw "Image platform mismatch for $($image.Artifact); linux/amd64 is required."
        }
        if ($inspection.Config.Labels.'io.kinsun.artifact' -ne $image.Artifact) {
            throw "Artifact label mismatch for $($image.Artifact)."
        }
        if ($image.Artifact -eq "frontend" -and
            $inspection.Config.Labels.'io.kinsun.consent-policy-version' -ne $ConsentPolicyVersion) {
            throw "Frontend consent policy provenance label mismatch."
        }
        if ([string]::IsNullOrWhiteSpace([string]$inspection.Config.User) -or
            [string]$inspection.Config.User -in @("0", "0:0", "root")) {
            throw "Image $($image.Artifact) does not declare a non-root runtime user."
        }
        Write-Host "ok    built $($image.Artifact) as linux/amd64, non-root"
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Local staging image build passed. No image was pushed to AWS."
Write-Host "Frontend consent policy compiled into the bundle: $ConsentPolicyVersion"
