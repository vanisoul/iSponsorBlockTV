import asyncio
import json

from iSponsorBlockTV.ai_segments import DifyConfig, infer_segments_dify_workflow


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return json.dumps(self._payload)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_dify_workflow_posts_youtube_url_and_parses_result_json():
    response = FakeResponse(
        200,
        {
            "workflow_run_id": "run-1",
            "task_id": "task-1",
            "data": {
                "status": "succeeded",
                "outputs": {
                    "result_json": json.dumps(
                        {
                            "schema_version": "1.0",
                            "video_id": "abc123",
                            "source": "dify",
                            "status": "ok",
                            "duration": 120.0,
                            "segments": [
                                {
                                    "start": 0,
                                    "end": 30,
                                    "category": "opening",
                                    "action": "skip",
                                    "confidence": 0.92,
                                    "reason": "opening section",
                                }
                            ],
                            "warnings": [],
                        }
                    )
                },
            },
        },
    )
    session = FakeSession(response)

    result = asyncio.run(
        infer_segments_dify_workflow(
            session,
            "abc123",
            cfg=DifyConfig(
                base_url="https://api.dify.ai",
                api_key="secret",
                timeout_seconds=15,
                min_confidence=0.85,
                response_mode="blocking",
                user="device-1",
            ),
        )
    )

    assert session.calls[0][0] == "https://api.dify.ai/v1/workflows/run"
    request = session.calls[0][1]
    assert request["headers"]["Authorization"] == "Bearer secret"
    assert request["json"] == {
        "inputs": {
            "video_id": "abc123",
            "youtube_url": "https://www.youtube.com/watch?v=abc123",
            "min_confidence": 0.85,
            "allowed_categories": ["opening", "ending", "preview", "recap"],
        },
        "response_mode": "blocking",
        "user": "device-1",
    }
    assert result["source"] == "dify"
    assert result["segments"] == [
        {
            "start": 0.0,
            "end": 30.0,
            "category": "opening",
            "action": "skip",
            "confidence": 0.92,
            "reason": "opening section",
        }
    ]


def test_dify_workflow_returns_fallback_when_result_json_missing():
    session = FakeSession(FakeResponse(200, {"data": {"status": "succeeded", "outputs": {}}}))

    result = asyncio.run(
        infer_segments_dify_workflow(
            session,
            "abc123",
            cfg=DifyConfig(base_url="https://api.dify.ai", api_key=None),
        )
    )

    assert result == {
        "schema_version": "1.0",
        "video_id": "abc123",
        "source": "dify",
        "status": "fallback",
        "segments": [],
        "warnings": ["dify_empty_result_json"],
    }
