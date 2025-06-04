# -*- coding: utf-8 -*-
"""Index building helpers for :mod:`gmail_chatbot`."""

from __future__ import annotations

import json
import logging
import traceback
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from gmail_chatbot.email_vector_db import EmailVectorDB

logger = logging.getLogger(__name__)


def create_new_index(db: "EmailVectorDB", chunks: List[str], chunk_metadata: List[Dict[str, Any]]) -> None:
    """Create a new FAISS index from provided chunks."""
    try:
        from langchain_community.vectorstores import FAISS
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.error("FAISS import failed: %s", exc)
        db.is_indexed = False
        return

    try:
        db.active_db = FAISS.from_texts(chunks, db.embeddings, metadatas=chunk_metadata)
        db.active_db.save_local(db.cache_dir, index_name=db.index_id)
        db.chunks = chunks
        db.chunk_metadata = chunk_metadata
        chunks_path = db._get_chunks_path()
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump({"chunks": db.chunks, "metadata": db.chunk_metadata}, f, indent=2)
        logger.info("Created new FAISS index with %d chunks", len(chunks))
        db.is_indexed = True
    except Exception as exc:  # pragma: no cover - index creation failure
        logger.error("Error creating FAISS index: %s", exc)
        traceback.print_exc()
        db.is_indexed = False


def store_chunks_without_vectors(db: "EmailVectorDB", chunks: List[str], chunk_metadata: List[Dict[str, Any]]) -> None:
    """Persist chunks for keyword fallback when embeddings are unavailable."""
    try:
        db.chunks = chunks if not db.chunks else db.chunks + chunks
        db.chunk_metadata = (
            chunk_metadata if not db.chunk_metadata else db.chunk_metadata + chunk_metadata
        )
        chunks_path = db._get_chunks_path()
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump({"chunks": db.chunks, "metadata": db.chunk_metadata}, f, indent=2)
        logger.info("Stored %d chunks without vector indexing", len(chunks))
    except Exception as exc:  # pragma: no cover - file system errors
        logger.error("Error storing chunks without vectors: %s", exc)
        traceback.print_exc()
