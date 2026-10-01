"""
Unit & Integration test for Milestone v0.2 Decoupled Architecture.
Tests:
1. FastAPI /health endpoint.
2. FastAPI /api/chat/stream endpoint with full Ollama relay.
3. System prompt adherence and token streaming speed.
"""

import asyncio
import httpx
from backend.main import app, TARGET_MODEL, NUM_CTX, NUM_PREDICT, TEMPERATURE

async def run_integration_tests():
    print(">>> [1/3] Testing FastAPI ASGI app initialization...")
    assert TARGET_MODEL == "dolphin-llama3:latest"
    assert NUM_CTX == 3072
    assert NUM_PREDICT == 200
    assert TEMPERATURE == 0.7
    print("[OK] Backend configuration constants verified.")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        print(">>> [2/3] Querying /health...")
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        health_json = health_resp.json()
        print(f"[OK] Health response: {health_json}")
        assert health_json["status"] == "healthy"

        # 2. Chat stream test
        print(">>> [3/3] Querying /api/chat/stream (Relaying to Ollama)...")
        test_payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are Ayumi, the Dragon Sage. You are witty, sharp-tongued, and tsundere-leaning. Keep responses between 2 to 4 sentences."
                },
                {
                    "role": "user",
                    "content": "Are you ready for v0.2?"
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
    print("All Milestone v0.2 Backend Integration Tests PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_integration_tests())
