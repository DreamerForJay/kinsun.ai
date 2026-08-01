# Demo data

`seed-demo-data.ts` populates the DynamoDB table with a single fictional
elder persona — **林阿嬤 (Lin Ah-ma)** — for demos and testing, matching the
Demo 必演流程 in requirements.md.

## De-identification (H05.1–H05.3)

- Every name, relationship, email address, and utterance in the seed data
  is **invented for this demo**. None of it describes, is derived from, or
  can be traced to a real person.
- IDs are prefixed `demo-` (`demo-elder-lin`, `demo-caregiver-chen`,
  `demo-family-lin-son`, ...) so demo records are trivially distinguishable
  from real tenant data in logs, dashboards, and DynamoDB scans.
- Email addresses use the reserved `.invalid` TLD (RFC 2606), which cannot
  resolve to a real mailbox.
- The generation method is manual authorship of short, natural-sounding
  Hokkien/Mandarin dialogue lines and plausible daily-life events (meals,
  a walk, a medication statement) — not sourced from any real conversation,
  care record, or transcript.
- **Never** run this script against a table that also holds real elder
  data without first confirming the `demo-` IDs can't collide with real
  ones (they won't, since real elder IDs are ULIDs generated at signup,
  never `demo-*`).

## Running it

```bash
DYNAMODB_TABLE_NAME=elderly-care-main-<env> npm run seed:demo --workspace=@elderly-care/backend
```

Requires AWS credentials with write access to the target table (the same
credentials `cdk deploy` would use). This only seeds DynamoDB. The historical
TypeScript knowledge-ETL path is deprecated; staging RAG ingestion is owned by
`services/rag-ingestion/` and the commands under `scripts/rag/`.
