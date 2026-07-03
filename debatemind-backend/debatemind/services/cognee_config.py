import logging

import cognee
from cognee.infrastructure.databases.vector.embeddings.config import get_embedding_config

from debatemind.config import Settings

logger = logging.getLogger(__name__)

# Routed through OpenRouter via cognee's "custom" provider (a generic
# OpenAI-compatible adapter) so Cognee's internal LLM calls share the same
# gateway/key as the debate agents instead of calling Anthropic directly.
LLM_MODEL = "openai/gpt-4.1-mini"
# Bare model name (no provider prefix): this goes straight to api.openai.com
# via OPENAI_BASE_URL below, not through OpenRouter's "vendor/model" scheme.
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072
# Embeddings MUST hit OpenAI directly, not OpenRouter: OpenRouter is a
# chat-completions gateway and does not expose an /embeddings endpoint, so
# routing text-embedding-3-large through it 404s and silently disables the
# entire memory layer (cognify fails in the background, recall returns []).
OPENAI_BASE_URL = "https://api.openai.com/v1"


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
        cognee.config.set_graph_db_config(
            {
                "graph_database_provider": "neo4j",
                "graph_database_url": settings.neo4j_url,
                "graph_database_username": settings.neo4j_username,
                "graph_database_password": settings.neo4j_password,
            }
        )
    elif settings.cognee_mode != "cloud":
        raise ValueError(
            f"Unknown COGNEE_MODE={settings.cognee_mode!r}. Expected 'local' or 'cloud'."
        )

    if settings.openrouter_api_key:
        # Chat/completions go through OpenRouter (works — it's a completions
        # gateway) so Cognee's internal LLM calls share the debate agents' key.
        cognee.config.set_llm_config(
            {
                "llm_provider": "custom",
                "llm_model": LLM_MODEL,
                "llm_endpoint": settings.openrouter_base_url,
                "llm_api_key": settings.openrouter_api_key,
            }
        )

    # Embeddings are configured independently of the LLM: they must reach
    # api.openai.com, never OpenRouter (see OPENAI_BASE_URL note above). Cognee
    # has no public set_embedding_config(), so we mutate the singleton directly.
    if settings.openai_api_key:
        embedding_config = get_embedding_config()
        object.__setattr__(embedding_config, "embedding_provider", "openai")
        object.__setattr__(embedding_config, "embedding_model", EMBEDDING_MODEL)
        object.__setattr__(embedding_config, "embedding_dimensions", EMBEDDING_DIMENSIONS)
        object.__setattr__(embedding_config, "embedding_endpoint", OPENAI_BASE_URL)
        object.__setattr__(embedding_config, "embedding_api_key", settings.openai_api_key)
    else:
        logger.warning(
            "cognee.embeddings.unconfigured: OPENAI_API_KEY is not set. Embeddings "
            "cannot run through OpenRouter (no /embeddings endpoint), so the Cognee "
            "memory layer (cognify + recall) will be non-functional until a key is set."
        )
