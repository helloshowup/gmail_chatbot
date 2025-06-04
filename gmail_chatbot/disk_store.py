#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import time
import random
from pathlib import Path
from typing import Any, TypeVar, Generic

# We'll use portalocker for cross-platform file locking. If it's not available,
# fall back to a very small stub so tests can run without the dependency.
try:  # pragma: no cover - optional dependency
    import portalocker  # type: ignore
except Exception:  # pragma: no cover - simplified fallback for test env
    import threading

    _LOCKS: dict[str, threading.Lock] = {}

    class _DummyLock:
        """Simplistic lock using a shared threading.Lock for tests."""

        def __init__(self, path: str, *_, **__):
            self._lock = _LOCKS.setdefault(path, threading.Lock())

        def acquire(self):
            self._lock.acquire()
            return True

        def release(self):
            try:
                self._lock.release()
            except RuntimeError:
                pass
            return True

    class _DummyPortalocker:
        def Lock(self, path, timeout=None):  # type: ignore[override]
            return _DummyLock(path)

        class exceptions:
            class LockException(Exception):
                pass

    portalocker = _DummyPortalocker()

# Set up logging
logger = logging.getLogger(__name__)

# Type for data stored in DiskStore
T = TypeVar('T')


class DiskStoreError(RuntimeError):
    """Base exception for disk store errors."""
    pass


class MemoryWriteError(DiskStoreError):
    """Exception raised when write operations fail after retries."""
    pass


class DiskStore(Generic[T]):
    """Thread-safe disk storage for JSON serializable data.
    
    Provides atomic read/write operations with file locking to prevent
    data corruption when multiple threads or processes access the same files.
    
    Features:
    - File locking with retry mechanism
    - Exponential backoff for retries
    - Type annotations for better IDE support
    - Custom exceptions for clear error handling
    """
    
    def __init__(self, path: Path, schema_version: int = 1):
        """Initialize a disk store for a specific file.
        
        Args:
            path: Path to the JSON file for storage
            schema_version: Version number for the data schema
        """
        self.path = path
        self.schema_version = schema_version
        self.lock_file = str(path) + '.lock'
        
        # Initialize lock
        self._lock = portalocker.Lock(self.lock_file, timeout=10)
    
    def _acquire_lock(self) -> None:
        """Acquire the file lock with retry mechanism."""
        
        max_retries = 3
        retry_count = 0
        backoff_time = 0.1  # Start with 100ms
        
        while retry_count < max_retries:
            try:
                self._lock.acquire()
                return
            except portalocker.exceptions.LockException as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise MemoryWriteError(f"Failed to acquire lock for {self.path} after {max_retries} retries") from e
                
                # Exponential backoff
                sleep_time = backoff_time * (2 ** (retry_count - 1))
                logger.warning(f"Lock acquisition failed, retrying in {sleep_time:.2f}s (attempt {retry_count}/{max_retries})")
                time.sleep(sleep_time)
    
    def _release_lock(self) -> None:
        """Release the file lock."""
        # portalocker.Lock doesn't have is_locked attribute in newer versions
        # Instead, just try to release and handle any exceptions
        try:
            if self._lock:
                self._lock.release()
        except Exception as e:
            # Log but don't fail - releasing an already released lock is ok
            logger.debug(f"Lock release issue (non-critical): {e}")
    
    def load(self) -> T:
        """Load data from disk with proper locking.
        
        Returns:
            The data structure stored in the file (typically dict or list)
            Empty structure (dict or list) if file doesn't exist
        
        Raises:
            DiskStoreError: If file exists but can't be parsed as JSON
        """
        if not self.path.exists():
            # Determine if we're storing a list or dict based on file suffix
            return [] if self.path.name.startswith(('interaction', 'preferences')) else {}
        
        try:
            self._acquire_lock()
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Add schema version if not present (for backward compatibility)
                if isinstance(data, dict) and 'schema_version' not in data:
                    data['schema_version'] = self.schema_version
                
                return data
        except json.JSONDecodeError as e:
            error_msg = f"Error decoding {self.path}. File may be corrupted."
            logger.error(error_msg)
            raise DiskStoreError(error_msg) from e
        finally:
            self._release_lock()
    
    def save(self, data: T) -> None:
        """Save data to disk with proper locking.
        
        Args:
            data: The data structure to save (must be JSON serializable)
        
        Raises:
            MemoryWriteError: If write operation fails after retries
        """
        max_retries = 3
        retry_count = 0
        backoff_time = 0.1
        
        # Make sure parent directory exists
        self.path.parent.mkdir(exist_ok=True, parents=True)
        
        # Add schema version for dict data (for future compatibility)
        if isinstance(data, dict) and 'schema_version' not in data:
            data['schema_version'] = self.schema_version
            
        while retry_count < max_retries:
            try:
                self._acquire_lock()
                with open(self.path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                return
            except (IOError, OSError) as e:
                retry_count += 1
                if retry_count >= max_retries:
                    error_msg = f"Failed to write to {self.path} after {max_retries} retries"
                    logger.error(error_msg)
                    raise MemoryWriteError(error_msg) from e
                
                # Exponential backoff
                sleep_time = backoff_time * (2 ** (retry_count - 1))
                logger.warning(f"Write failed, retrying in {sleep_time:.2f}s (attempt {retry_count}/{max_retries})")
                time.sleep(sleep_time)
            finally:
                self._release_lock()
    
    def append(self, entry: Any) -> None:
        """Append an entry to a list-based store with atomic operations.
        
        Args:
            entry: New entry to append (must be JSON serializable)
            
        Raises:
            DiskStoreError: If the store doesn't contain a list
            MemoryWriteError: If write operation fails after retries
        """
        max_retries = 10  # Increased retries for append operations
        retry_count = 0
        backoff_time = 0.05  # Shorter initial backoff
        max_backoff = 1.0  # Cap on backoff time
        jitter_factor = 0.25  # Add randomness to avoid thundering herd
        
        # Track success status
        success = False
        latest_error = None
        
        while retry_count < max_retries and not success:
            try:
                # Acquire lock for the entire operation
                self._acquire_lock()
                locked = True
                
                try:
                    # Load latest data with lock held
                    if self.path.exists():
                        with open(self.path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                    else:
                        data = []
                    
                    if not isinstance(data, list):
                        raise DiskStoreError(f"Cannot append to {self.path} - not a list-based store")
                    
                    # Append the entry
                    data.append(entry)
                    
                    # Write back with the lock still held
                    self.path.parent.mkdir(exist_ok=True, parents=True)
                    
                    # Use a temp file for atomic write
                    temp_path = self.path.with_suffix('.tmp')
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                        f.flush()  # Ensure data is written to disk
                        os.fsync(f.fileno())  # Force flush to physical storage
                    
                    # Atomic rename for maximum safety
                    try:
                        # On Windows rename might fail if destination exists
                        if temp_path.exists() and self.path.exists():
                            self.path.unlink()  # Remove destination first
                        os.replace(temp_path, self.path)  # Atomic rename
                    except Exception:
                        # Fallback to non-atomic copy if rename fails
                        with open(self.path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2)
                            f.flush()
                            os.fsync(f.fileno())
                        # Try to clean up temp file
                        try:
                            if temp_path.exists():
                                temp_path.unlink()
                        except:
                            pass  # Ignore cleanup errors
                    
                    success = True
                    return
                finally:
                    # Always release the lock in the inner try block
                    if locked:
                        self._release_lock()
                        locked = False
            except (IOError, OSError, json.JSONDecodeError) as e:
                # Make sure lock is released
                if 'locked' in locals() and locked:
                    self._release_lock()
                
                latest_error = e
                retry_count += 1
                
                if retry_count >= max_retries:
                    error_msg = f"Failed to append to {self.path} after {max_retries} retries: {e}"
                    logger.error(error_msg)
                    # Don't give up - one more fallback attempt with forced sequential access
                    try:
                        # Simple read-modify-write with aggressive locking
                        self._acquire_lock()
                        try:
                            # Load or create
                            data = []
                            if self.path.exists():
                                try:
                                    with open(self.path, 'r', encoding='utf-8') as f:
                                        data = json.load(f)
                                except json.JSONDecodeError:
                                    # File exists but is corrupt, start with empty list
                                    data = []
                            
                            # Validate type
                            if not isinstance(data, list):
                                data = []
                                
                            # Append
                            data.append(entry)
                            
                            # Write with forced sync
                            self.path.parent.mkdir(exist_ok=True, parents=True)
                            with open(self.path, 'w', encoding='utf-8') as f:
                                json.dump(data, f, indent=2)
                                f.flush()
                                os.fsync(f.fileno())
                            
                            logger.info(f"Successfully appended to {self.path} using emergency fallback method")
                            return
                        finally:
                            self._release_lock()
                    except Exception as fallback_error:
                        # Now we really give up
                        raise DiskStoreError(f"All append methods failed for {self.path}: {fallback_error}") from fallback_error
                
                # Exponential backoff with jitter
                sleep_time = min(
                    max_backoff,
                    backoff_time * (2 ** (retry_count - 1)) * (1 + jitter_factor * random.random())
                )
                logger.warning(f"Append failed, retrying in {sleep_time:.2f}s (attempt {retry_count}/{max_retries}): {e}")
                time.sleep(sleep_time)
            except Exception as e:
                # Always release lock
                self._release_lock()
                raise e
    
    def update(self, key: str, value: Any) -> None:
        """Update a value in a dict-based store with atomic operations.
        
        Args:
            key: Dictionary key to update
            value: New value for the key
            
        Raises:
            DiskStoreError: If the store doesn't contain a dict
            MemoryWriteError: If write operation fails after retries
        """
        max_retries = 5  # More retries for update operations
        retry_count = 0
        backoff_time = 0.05  # Shorter initial backoff
        
        while retry_count < max_retries:
            try:
                # Acquire lock for the entire operation
                self._acquire_lock()
                
                # Load latest data with lock held
                if self.path.exists():
                    with open(self.path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                else:
                    data = {}
                
                if not isinstance(data, dict):
                    self._release_lock()
                    raise DiskStoreError(f"Cannot update key in {self.path} - not a dict-based store")
                
                # Update the value
                data[key] = value
                
                # Write back with the lock still held
                self.path.parent.mkdir(exist_ok=True, parents=True)
                with open(self.path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                    
                # Only release lock after successful write
                self._release_lock()
                return
                
            except (IOError, OSError, json.JSONDecodeError) as e:
                # Release lock in case of exception
                self._release_lock()
                
                retry_count += 1
                if retry_count >= max_retries:
                    error_msg = f"Failed to update key '{key}' in {self.path} after {max_retries} retries: {e}"
                    logger.error(error_msg)
                    raise MemoryWriteError(error_msg) from e
                
                # Exponential backoff with jitter
                sleep_time = backoff_time * (2 ** (retry_count - 1)) * (0.5 + 0.5 * random.random())
                logger.warning(f"Update failed, retrying in {sleep_time:.2f}s (attempt {retry_count}/{max_retries})")
                time.sleep(sleep_time)
            except Exception as e:
                # Always release lock
                self._release_lock()
                raise e
