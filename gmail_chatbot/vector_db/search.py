# -*- coding: utf-8 -*-
"""Search helpers for :mod:`gmail_chatbot`."""

from __future__ import annotations

import json
import logging
import os
import traceback
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from gmail_chatbot.email_vector_db import EmailVectorDB

logger = logging.getLogger(__name__)


def keyword_search(
    db: "EmailVectorDB", query: str, num_results: int = 5, filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Fallback keyword-based search when vector search is unavailable."""
    if not db.chunks:
        chunks_path = db._get_chunks_path()
        if os.path.exists(chunks_path):
            try:
                with open(chunks_path, "r", encoding="utf-8") as f:
                    chunks_data = json.load(f)
                    db.chunks = chunks_data.get("chunks", [])
                    db.chunk_metadata = chunks_data.get("metadata", [])
            except Exception as exc:  # pragma: no cover - corrupted file
                logger.error("Error loading chunks for keyword search: %s", exc)
                return []
        else:
            logger.warning("No chunks found for keyword search")
            return []

    results: List[Dict[str, Any]] = []
    query_terms = query.lower().split()

    for i, chunk in enumerate(db.chunks):
        if filters and i < len(db.chunk_metadata):
            if not db._matches_filters(db.chunk_metadata[i], filters):
                continue
        chunk_lower = chunk.lower()
        score = 0
        for term in query_terms:
            if term in chunk_lower:
                score += 1 + chunk_lower.count(term) * 0.1
        if score > 0:
            metadata = db.chunk_metadata[i] if i < len(db.chunk_metadata) else {}
            results.append(
                {
                    "content": chunk,
                    "metadata": metadata,
                    "similarity": min(1.0, score / len(query_terms)),
                    "search_type": "keyword",
                }
            )

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:num_results]


def search(
    db: "EmailVectorDB", query: str, num_results: int = 5, filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Search the vector database if available, otherwise fall back to keywords."""
    results: List[Dict[str, Any]] = []
    if db.embeddings is not None and db.active_db is not None:
        try:
            logger.info("Performing vector search for query: %s", query)
            vector_results = db.active_db.similarity_search_with_score(query, k=num_results)
            for doc, score in vector_results:
                similarity = 1.0 - min(1.0, score)
                content = doc.page_content
                metadata = doc.metadata
                if filters and not db._matches_filters(metadata, filters):
                    continue
                results.append(
                    {
                        "content": content,
                        "metadata": metadata,
                        "similarity": similarity,
                        "search_type": "vector",
                    }
                )
            if results:
                logger.info("Found %d results via vector search", len(results))
                return results
            logger.info("No vector search results, falling back to keyword search")
        except Exception as exc:  # pragma: no cover - FAISS errors
            logger.error("Error in vector search: %s", exc)
            traceback.print_exc()

    return keyword_search(db, query, num_results, filters)
