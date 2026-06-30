import cognee

from debatemind.config import Settings

LLM_MODEL = "claude-haiku-4-5-20251001"


def configure_cognee(settings: Settings) -> None:
    if settings.cognee_mode == "local":
        cognee.config.set_relational_db_config(
            {
                "db_provider": "postgres",
                "db_host": settings.cognee_db_host,
                "db_port": settings.cognee_db_port,
                "db_name": settings.cognee_db_name,
                "db_username": settings.cognee_db_username,
                "db_password": settings.cognee_db_password,
            }
        )
        cognee.config.set_vector_db_config({"vector_db_provider": "pgvector"})
        cognee.config.set_graph_db_config({"graph_database_provider": "kuzu"})
        if settings.cognee_llm_api_key:
            cognee.config.set_llm_config(
                {
                    "provider": "anthropic",
                    "model": LLM_MODEL,
                    "api_key": settings.cognee_llm_api_key,
                }
            )
    elif settings.cognee_mode == "cloud":
        if settings.cognee_api_key and settings.cognee_llm_api_key:
            cognee.config.set_llm_config(
                {
                    "provider": "anthropic",
                    "model": LLM_MODEL,
                    "api_key": settings.cognee_llm_api_key,
                }
            )
