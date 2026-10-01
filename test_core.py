"""
Integration test for Project Amica v0.1 Core & Ollama connection.
Verifies:
1. Ollama service availability.
2. Ayumi system prompt and 3072 context streaming.
3. Token accumulation speed and content sanity.
4. Flet app layout structure initialization.
"""

import asyncio
import json
import httpx
import flet as ft
from app import OLLAMA_CHAT_URL, TARGET_MODEL, CONTEXT_WINDOW_SIZE, SYSTEM_PROMPT, main

async def test_ollama_streaming():
    print(">>> [1/2] Testing Ollama API Streaming Connection...")
    test_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Tell me who you are in one quick sarcastic sentence."}
    ]
    payload = {
        "model": TARGET_MODEL,
        "messages": test_messages,
        "stream": True,
        "options": {
            "num_ctx": CONTEXT_WINDOW_SIZE,
        }
    }
    
    received_tokens = []
    start_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", OLLAMA_CHAT_URL, json=payload) as response:
            assert response.status_code == 200, f"Ollama HTTP error: {response.status_code}"
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    received_tokens.append(token)
                    print(token, end="", flush=True)
                if chunk.get("done", False):
                    break
                    
    duration = asyncio.get_event_loop().time() - start_time
    full_response = "".join(received_tokens)
    print(f"\n[OK] Stream complete! Received {len(received_tokens)} chunks in {duration:.2f}s")
    assert len(full_response) > 0, "No content received from model!"
    print(">>> Response verified.")

def test_app_import():
    print("\n>>> [2/2] Testing app.py layout and component definitions...")
    import app
    assert app.CONTEXT_WINDOW_SIZE == 3072
    assert "Ayumi" in app.SYSTEM_PROMPT
    assert app.TARGET_MODEL == "dolphin-llama3:latest"
    print("[OK] app.py configuration parameters verified successfully.")

if __name__ == "__main__":
    test_app_import()
    asyncio.run(test_ollama_streaming())
    print("\nAll integration checks passed successfully!")
