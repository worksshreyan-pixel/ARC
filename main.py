import os
import subprocess
import platform
from fastapi.responses import HTMLResponse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# SDK Imports
from google import genai
from groq import Groq
from openai import OpenAI
from supabase import create_client, Client

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Project ARC | Ava HUD</title>
        <style>
            body {
                background-color: #0b0f19;
                color: #00ffcc;
                font-family: 'Courier New', Courier, monospace;
                margin: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                height: 100vh;
            }
            header {
                background: #111827;
                padding: 15px;
                text-align: center;
                border-bottom: 2px solid #00ffcc;
                font-size: 1.2rem;
                letter-spacing: 2px;
            }
            #chat-container {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 15px;
            }
            .message {
                max-width: 80%;
                padding: 12px 16px;
                border-radius: 6px;
                line-height: 1.4;
            }
            .user-message {
                background: #1f2937;
                color: #f3f4f6;
                align-self: flex-end;
                border-right: 3px solid #3b82f6;
            }
            .assistant-message {
                background: #111827;
                color: #00ffcc;
                align-self: flex-start;
                border-left: 3px solid #00ffcc;
                box-shadow: 0 0 10px rgba(0, 255, 204, 0.1);
            }
            .meta {
                font-size: 0.75rem;
                color: #9ca3af;
                margin-top: 5px;
            }
            #input-area {
                display: flex;
                padding: 15px;
                background: #111827;
                border-top: 2px solid #00ffcc;
            }
            input {
                flex: 1;
                background: #1f2937;
                border: 1px solid #374151;
                color: #fff;
                padding: 12px;
                border-radius: 4px;
                font-family: inherit;
                font-size: 1rem;
            }
            input:focus {
                outline: none;
                border-color: #00ffcc;
            }
            button {
                background: #00ffcc;
                color: #0b0f19;
                border: none;
                padding: 0 20px;
                margin-left: 10px;
                border-radius: 4px;
                font-weight: bold;
                cursor: pointer;
                font-family: inherit;
            }
            button:hover {
                background: #00b386;
            }
        </style>
    </head>
    <body>
        <header>PROJECT ARC // AVA HUD LINKED</header>
        <div id="chat-container">
            <div class="message assistant-message">
                Greetings. I am Ava, your Project ARC cloud HUD. Systems are online and memory is synced. How may I assist you?
            </div>
        </div>
        <div id="input-area">
            <input type="text" id="prompt-input" placeholder="Enter command or query for Ava..." autofocus>
            <button onclick="sendCommand()">TRANSMIT</button>
        </div>

        <script>
            const chatContainer = document.getElementById('chat-container');
            const promptInput = document.getElementById('prompt-input');

            promptInput.addEventListener('keypress', function (e) {
                if (e.key === 'Enter') sendCommand();
            });

            async function sendCommand() {
                const text = promptInput.value.trim();
                if (!text) return;

                // Append User Message
                appendMessage(text, 'user-message');
                promptInput.value = '';
                chatContainer.scrollTop = chatContainer.scrollHeight;

                try {
                    const response = await fetch('/api/command', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ prompt: text })
                    });
                    
                    const data = await response.json();
                    if (response.ok) {
                        appendMessage(data.reply, 'assistant-message', data.provider);
                    } else {
                        appendMessage("Error: " + (data.detail || "Command failed."), 'assistant-message', 'system');
                    }
                } catch (err) {
                    appendMessage("Network transmission error.", 'assistant-message', 'system');
                }
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }

            function appendMessage(text, className, provider = '') {
                const div = document.createElement('div');
                div.className = `message ${className}`;
                div.innerText = text;
                if (provider) {
                    const meta = document.createElement('div');
                    meta.className = 'meta';
                    meta.innerText = `[Provider: ${provider}]`;
                    div.appendChild(meta);
                }
                chatContainer.appendChild(div);
            }
        </script>
    </body>
    </html>
    """
# Initialize AI Clients
gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY")
)

# --- Supabase Cloud Database Setup ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_cloud_history():
    try:
        response = supabase.table("messages").select("role, content").order("id", desc=False).execute()
        rows = response.data
        if not rows:
            return [{"role": "system", "content": "You are Ava, a helpful, advanced AI HUD assistant for Project ARC with local machine control capabilities."}]
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    except Exception as e:
        print(f"[Supabase Fetch Error]: {e}")
        return [{"role": "system", "content": "You are Ava, a helpful, advanced AI HUD assistant for Project ARC."}]

def save_to_cloud(role: str, content: str):
    try:
        supabase.table("messages").insert({"role": role, "content": content}).execute()
    except Exception as e:
        print(f"[Supabase Insert Error]: {e}")

# --- Local PC Environment Execution Tool ---
def execute_local_command(prompt: str):
    lower_prompt = prompt.lower()
    
    # Example 1: Check system specs / OS info
    if "system info" in lower_prompt or "specs" in lower_prompt:
        info = f"OS: {platform.system()} {platform.release()}, Processor: {platform.processor()}"
        return f"Executed System Info Diagnostic: {info}"
    
    # Example 2: List files in current project directory
    elif "list files" in lower_prompt or "dir" in lower_prompt:
        files = ", ".join(os.listdir())
        return f"Local Directory Contents: {files}"
        
    # Example 3: Open Notepad safely
    elif "open notepad" in lower_prompt:
        subprocess.Popen(["notepad.exe"])
        return "Successfully launched Notepad on your local machine."
        
    return None

class CommandRequest(BaseModel):
    prompt: str

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

manager = ConnectionManager()

@app.websocket("/ws/feed")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/command")
def handle_command(req: CommandRequest):
    last_error = None

    # Save user prompt to Supabase cloud memory
    save_to_cloud("user", req.prompt)

    # Check if the prompt triggers a local system control action
    local_action_result = execute_local_command(req.prompt)
    if local_action_result:
        save_to_cloud("assistant", local_action_result)
        return {"reply": local_action_result, "provider": "local-agent", "model": "system-subprocess"}

    # Load full conversation history from Supabase cloud
    conversation_history = get_cloud_history()

    # Tier 1: Google Gemini Flash
    try:
        gemini_contents = [
            {"role": m["role"] if m["role"] != "system" else "user", "parts": [{"text": m["content"]}]} 
            for m in conversation_history
        ]
        
        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=gemini_contents,
        )
        if response and response.text:
            reply_text = response.text
            save_to_cloud("assistant", reply_text)
            return {"reply": reply_text, "provider": "gemini", "model": "gemini-3.6-flash"}
    except Exception as e:
        last_error = str(e)
        print(f"[Gemini Error]: {last_error}")

    # Tier 2: Groq Fallback
    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=conversation_history,
        )
        reply_text = completion.choices[0].message.content
        if reply_text:
            save_to_cloud("assistant", reply_text)
            return {"reply": reply_text, "provider": "groq", "model": "openai/gpt-oss-20b"}
    except Exception as e:
        last_error = f"Groq Error: {str(e)}"
        print(f"[Groq Error]: {last_error}")

    # Tier 3: OpenRouter Fallback
    try:
        completion = openrouter_client.chat.completions.create(
            model="nvidia/nemotron-3-ultra-550b-a55b:free",
            messages=conversation_history,
        )
        reply_text = completion.choices[0].message.content
        if reply_text:
            save_to_cloud("assistant", reply_text)
            return {"reply": reply_text, "provider": "openrouter", "model": "nvidia/nemotron-3-ultra-550b-a55b:free"}
    except Exception as e:
        last_error = f"OpenRouter Error: {str(e)}"
        print(f"[OpenRouter Error]: {last_error}")

    raise HTTPException(
        status_code=429,
        detail=f"All models and fallback tiers exhausted. Last error: {last_error}"
    )