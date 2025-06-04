#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    _ = 1  # Dummy operation to ensure try block has content
except Exception as e:
    # Attempt low-level logging if even basic print fails
    import os
    import traceback

    try:
        with open("email_vector_db_early_error.txt", "a") as f_err:
            f_err.write(f"EARLY STDERR FAIL in email_vector_db.py: {e}\n")
            traceback.print_exc(file=f_err)
    except OSError:
        pass  # If this fails, we're truly blind here.

"""
Email Vector Database for the Gmail Chatbot.

Implements a FAISS-based vector database for email content with efficient chunking,
deduplicated storage, and fallback keyword search capabilities."""

import os
import re
import json
import time
import hashlib
import logging
import warnings
import traceback
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

from gmail_chatbot.vector_db import create_new_index, store_chunks_without_vectors
from gmail_chatbot.vector_db import search as vector_search, keyword_search
# Apply hot-patch for PyTorch before importing it
try:  # pragma: no cover - torch is optional in the test environment
    import torch  # type: ignore

    torch.classes.__path__ = (
        []
    )  # Hot-patch to prevent Streamlit watcher issues
    warnings.filterwarnings(
        "ignore",
        message=r".*Tried to instantiate class '__path__._path'.*",
        category=UserWarning,
        module="torch",
    )

    # Also suppress other common torch warnings
    warnings.filterwarnings(
        "ignore",
        message=r".*Examining the path of torch\.classes raised.*",
        category=UserWarning,
    )

    # Force disable torch warnings completely
    logging.getLogger("pytorch_pretrained_bert").setLevel(logging.ERROR)
    logging.getLogger("pytorch").setLevel(logging.ERROR)
    logging.getLogger("transformers").setLevel(logging.ERROR)

    # Last resort: filter all torch-related warnings
    old_showwarning = warnings.showwarning

    def custom_showwarning(message, *args, **kwargs):
        msg_str = str(message)
        if (
            "torch" in msg_str
            or "Tried to instantiate class" in msg_str
            or "__path__._path" in msg_str
        ):
            return  # Suppress the warning
        old_showwarning(message, *args, **kwargs)  # Show other warnings

    warnings.showwarning = custom_showwarning
except Exception:
    torch = None

# Import environment configuration
from gmail_chatbot.email_config import DATA_DIR

# Provide simple constants for tests that import them
EMBEDDING_MODEL_NAME = "test-embeddings"
DEFAULT_CACHE_DIR = os.path.join(DATA_DIR, "vector_cache")

# Configure logging
logger = logging.getLogger(__name__)
logging.getLogger("faiss.loader").setLevel(logging.WARNING)
logging.getLogger("torch").setLevel(logging.ERROR)
logger.debug("email_vector_db.py loaded")

# Try to import required dependencies
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.warning("langchain not installed. TextSplitter will be limited.")

# Try to import vector libraries with proper fallbacks
try:
    from langchain_community.vectorstores import FAISS

    # Force FAISS to CPU-only mode as per user request / configuration
    GPU_AVAILABLE = False
    logger.info(
        "FAISS GPU acceleration explicitly disabled. Running in CPU-only mode."
    )
    logger.debug(
        "email_vector_db.py - FAISS GPU_AVAILABLE explicitly set to False."
    )

    # Ensure 'langchain-huggingface' is installed in your environment
    from langchain_huggingface import HuggingFaceEmbeddings

    logger.info(
        "Using HuggingFaceEmbeddings from langchain_huggingface package"
    )

    VECTOR_LIBS_AVAILABLE = True
except ModuleNotFoundError as e:  # pragma: no cover - optional dependency
    logger.error("FAISS import failed (%s). Vector search disabled.", e)
    VECTOR_LIBS_AVAILABLE = False
    logger.warning(
        "Required vector search libraries are not installed. Falling back to keyword search."
    )


class SimpleTextSplitter:
    """Fallback text splitter when langchain is not available"""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 50):
        """Initialize with chunk parameters

        Args:
            chunk_size: Target size of each chunk in characters
            chunk_overlap: Overlap between chunks in characters
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        if not text:
            return []

        # Basic splitting on paragraph breaks when possible
        paragraphs = re.split(r"\n\s*\n", text)

        chunks = []
        current_chunk = ""

        for para in paragraphs:
            # If adding this paragraph would exceed chunk size, store current chunk and start new one
            if (
                len(current_chunk) + len(para)
                > self.chunk_size - self.chunk_overlap
                and current_chunk
            ):
                chunks.append(current_chunk.strip())
                # Start new chunk with overlap from the end of previous chunk
                if len(current_chunk) > self.chunk_overlap:
                    current_chunk = (
                        current_chunk[-self.chunk_overlap :] + "\n\n" + para
                    )
                else:
                    current_chunk = para
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        # Add the last chunk if not empty
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks


class EmailVectorDB:
    """Vector database for email storage and retrieval with fallback keyword search"""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 600,
        chunk_overlap: int = 50,
    ):
        """Initialize the vector database with configurable parameters."""
        self.vector_search_available: bool = False
        self.initialization_error_message: Optional[str] = None
        self.embeddings: Optional[HuggingFaceEmbeddings] = (
            None  # Ensure HuggingFaceEmbeddings is imported if not already
        )
        self.embedding_model_name: str = embedding_model

        # Set up cache directory
        if cache_dir is None:
            self.cache_dir = os.path.join(DATA_DIR, "vector_cache")
        else:
            self.cache_dir = cache_dir

        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
                logger.info(
                    f"Created vector cache directory: {self.cache_dir}"
                )
            except Exception as e:
                logger.error(f"Failed to create vector cache directory: {e}")
                raise RuntimeError(
                    f"Cannot create vector cache directory: {e}"
                )

        # Set up the text splitter
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        if LANGCHAIN_AVAILABLE:
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            logger.info("Using langchain RecursiveCharacterTextSplitter")
        else:
            self.text_splitter = SimpleTextSplitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
            logger.info("Using SimpleTextSplitter fallback")

        # Initialize embeddings model if available
        if VECTOR_LIBS_AVAILABLE:
            try:
                logger.info(
                    f"Attempting to initialize embedding model: {self.embedding_model_name}"
                )
                self.embeddings = HuggingFaceEmbeddings(
                    model_name=self.embedding_model_name,
                    cache_folder=os.path.join(self.cache_dir, "models"),
                    # Consider adding model_kwargs={'device': 'cpu'} if GPU issues persist despite FAISS CPU mode
                )
                self.vector_search_available = True
                self.initialization_error_message = None
                logger.info(
                    f"Successfully initialized embedding model: {self.embedding_model_name}"
                )
            except OSError as e_os:
                self.embeddings = None
                self.vector_search_available = False
                error_code_info = (
                    f" (OS Error Code: {e_os.errno})"
                    if hasattr(e_os, "errno")
                    else ""
                )
                self.initialization_error_message = (
                    f"✗ Embedding model ('{self.embedding_model_name}') failed to load due to an OS error (likely out of memory): {str(e_os)}.{error_code_info} "
                    f"Try on a machine with more RAM (e.g., 16GB+) or use a lighter model like 'sentence-transformers/all-MiniLM-L6-v2'."
                )
                logger.error(
                    f"Failed to initialize embedding model '{self.embedding_model_name}' due to OSError: {e_os}",
                    exc_info=True,
                )
            except Exception as e:
                self.embeddings = None
                self.vector_search_available = False
                self.initialization_error_message = f"✗ Embedding model ('{self.embedding_model_name}') failed to load due to an unexpected error: {str(e)}."
                logger.exception(
                    f"Failed to initialize embedding model '{self.embedding_model_name}': {e}"
                )
        else:
            self.embeddings = None
            self.vector_search_available = False
            self.initialization_error_message = "✗ Vector search libraries (FAISS, HuggingFaceEmbeddings) are not available or failed to import. Vector search disabled."
            logger.error(self.initialization_error_message)

        # Active vector DB and chunks
        self.active_db = None
        self.chunks: List[str] = []

        # Metadata for chunks to enable filtering
        self.chunk_metadata: List[Dict[str, Any]] = []

        # Vector DB status
        self.is_indexed = False
        self.index_id = "email_index"

        # Initialize email metadata index
        self.email_metadata: Dict[str, Dict[str, Any]] = {}
        self.load_email_metadata()

    def _get_content_hash(self, content: str) -> str:
        """Generate content hash for deduplication and versioning"""
        return hashlib.md5(content.encode()).hexdigest()

    def _get_index_path(self) -> str:
        """Get path to FAISS index file"""
        return os.path.join(self.cache_dir, f"{self.index_id}.faiss")

    def _get_chunks_path(self) -> str:
        """Get path to chunk data file"""
        return os.path.join(self.cache_dir, f"{self.index_id}.chunks.json")

    def _get_metadata_path(self) -> str:
        """Get path to email metadata file"""
        return os.path.join(self.cache_dir, "email_metadata.json")

    def load_email_metadata(self) -> None:
        """Load email metadata from disk"""
        metadata_path = self._get_metadata_path()
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    self.email_metadata = json.load(f)
                logger.info(
                    f"Loaded metadata for {len(self.email_metadata)} emails"
                )
            except Exception as e:
                logger.error(f"Error loading email metadata: {e}")
                self.email_metadata = {}

    def save_email_metadata(self) -> None:
        """Save email metadata to disk"""
        metadata_path = self._get_metadata_path()
        try:
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(self.email_metadata, f, indent=2)
            logger.info(
                f"Saved metadata for {len(self.email_metadata)} emails"
            )
        except Exception as e:
            logger.error(f"Error saving email metadata: {e}")
            traceback.print_exc()

    def add_email(
        self,
        email_id: str,
        subject: str,
        sender: str,
        recipient: str,
        body: str,
        date: str,
        tags: Optional[List[str]] = None,
        force_reindex: bool = False,
    ) -> bool:
        """Add an email to the vector database

        Args:
            email_id: Unique ID for the email
            subject: Email subject
            sender: Email sender
            recipient: Email recipient
            body: Email body text
            date: Date string
            tags: Optional list of tags/categories
            force_reindex: Whether to force reindexing even if email exists

        Returns:
            bool: True if email was added successfully
        """
        # Calculate content hash for deduplication
        content = f"Subject: {subject}\n\nFrom: {sender}\nTo: {recipient}\nDate: {date}\n\n{body}"
        content_hash = self._get_content_hash(content)

        # Check if email already exists with same hash
        if email_id in self.email_metadata and not force_reindex:
            if (
                self.email_metadata[email_id].get("content_hash")
                == content_hash
            ):
                logger.info(
                    f"Email {email_id} already indexed with same content"
                )
                return True

        # Store email metadata
        self.email_metadata[email_id] = {
            "subject": subject,
            "sender": sender,
            "recipient": recipient,
            "date": date,
            "content_hash": content_hash,
            "tags": tags or [],
            "indexed_at": datetime.now().isoformat(),
            "chunk_count": 0,
        }

        try:
            # Split the content into chunks
            if LANGCHAIN_AVAILABLE:
                chunks = self.text_splitter.split_text(content)
            else:
                chunks = self.text_splitter.split_text(content)

            if not chunks:
                logger.warning(f"No chunks generated for email {email_id}")
                return False

            # Create metadata for each chunk
            chunk_metadata = []
            for i, chunk in enumerate(chunks):
                chunk_metadata.append(
                    {
                        "email_id": email_id,
                        "chunk_index": i,
                        "subject": subject,
                        "sender": sender,
                        "date": date,
                        "tags": tags or [],
                    }
                )

            # Update email metadata with chunk count
            self.email_metadata[email_id]["chunk_count"] = len(chunks)

            # Add to existing index if it exists, otherwise create new one
            if self.active_db is not None:
                # Add new chunks to existing vector DB
                self.active_db.add_texts(chunks, metadatas=chunk_metadata)
                logger.info(
                    f"Added {len(chunks)} chunks for email {email_id} to existing index"
                )
            else:
                # Check if index exists on disk
                index_path = self._get_index_path()
                chunks_path = self._get_chunks_path()

                if os.path.exists(index_path) and os.path.exists(chunks_path):
                    # Load existing index
                    if self.embeddings is not None:
                        try:
                            self.active_db = FAISS.load_local(
                                self.cache_dir,
                                self.embeddings,
                                index_name=self.index_id,
                                allow_dangerous_deserialization=True,
                            )
                            logger.info(
                                f"Loaded existing FAISS index from {index_path}"
                            )

                            # Load existing chunks metadata
                            with open(chunks_path, "r", encoding="utf-8") as f:
                                existing_metadata = json.load(f)
                                self.chunks = existing_metadata.get(
                                    "chunks", []
                                )
                                self.chunk_metadata = existing_metadata.get(
                                    "metadata", []
                                )

                            # Add new chunks to existing vector DB
                            self.active_db.add_texts(
                                chunks, metadatas=chunk_metadata
                            )

                            # Update chunks metadata
                            self.chunks.extend(chunks)
                            self.chunk_metadata.extend(chunk_metadata)

                            # Save updated chunks metadata
                            with open(chunks_path, "w", encoding="utf-8") as f:
                                json.dump(
                                    {
                                        "chunks": self.chunks,
                                        "metadata": self.chunk_metadata,
                                    },
                                    f,
                                    indent=2,
                                )

                            logger.info(
                                f"Added {len(chunks)} chunks to existing index, total chunks: {len(self.chunks)}"
                            )

                        except Exception as e:
                            logger.error(f"Error loading existing index: {e}")
                            traceback.print_exc()

                            # Create new index from scratch
                            self._create_new_index(chunks, chunk_metadata)
                    else:
                        logger.warning(
                            "Embeddings not available, using fallback keyword storage"
                        )
                        # Save just the chunks without vector index
                        self._store_chunks_without_vectors(
                            chunks, chunk_metadata
                        )
                else:
                    # Create new index
                    if self.embeddings is not None:
                        self._create_new_index(chunks, chunk_metadata)
                    else:
                        logger.warning(
                            "Embeddings not available, using fallback keyword storage"
                        )
                        # Save just the chunks without vector index
                        self._store_chunks_without_vectors(
                            chunks, chunk_metadata
                        )

            # Save updated metadata
            self.save_email_metadata()
            return True

        except Exception as e:
            logger.error(f"Error adding email {email_id} to vector DB: {e}")
            traceback.print_exc()
            return False

    def _create_new_index(
        self, chunks: List[str], chunk_metadata: List[Dict[str, Any]]
    ) -> None:
        create_new_index(self, chunks, chunk_metadata)

    def _store_chunks_without_vectors(
        self, chunks: List[str], chunk_metadata: List[Dict[str, Any]]
    ) -> None:
        store_chunks_without_vectors(self, chunks, chunk_metadata)

    def search(
        self,
        query: str,
        num_results: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return vector_search(self, query, num_results, filters)

    def _keyword_search(
        self,
        query: str,
        num_results: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return keyword_search(self, query, num_results, filters)

    def _matches_filters(
        self, metadata: Dict[str, Any], filters: Dict[str, Any]
    ) -> bool:
        """Check if metadata matches the specified filters

        Args:
            metadata: Chunk metadata
            filters: Filter criteria

        Returns:
            bool: True if metadata matches all filters
        """
        for key, value in filters.items():
            if key not in metadata:
                return False

            # Handle different filter types
            if key == "sender" or key == "recipient":
                # Case-insensitive substring match for emails
                if value.lower() not in metadata[key].lower():
                    return False
            elif key == "tags":
                # Check if any of the filter tags match
                if not any(tag in metadata["tags"] for tag in value):
                    return False
            elif key == "date_range":
                # Date range filter (expects [start_date, end_date])
                try:
                    if len(value) == 2:
                        email_date = datetime.fromisoformat(metadata["date"])
                        start_date = datetime.fromisoformat(value[0])
                        end_date = datetime.fromisoformat(value[1])
                        if not (start_date <= email_date <= end_date):
                            return False
                except (ValueError, TypeError):
                    # If date parsing fails, skip this filter
                    pass
            else:
                # Default exact match for other fields
                if metadata[key] != value:
                    return False

        return True

    def get_email_by_id(self, email_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve email metadata by ID

        Args:
            email_id: The email ID to retrieve

        Returns:
            Dict containing email metadata or None if not found
        """
        return self.email_metadata.get(email_id)

    def get_all_email_ids(self) -> List[str]:
        """Get list of all indexed email IDs

        Returns:
            List of email IDs
        """
        return list(self.email_metadata.keys())

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the vector DB

        Returns:
            Dict with status information
        """
        return {
            "vector_search_available": VECTOR_LIBS_AVAILABLE
            and self.embeddings is not None,
            "gpu_acceleration": (
                GPU_AVAILABLE if "GPU_AVAILABLE" in globals() else False
            ),
            "fallback_search_available": len(self.chunks) > 0,
            "embedding_model": (
                self.embedding_model_name if self.embeddings else None
            ),
            "indexed_emails": len(self.email_metadata),
            "total_chunks": len(self.chunks),
            "index_path": self._get_index_path(),
            "cache_dir": self.cache_dir,
        }


# Create a singleton instance for easy import
vector_db = EmailVectorDB()


def test_email_vector_db():
    """Simple test for the email vector DB"""
    # Create test instance with small context size for testing
    test_db = EmailVectorDB(
        cache_dir="./test_vector_cache", chunk_size=200, chunk_overlap=20
    )

    # Test adding an email
    test_email_id = f"test_{int(time.time())}"
    result = test_db.add_email(
        email_id=test_email_id,
        subject="Test Email Subject",
        sender="sender@example.com",
        recipient="recipient@example.com",
        body="""This is a test email body with some specific keywords like vector database testing.
We want to make sure that search functionality works correctly.
This should be indexed and retrievable by semantic or keyword search.""",
        date=datetime.now().isoformat(),
        tags=["test", "email"],
    )

    logger.info("Email added: %s", result)

    # Test search functionality
    search_results = test_db.search("vector database", num_results=2)

    logger.info("Search results: %d", len(search_results))
    for i, result in enumerate(search_results):
        logger.info(
            "Result %d: Content: %s... Similarity: %.4f Search type: %s",
            i + 1,
            result["content"][:100],
            result["similarity"],
            result["search_type"],
        )

    # Test with filters
    filtered_results = test_db.search(
        "test email", filters={"sender": "sender@example.com"}
    )

    logger.info("Filtered results: %d", len(filtered_results))

    # Print status
    status = test_db.get_status()
    logger.info("Vector DB Status:\n%s", json.dumps(status, indent=2))


def reindex_all_emails():
    """Rebuild the FAISS index from scratch using all emails in memory."""
    from gmail_chatbot.email_memory_vector import vector_memory

    logger.info("Starting complete vector reindexing...")

    # Check if vector index file exists and delete it
    index_path = vector_db._get_index_path()
    if os.path.exists(index_path):
        try:
            os.remove(index_path)
            logger.info(f"Deleted existing index file: {index_path}")
        except Exception as e:
            logger.error(f"Error deleting index file: {e}")
            return False

    # Get all email IDs from memory
    email_ids = vector_memory.get_all_email_ids()
    logger.info(f"Found {len(email_ids)} emails to reindex")

    # Reset the vector indexed emails tracking
    vector_memory.vector_indexed_emails = set()

    # Process all emails in batches
    batch_size = 100
    total_processed = 0
    total_indexed = 0

    for i in range(0, len(email_ids), batch_size):
        batch = email_ids[i : i + batch_size]
        logger.info(
            f"Processing batch {i//batch_size + 1} ({len(batch)} emails)"
        )

        result = vector_memory.batch_process_historical_emails(
            limit=len(batch)
        )

        total_processed += result.get("processed", 0)
        total_indexed += result.get("indexed", 0)

        logger.info(
            f"Batch result: {result.get('indexed')} indexed, {result.get('errors')} errors"
        )

    logger.info(
        f"Reindexing complete: {total_indexed}/{total_processed} emails indexed"
    )
    return True


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Email Vector Database")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Rebuild the vector index from scratch",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run a simple test of the vector database",
    )
    args = parser.parse_args()

    # Check vector search availability
    status = vector_db.get_status()
    logger.info(
        f"Vector search available: {status['vector_search_available']}"
    )
    if "gpu_acceleration" in status:
        logger.info(f"GPU acceleration: {status['gpu_acceleration']}")

    if args.reindex:
        reindex_all_emails()
    elif args.test:
        test_email_vector_db()
    else:
        # If no arguments provided, show status and instructions
        logger.info("\nEmail Vector Database Status:")
        for key, value in status.items():
            logger.info("  %s: %s", key, value)
        logger.info(
            "\nTo rebuild the index: python -m gmail_chatbot.email_vector_db --reindex"
        )
        logger.info(
            "To run tests: python -m gmail_chatbot.email_vector_db --test"
        )
