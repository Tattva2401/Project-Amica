"""
===============================================================================
Project Amica - Milestone v0.2: Decoupled Backend Service
===============================================================================
FastAPI microservice that acts as the "Brain" for Project Amica.
Responsibilities:
1. Receives chat requests from the Flet frontend or external clients.
2. Formats messages and applies M3 hardware-optimized LLM parameters:
   - Target Model: `dolphin-llama3:latest`
   - Context Window: 3072 tokens
   - Predict Tokens: 200 tokens (caps generation for punchy responses)
   - Temperature: 0.7
3. Relays token chunks via StreamingResponse back to the client in real-time.
===============================================================================
"""

import json
import logging
from typing import AsyncGenerator, List
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx

# -----------------------------------------------------------------------------
# Configuration & Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("amica.backend")

OLLAMA_API_URL = "http://localhost:11434/api/chat"
TARGET_MODEL = "dolphin-llama3:latest"
NUM_CTX = 3072       # Context window limit calibrated from M3 benchmark
NUM_PREDICT = 200    # Caps generation length (concise but complete thoughts)
TEMPERATURE = 0.7    # Balanced creativity and coherence

# -----------------------------------------------------------------------------
# Application Setup
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Project Amica - Brain Service",
    description="FastAPI LLM relay service for Project Amica desktop client",
    version="0.2.0",
)

# Enable CORS for local client-server flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------
class ChatMessage(BaseModel):
    """Represents a single message in the conversation history."""
    role: str = Field(..., description="Role of the sender ('system', 'user', 'assistant')")
    content: str = Field(..., description="Message text content")


class ChatStreamRequest(BaseModel):
    """Payload sent by the frontend client to initiate streaming."""
    messages: List[ChatMessage] = Field(..., min_length=1, description="List of prior messages including system prompt")


# -----------------------------------------------------------------------------
# LLM Streaming Generator
# -----------------------------------------------------------------------------
async def stream_ollama_tokens(messages: List[dict]) -> AsyncGenerator[str, None]:
    """
    Connects to the local Ollama daemon at `http://localhost:11434/api/chat`
    and yields individual token text strings as they are generated.
    """
    payload = {
        "model": TARGET_MODEL,
        "messages": messages,
        "stream": True,
        "options": {
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
            "temperature": TEMPERATURE,
        },
    }

    logger.info("Initiating stream to Ollama with %d messages (model: %s)", len(messages), TARGET_MODEL)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", OLLAMA_API_URL, json=payload) as response:
                # Handle non-200 responses from Ollama
                if response.status_code != 200:
                    error_bytes = await response.aread()
                    error_msg = f"[Ollama Error {response.status_code}: {error_bytes.decode(errors='ignore')}]"
                    logger.error("Ollama returned HTTP %d: %s", response.status_code, error_msg)
                    yield error_msg
                    return

                # Parse streaming lines from Ollama's NDJSON response
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue

                    try:
                        chunk_data = json.loads(line)
                        if "error" in chunk_data:
                            error_msg = f"[Ollama Error: {chunk_data['error']}]"
                            logger.error("Ollama streaming error: %s", error_msg)
                            yield error_msg
                            return

                        token = chunk_data.get("message", {}).get("content", "")
                        if token:
                            yield token

                        if chunk_data.get("done", False):
                            logger.info("Ollama stream completed successfully.")
                            break
                    except json.JSONDecodeError:
                        continue

    except asyncio.CancelledError:
        logger.info("Client connection closed before stream finished.")
        raise
    except httpx.ConnectError:
        error_msg = (
            "[Backend Error: Could not connect to local Ollama at http://localhost:11434. "
            "Please make sure the Ollama service is active.]"
        )
        logger.error("Ollama connection failed: %s", error_msg)
        yield error_msg
    except Exception as exc:
        error_msg = f"[Backend Unexpected Error: {str(exc)}]"
        logger.exception("Unexpected exception in stream_ollama_tokens: %s", exc)
        yield error_msg


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Liveness probe used by run.py to confirm the backend is ready."""
    return {
        "status": "healthy",
        "service": "Project Amica Brain",
        "model": TARGET_MODEL,
        "context_window": NUM_CTX,
    }


@app.post("/api/chat/stream")
async def chat_stream(request: ChatStreamRequest):
    """
    Primary chat streaming endpoint.
    Accepts conversation messages, queries the local Ollama instance,
    and returns a raw text chunk stream.
    """
    if not request.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message history cannot be empty."
        )

    # Convert Pydantic objects to dictionary records for Ollama
    raw_messages = [msg.model_dump() for msg in request.messages]

    return StreamingResponse(
        stream_ollama_tokens(raw_messages),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable proxy buffering if any
        },
    )


# -----------------------------------------------------------------------------
# Standalone Execution
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
