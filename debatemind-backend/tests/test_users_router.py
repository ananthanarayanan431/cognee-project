"""
Router tests for the knowledge-graph endpoints — GET /me/knowledge-graph and
DELETE /me/facts/{node_id}. user_graph_view/forget_personal_fact are mocked;
no real Cognee calls happen here. Follows the FastAPI TestClient + dependency
override pattern used by tests/test_topics_router.py.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from debatemind.deps import current_user_id
from debatemind.routers import users as users_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api/users")
    app.dependency_overrides[current_user_id] = lambda: "u1"
    return TestClient(app)


def test_get_knowledge_graph_returns_nodes_and_edges(client):
    view = {
        "nodes": [{"id": "a", "label": "mine", "type": "ArgumentRecord", "props": {}}],
        "edges": [],
    }
    with patch.object(users_router, "user_graph_view", new=AsyncMock(return_value=view)):
        res = client.get("/api/users/me/knowledge-graph")

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["nodes"] == view["nodes"]
    assert data["edges"] == []


def test_delete_fact_returns_forgotten_status(client):
    with patch.object(
        users_router,
        "forget_personal_fact",
        new=AsyncMock(return_value={"node_id": "id-a", "status": "forgotten"}),
    ):
        res = client.delete("/api/users/me/facts/id-a")

    assert res.status_code == 200
    assert res.json()["data"] == {"node_id": "id-a", "status": "forgotten"}


def test_delete_fact_returns_404_when_not_found(client):
    with patch.object(
        users_router,
        "forget_personal_fact",
        new=AsyncMock(return_value={"node_id": "id-a", "status": "not_found"}),
    ):
        res = client.delete("/api/users/me/facts/id-a")

    assert res.status_code == 404
