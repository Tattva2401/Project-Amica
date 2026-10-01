"""
Unit & Integration test for Milestone v0.3 Data-Driven Persona Architecture.
Tests:
1. Dynamic loading of persona.yaml and system_prompt.md.
2. FastAPI /health and /api/persona endpoints.
3. FastAPI /api/chat/stream endpoint with backend system prompt injection and Ollama streaming.
"""

import asyncio
import httpx
from backend.main import app, PERSONA_CONFIG, SYSTEM_PROMPT

async def run_integration_tests():
    print(">>> [1/4] Verifying Dynamic Persona Configuration...")
    assert PERSONA_CONFIG["id"] == "ayumi"
    assert PERSONA_CONFIG["name"] == "Ayumi"
    assert PERSONA_CONFIG["model"] == "dolphin-llama3:latest"
    assert PERSONA_CONFIG["num_ctx"] == 3072
    assert PERSONA_CONFIG["num_predict"] == 200
    assert PERSONA_CONFIG["temperature"] == 0.7
    assert "Ayumi" in SYSTEM_PROMPT
    assert "Dragon Sage" in SYSTEM_PROMPT
    print("[OK] persona.yaml and system_prompt.md parsed and verified.")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        print(">>> [2/4] Querying /health...")
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        health_json = health_resp.json()
        print(f"[OK] Health response: {health_json}")
        assert health_json["status"] == "healthy"
        assert health_json["persona_name"] == "Ayumi"

        # 2. Persona endpoint
        print(">>> [3/4] Querying /api/persona...")
        persona_resp = await client.get("/api/persona")
        assert persona_resp.status_code == 200
        persona_json = persona_resp.json()
        print(f"[OK] Persona response: {persona_json}")
        assert persona_json["id"] == "ayumi"
        assert persona_json["name"] == "Ayumi"

        # 3. Chat stream test (Client sends pure user turn; backend injects system prompt)
        print(">>> [4/4] Querying /api/chat/stream (Relaying to Ollama with injected persona)...")
        test_payload = {
            "messages": [
                {
                    "role": "user",
                    "content": "Tell me who you are in one quick sentence."
                }
            ]
        }

        tokens_received = []
        async with client.stream("POST", "/api/chat/stream", json=test_payload, timeout=60.0) as stream_resp:
            assert stream_resp.status_code == 200, f"Error: {stream_resp.status_code}"
            print(">>> Stream connected! Reading tokens:")
            async for chunk in stream_resp.aiter_text():
                if chunk:
                    tokens_received.append(chunk)
                    print(chunk, end="", flush=True)

        full_reply = "".join(tokens_received)
        print(f"\n[OK] Received {len(tokens_received)} chunks ({len(full_reply)} chars).")
        assert len(full_reply) > 0, "No response tokens received!"

    print("\n" + "=" * 60)
    print("All Milestone v0.3 Backend Integration Tests PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_integration_tests())
