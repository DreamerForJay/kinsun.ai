[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ServicesCsv,

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$SageMakerCsv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$services = Import-Csv -LiteralPath $ServicesCsv
$sagemaker = Import-Csv -LiteralPath $SageMakerCsv

function Test-AllowedAction {
    param(
        [Parameter(Mandatory = $true)][string]$Namespace,
        [Parameter(Mandatory = $true)][string]$Action
    )

    $row = $services | Where-Object {
        ($_.'IAM Namespace' -split ' ')[0] -eq $Namespace
    } | Select-Object -First 1

    if ($null -eq $row) {
        return $false
    }

    return ($row.'Allowed Actions' -split ', ') -contains $Action
}

$requiredActions = @(
    @('bedrock', 'InvokeModel'),
    @('ecr', 'CreateRepository'),
    @('ecr', 'PutImage'),
    @('lambda', 'CreateFunction'),
    @('polly', 'SynthesizeSpeech'),
    @('s3', 'PutBucketPublicAccessBlock'),
    @('s3', 'PutObject'),
    @('sagemaker', 'CreateEndpoint'),
    @('sagemaker', 'CreateEndpointConfig'),
    @('sagemaker', 'InvokeEndpoint'),
    @('states', 'CreateStateMachine'),
    @('states', 'StartSyncExecution'),
    @('transcribe', 'StartStreamTranscription')
)

$failures = @()
foreach ($requirement in $requiredActions) {
    $namespace = $requirement[0]
    $action = $requirement[1]
    $allowed = Test-AllowedAction -Namespace $namespace -Action $action
    $status = if ($allowed) { 'ok' } else { 'BLOCKED' }
    Write-Output ("{0,-7} {1}:{2}" -f $status, $namespace, $action)
    if (-not $allowed) {
        $failures += "$namespace`:$action"
    }
}

$endpointKeys = @(
    'endpoint/ml.g4dn.xlarge',
    'endpoint/ml.g5.xlarge',
    'endpoint/ml.g5.2xlarge',
    'endpoint/ml.c5.2xlarge',
    'endpoint/ml.m5.2xlarge'
)

Write-Output ''
Write-Output 'SageMaker endpoint limits:'
foreach ($key in $endpointKeys) {
    $rows = @($sagemaker | Where-Object {
        $_.'Resource Key' -eq $key -and ($_.Region -eq '*' -or $_.Region -in @('us-east-1', 'us-west-2'))
    })
    $limit = ($rows | Measure-Object -Property Limit -Maximum).Maximum
    if ($null -eq $limit -or [double]$limit -le 0) {
        $failures += $key
        Write-Output ("BLOCKED {0}" -f $key)
    }
    else {
        Write-Output ("ok      {0} limit={1}" -f $key, $limit)
    }
}

if ($failures.Count -gt 0) {
    throw "Hackathon service support check failed. Missing/zero entries: $($failures -join ', ')"
}

Write-Output ''
Write-Output 'Hackathon service support check passed for the current speech deployment prerequisites.'
