# memory_writers.py
from typing import List, Dict, Any
from datetime import date, datetime


def store_professional_context(memory_store,
                               title: str,
                               content: str,
                               date_obj: date = None) -> None:
    """Write a structured 'professional context' note into vector memory.
    
    Args:
        memory_store: The memory store instance to write to
        title: Title for the professional context entry
        content: Formatted content with summary and bullet points
        date_obj: Optional date for the entry (defaults to today if not provided)
        
    Raises:
        ValueError: If a professional context entry already exists for today
        RuntimeError: If the notebook update operation fails
    """
    # Use provided date or default to today
    entry_date = date_obj or date.today()
    
    # Check for existing entry to prevent duplication in the memory_entries collection
    # This ensures we're checking the same collection we'll write to
    if any(entry.get("type") == "professional_context" and 
           datetime.fromisoformat(entry.get("date")).date() == entry_date
           for entry in memory_store.memory_entries):
        raise ValueError(f"Professional context already logged for {entry_date}")
        
    # Create the memory entry in the correct format for the memory store
    entry = {
        "id": f"prof_context_{entry_date.isoformat()}",
        "title": title,
        "content": content,
        "type": "professional_context",
        "date": datetime.combine(entry_date, datetime.min.time()).isoformat(),
        "tags": ["professional_context", "automated"]
    }
    
    # Store the entry in the memory_entries collection
    success = memory_store.add_memory_entry(entry)
    
    # Fail-fast pattern - no silent failures
    if not success:
        raise RuntimeError("Failed to store professional context in memory")


def format_research_payload(research_data: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format research results into a human-readable summary with bullet points.
    
    Args:
        research_data: Dictionary containing 'clients' and 'projects' lists with metadata
        
    Returns:
        Formatted string with summary and bullet points ready for storage
    """
    # Extract client and project counts
    client_count = len(research_data.get('clients', []))
    project_count = len(research_data.get('projects', []))
    
    # Generate the summary header
    summary = f"Snapshot of current professional landscape ({client_count} clients, {project_count} active projects)."
    
    # Format bullet points for clients
    bullet_points = []
    
    # Add client information
    if client_count > 0:
        bullet_points.append("\n\n**Clients:**")
        for client in research_data.get('clients', []):
            status_indicator = "✅" if client.get('status') == 'active' else "⚠️"
            email_count = client.get('emails_count', 0)
            bullet_points.append(f"- {status_indicator} **{client['name']}** – {email_count} recent emails")
    
    # Add project information
    if project_count > 0:
        bullet_points.append("\n\n**Projects:**")
        for project in research_data.get('projects', []):
            deadline = project.get('deadline', 'unknown')
            status = project.get('status', 'in progress')
            bullet_points.append(f"- **{project['name']}** – Status: {status}, Deadline: {deadline}")
    
    # Combine everything into a formatted string
    formatted_content = summary + '\n' + '\n'.join(bullet_points)
    
    return formatted_content
