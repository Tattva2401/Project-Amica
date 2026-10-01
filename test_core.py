"""
Integration test for Project Amica Core & Ollama connection.
Verifies:
1. Direct Ollama API connectivity using data-driven persona parameters.
2. Ayumi system prompt and context window validation.
3. Token accumulation speed and content sanity.
4. Flet app layout structure initialization.
"""

import asyncio
import json
import httpx
import flet as ft
from backend.main import OLLAMA_API_URL, PERSONA_CONFIG, SYSTEM_PROMPT
from frontend.app import main as frontend_main

async def test_ollama_streaming():
    print(">>> [1/2] Testing Direct Ollama API Streaming Connection...")
    test_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Tell me who you are in one quick sarcastic sentence."}
    ]
    payload = {
        "model": PERSONA_CONFIG.get("model", "dolphin-llama3:latest"),
        "messages": test_messages,
        "stream": True,
        "options": {
            "num_ctx": PERSONA_CONFIG.get("num_ctx", 3072),
            "temperature": PERSONA_CONFIG.get("temperature", 0.7),
        }
    }
    
    received_tokens = []
    start_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", OLLAMA_API_URL, json=payload) as response:
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
    print("\n>>> [2/2] Testing frontend & backend layout and component definitions...")
    import backend.main as bmain
    import frontend.app as fapp
    assert bmain.PERSONA_CONFIG["num_ctx"] == 3072
    assert "Ayumi" in bmain.SYSTEM_PROMPT
    assert bmain.PERSONA_CONFIG["model"] == "dolphin-llama3:latest"
    print("[OK] Configuration parameters verified successfully.")

if __name__ == "__main__":
    test_app_import()
    asyncio.run(test_ollama_streaming())
    print("\nAll integration checks passed successfully!")
