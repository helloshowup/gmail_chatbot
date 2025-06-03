import logging
import sys
import os
import atexit
from pathlib import Path

# Global reference to original handlers so we can restore them if needed
_original_handlers = []
_file_log_path = None

# Create a special null handler that won't fail during shutdown
class NullHandler(logging.Handler):
    def emit(self, record):
        pass  # Do nothing, but safely

class SafeStreamHandler(logging.StreamHandler):
    """A stream handler that catches I/O errors during shutdown."""
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # Handle case where stream is closed or invalid
            if stream and hasattr(stream, 'closed') and not stream.closed:
                stream.write(msg + self.terminator)
                self.flush()
        except Exception:
            pass  # Silently ignore any errors, especially during shutdown

# Safe file handler that won't fail on closed files
class SafeFileHandler(logging.FileHandler):
    """A file handler that catches I/O errors during shutdown."""
    def emit(self, record):
        try:
            if self.stream and not getattr(self.stream, 'closed', True):
                super().emit(record)
        except Exception:
            pass  # Silently ignore any errors

def configure_safe_logging(log_path: Path) -> None:
    """Configure logging with safe handlers that won't cause issues during shutdown."""
    global _original_handlers, _file_log_path
    _file_log_path = log_path
    
    # Store original handlers
    _original_handlers = logging.root.handlers[:]
    
    # Ensure directory exists
    os.makedirs(log_path.parent, exist_ok=True)

    # Remove all existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Build safe handlers
    try:
        file_handler = SafeFileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        stream_handler = SafeStreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)

        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        # Configure root logger
        logging.root.setLevel(logging.DEBUG)
        logging.root.addHandler(file_handler)
        logging.root.addHandler(stream_handler)
    except Exception as e:
        # If logging setup fails, set up a minimal configuration that won't fail
        logging.root.setLevel(logging.WARNING)
        null_handler = NullHandler()
        logging.root.addHandler(null_handler)
        
        # Print error directly to avoid using logging
        try:
            print(f"WARNING: Failed to configure logging: {e}")
        except Exception:
            pass  # If print fails, give up silently

    # Register for shutdown
    atexit.register(shutdown_logging)

def shutdown_logging():
    """Safely shutdown all logging handlers to prevent I/O errors."""
    # Close all handlers to avoid writing to closed streams
    root = logging.getLogger()
    handlers = root.handlers[:] # Make a copy
    for handler in handlers:
        try:
            handler.flush()
        except Exception:
            pass # Ignore flush errors
        try:
            handler.close()
        except Exception:
            pass # Ignore close errors
        try:
            # Attempt to remove the handler from the root logger.
            # This is crucial to prevent further use of potentially closed handlers.
            root.removeHandler(handler)
        except Exception:
            pass # Ignore remove errors (e.g. if already removed or other issue)
    
    # Replace handlers with NullHandler to prevent fallback logs after explicit shutdown
    # This ensures that any subsequent logging calls (e.g. from third-party libs during interpreter teardown)
    # are silently ignored by a benign handler, rather than attempting to use a closed stream or file.
    root.addHandler(logging.NullHandler())
