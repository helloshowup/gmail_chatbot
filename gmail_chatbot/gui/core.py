#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import io
import traceback
import os
from datetime import datetime, timedelta
import logging
from typing import Callable, List, Dict, Any
import threading
import queue

logger = logging.getLogger(__name__)

def can_initialize_gui() -> bool:
    """Checks if a Tkinter GUI can be initialized.
    Returns True if successful, False otherwise.
    Logs errors and prints messages for diagnostics.
    """
    try:
        # Attempt to import tkinter. This is the first point of failure if not installed.
        import tkinter as tk_local
    except ImportError as e:
        error_msg = (
            f"GUI environment check: Tkinter module import failed: {e}. Ensure Tkinter is installed."
        )
        logger.error(error_msg)
        return False

    try:
        # Attempt to create and destroy a root window.
        # This can fail if there's no display server (e.g., headless environment) or other Tcl errors.
        root = tk_local.Tk()
        root.withdraw()  # Make it invisible, don't show on screen
        root.destroy()   # Cleanly destroy it
        logger.info("GUI environment check: Tkinter initialized successfully.")
        return True
    except tk_local.TclError as e: # Catch specific Tcl errors often related to display
        error_msg = (
            f"GUI environment check: Tkinter TclError: {e}. This often means no display is available or X server is misconfigured."
        )
        logger.error(error_msg)
        return False
    except Exception as e: # Catch any other unexpected errors during Tkinter initialization
        error_msg = (
            f"GUI environment check: Failed to initialize Tkinter due to an unexpected error: {e}"
        )
        logger.error(error_msg)
        return False

# Determine GUI availability by calling the check function.
# This should be done before attempting to import GUI-specific submodules.
GUI_AVAILABLE = can_initialize_gui()

# Conditionally import Tkinter submodules and other GUI libraries only if GUI is available.
if GUI_AVAILABLE:
    import tkinter as tk # Make 'tk' available for the rest of the module if GUI is up
    from tkinter import ttk, scrolledtext, messagebox
    # print("[INFO] GUI components will be initialized.") # Optional: can_initialize_gui already prints success
else:
    # Error messages are printed by can_initialize_gui().
    # Logging is also attempted by can_initialize_gui().
    logger.info(
        "GUI_AVAILABLE is False. GUI components will not be loaded. Application behavior depends on main module."
    )
    tk = None # Define tk as None to prevent NameErrors if parts of the code not guarded by GUI_AVAILABLE try to access tk

from gmail_chatbot.email_config import UI_TITLE, UI_WIDTH, UI_HEIGHT, UI_THEME_COLOR

# Check if vector memory is available - use conditional import
try:
    from ..email_memory_vector import vector_memory
    VECTOR_MEMORY_AVAILABLE = True
except ImportError:
    VECTOR_MEMORY_AVAILABLE = False
    logger.warning("Vector memory module not available, vector search features will be disabled")

# Configure logging
# Configure stdout/stderr for UTF-8 to properly handle emojis in console output
if not os.environ.get("PYTEST_RUNNING"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class EmailChatbotGUI:
    """GUI for Gmail Chatbot Assistant with vector search capabilities.
    Supports both GUI and headless mode depending on environment.
    """
    
    def __init__(self, process_message_callback: Callable[[str], None]) -> None:
        """Initialize the GUI or headless interface.
        
        Args:
            process_message_callback: Callback function to process user messages
        """
        self.process_message_callback = process_message_callback
        self.message_queue = queue.Queue()
        self.is_processing = False
        
        if not GUI_AVAILABLE:
            # Headless mode initialization
            logger.info("Initializing in headless mode (no GUI)")
            print("[HEADLESS MODE] Gmail Chatbot running without GUI")
            print("[HEADLESS MODE] Use the command line interface instead")
            self.headless_mode = True
            return
            
        # GUI mode initialization
        logger.info("Initializing GUI mode")
        self.headless_mode = False
        
        try:
            self.root = tk.Tk()
            self.root.title(UI_TITLE)
            self.root.geometry(f"{UI_WIDTH}x{UI_HEIGHT}")
            self.root.minsize(800, 600)
            
            # Configure style
            self.style = ttk.Style()
            self.style.configure("TFrame", background="#f5f5f5")
            self.style.configure("TButton", background=UI_THEME_COLOR, foreground="white")
            self.style.configure("TLabel", background="#f5f5f5", font=("Segoe UI", 10))
            self.style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
            
            self._create_widgets()
            self._setup_layout()
            
            # Start message processing thread
            self.root.after(100, self._process_message_queue)
            
            logger.info("GUI initialized successfully")
        except Exception as e:
            error_msg = f"Failed to initialize GUI: {str(e)}"
            logger.error(error_msg)
            print(f"[ERROR] {error_msg}")
            traceback.print_exc()
            self.headless_mode = True
            print("[FALLBACK] Switching to headless mode")
    
    def _create_widgets(self) -> None:
        """Create the GUI widgets."""
        # Main frame
        self.main_frame = ttk.Frame(self.root)
        
        # Title and header
        self.header_frame = ttk.Frame(self.main_frame)
        self.title_label = ttk.Label(
            self.header_frame, 
            text=UI_TITLE, 
            style="Title.TLabel"
        )
        
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.main_frame)
        
        # Chat tab
        self.chat_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.chat_tab, text="Chat")
        
        # Vector Search tab (only if available)
        if VECTOR_MEMORY_AVAILABLE:
            self.vector_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.vector_tab, text="Vector Search")
            self._create_vector_widgets()
        
        # Chat display
        self.chat_frame = ttk.Frame(self.chat_tab)
        self.chat_display = scrolledtext.ScrolledText(
            self.chat_frame,
            wrap=tk.WORD,
            width=80,
            height=20,
            font=("Segoe UI", 10),
            bg="white",
            state="disabled"
        )
        
        # Input area
        self.input_frame = ttk.Frame(self.main_frame)
        self.message_input = scrolledtext.ScrolledText(
            self.input_frame,
            wrap=tk.WORD,
            width=80,
            height=4,
            font=("Segoe UI", 10),
            bg="white"
        )
        self.message_input.bind("<Return>", self._on_enter_pressed)
        self.message_input.bind("<Shift-Return>", self._on_shift_enter_pressed)
        
        # Send button
        self.send_button = ttk.Button(
            self.input_frame,
            text="Send",
            command=self._send_message,
            style="TButton"
        )
        
        # Status bar
        self.status_frame = ttk.Frame(self.main_frame)
        self.status_label = ttk.Label(
            self.status_frame,
            text="Ready",
            anchor=tk.W
        )
        
        # Loading indicator
        self.loading_label = ttk.Label(
            self.status_frame,
            text="",
            anchor=tk.E
        )
    
    def _setup_layout(self) -> None:
        """Set up the GUI layout."""
        # Configure main frame
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header layout
        self.header_frame.pack(fill=tk.X, pady=(0, 10))
        self.title_label.pack(side=tk.LEFT)
        
        # Notebook layout
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Chat display layout
        self.chat_frame.pack(fill=tk.BOTH, expand=True)
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Vector tab layout (if available)
        if VECTOR_MEMORY_AVAILABLE:
            self._setup_vector_layout()
        
        # Input area layout
        self.input_frame.pack(fill=tk.X, pady=(0, 10))
        self.message_input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        self.send_button.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Status bar layout
        self.status_frame.pack(fill=tk.X)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.loading_label.pack(side=tk.RIGHT)
    
    def _on_enter_pressed(self, event) -> None:
        """Handle Enter key press (send message).
        
        Args:
            event: Key event
        """
        if not event.state & 0x001:  # Shift key is not pressed
            self._send_message()
            return "break"  # Prevent default behavior (newline)
    
    def _on_shift_enter_pressed(self, event) -> None:
        """Handle Shift+Enter key press (newline).
        
        Args:
            event: Key event
        """
        # Allow default behavior (newline)
        pass
    
    def _send_message(self) -> None:
        """Send the user message."""
        # This method should only be called in GUI mode
        if getattr(self, 'headless_mode', False):
            logger.warning("_send_message called in headless mode - this should not happen")
            return
            
        try:
            message = self.message_input.get("1.0", tk.END).strip()
            if not message:
                return
            
            # Add debug logging
            print(f"[GUI DEBUG] _send_message called with: {message[:50]}...")
            logger.info(f"[GUI DEBUG] _send_message called with: {message[:50]}...")
            
            # Display user message in chat
            self.display_message("You", message)
            
            # Clear input field
            self.message_input.delete("1.0", tk.END)
            
            # Update status
            self.update_status("Processing your request...")
            # REMOVED: self.is_processing = True (moved to _process_message_queue)
            print("[GUI DEBUG] Setting status to 'Processing' but NOT setting is_processing flag yet")
            
            # Add message to processing queue
            self.message_queue.put(message)
            print(f"[GUI DEBUG] Added message to queue, queue size: {self.message_queue.qsize()}")
            
            # Force immediate processing of the message - FIX for queue deadlock
            print("[GUI DEBUG] Forcing immediate queue processing")
            self._process_message_queue() # Force immediate queue processing
        except Exception as e:
            logger.error(f"Error in _send_message: {str(e)}")
            print(f"[GUI ERROR] {str(e)}")
            # Don't crash if GUI components are unavailable
    
    def _safe_log_error(self, message: str) -> None:
        """Log errors safely even during shutdown."""
        try:
            logger.error(message)
        except Exception:
            pass  # Ignore logging errors during shutdown
        
        try:
            if not getattr(self, 'headless_mode', False) and hasattr(self, 'root') and self.root and hasattr(self.root, 'winfo_exists') and self.root.winfo_exists():
                self.display_error(message)
            else:
                print(f"[ERROR] {message}")
        except Exception:
            try:
                print(f"[ERROR] {message} (Failed to display in GUI)")
            except Exception:
                pass  # Last resort - ignore if print fails too
                
    def _process_message_queue(self) -> None:
        """Process messages from the queue."""
        # In headless mode, this method isn't needed for periodic checks
        # Messages are processed directly in the run method's CLI loop
        if getattr(self, 'headless_mode', False):
            return
        
        # Check if root still exists (prevents errors during shutdown)
        if not hasattr(self, 'root') or not self.root or not hasattr(self.root, 'winfo_exists') or not self.root.winfo_exists():
            return  # GUI is closing or already closed
        
        try:
            # Only log when there's an actual state change or message to process
            queue_size = self.message_queue.qsize()
            
            # Process queue only if we're not already processing a message
            if not self.message_queue.empty() and not self.is_processing:
                # Get message from queue
                message = self.message_queue.get()
                print(f"[GUI DEBUG] Processing message from queue - Remaining queue size: {self.message_queue.qsize()}")
                
                # Set processing flag at the right moment - just before starting the thread
                self.is_processing = True
                
                # Process message in a separate thread with name for better debugging
                thread = threading.Thread(
                    target=self._threaded_message_processing,
                    args=(message,),
                    daemon=True,
                    name=f"MessageProcessor-{threading.active_count()}"
                )
                thread.start()
            elif not self.message_queue.empty() and self.is_processing:
                # Only log this once when the queue gets a new item while processing
                if queue_size == 1:
                    print("[GUI DEBUG] New message queued while processing another message")
            # We don't need to constantly log that the queue is empty
            
            # Schedule next check only if GUI is still alive
            if hasattr(self, 'root') and self.root and hasattr(self.root, 'winfo_exists') and self.root.winfo_exists():
                self.root.after(100, self._process_message_queue)
        except Exception as e:
            self._safe_log_error(f"Error in _process_message_queue: {str(e)}")
            # Schedule next check even if there was an error, but check if GUI is still alive
            try:
                if hasattr(self, 'root') and self.root and hasattr(self.root, 'winfo_exists') and self.root.winfo_exists():
                    self.root.after(100, self._process_message_queue)
            except Exception as e2:
                self._safe_log_error(f"Failed to schedule next queue check: {str(e2)}")
                # Critical failure in the message queue processing
    
    def _threaded_message_processing(self, message: str) -> None:
        """Process message in a separate thread.
        
        Args:
            message: User message to process
        """
        try:
            # Add debug logging
            print(f"[GUI DEBUG] _threaded_message_processing started with: {message[:50]}...")
            logger.info(f"[GUI DEBUG] _threaded_message_processing started with: {message[:50]}...")
            
            # Special test case for debugging API logging
            if message.lower().strip() == "log test":
                print("[GUI DEBUG] Detected 'log test' command - forcing API call for testing")
                logger.info("[GUI DEBUG] Detected 'log test' command - forcing API call for testing")
            
            # Call the callback function to process the message
            print("[GUI DEBUG] About to call process_message_callback()")
            response = self.process_message_callback(message)
            print(f"[GUI DEBUG] process_message_callback() returned {len(response) if response else 0} chars")
            
            # Update GUI or print response in headless mode
            if getattr(self, 'headless_mode', False):
                # In headless mode, just print the response
                # (This block should not be reached in normal headless mode as we don't use threads there)
                print(f"\nAssistant: {response}\n")
                logger.info(f"[HEADLESS] Response: {response[:100]}...")
            else:
                # Update GUI in the main thread
                try:
                    self.root.after(0, lambda: self.display_message("Assistant", response))
                    self.root.after(0, lambda: self.update_status("Ready"))
                except Exception as gui_error:
                    # This could happen if GUI becomes unavailable during processing
                    logger.error(f"Error updating GUI after processing: {str(gui_error)}")
                    print(f"[GUI ERROR] {str(gui_error)}")
                    print(f"\nAssistant: {response}\n")  # Fall back to console output
        except Exception as e:
            error_msg = f"Error in message processing thread: {e}"
            print(f"[GUI DEBUG] {error_msg}")
            traceback.print_exc()  # This will print the full stack trace
            logger.error(error_msg)
            
            if getattr(self, 'headless_mode', False):
                print(f"\nError: {str(e)}\n")
            else:
                try:
                    self.root.after(0, lambda: self.display_error(f"Error processing your request: {str(e)}"))
                except Exception:
                    # This could happen if GUI becomes unavailable during processing
                    print(f"Error processing your request: {str(e)}")
        finally:
            self.is_processing = False
            print("[GUI DEBUG] Message processing complete, is_processing set to False")
    
    def display_message(self, sender: str, message: str) -> None:
        """Display a message in the chat or console in headless mode.
        
        Args:
            sender: Message sender ("You" or "Assistant")
            message: Message content
        """
        # In headless mode, just log the message
        if getattr(self, 'headless_mode', False):
            logger.info(f"[{sender}] {message[:100]}...")
            return
            
        try:
            self.chat_display.config(state=tk.NORMAL)
            
            # Add timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.chat_display.insert(tk.END, f"[{timestamp}] ")
            
            # Add sender with appropriate color
            if sender == "You":
                self.chat_display.insert(tk.END, f"{sender}: ", "user")
            else:
                self.chat_display.insert(tk.END, f"{sender}: ", "assistant")
            
            # Add message and newline
            self.chat_display.insert(tk.END, f"{message}\n\n")
            
            # Configure tags
            self.chat_display.tag_configure("user", foreground="#007BFF", font=("Segoe UI", 10, "bold"))
            self.chat_display.tag_configure("assistant", foreground="#28A745", font=("Segoe UI", 10, "bold"))
            
            # Scroll to bottom
            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)
        except Exception as e:
            logger.error(f"Error displaying message in GUI: {str(e)}")
            # Don't crash if GUI components are unavailable
    
    def display_error(self, error_message: str) -> None:
        """Display an error message in the chat or console in headless mode.
        
        Args:
            error_message: Error message
        """
        # In headless mode, just log and print the error
        if getattr(self, 'headless_mode', False):
            logger.error(f"Error: {error_message}")
            print(f"Error: {error_message}")
            return
            
        try:
            self.chat_display.config(state=tk.NORMAL)
            
            # Add timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.chat_display.insert(tk.END, f"[{timestamp}] ")
            
            # Add error message with appropriate color
            self.chat_display.insert(tk.END, "Error: ", "error")
            self.chat_display.insert(tk.END, f"{error_message}\n\n")
            
            # Configure tags
            self.chat_display.tag_configure("error", foreground="#DC3545", font=("Segoe UI", 10, "bold"))
            
            # Scroll to bottom
            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)
            
            # Update status
            self.update_status("Ready")
        except Exception as e:
            logger.error(f"Error displaying error message in GUI: {str(e)}")
            # Don't crash if GUI components are unavailable
    
    def update_status(self, status: str) -> None:
        """Update the status bar or log status in headless mode.
        
        Args:
            status: Status message
        """
        # In headless mode, just log the status change
        if getattr(self, 'headless_mode', False):
            logger.info(f"Status update: {status}")
            return
            
        try:
            self.status_label.config(text=status)
            
            # Show/hide loading indicator
            if status == "Ready":
                self.loading_label.config(text="")
            else:
                self.loading_label.config(text="Processing...")
        except Exception as e:
            logger.error(f"Error updating status in GUI: {str(e)}")
            # Don't crash if GUI components are unavailable
    
    def run(self) -> None:
        """Run the GUI main loop or provide CLI interface in headless mode."""
        if self.headless_mode:
            # Headless mode - provide a simple CLI interface
            print("\n" + "=" * 50)
            print(f"  {UI_TITLE} - HEADLESS MODE")
            print("=" * 50)
            print("Type 'exit' or 'quit' to exit the application.")
            print("=" * 50 + "\n")
            
            try:
                while True:
                    try:
                        # Get user input
                        user_input = input("\n> ")
                        
                        # Check for exit command
                        if user_input.lower() in ["exit", "quit"]:
                            print("Exiting application...")
                            break
                        
                        # Process message
                        if user_input.strip():
                            print("\nProcessing your request...")
                            try:
                                response = self.process_message_callback(user_input)
                                print(f"\nAssistant: {response}\n")
                            except Exception as e:
                                print(f"\nError: {str(e)}\n")
                                logger.error(f"Error processing message in headless mode: {str(e)}")
                                traceback.print_exc()
                    except KeyboardInterrupt:
                        print("\nExiting application...")
                        break
            except Exception as e:
                logger.error(f"Error in headless CLI mode: {str(e)}")
                print(f"Error in headless CLI mode: {str(e)}")
                traceback.print_exc()
                return
        else:
            # GUI mode - start the Tkinter main loop
            self.root.mainloop()

# ... (rest of the code remains the same)
    
    def _create_vector_widgets(self) -> None:
        """Create widgets for the vector search tab."""
        # Vector status frame
        self.vector_status_frame = ttk.LabelFrame(self.vector_tab, text="Vector Database Status")
        
        # Status display
        self.vector_status_text = scrolledtext.ScrolledText(
            self.vector_status_frame,
            wrap=tk.WORD,
            width=80,
            height=8,
            font=("Segoe UI", 10),
            bg="white",
            state="disabled"
        )
        
        # Refresh status button
        self.refresh_status_button = ttk.Button(
            self.vector_status_frame,
            text="Refresh Status",
            command=self._refresh_vector_status
        )
        
        # Vector search frame
        self.vector_search_frame = ttk.LabelFrame(self.vector_tab, text="Semantic Search")
        
        # Search input
        self.search_input_frame = ttk.Frame(self.vector_search_frame)
        self.search_input_label = ttk.Label(self.search_input_frame, text="Search Query:")
        self.search_input = ttk.Entry(self.search_input_frame, width=50)
        
        # Search filters
        self.filter_frame = ttk.Frame(self.vector_search_frame)
        
        # Date range filter
        self.date_filter_frame = ttk.Frame(self.filter_frame)
        self.date_filter_label = ttk.Label(self.date_filter_frame, text="Date Range:")
        self.date_filter_options = ["Any time", "Last 24 hours", "Last week", "Last month", "Last year"]
        self.date_filter_var = tk.StringVar(value=self.date_filter_options[0])
        self.date_filter_dropdown = ttk.Combobox(
            self.date_filter_frame, 
            textvariable=self.date_filter_var,
            values=self.date_filter_options,
            state="readonly",
            width=15
        )
        
        # Sender filter
        self.sender_filter_frame = ttk.Frame(self.filter_frame)
        self.sender_filter_label = ttk.Label(self.sender_filter_frame, text="Sender:")
        self.sender_filter = ttk.Entry(self.sender_filter_frame, width=20)
        
        # Search button
        self.search_button = ttk.Button(
            self.vector_search_frame,
            text="Search",
            command=self._run_vector_search
        )
        
        # Search results
        self.search_results_frame = ttk.LabelFrame(self.vector_search_frame, text="Search Results")
        self.search_results = scrolledtext.ScrolledText(
            self.search_results_frame,
            wrap=tk.WORD,
            width=80,
            height=12,
            font=("Segoe UI", 10),
            bg="white",
            state="disabled"
        )
        
        # Batch processing frame
        self.batch_frame = ttk.LabelFrame(self.vector_tab, text="Batch Index Processing")
        
        # Info label
        self.batch_info_label = ttk.Label(
            self.batch_frame,
            text="Index historical emails to improve vector search results.",
            wraplength=400
        )
        
        # Batch settings
        self.batch_settings_frame = ttk.Frame(self.batch_frame)
        
        # Number of emails to process
        self.batch_count_frame = ttk.Frame(self.batch_settings_frame)
        self.batch_count_label = ttk.Label(self.batch_count_frame, text="Number of emails:")
        self.batch_count_var = tk.StringVar(value="100")
        self.batch_count = ttk.Combobox(
            self.batch_count_frame,
            textvariable=self.batch_count_var,
            values=["10", "50", "100", "500", "1000"],
            width=8
        )
        
        # Start batch button
        self.batch_button = ttk.Button(
            self.batch_frame,
            text="Start Batch Processing",
            command=self._start_batch_processing
        )
        
        # Batch status
        self.batch_status_label = ttk.Label(self.batch_frame, text="Status: Ready")
        self.batch_progress = ttk.Progressbar(self.batch_frame, orient=tk.HORIZONTAL, length=400, mode='determinate')
        
    def _setup_vector_layout(self) -> None:
        """Set up the layout for the vector search tab."""
        # Vector status layout
        self.vector_status_frame.pack(fill=tk.X, expand=False, padx=5, pady=5)
        self.vector_status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.refresh_status_button.pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Vector search layout
        self.vector_search_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Search input layout
        self.search_input_frame.pack(fill=tk.X, padx=5, pady=5)
        self.search_input_label.pack(side=tk.LEFT, padx=(5, 10))
        self.search_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Filters layout
        self.filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Date filter
        self.date_filter_frame.pack(side=tk.LEFT, padx=(5, 15))
        self.date_filter_label.pack(side=tk.LEFT, padx=(0, 5))
        self.date_filter_dropdown.pack(side=tk.LEFT)
        
        # Sender filter
        self.sender_filter_frame.pack(side=tk.LEFT)
        self.sender_filter_label.pack(side=tk.LEFT, padx=(0, 5))
        self.sender_filter.pack(side=tk.LEFT)
        
        # Search button
        self.search_button.pack(anchor=tk.E, padx=5, pady=5)
        
        # Search results layout
        self.search_results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.search_results.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Batch processing layout
        self.batch_frame.pack(fill=tk.X, expand=False, padx=5, pady=5)
        self.batch_info_label.pack(fill=tk.X, padx=5, pady=5)
        
        # Batch settings layout
        self.batch_settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Batch count
        self.batch_count_frame.pack(side=tk.LEFT, padx=5)
        self.batch_count_label.pack(side=tk.LEFT, padx=(0, 5))
        self.batch_count.pack(side=tk.LEFT)
        
        # Batch button
        self.batch_button.pack(padx=5, pady=5)
        
        # Batch status
        self.batch_status_label.pack(fill=tk.X, padx=5, pady=(5, 0))
        self.batch_progress.pack(fill=tk.X, padx=5, pady=5)
        
        # Initial refresh of vector status
        self._refresh_vector_status()
    
    def _refresh_vector_status(self) -> None:
        """Refresh and display vector database status."""
        if not VECTOR_MEMORY_AVAILABLE:
            return
            
        try:
            # Get status from vector memory
            status = vector_memory.get_vector_status()
            
            # Format status information
            status_text = "Vector Database Status:\n"
            for key, value in status.items():
                status_text += f"• {key}: {value}\n"
                
            # Update status display
            self.vector_status_text.config(state=tk.NORMAL)
            self.vector_status_text.delete(1.0, tk.END)
            self.vector_status_text.insert(tk.END, status_text)
            self.vector_status_text.config(state=tk.DISABLED)
        except Exception as e:
            error_message = f"Error refreshing vector status: {str(e)}"
            logger.error(error_message)
            messagebox.showerror("Error", error_message)
    
    def _run_vector_search(self) -> None:
        """Run a vector search with the current query and filters."""
        if not VECTOR_MEMORY_AVAILABLE:
            return
            
        try:
            # Get search parameters
            query = self.search_input.get().strip()
            if not query:
                messagebox.showwarning("Warning", "Please enter a search query")
                return
                
            # Prepare filters
            filters = {}
            
            # Sender filter
            sender = self.sender_filter.get().strip()
            if sender:
                filters['sender'] = sender
                
            # Date filter
            date_filter = self.date_filter_var.get()
            if date_filter != "Any time":
                now = datetime.now()
                if date_filter == "Last 24 hours":
                    date_from = (now - timedelta(days=1)).isoformat()
                elif date_filter == "Last week":
                    date_from = (now - timedelta(weeks=1)).isoformat()
                elif date_filter == "Last month":
                    date_from = (now - timedelta(days=30)).isoformat()
                elif date_filter == "Last year":
                    date_from = (now - timedelta(days=365)).isoformat()
                    
                filters['date_range'] = {
                    'from': date_from,
                    'to': now.isoformat()
                }
                
            # Run search
            results = vector_memory.find_related_emails(query, max_results=10, filters=filters if filters else None)
            
            # Display results
            self._display_search_results(results, query)
        except Exception as e:
            error_message = f"Error performing vector search: {str(e)}"
            logger.error(error_message)
            traceback.print_exc()
            messagebox.showerror("Error", error_message)
    
    def _display_search_results(self, results: List[Dict[str, Any]], query: str) -> None:
        """Display vector search results in the results panel.
        
        Args:
            results: List of search result dictionaries
            query: Original search query
        """
        self.search_results.config(state=tk.NORMAL)
        self.search_results.delete(1.0, tk.END)
        
        if not results:
            self.search_results.insert(tk.END, f"No results found for query: '{query}'\n")
            self.search_results.config(state=tk.DISABLED)
            return
            
        self.search_results.insert(tk.END, f"Found {len(results)} results for: '{query}'\n\n")
        
        for i, result in enumerate(results):
            # Format the result
            self.search_results.insert(tk.END, f"Result {i+1}:\n", "result_header")
            self.search_results.insert(tk.END, "Subject: ", "field")
            self.search_results.insert(tk.END, f"{result['subject']}\n")
            
            self.search_results.insert(tk.END, "From: ", "field")
            self.search_results.insert(tk.END, f"{result['sender']}\n")
            
            self.search_results.insert(tk.END, "Date: ", "field")
            self.search_results.insert(tk.END, f"{result['date']}\n")
            
            self.search_results.insert(tk.END, "Relevance: ", "field")
            self.search_results.insert(tk.END, f"{result.get('relevance_score', 'N/A')} ({result.get('search_type', 'unknown')})\n")
            
            if result.get('summary'):
                self.search_results.insert(tk.END, "Summary: ", "field")
                self.search_results.insert(tk.END, f"{result['summary']}\n")
                
            self.search_results.insert(tk.END, "\n")
            
        # Configure tags
        self.search_results.tag_configure("result_header", foreground="#007BFF", font=("Segoe UI", 10, "bold"))
        self.search_results.tag_configure("field", foreground="#28A745", font=("Segoe UI", 10, "bold"))
        
        self.search_results.config(state=tk.DISABLED)
    
    def _start_batch_processing(self) -> None:
        """Start batch processing of historical emails for vector indexing."""
        if not VECTOR_MEMORY_AVAILABLE:
            return
            
        try:
            # Get batch size
            try:
                batch_size = int(self.batch_count_var.get())
                if batch_size <= 0:
                    raise ValueError("Batch size must be positive")
            except ValueError:
                messagebox.showwarning("Warning", "Please enter a valid number of emails to process")
                return
                
            # Confirm batch processing
            confirm = messagebox.askyesno(
                "Confirm Batch Processing", 
                f"This will process {batch_size} emails for vector indexing. "
                f"Depending on the number of emails, this may take some time. "
                f"Continue?"
            )
            
            if not confirm:
                return
                
            # Update UI
            self.batch_button.config(state=tk.DISABLED)
            self.batch_status_label.config(text="Status: Starting batch processing...")
            self.batch_progress['value'] = 0
            
            # Start batch processing in a separate thread
            thread = threading.Thread(
                target=self._threaded_batch_processing,
                args=(batch_size,),
                daemon=True
            )
            thread.start()
        except Exception as e:
            error_message = f"Error starting batch processing: {str(e)}"
            logger.error(error_message)
            traceback.print_exc()
            messagebox.showerror("Error", error_message)
            
            # Reset UI
            self.batch_button.config(state=tk.NORMAL)
            self.batch_status_label.config(text="Status: Ready")
            self.batch_progress['value'] = 0
    
    def _threaded_batch_processing(self, batch_size: int) -> None:
        """Run batch processing in a separate thread.
        
        Args:
            batch_size: Number of emails to process
        """
        try:
            # This would need to be implemented in the email_memory_vector module
            # For now, we'll simulate processing
            
            # In a real implementation, you would call a method like:
            # vector_memory.batch_process_historical_emails(batch_size, callback=self._update_batch_progress)
            
            # Simulation of batch processing
            total_processed = 0
            
            for i in range(batch_size):
                # Simulate processing time
                import time
                time.sleep(0.1)  # 100ms per email
                
                # Update progress
                total_processed += 1
                progress_pct = (total_processed / batch_size) * 100
                
                # Update UI in the main thread
                self.root.after(0, lambda p=progress_pct, t=total_processed: self._update_batch_progress(p, t, batch_size))
            
            # Final update in the main thread
            self.root.after(0, lambda: self._complete_batch_processing(total_processed))
        except Exception as e:
            error_message = f"Error in batch processing: {str(e)}"
            logger.error(error_message)
            traceback.print_exc()
            
            # Update UI in the main thread
            self.root.after(0, lambda: self._handle_batch_error(error_message))
    
    def _update_batch_progress(self, progress_pct: float, processed: int, total: int) -> None:
        """Update batch processing progress.
        
        Args:
            progress_pct: Percentage of completion (0-100)
            processed: Number of emails processed
            total: Total number of emails to process
        """
        self.batch_progress['value'] = progress_pct
        self.batch_status_label.config(text=f"Status: Processing... {processed}/{total} emails ({progress_pct:.1f}%)")
    
    def _complete_batch_processing(self, total_processed: int) -> None:
        """Complete batch processing and update UI.
        
        Args:
            total_processed: Total number of emails processed
        """
        self.batch_button.config(state=tk.NORMAL)
        self.batch_status_label.config(text=f"Status: Completed processing {total_processed} emails")
        self.batch_progress['value'] = 100
        
        # Refresh vector status to show updated stats
        self._refresh_vector_status()
        
        messagebox.showinfo("Batch Processing Complete", f"Successfully processed {total_processed} emails for vector indexing.")
    
    def _handle_batch_error(self, error_message: str) -> None:
        """Handle batch processing error.
        
        Args:
            error_message: Error message
        """
        logger.error(f"Batch processing error: {error_message}")
        traceback.print_exc()
        
        # Update UI in the main thread
        if not getattr(self, 'headless_mode', False):
            try:
                self.root.after(0, lambda: self.batch_button.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.batch_status_label.config(text=f"Status: Error - {error_message}"))
                self.root.after(0, lambda: self.batch_progress.config(value=0))
                messagebox.showerror("Batch Processing Error", error_message)
            except Exception as e:
                logger.error(f"Error updating batch UI after error: {str(e)}")
                print(f"[ERROR] {error_message}")
    
    def close(self) -> None:
        """Close the GUI or terminate headless mode safely."""
        # Use a try-except block for all logging operations since they might fail during shutdown
        try:
            logger.info("Closing Gmail Chatbot application")
        except Exception:
            pass  # Silently ignore logging errors during shutdown
            
        # Clear any message queue to prevent further processing
        try:
            if hasattr(self, 'message_queue'):
                while not self.message_queue.empty():
                    try:
                        self.message_queue.get_nowait()
                    except Exception:
                        break
        except Exception:
            pass  # Ignore errors clearing queue
            
        # Signal threads to stop (critical for background processes)
        self.is_processing = False
        
        # Handle closing based on mode
        if getattr(self, 'headless_mode', False):
            try:
                print("\nShutting down headless mode...")
            except Exception:
                pass  # Ignore print errors during shutdown
        else:
            # GUI mode cleanup
            try:
                # Then destroy the root window if it exists and is not already destroyed
                if hasattr(self, 'root') and self.root is not None:
                    try:
                        # First quit the mainloop if it's running
                        if hasattr(self.root, 'quit'):
                            try:
                                self.root.quit()
                            except Exception:
                                pass  # Ignore errors in quit()
                                
                        # Then destroy the window
                        if hasattr(self.root, 'destroy'):
                            try:
                                self.root.destroy()
                            except Exception:
                                pass  # Ignore errors in destroy()
                                
                        # Set root to None to prevent further access attempts
                        self.root = None
                    except Exception:
                        pass  # Ignore all errors during root window cleanup
            except Exception:
                pass  # Ignore all errors during GUI mode cleanup
                
        # Additional cleanup for any open resources
        try:
            # Close any open files or resources that might be held
            for attr_name in ['file_dialog', 'text_widget', 'batch_window']:
                if hasattr(self, attr_name) and getattr(self, attr_name) is not None:
                    try:
                        # Attempt to close/destroy if it has such method
                        obj = getattr(self, attr_name)
                        if hasattr(obj, 'close'):
                            obj.close()
                        elif hasattr(obj, 'destroy'):
                            obj.destroy()
                    except Exception:
                        pass  # Ignore any errors in resource cleanup
        except Exception:
            pass  # Ignore all errors in additional cleanup
            
        # Signal complete shutdown
        try:
            print("Gmail Chatbot GUI resources released.")
        except Exception:
            pass  # Ignore print errors
