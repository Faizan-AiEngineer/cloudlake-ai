# AWS deployment boundary

Terraform covers S3, AWS Glue jobs and Data Catalog, Athena, IAM, EventBridge, SQS and its dead-letter queue, Lambda and CloudWatch. The Glue job shares validation expressions and feed definitions with the local Spark implementation. It reads landing files and writes run-scoped Bronze, Silver and quarantine datasets. Cloud Gold currently contains the Iceberg sales fact and daily sales mart. The AWS job does a full rebuild and commits the Iceberg tables individually.

## Local validation

```powershell
terraform -chdir=infrastructure/terraform fmt -check
terraform -chdir=infrastructure/terraform init -backend=false -input=false
terraform -chdir=infrastructure/terraform validate
```

These commands do not deploy or require AWS credentials. The provider registry is needed for initialization on a clean machine.

## Approved deployment sequence

1. Select an AWS account, supported region, globally unique bucket name and an isolated deployment role. Configure a protected remote Terraform state backend and locking for shared use.
2. Obtain explicit approval for any operation that calls AWS or may incur costs. Review [cost drivers](COST_ESTIMATION.md), service quotas, identity boundaries and data restrictions.
3. After authorization, create and inspect a Terraform plan before applying. Keep schedules disabled during setup. Use a separate state per deployment environment.
4. Produce all synthetic feeds locally. Stage a complete feed set under `landing/<dataset>/`. Trigger a reviewed Glue run, inspect logs and quarantine, and check the Glue Data Catalog before querying Athena.
5. Run the [Athena SQL](../aws/athena_queries/daily_sales.sql) in the configured workgroup. Verify query result encryption, scanned-byte cutoff, quality gating, event delivery and deduplication behavior against the real account.
6. Enable the scheduled or landing-event path only after readiness checks and budget approval.

Cleanup can incur charges. Pause triggers and drain or archive queue messages per retention needs. After explicit approval, remove intended objects, object versions and delete markers from the versioned bucket, then use the reviewed Terraform removal plan. Preserve investigation data and intentional state history.
