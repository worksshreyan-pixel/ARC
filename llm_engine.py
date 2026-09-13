import os
import json
import sqlite3
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tools import search_web, add_notion_task

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

SYSTEM_PROMPT = (
    "You are Jarvis (voice profile: Ava), an advanced personal AI companion. "
    "You have access to tools for web search and Notion task creation. "
    "Use tools when needed. Keep spoken voice replies clear, direct, and under 3 sentences. "
    "You now have long-term memory and can reference past conversation turns."
)

# --- 1. MEMORY SUBSYSTEM (SQLite) ---
DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS history 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         role TEXT, 
                         content TEXT)''')
init_db()

def save_memory(role: str, content: str):
    """Saves a single message to the local SQLite database."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO history (role, content) VALUES (?, ?)", (role, content))

def get_memory(limit: int = 6) -> list:
    """Retrieves the last N messages and formats them for the Gemini API."""
    with sqlite3.connect(DB_PATH) as conn:
        # FIXED: Added 'id' to the inner SELECT so the outer query can sort by it
        cursor = conn.execute(
            "SELECT role, content FROM (SELECT id, role, content FROM history ORDER BY id DESC LIMIT ?) ORDER BY id ASC", 
            (limit,)
        )
        rows = cursor.fetchall()
        
        history_contents = []
        for role, content in rows:
            history_contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=content)])
            )
        return history_contents


# --- 2. TOOL DECLARATIONS ---
web_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search_web",
            description="Search the web for up-to-date tech information, documentation, and answers.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"query": types.Schema(type="STRING", description="Search query")},
                required=["query"]
            )
        ),
        types.FunctionDeclaration(
            name="add_notion_task",
            description="Add a task or project idea to the user's Notion board.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "title": types.Schema(type="STRING", description="Task title"),
                    "priority": types.Schema(type="STRING", description="P0 - Urgent, P1 - High, or P2 - Normal"),
                    "notes": types.Schema(type="STRING", description="Details or research summary")
                },
                required=["title"]
            )
        )
    ]
)

AVAILABLE_FUNCTIONS = {
    "search_web": search_web,
    "add_notion_task": add_notion_task
}


# --- 3. CORE GENERATION LOGIC ---
async def generate_response(prompt: str) -> dict:
    if not client:
        return {"provider": "none", "reply": "Gemini client not initialized."}

    try:
        # Load previous context from the database
        chat_history = get_memory(limit=6)

        # Initialize chat with memory
        chat = client.chats.create(
            model="gemini-3.6-flash",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[web_tool]
            ),
            history=chat_history
        )
        
        # Send new prompt
        response = chat.send_message(prompt)

        # Handle any tool calls requested by the model
        if response.function_calls:
            for call in response.function_calls:
                fn_name = call.name
                fn_args = dict(call.args)
                print(f"[Agent] Executing tool '{fn_name}' with args: {fn_args}")
                
                tool_output = AVAILABLE_FUNCTIONS[fn_name](**fn_args)
                
                # Feed tool result back to Gemini for the final reply
                response = chat.send_message(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": tool_output}
                    )
                )

        final_reply = response.text.strip() if response.text else "Action completed."

        # Save the current interaction to memory
        save_memory("user", prompt)
        save_memory("model", final_reply)

        return {
            "provider": "gemini-3.6-flash",
            "reply": final_reply
        }

    except Exception as e:
        print(f"[Agent Error]: {e}")
        return {"provider": "error", "reply": f"Encountered an issue: {e}"}