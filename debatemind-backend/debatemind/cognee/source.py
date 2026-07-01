"""Source document operations.

Manages per-session debate source material (PDFs, text) in the cognee
knowledge graph so the opponent can ground its rebuttals in actual evidence.

Operations:
  index_source_document — ingest a document file into the session dataset
  recall_source_context — retrieve relevant chunks for a given query
"""

import asyncio
import logging
import time

import cognee
from cognee.api.v1.search.search import SearchType

from debatemind.cognee._base import (
    ADD_TIMEOUT,
    COGNIFY_TIMEOUT,
    SEARCH_TIMEOUT,
    elapsed_ms,
    preview,
    result_text,
    source_dataset,
)

logger = logging.getLogger(__name__)


async def index_source_document(session_id: str, file_path: str) -> None:
    dataset = source_dataset(session_id)

    logger.info(
        "cognee.add start",
        extra={
            "event": "cognee.add.start",
            "operation": "index_source_document",
            "dataset": dataset,
            "session_id": session_id,
            "file_path": file_path,
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.add(file_path, dataset_name=dataset), timeout=ADD_TIMEOUT)
    logger.info(
        "cognee.add ok",
        extra={
            "event": "cognee.add.ok",
            "operation": "index_source_document",
            "dataset": dataset,
            "session_id": session_id,
            "file_path": file_path,
            "elapsed_ms": elapsed_ms(t0),
        },
    )

    logger.info(
        "cognee.cognify start",
        extra={
            "event": "cognee.cognify.start",
            "operation": "index_source_document",
            "dataset": dataset,
            "session_id": session_id,
            "file_path": file_path,
        },
    )
    t0 = time.monotonic()
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)
    logger.info(
        "cognee.cognify ok",
        extra={
            "event": "cognee.cognify.ok",
            "operation": "index_source_document",
            "dataset": dataset,
            "session_id": session_id,
            "file_path": file_path,
            "elapsed_ms": elapsed_ms(t0),
        },
    )


async def recall_source_context(session_id: str, query_text: str) -> list[dict]:
    dataset = source_dataset(session_id)

    logger.info(
        "cognee.search start",
        extra={
            "event": "cognee.search.start",
            "operation": "recall_source_context",
            "dataset": dataset,
            "session_id": session_id,
            "query_type": "CHUNKS",
            "query": query_text,
            "top_k": 5,
        },
    )
    t0 = time.monotonic()
    try:
        results = await asyncio.wait_for(
            cognee.search(
                query_text=query_text,
                query_type=SearchType.CHUNKS,
                datasets=[dataset],
                top_k=5,
            ),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "cognee.search timeout",
            extra={
                "event": "cognee.search.timeout",
                "operation": "recall_source_context",
                "dataset": dataset,
                "session_id": session_id,
                "timeout_s": SEARCH_TIMEOUT,
                "elapsed_ms": elapsed_ms(t0),
            },
        )
        return []
    except Exception:
        logger.exception(
            "cognee.search error",
            extra={
                "event": "cognee.search.error",
                "operation": "recall_source_context",
                "dataset": dataset,
                "session_id": session_id,
                "query": query_text,
                "elapsed_ms": elapsed_ms(t0),
            },
        )
        return []

    items = [{"text": result_text(r)} for r in results]
    logger.info(
        "cognee.search ok",
        extra={
            "event": "cognee.search.ok",
            "operation": "recall_source_context",
            "dataset": dataset,
            "session_id": session_id,
            "query_type": "CHUNKS",
            "results_count": len(items),
            "results_preview": [preview(it["text"], 120) for it in items[:3]],
            "elapsed_ms": elapsed_ms(t0),
        },
    )
    return items
