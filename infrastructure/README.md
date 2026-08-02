# AWS infrastructure status

> **Do not deploy the current `ElderlyCareStack`.**

ADR 0007 選定 AWS CDK v2 作為 canonical IaC 工具，但本目錄現有 stack 是凍結的
Lambda／DynamoDB legacy implementation，會建立另一套 Cognito，與目前
Next.js BFF → Python Core／Aurora → Agent Runtime 主線不相容。

`cdk.json` 的預設 app 已切到 asset-free 的 canonical staging foundation；它只建立
VPC、ECR、ECS cluster、Aurora、Secrets、Logs、IAM roles 與 external-resource references，
不建立 task／service，也不建立 Cognito／OpenSearch。Frontend、Core API、Core migration 與
Agent Runtime 的 deployable container image 已可在本機建立；獨立的 application stack 也已完成
asset-free synth，但尚未部署至 AWS。

目前 canonical template 是已套用的穩定保護狀態：Aurora
`deletionProtection=true`，`DeletionPolicy` 與 `UpdateReplacePolicy` 皆為 `Snapshot`，且
Aurora admin Secret 採 `Retain`，foundation stack 已啟用 termination protection。首次
bootstrap 曾使用經 change set 稽核的
create-only template（`Delete`／`false`），避免其他資源失敗時，尚未 available 的空 cluster
因無法拍 snapshot 而卡在 `ROLLBACK_FAILED`；stack 到 `CREATE_COMPLETE` 後已立即用第二階段
update 切回本檔所代表的保護狀態。新環境若需要同樣的兩階段 bootstrap，必須留下 change set
證據並在 create 完成後立即套用 canonical template，不得把 create-only 例外保留為 steady state。

既有 `kinsun-rag-staging-data` OpenSearch Serverless data policy 已保留 ingestion 與原 runtime
principals，並只把 canonical Agent ECS task role 追加到 read-only statement；Cognito 與
OpenSearch 本身仍由外部管理，本 stack 不重建它們。

External Cognito app-client reference 已指向 `kinsun-web-bff-staging`；
`CognitoWebBffClientId` 以單值 `AllowedValues` fail closed，避免 stack update 誤用 legacy client。

兩個 physical CloudFormation stack name 已固定，避免 CDK 因 construct ID 建立第二套：

- foundation：`kinsun-staging-foundation-v1`
- application：`kinsun-staging-application-v1`

目前允許：

- `npm run synth`／`npm run deploy` 操作 canonical staging foundation。
- `npm run synth:legacy:audit` 只做 legacy template 的唯讀稽核。
- `npm run synth:application` 產生初始 `desiredCount=0` 的 application template。
- `scripts/build_staging_images.ps1` 建立四個 Linux/amd64、non-root 本機 image；Frontend 的
  consent policy version 必須在 `next build` 時傳入並記錄於 OCI label。
- `scripts/validate_ecr_release.ps1` 在部署前驗證每個 digest 的 repository、tag、ECR scan、
  Linux/amd64 與 artifact/provenance label。
- 為遷移盤點既有 resource dependencies。

目前禁止：

- 對任何環境執行現有 stack 的 `cdk deploy`。
- 建立第二套 Cognito、OpenSearch、DynamoDB Domain Store 或 Legacy Lambda backend。
- 把 foundation 的成功部署當成 application runtime 已完成；目前 AWS 尚未建立 canonical
  application task／service。
- 在 Next.js deployment security gate 未解除前推送 Frontend release image、修改 Cognito
  callback 或把 service 從 `desiredCount=0` 調為 `1`。

Application rollout 必須依序完成：foundation runtime DB Secret／migration repository update、
四個 ECR digest preflight、`desiredCount=0` change set、Cognito callback 複驗、one-shot migration
與 runtime principal reconciliation、unsigned synthetic staging consent bootstrap、內部 smoke，
最後才可 scale 到 `1`。Core 長期 task 只讀 `kinsun_app` runtime Secret；Aurora admin Secret
只注入 one-shot migration。Staging Core 使用 `NullPool` 與 request-triggered bounded recovery，
避免健康檢查或 idle connection 永久喚醒 Aurora；是否真的降至 0 ACU 仍須以 CloudWatch/RDS
實測，不以設定值推定。

新的 canonical constructs 必須重建 application topology，並以 externally managed reference
重用既有 staging Cognito 與 OpenSearch。詳見
[`docs/adr/0007-canonical-backend-and-aws-deployment-authority.md`](../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md)。
