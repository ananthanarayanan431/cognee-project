"""Verifies Settings exposes the Cognee local/cloud mode switch with safe defaults."""

from debatemind.config import Settings


def test_cognee_mode_defaults_to_local():
    settings = Settings(
        database_url="sqlite+aiosqlite:///./test.db",
        secret_key="test-secret-key-at-least-32-characters!",
        openrouter_api_key="test-key",
    )
    assert settings.cognee_mode == "local"
    assert settings.cognee_db_host == "localhost"
    assert settings.cognee_db_port == "5433"
    assert settings.cognee_db_name == "cognee"
    assert settings.cognee_db_username == "cognee"
    assert settings.cognee_db_password == "cognee"
