import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from debatemind.deps import current_user_id
from debatemind.routers import topics as topics_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(topics_router.router, prefix="/api/topics")
    # /generate and other write endpoints require auth; supply a stub user.
    app.dependency_overrides[current_user_id] = lambda: "u1"
    return TestClient(app)


def test_suggest_returns_12_questions(client):
    res = client.get("/api/topics/suggest")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    questions = data["data"]
    assert len(questions) == 12


def test_suggest_covers_all_domains(client):
    res = client.get("/api/topics/suggest")
    questions = res.json()["data"]
    domains = {q["domain"] for q in questions}
    assert domains == {"POLICY", "TECHNOLOGY", "SOCIETY", "LIFE"}


def test_suggest_question_has_required_fields(client):
    res = client.get("/api/topics/suggest")
    q = res.json()["data"][0]
    assert "id" in q
    assert "domain" in q
    assert "title" in q
    assert "description" in q
    assert len(q["description"]) > 50  # non-trivial description


def _mock_openrouter(questions_json: str):
    """Return a mock that makes openrouter.chat.completions.create return questions_json."""
    choice = MagicMock()
    choice.message.content = questions_json
    completion = MagicMock()
    completion.choices = [choice]
    mock_create = AsyncMock(return_value=completion)
    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create
    return mock_client


def test_generate_returns_questions(client):
    payload = [
        {
            "id": "test-question-1",
            "domain": "POLICY",
            "title": "Test debate question",
            "description": "A description that is long enough to be meaningful for the test.",
        }
    ]
    mock_client = _mock_openrouter(json.dumps({"questions": payload}))
    with patch("debatemind.routers.topics.openrouter", mock_client):
        res = client.post("/api/topics/generate", json={"domain": "POLICY", "count": 1})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "test-question-1"


def test_generate_clamps_count_to_10(client):
    payload = [
        {
            "id": f"q-{i}",
            "domain": "LIFE",
            "title": f"Question {i}",
            "description": "Enough text to pass description length check in future.",
        }
        for i in range(10)
    ]
    mock_client = _mock_openrouter(json.dumps({"questions": payload}))
    with patch("debatemind.routers.topics.openrouter", mock_client):
        res = client.post("/api/topics/generate", json={"domain": "LIFE", "count": 999})
    assert res.status_code == 200
    # Verify the LLM was called with count clamped to 10, not 999
    call_args = mock_client.chat.completions.create.call_args
    user_message = call_args.kwargs["messages"][1]["content"]
    assert "10" in user_message
    assert "999" not in user_message


def test_generate_rejects_invalid_count(client):
    res = client.post("/api/topics/generate", json={"domain": "POLICY", "count": 0})
    assert res.status_code == 422


def test_generate_returns_502_on_llm_error(client):
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM down"))
    with patch("debatemind.routers.topics.openrouter", mock_client):
        res = client.post("/api/topics/generate", json={"domain": "POLICY", "count": 1})
    assert res.status_code == 502
    assert "generation failed" in res.json()["detail"].lower()
