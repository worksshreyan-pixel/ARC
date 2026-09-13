import asyncio
import websockets
import json
import os
import subprocess
import edge_tts

# British AI voice profile (Ryan Neural)
VOICE = "en-US-AvaNeural"
WS_URI = "ws://127.0.0.1:8000/ws/feed"
TEMP_AUDIO = os.path.abspath("alert.mp3")

async def play_audio_native(file_path: str):
    """Plays audio using Windows native Media Player without third-party C++ libraries."""
    # Use PowerShell's built-in Windows Media Player COM object
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f'$wmp = New-Object -ComObject WMPlayer.OCX; '
        f'$wmp.URL = "{file_path}"; '
        f'$wmp.controls.play(); '
        f'while ($wmp.playState -ne 1 -and $wmp.playState -ne 0) {{ Start-Sleep -Milliseconds 100 }}'
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await process.communicate()

async def speak(text: str):
    """Synthesizes voice with edge-tts and plays via Windows native audio."""
    try:
        communicate = edge_tts.Communicate(text, VOICE, rate="-4%", pitch="-2Hz")
        await communicate.save(TEMP_AUDIO)
        
        await play_audio_native(TEMP_AUDIO)
        
        if os.path.exists(TEMP_AUDIO):
            os.remove(TEMP_AUDIO)
    except Exception as e:
        print(f"[Voice Error]: {e}")

async def listen_hub():
    print(f"\n[A.R.C. Voice Daemon] Connecting to Core at {WS_URI}...")
    while True:
        try:
            async with websockets.connect(WS_URI) as ws:
                print("[A.R.C. Voice Daemon] Online & Connected. Listening for audio triggers...")
                while True:
                    raw_msg = await ws.recv()
                    data = json.loads(raw_msg)
                    
                    if data.get("event_type") == "TASK_COMPLETED":
                        speak_text = data.get("speak_text", "")
                        print(f"\n[Jarvis Spoke]: {speak_text}\n")
                        await speak(speak_text)
        except Exception as e:
            print(f"[Hub Disconnected] Reconnecting in 3s: {e}")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(listen_hub())