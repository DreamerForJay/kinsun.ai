# Speech deployment guide for the 2026 hackathon account

This guide is intentionally fail-closed. It deploys no resource until the
competition service list, account, Region, quota, model license, and synthetic
test data are confirmed.

## 1. Data rules

Only team-authored synthetic test content may be used. Do not upload real elder
audio, real transcripts, health information, personal data, voice identifiers,
or an external speech dataset to the competition account. Public availability
does not imply competition approval.

For every evaluation input, create a manifest containing:

```json
{
  "data_origin": "team-authored-synthetic",
  "real_person": false,
  "contains_personal_data": false,
  "contains_health_data": false,
  "contains_biometric_identifier": false,
  "approved_for_hackathon_aws": true
}
```

## 2. Verify the exported service list

The source workbook and UTF-8 CSV exports remain outside this repository. The
team has exported these sheets without changing the source workbook:

1. `Services List`
2. `EC2`
3. `SageMaker AI`

Keep the CSV files outside Git until the organizer confirms redistribution is
allowed. Run `scripts/check_hackathon_service_support.ps1` against the exports;
the project-specific result is recorded in
`hackathon-supported-services-evidence.md`.

Confirm at minimum: Amazon S3, ECR, Lambda, Step Functions, CloudWatch,
Transcribe, Polly, SageMaker AI, and the exact allowed SageMaker endpoint
instance type. Bedrock model access is checked separately and must be limited to
models directly used by this project.

## 3. Obtain temporary Workshop credentials safely

This competition uses an AWS Academy/Workshop login page, not IAM Identity
Center SSO. Sign in with the competition registration email, start the lab, and
use its AWS CLI/credentials panel. Do not put credentials in `.env`.

```powershell
# Follow the Workshop page's CLI credentials instructions. The temporary
# access key, secret key, and session token must all come from the same session.
```

After configuring a local temporary profile, ask the deployment owner for the
expected 12-digit account ID, then run:

```powershell
.\scripts\aws_preflight.ps1 `
  -Region "us-west-2" `
  -ExpectedAccountId "<owner-provided-account-id>"
```

Omit `-Profile` when using Workshop credentials held in the current PowerShell
environment. A named profile remains optional for an organizer-approved profile.

Use `us-west-2` because the organizer's Workshop entry point explicitly selects
it. Use `us-east-1` only as a documented fallback after proving a required
service or model is unavailable. Any other Region is rejected.

Before CDK commands, set the project-owned Region variable:

```powershell
$env:KINSUN_AWS_REGION = "us-west-2"
```

Do not rely on `CDK_DEFAULT_REGION`; CDK CLI can repopulate it from the active
AWS configuration.

## 4. First speech milestone: inference only

Do not start LoRA or a SageMaker Training Job. First produce a local baseline
and deploy only a pre-trained inference endpoint after its exact instance type
is confirmed.

Recommended order:

1. Run zh-TW/en-US Transcribe and Polly smoke tests.
2. Evaluate nan-TW/hak-TW locally with synthetic inputs.
3. Verify model license and immutable model revision.
4. Build the existing SageMaker container locally.
5. Scan the image and push it to a private ECR repository.
6. Create one necessary endpoint at a time.
7. Run the synthetic smoke set and export metrics.
8. Stop/delete the endpoint when the test window ends.

`ASR_SAGEMAKER_ENDPOINT` and `TTS_SAGEMAKER_ENDPOINT` must remain empty until
those steps pass. Endpoint success means only that inference ran; it does not
prove transcription or voice quality.

## 5. Taiwanese/Hakka quality decision

Evaluate raw Hanji CER, normalized Hanji CER, Tailo/syllable error rate,
semantic intent, negation preservation, keyword preservation, latency, and
failure rate. A Mandarin paraphrase may preserve intent while failing verbatim
transcription.

Consider LoRA only when decoding/normalization experiments still fail, the
remaining errors are demonstrably acoustic or lexical, the training dataset is
licensed, the organizer approves bringing it into the account, and the service
list permits the exact training resource. Otherwise retain the pre-trained
model plus low-confidence confirmation and text fallback.

## 6. Stop conditions

Stop immediately if the account ID is wrong, the Region is not allowed, the
service/instance is absent from the competition list, a test item may contain
prohibited data, a bucket or database would be public, Bedrock can exceed one
request per second, or model licensing is unresolved.

## 7. TTS endpoint deployment candidate

`Dockerfile.tts` packages both low-resource routes into one private endpoint:

- `nan-TW`: `facebook/mms-tts-nan` revision
  `f28526a6caaf9dc55e030da83008c933f6a1978b`
- `hak-TW`: `formospeech/yourtts-htia-240704` revision
  `e61e1026d1fe5edb29f35ad025c090526a7e4fe7`

Both are CC-BY-NC-4.0. The build intentionally fails unless the Owner records
that the hackathon use is an allowed non-commercial demonstration and passes
the explicit build argument. This does not authorize later commercial use.

```powershell
# Run only after the Owner license decision and Workshop credentials are valid.
$env:KINSUN_TTS_IMAGE = "kinsun-speech-tts:tts-v1"
docker build `
  --file .\services\speech-gateway\sagemaker\Dockerfile.tts `
  --build-arg ACCEPT_CC_BY_NC_4_0=true `
  --tag $env:KINSUN_TTS_IMAGE `
  .\services\speech-gateway\sagemaker
```

The build downloads the two immutable revisions into the image. Runtime sets
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, so a network-isolated endpoint
does not download models during startup or requests. After local synthetic
container smoke tests pass:

1. Tag and push `tts-v1` to the existing private ECR repository.
2. Create SageMaker Model `kinsun-speech-tts-v1` with network isolation.
3. Create Endpoint Config `kinsun-speech-tts-config-v1` using an instance type
   explicitly present in the competition service list.
4. Create Endpoint `kinsun-speech-tts-v1` with data capture disabled.
5. Invoke once per language using Synthetic text and verify the response starts
   with WAV `RIFF` bytes; record latency and immutable image digest.
6. Set `TTS_SAGEMAKER_ENDPOINT=kinsun-speech-tts-v1` only after both routes pass.
7. Delete the endpoint after the demo window; retain Model/ECR only if needed
   for reproducible recreation.

Image push 完成並取得 immutable digest URI 後，可先 dry-run 部署腳本；只有加上
`-Execute` 才會建立資源：

```powershell
.\scripts\deploy_sagemaker_tts.ps1 `
  -ExpectedAccountId "<12-digit-account>" `
  -ExecutionRoleArn "arn:aws:iam::<account>:role/<sagemaker-role>" `
  -ImageDigestUri "<account>.dkr.ecr.us-west-2.amazonaws.com/kinsun-speech-gateway@sha256:<64-hex>" `
  -AcceptCcByNcNonCommercialDemo
```

確認輸出後，再補 `-Execute`。腳本會重驗 AWS Account、使用 image digest、開啟
Network Isolation，且不啟用 Data Capture。

Do not send agent replies or elder content to external Hugging Face Spaces.
