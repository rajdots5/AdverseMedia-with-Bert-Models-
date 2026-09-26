from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    # Input
    target_id: int
    target_name: str
    target_context: str
    region: str
    
    # Processing state
    search_results: List[Dict[str, str]] # Search se aaye URLs store honge
    current_article: Dict[str, str] # Scraper ka text
    analyzed_results: List[Dict[str, Any]] # LLM ka final verdict
    
    # Error handling
    errors: List[str]