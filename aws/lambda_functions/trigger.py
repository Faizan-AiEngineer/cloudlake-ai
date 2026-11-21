import json
import os

import boto3

glue = boto3.client("glue")


def accepted(body):
    if body.get("source") == "cloudlake.schedule" and body.get("detail-type") == "CloudLake timer":
        return True
    if body.get("source") == "aws.s3" and body.get("detail-type") == "Object Created":
        detail = body.get("detail", {})
        return (
            detail.get("bucket", {}).get("name") == os.environ["LAKE_BUCKET"]
            and detail.get("object", {}).get("key", "").startswith("landing/")
        )
    return False


def handle(event, _):
    records = event.get("Records", [])
    work = []
    failures = []
    for item in records:
        try:
            body = json.loads(item["body"])
            if not isinstance(body, dict) or not accepted(body):
                raise ValueError("Unexpected event envelope")
            work.append(item["messageId"])
        except (KeyError, ValueError, TypeError, AttributeError):
            failures.append({"itemIdentifier": item["messageId"]})
    if work:
        try:
            glue.start_job_run(JobName=os.environ["GLUE_JOB_NAME"])
        except glue.exceptions.ConcurrentRunsExceededException:
            failures.extend({"itemIdentifier": item} for item in work)
    return {"batchItemFailures": failures}
