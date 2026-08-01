# Hackathon supported-services evidence

- Source: organizer-provided `Supported AWS Services List 20260722.xlsx`
- Inspected exports: `Services List.csv`, `EC2.csv`, `SageMaker AI.csv`
- Inspection date: 2026-08-01
- Scope: prerequisites for the Kinsun speech vertical slice
- Data policy: source workbook and CSV exports remain outside the public repository

This document records only project-relevant facts. The organizer's live
environment and announcements remain authoritative.

## Required service actions

The exported service list includes the actions needed for the planned speech
path, including:

| Service | Confirmed relevant actions |
| --- | --- |
| Amazon Bedrock | `InvokeModel` |
| Amazon ECR | private repository/image operations |
| AWS Lambda | create, update, and invoke function |
| Amazon Polly | `SynthesizeSpeech` |
| Amazon S3 | bucket public-access block and object operations |
| Amazon SageMaker AI | create/configure/invoke/delete endpoint |
| AWS Step Functions | create/update/start state machine execution |
| Amazon Transcribe | `StartStreamTranscription` |

This is an account allowlist result, not proof that a particular model is
enabled or that runtime quota is currently available.

## SageMaker endpoint limits relevant to speech

| Endpoint instance | Exported limit | Current use decision |
| --- | ---: | --- |
| `ml.g4dn.xlarge` | 2 | preferred first GPU inference spike |
| `ml.g5.xlarge` | 2 | quality/performance comparison only if needed |
| `ml.g5.2xlarge` | 2 | avoid unless measured memory requires it |
| `ml.c5.2xlarge` | 2 | CPU compatibility/baseline candidate |
| `ml.m5.2xlarge` | 2 | CPU compatibility/baseline candidate |

The smallest confirmed instance should be tried first. Only one speech endpoint
should be active during the first smoke test; do not consume the exported quota
merely because it exists.

## Training and LoRA decision

Most listed GPU training-job quotas are zero. The inspected export has a limit
of one for `training-job/ml.p3.2xlarge` and one for
`training-job/ml.trn1.2xlarge`. This means training is technically possible on
only a narrow subset, but it is not approved for this project because:

1. the competition account prohibits importing the speech/person-related data
   that would normally be needed;
2. the organizer discourages large training workloads;
3. the current Taiwanese example has not separated transcription, writing
   system, decoding, and semantic-paraphrase errors;
4. inference, normalization, and evaluation are sufficient for the next Gate 1
   evidence step.

LoRA therefore remains blocked unless the organizer gives written dataset
approval and a later benchmark proves an acoustic/lexical model deficit.

## Region and account lifetime

- Deployment Regions: `us-east-1`, `us-west-2` only.
- Competition environment availability: 2026-08-01 08:00 through
  2026-08-02 14:00, according to the organizer notice supplied by the team.
- Authentication: competition AWS Academy/Workshop page with the registration
  email; not IAM Identity Center SSO.

## Reproduce the check

Run locally against the organizer CSV exports (do not commit them):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\check_hackathon_service_support.ps1 `
  -ServicesCsv "<path>\Services List.csv" `
  -SageMakerCsv "<path>\SageMaker AI.csv"
```

The script fails closed when a required action or selected endpoint quota is
missing or zero.
