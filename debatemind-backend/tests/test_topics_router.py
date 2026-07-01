import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from debatemind.routers import topics as topics_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(topics_router.router, prefix="/api/topics")
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
