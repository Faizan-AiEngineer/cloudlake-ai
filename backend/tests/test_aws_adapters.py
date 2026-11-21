import json
import sys
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from data_engineering.ingest import S3Source


def test_s3_compatible_source_lists_only_registered_feeds():
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = [{
        "Contents": [
            {"Key": "landing/orders/source.json", "Size": 3},
            {"Key": "landing/unregistered/source.json", "Size": 3},
            {"Key": "landing/orders/deeper/ignored.json", "Size": 3},
        ],
    }]
    client.get_object.return_value = {"Body": BytesIO(b"[]")}
    [source] = S3Source(client, "test-lake").sources()
    assert source.dataset == "orders"
    assert source.content == b"[]"
    client.get_object.assert_called_once_with(Bucket="test-lake", Key="landing/orders/source.json")


def test_lambda_retries_capacity_and_rejects_an_unrelated_event(monkeypatch):
    class ConcurrentRunsExceeded(Exception):
        pass

    glue = Mock()
    glue.start_job_run.side_effect = ConcurrentRunsExceeded
    glue.exceptions.ConcurrentRunsExceededException = ConcurrentRunsExceeded
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda _: glue))
    monkeypatch.setenv("LAKE_BUCKET", "test-lake")
    monkeypatch.setenv("GLUE_JOB_NAME", "test-job")
    from aws.lambda_functions.trigger import handle

    def event(identifier, source, detail_type):
        return {"messageId": identifier, "body": json.dumps({"source": source, "detail-type": detail_type})}

    results = handle({"Records": [
        event("accepted", "cloudlake.schedule", "CloudLake timer"),
        event("rejected", "unknown", "unexpected"),
    ]}, None)
    assert results == {"batchItemFailures": [{"itemIdentifier": "rejected"}, {"itemIdentifier": "accepted"}]}
    glue.start_job_run.assert_called_once_with(JobName="test-job")
