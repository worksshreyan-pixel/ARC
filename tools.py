import os
from dotenv import load_dotenv
from ddgs import DDGS
from notion_client import Client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

NOTION_KEY = os.getenv("NOTION_API_KEY")
NOTION_DB_ID = os.getenv("NOTION_DATABASE_ID")

notion = Client(auth=NOTION_KEY) if NOTION_KEY and not NOTION_KEY.startswith("your_") else None

def search_web(query: str, max_results: int = 3) -> str:
    """Searches DuckDuckGo without API keys or token limits."""
    try:
        print(f"[Tool] Searching DuckDuckGo: {query}")
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "No web results found."
        
        formatted = []
        for r in results:
            formatted.append(f"• Title: {r.get('title')}\n  Snippet: {r.get('body')}\n  Link: {r.get('href')}")
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Web search error: {e}"

def add_notion_task(title: str, priority: str = "P1 - High", notes: str = "") -> str:
    """Creates a new task in your Notion Database."""
    if not notion or not NOTION_DB_ID:
        return "Notion integration is not configured in .env."
    
    try:
        print(f"[Tool] Adding task to Notion: {title} ({priority})")
        children = []
        if notes:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": notes[:1900]}}]
                }
            })
            
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Name": {
                    "title": [{"type": "text", "text": {"content": title}}]
                },
                "Priority": {
                    "select": {"name": priority}
                }
            },
            children=children
        )
        return f"Successfully added task '{title}' to Notion."
    except Exception as e:
        return f"Notion insertion error: {e}"