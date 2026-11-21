locals {
  name      = "cloudlake-${var.environment}"
  job       = "${local.name}-lakehouse"
  artifacts = "${path.module}/../.."
  glue_logs = "/aws-glue/jobs/${local.name}"
}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_s3_bucket" "lake" {
  bucket = var.bucket_name
}
resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket     = aws_s3_bucket.lake.id
  depends_on = [aws_s3_bucket_versioning.lake]
  rule {
    id     = "query-results-and-history"
    status = "Enabled"
    filter {
      prefix = "athena/"
    }
    expiration {
      days = 14
    }
    noncurrent_version_expiration {
      noncurrent_days = 14
    }
  }
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
resource "aws_s3_bucket_policy" "tls" {
  bucket = aws_s3_bucket.lake.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
resource "aws_s3_bucket_notification" "events" {
  bucket      = aws_s3_bucket.lake.id
  eventbridge = true
}
resource "aws_glue_catalog_database" "lake" {
  name = replace(local.name, "-", "_")
}

resource "aws_athena_workgroup" "lake" {
  name = local.name
  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824
    result_configuration {
      output_location = "s3://${aws_s3_bucket.lake.bucket}/athena/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
data "archive_file" "glue_library" {
  type        = "zip"
  output_path = "${path.module}/.terraform/cloudlake-glue-library.zip"
  source {
    content  = file("${local.artifacts}/data_engineering/rules.py")
    filename = "data_engineering/rules.py"
  }
  source {
    content  = file("${local.artifacts}/data_engineering/schema.py")
    filename = "data_engineering/schema.py"
  }
  source {
    content  = "# Shared CloudLake validation and schema"
    filename = "data_engineering/__init__.py"
  }
}
resource "aws_s3_object" "library" {
  bucket      = aws_s3_bucket.lake.id
  key         = "artifacts/cloudlake-glue-library.zip"
  source      = data.archive_file.glue_library.output_path
  source_hash = data.archive_file.glue_library.output_base64sha256
}
resource "aws_s3_object" "job" {
  bucket      = aws_s3_bucket.lake.id
  key         = "artifacts/lakehouse.py"
  source      = "${local.artifacts}/aws/glue_jobs/lakehouse.py"
  source_hash = filesha256("${local.artifacts}/aws/glue_jobs/lakehouse.py")
}
resource "aws_glue_job" "lake" {
  name              = local.job
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "5.1"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 15
  max_retries       = 0
  execution_property {
    max_concurrent_runs = 1
  }
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.lake.id}/${aws_s3_object.job.key}"
  }
  default_arguments = {
    "--job-language"                 = "python"
    "--datalake-formats"             = "iceberg"
    "--extra-py-files"               = "s3://${aws_s3_bucket.lake.id}/${aws_s3_object.library.key}"
    "--LAKE_BUCKET"                  = aws_s3_bucket.lake.id
    "--CATALOG_DB"                   = aws_glue_catalog_database.lake.name
    "--QUALITY_LIMIT"                = "0.15"
    "--enable-metrics"               = "true"
    "--enable-observability-metrics" = "true"
    "--custom-logGroup-prefix"       = local.glue_logs
  }
}
resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.name}-dead"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue" "ingestion" {
  name                       = "${local.name}-ingestion"
  visibility_timeout_seconds = 180
  message_retention_seconds  = 86400
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 8
  })
}
resource "aws_cloudwatch_event_rule" "arrivals" {
  name  = "${local.name}-arrivals"
  state = var.enable_arrivals ? "ENABLED" : "DISABLED"
  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.lake.id] }
      object = { key = [{ prefix = "landing/" }] }
    }
  })
}
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${local.name}-daily"
  schedule_expression = "cron(0 2 * * ? *)"
  state               = var.enable_schedule ? "ENABLED" : "DISABLED"
}
resource "aws_cloudwatch_event_target" "arrival" {
  rule = aws_cloudwatch_event_rule.arrivals.name
  arn  = aws_sqs_queue.ingestion.arn
}
resource "aws_cloudwatch_event_target" "schedule" {
  rule  = aws_cloudwatch_event_rule.schedule.name
  arn   = aws_sqs_queue.ingestion.arn
  input = jsonencode({ source = "cloudlake.schedule", detail-type = "CloudLake timer" })
}
resource "aws_sqs_queue_policy" "events" {
  queue_url = aws_sqs_queue.ingestion.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.ingestion.arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = [aws_cloudwatch_event_rule.arrivals.arn, aws_cloudwatch_event_rule.schedule.arn] }
      }
    }]
  })
}
data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${local.artifacts}/aws/lambda_functions/trigger.py"
  output_path = "${path.module}/.terraform/cloudlake-trigger.zip"
}
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}-trigger"
  retention_in_days = 14
}
resource "aws_cloudwatch_log_group" "glue" {
  for_each          = toset(["error", "output"])
  name              = "${local.glue_logs}/${each.key}"
  retention_in_days = 14
}
resource "aws_lambda_function" "trigger" {
  function_name    = "${local.name}-trigger"
  role             = aws_iam_role.lambda.arn
  handler          = "trigger.handle"
  runtime          = "python3.12"
  timeout          = 20
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  environment {
    variables = { GLUE_JOB_NAME = aws_glue_job.lake.name, LAKE_BUCKET = aws_s3_bucket.lake.id }
  }
  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.lambda]
}
resource "aws_lambda_event_source_mapping" "queue" {
  event_source_arn                   = aws_sqs_queue.ingestion.arn
  function_name                      = aws_lambda_function.trigger.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 30
  function_response_types            = ["ReportBatchItemFailures"]
}
resource "aws_cloudwatch_metric_alarm" "dead_letter" {
  alarm_name          = "${local.name}-dead-letter"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dead_letter.name }
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  period              = 300
  threshold           = 0
  treat_missing_data  = "notBreaching"
}
output "lake_bucket" {
  value = aws_s3_bucket.lake.id
}
output "athena_workgroup" {
  value = aws_athena_workgroup.lake.name
}
