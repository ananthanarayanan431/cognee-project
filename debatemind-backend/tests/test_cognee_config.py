"""
Unit tests for cognee_config.configure_cognee — verifies the local/cloud mode
switch calls the right cognee.config.set_* methods with the right dict keys,
and that Cognee's own LLM calls are routed through OpenRouter (not a direct
Anthropic call) in both modes.
All cognee.config.set_* calls are mocked; nothing touches a real database.
"""

from unittest.mock import MagicMock

from debatemind.config import Settings
from debatemind.services import cognee_config


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="sqlite+aiosqlite:///./test.db",
        secret_key="test-secret-key-at-least-32-characters!",
        openrouter_api_key="or-test-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
        cognee_mode="local",
        cognee_db_host="localhost",
        cognee_db_port="5433",
        cognee_db_name="cognee",
        cognee_db_username="cognee",
        cognee_db_password="cognee",
    )
    base.update(overrides)
    return Settings(**base)


def _patch_cognee_config(monkeypatch):
    mocks = {
        "relational": MagicMock(),
        "vector": MagicMock(),
        "graph": MagicMock(),
        "llm": MagicMock(),
    }
    monkeypatch.setattr(
        cognee_config.cognee.config, "set_relational_db_config", mocks["relational"]
    )
    monkeypatch.setattr(cognee_config.cognee.config, "set_vector_db_config", mocks["vector"])
    monkeypatch.setattr(cognee_config.cognee.config, "set_graph_db_config", mocks["graph"])
    monkeypatch.setattr(cognee_config.cognee.config, "set_llm_config", mocks["llm"])
    return mocks


def test_local_mode_configures_postgres_pgvector_kuzu_and_openrouter_llm(monkeypatch):
    mocks = _patch_cognee_config(monkeypatch)

    cognee_config.configure_cognee(_settings(cognee_mode="local"))

    mocks["relational"].assert_called_once_with(
        {
            "db_provider": "postgres",
            "db_host": "localhost",
            "db_port": "5433",
            "db_name": "cognee",
            "db_username": "cognee",
            "db_password": "cognee",
        }
    )
    mocks["vector"].assert_called_once_with({"vector_db_provider": "pgvector"})
    mocks["graph"].assert_called_once_with({"graph_database_provider": "kuzu"})
    mocks["llm"].assert_called_once_with(
        {
            "llm_provider": "custom",
            "llm_model": "openai/gpt-4.1-mini",
            "llm_endpoint": "https://openrouter.ai/api/v1",
            "llm_api_key": "or-test-key",
        }
    )


def test_local_mode_skips_llm_config_without_an_openrouter_key(monkeypatch):
    mocks = _patch_cognee_config(monkeypatch)

    cognee_config.configure_cognee(_settings(cognee_mode="local", openrouter_api_key=""))

    mocks["llm"].assert_not_called()


def test_cloud_mode_does_not_touch_local_db_config_but_still_configures_llm(monkeypatch):
    mocks = _patch_cognee_config(monkeypatch)

    cognee_config.configure_cognee(_settings(cognee_mode="cloud"))

    mocks["relational"].assert_not_called()
    mocks["vector"].assert_not_called()
    mocks["graph"].assert_not_called()
    mocks["llm"].assert_called_once_with(
        {
            "llm_provider": "custom",
            "llm_model": "openai/gpt-4.1-mini",
            "llm_endpoint": "https://openrouter.ai/api/v1",
            "llm_api_key": "or-test-key",
        }
    )


def test_cloud_mode_skips_llm_config_without_an_openrouter_key(monkeypatch):
    mocks = _patch_cognee_config(monkeypatch)

    cognee_config.configure_cognee(_settings(cognee_mode="cloud", openrouter_api_key=""))

    mocks["llm"].assert_not_called()
