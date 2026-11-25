"""
test_unified_lambda_dispatcher.py — Tests for unified Lambda event dispatcher
=============================================================================
Written test-first prior to unified dispatcher implementation:
1. Trusted routing via eventSourceARN + configured queue mappings (not body).
2. API Gateway HTTP API v2 & REST API v1 routing via Mangum.
3. Scheduled EventBridge / Scheduler routing to recovery handler.
4. Safe failure on untrusted / unknown SQS ARNs and unknown event shapes.
5. Lazy import isolation (API import path does not load heavy workers).
6. Preprod ODL staging bucket isolation without touching prod storage.
"""

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def configured_queues(monkeypatch):
    monkeypatch.setenv("SQS_STAGE1_QUEUE_URL", "https://sqs.ap-south-1.amazonaws.com/445567096027/resume-ranker-stage1-preprod")
    monkeypatch.setenv("SQS_STAGE2_QUEUE_URL", "https://sqs.ap-south-1.amazonaws.com/445567096027/resume-ranker-stage2-preprod")
    monkeypatch.setenv("SQS_SCORING_QUEUE_URL", "https://sqs.ap-south-1.amazonaws.com/445567096027/resume-ranker-scoring-preprod")
    monkeypatch.setenv("SQS_STAGE1_DLQ_URL", "https://sqs.ap-south-1.amazonaws.com/445567096027/resume-ranker-stage1-dlq-preprod")
    monkeypatch.setenv("SQS_STAGE2_DLQ_URL", "https://sqs.ap-south-1.amazonaws.com/445567096027/resume-ranker-stage2-dlq-preprod")
    monkeypatch.setenv("SQS_SCORING_DLQ_URL", "https://sqs.ap-south-1.amazonaws.com/445567096027/resume-ranker-scoring-dlq-preprod")
    from src.config.aws import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_unified_dispatcher_routes_http_api_v2_event():
    """HTTP API v2 events route to Mangum API handler."""
    import src.lambda_handler as lh

    http_v2_event = {
        "version": "2.0",
        "rawPath": "/health",
        "requestContext": {
            "http": {"method": "GET", "path": "/health"},
        },
    }

    with patch("src.handlers.api.handler", return_value={"statusCode": 200, "body": '{"status":"ok"}'}) as mock_api:
        res = lh.handler(http_v2_event, None)
        mock_api.assert_called_once_with(http_v2_event, None)
        assert res["statusCode"] == 200


def test_unified_dispatcher_routes_rest_api_v1_event():
    """REST API v1 events route to Mangum API handler."""
    import src.lambda_handler as lh

    http_v1_event = {
        "httpMethod": "GET",
        "path": "/health",
    }

    with patch("src.handlers.api.handler", return_value={"statusCode": 200}) as mock_api:
        res = lh.handler(http_v1_event, None)
        mock_api.assert_called_once_with(http_v1_event, None)
        assert res["statusCode"] == 200


def test_unified_dispatcher_routes_stage1_sqs_by_configured_arn(configured_queues):
    """SQS events from Stage1 ARN route to stage1 handler regardless of body contents."""
    import src.lambda_handler as lh

    event = {
        "Records": [
            {
                "messageId": "m1",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:ap-south-1:445567096027:resume-ranker-stage1-preprod",
                # Attempted payload spoof: must be ignored for routing
                "body": json.dumps({"stage": "FINAL_RANK", "job_id": "j1"}),
            }
        ]
    }

    with patch("src.handlers.stage1.handler", return_value={"statusCode": 200, "batchItemFailures": []}) as mock_s1, \
         patch("src.handlers.scoring.handler") as mock_score:
        res = lh.handler(event, None)
        mock_s1.assert_called_once_with(event, None)
        mock_score.assert_not_called()
        assert res["statusCode"] == 200


def test_unified_dispatcher_routes_stage2_sqs_by_configured_arn(configured_queues):
    """SQS events from Stage2 ARN route strictly to stage2 handler."""
    import src.lambda_handler as lh

    event = {
        "Records": [
            {
                "messageId": "m2",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:ap-south-1:445567096027:resume-ranker-stage2-preprod",
                "body": json.dumps({"job_id": "j1", "file_id": "f1"}),
            }
        ]
    }

    with patch("src.handlers.stage2.handler", return_value={"statusCode": 200, "batchItemFailures": []}) as mock_s2:
        res = lh.handler(event, None)
        mock_s2.assert_called_once_with(event, None)
        assert res["statusCode"] == 200


def test_unified_dispatcher_routes_scoring_sqs_by_configured_arn(configured_queues):
    """SQS events from Scoring ARN route strictly to scoring handler."""
    import src.lambda_handler as lh

    event = {
        "Records": [
            {
                "messageId": "m3",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:ap-south-1:445567096027:resume-ranker-scoring-preprod",
                "body": json.dumps({"job_id": "j1"}),
            }
        ]
    }

    with patch("src.handlers.scoring.handler", return_value={"statusCode": 200, "batchItemFailures": []}) as mock_score:
        res = lh.handler(event, None)
        mock_score.assert_called_once_with(event, None)
        assert res["statusCode"] == 200


@pytest.mark.parametrize("dlq_name", [
    "resume-ranker-stage1-dlq-preprod",
    "resume-ranker-stage2-dlq-preprod",
    "resume-ranker-scoring-dlq-preprod",
])
def test_unified_dispatcher_routes_dlq_sqs_by_configured_arn(configured_queues, dlq_name):
    """SQS events from any configured DLQ ARN route to dlq handler."""
    import src.lambda_handler as lh

    event = {
        "Records": [
            {
                "messageId": "dlq-1",
                "eventSource": "aws:sqs",
                "eventSourceARN": f"arn:aws:sqs:ap-south-1:445567096027:{dlq_name}",
                "body": json.dumps({"job_id": "j1", "file_id": "f1"}),
            }
        ]
    }

    with patch("src.handlers.dlq.handler", return_value={"statusCode": 200, "batchItemFailures": []}) as mock_dlq:
        res = lh.handler(event, None)
        mock_dlq.assert_called_once_with(event, None)
        assert res["statusCode"] == 200


def test_unified_dispatcher_rejects_untrusted_sqs_arn_safely(configured_queues):
    """Untrusted or unconfigured SQS ARNs must never execute workers and must report batchItemFailures."""
    import src.lambda_handler as lh

    event = {
        "Records": [
            {
                "messageId": "msg-foreign-1",
                "eventSource": "aws:sqs",
                "eventSourceARN": "arn:aws:sqs:ap-south-1:445567096027:unrelated-project-queue",
                "body": json.dumps({"stage": "FAST_PARSE", "job_id": "j1"}),
            }
        ]
    }

    with patch("src.handlers.stage1.handler") as mock_s1, \
         patch("src.handlers.stage2.handler") as mock_s2, \
         patch("src.handlers.scoring.handler") as mock_sc, \
         patch("src.handlers.dlq.handler") as mock_dlq:
        res = lh.handler(event, None)
        mock_s1.assert_not_called()
        mock_s2.assert_not_called()
        mock_sc.assert_not_called()
        mock_dlq.assert_not_called()
        assert res["batchItemFailures"] == [{"itemIdentifier": "msg-foreign-1"}]


def test_unified_dispatcher_routes_scheduled_events():
    """EventBridge and Scheduler scheduled events route to recovery handler."""
    import src.lambda_handler as lh

    eb_event = {
        "version": "0",
        "id": "evt-1",
        "detail-type": "Scheduled Event",
        "source": "aws.events",
    }
    sched_event = {
        "source": "aws.scheduler",
        "action": "reconcile_outbox",
    }

    with patch("src.handlers.recovery.handler", return_value={"statusCode": 200, "relayed_events": 1, "recovered_jobs": 0}) as mock_rec:
        res1 = lh.handler(eb_event, None)
        res2 = lh.handler(sched_event, None)
        assert mock_rec.call_count == 2
        assert res1["statusCode"] == 200
        assert res2["statusCode"] == 200


def test_unified_dispatcher_rejects_unknown_event_sources():
    """Unknown non-SQS, non-HTTP, non-Schedule events fail safely by raising ValueError."""
    import src.lambda_handler as lh

    with pytest.raises(ValueError, match="Unsupported event source"):
        lh.handler({"unexpected_payload": True}, None)

    with pytest.raises(ValueError, match="Unsupported event source"):
        lh.handler({"Records": [{"eventSource": "aws:s3", "eventName": "ObjectCreated:Put"}]}, None)


def test_unified_dispatcher_empty_sqs_records():
    """Empty SQS batch succeeds with zero processed and no failures."""
    import src.lambda_handler as lh

    res = lh.handler({"Records": []}, None)
    assert res["statusCode"] == 200
    assert res["processed"] == 0
    assert res["batchItemFailures"] == []


def test_unified_dispatcher_module_import_is_lazy():
    """Importing src.lambda_handler must not eagerly import worker stacks or FastAPI/Mangum."""
    code = (
        "import sys, src.lambda_handler; "
        "loaded = [m for m in ('fastapi', 'mangum', 'src.pipeline.stage1_worker', 'src.pipeline.stage2_worker', 'src.pipeline.scoring_worker') if m in sys.modules]; "
        "assert not loaded, f'Eager imports detected: {loaded}'"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd="/home/swyra/projects/resume_ranker/backend",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_odl_client_staging_bucket_isolates_preprod_from_prod(monkeypatch):
    """When ODL_STAGING_BUCKET is set, parse_batch stages PDFs to staging bucket and cleans up in finally."""
    from src.extraction import odl_client

    monkeypatch.setenv("ODL_STAGING_BUCKET", "pdf-test-bucket-09")
    monkeypatch.setenv("ODL_STAGING_PREFIX", "preprod-staging")
    from src.config.aws import get_settings
    get_settings.cache_clear()

    mock_s3 = MagicMock()
    mock_lambda = MagicMock()
    payload_bytes = json.dumps({
        "statusCode": 200,
        "body": json.dumps({"results": [{"document_id": "doc-1", "markdown": "# Alice", "elements": []}], "failed": []}),
    }).encode("utf-8")
    mock_lambda.invoke.return_value = {"Payload": MagicMock(read=MagicMock(return_value=payload_bytes))}

    with patch("src.config.aws.get_client", side_effect=lambda svc, **kw: mock_s3 if svc == "s3" else mock_lambda), \
         patch.object(odl_client, "_lambda_client", mock_lambda):
        docs = [odl_client.DocDescriptor(document_id="doc-1", s3_bucket="resume-ranker-preprod-445567096027", s3_key="job_1/doc-1.pdf")]
        res = odl_client.parse_batch(docs)

    assert "doc-1" in res.results
    # Copied from preprod bucket into staging bucket
    mock_s3.copy_object.assert_called_once()
    copy_kwargs = mock_s3.copy_object.call_args[1]
    assert copy_kwargs["Bucket"] == "pdf-test-bucket-09"
    assert copy_kwargs["Key"].startswith("preprod-staging/")
    # Lambda invoked with staging bucket, NOT prod or preprod bucket
    invoked_event = json.loads(mock_lambda.invoke.call_args[1]["Payload"].decode("utf-8"))
    assert invoked_event["documents"][0]["s3_bucket"] == "pdf-test-bucket-09"
    # Temporary staged object deleted in finally
    mock_s3.delete_object.assert_called_once_with(Bucket="pdf-test-bucket-09", Key=copy_kwargs["Key"])
    get_settings.cache_clear()


def test_bm25_scorer_handles_zero_skill_corpus_without_division_by_zero():
    """Single scanned or empty-skills candidate corpus must score 0.0 instead of ZeroDivisionError."""
    from src.ranking.bm25_scorer import bm25_skill_score, precompute_bm25_idf

    idf, avg_len = precompute_bm25_idf(["Python", "SQL"], [[]])
    assert avg_len >= 1.0
    score = bm25_skill_score([], ["Python", "SQL"], [[]], precomputed_idf=(idf, avg_len))
    assert score == 0.0
    score_zero_avg = bm25_skill_score([], ["Python"], [[]], precomputed_idf=(idf, 0.0))
    assert score_zero_avg == 0.0


def test_stage2_extracts_odl_batch_document_ids_and_merges_provenance():
    """ODL_BATCH messages with document_ids list expand cleanly and track field_sources provenance."""
    from src.pipeline.stage2_worker import _extract_job_file_ids, merge_extracted_fields

    jid, fids = _extract_job_file_ids({
        "messageId": "m-1",
        "body": json.dumps({
            "job_id": "job-1",
            "document_id": None,
            "document_ids": ["doc-a", "doc-b", "doc-a"],
            "stage": "ODL_BATCH",
        }),
    })
    assert jid == "job-1"
    assert fids == ["doc-a", "doc-b"]

    merged_odl = merge_extracted_fields(
        {"skills": ["Python"], "experience": []},
        {"skills": ["SQL"], "experience": [{"title": "Dev"}]},
        "ODL",
    )
    assert merged_odl["extraction_providers"] == ["pymupdf", "ODL"]
    assert merged_odl["extraction_source"] == "pymupdf+ODL"
    assert merged_odl["field_sources"]["experience"] == "ODL"

    merged_nova = merge_extracted_fields(
        merged_odl,
        {"name": "Sophia Bennett"},
        "Nova",
    )
    assert merged_nova["extraction_providers"] == ["pymupdf", "ODL", "Nova"]
    assert merged_nova["extraction_source"] == "pymupdf+ODL+Nova"
    assert merged_nova["field_sources"]["name"] == "Nova"

