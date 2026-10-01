"""
===============================================================================
Project Amica - Milestone v0.3: Data-Driven Persona Backend Service
===============================================================================
FastAPI microservice acting as the "Brain" for Project Amica.
Decouples character definitions from the codebase by dynamically loading:
- `personas/<id>/persona.yaml`: Model parameters (temperature, num_ctx, num_predict)
- `personas/<id>/system_prompt.md`: Behavioral persona & conversational guidelines

Responsibilities:
1. Dynamically reads persona configuration and prompt text on startup with robust error fallbacks.
2. Injects system instructions at index 0 for all incoming chat turns.
3. Streams tokens back to the Flet client via StreamingResponse.
===============================================================================
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator, List, Tuple
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx
import yaml

# -----------------------------------------------------------------------------
# Configuration & Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("amica.backend")

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/chat")
BASE_DIR = Path(__file__).resolve().parent.parent
PERSONAS_DIR = BASE_DIR / "personas"
DEFAULT_PERSONA_ID = os.environ.get("AMICA_PERSONA", "ayumi")


# -----------------------------------------------------------------------------
# Data-Driven Persona Loader
# -----------------------------------------------------------------------------
def load_persona(persona_id: str = DEFAULT_PERSONA_ID) -> Tuple[dict, str]:
    """
    Dynamically loads configuration from persona.yaml and system prompt from
    system_prompt.md with comprehensive fallback handling.
    """
    persona_path = PERSONAS_DIR / persona_id
    config_file = persona_path / "persona.yaml"
    prompt_file = persona_path / "system_prompt.md"

    fallback_config = {
        "id": persona_id,
        "name": persona_id.capitalize(),
        "model": "dolphin-llama3:latest",
        "temperature": 0.7,
        "num_ctx": 3072,
        "num_predict": 200,
    }
    fallback_prompt = (
        f"You are {persona_id.capitalize()}, a witty companion. Keep responses concise."
    )

    config = dict(fallback_config)
    prompt = fallback_prompt

    # 1. Parse persona.yaml
    if not config_file.is_file():
        logger.warning("Persona config file not found at %s. Using default fallback configuration.", config_file)
    else:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                parsed_yaml = yaml.safe_load(f)
                if isinstance(parsed_yaml, dict):
                    config.update(parsed_yaml)
                    logger.info("Successfully loaded persona config from %s", config_file)
                else:
                    logger.warning("YAML content in %s was not a mapping. Falling back to defaults.", config_file)
        except Exception as exc:
            logger.error("Error reading or parsing %s: %s. Using fallback configuration.", config_file, exc)

    # 2. Parse system_prompt.md
    if not prompt_file.is_file():
        logger.warning("System prompt file not found at %s. Using default fallback prompt.", prompt_file)
    else:
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    prompt = content
                    logger.info("Successfully loaded system prompt from %s (%d chars)", prompt_file, len(prompt))
                else:
                    logger.warning("System prompt in %s was empty. Using fallback prompt.", prompt_file)
        except Exception as exc:
            logger.error("Error reading %s: %s. Using fallback prompt.", prompt_file, exc)

    return config, prompt


# Load default persona into memory
PERSONA_CONFIG, SYSTEM_PROMPT = load_persona(DEFAULT_PERSONA_ID)


# -----------------------------------------------------------------------------
# Application Setup
# -----------------------------------------------------------------------------
app = FastAPI(
    title=f"Project Amica - Brain Service ({PERSONA_CONFIG.get('name', 'Ayumi')})",
    description="FastAPI LLM relay service for Project Amica desktop client",
    version="0.3.0",
)

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
    messages: List[ChatMessage] = Field(..., min_length=1, description="List of messages from user/assistant")


# -----------------------------------------------------------------------------
# LLM Streaming Generator
# -----------------------------------------------------------------------------
async def stream_ollama_tokens(messages: List[dict]) -> AsyncGenerator[str, None]:
    """
    Connects to the local Ollama daemon at `http://localhost:11434/api/chat`
    and yields individual token text strings as they are generated.
    Parameters are dynamically loaded from PERSONA_CONFIG.
    """
    model = PERSONA_CONFIG.get("model", "dolphin-llama3:latest")
    num_ctx = int(PERSONA_CONFIG.get("num_ctx", 3072))
    num_predict = int(PERSONA_CONFIG.get("num_predict", 200))
    temperature = float(PERSONA_CONFIG.get("temperature", 0.7))

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "temperature": temperature,
        },
    }

    logger.info(
        "Initiating stream to Ollama with %d messages (persona: %s, model: %s, ctx: %d, predict: %d, temp: %s)",
        len(messages),
        PERSONA_CONFIG.get("name"),
        model,
        num_ctx,
        num_predict,
        temperature,
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", OLLAMA_API_URL, json=payload) as response:
                if response.status_code != 200:
                    error_bytes = await response.aread()
                    error_msg = f"[Ollama Error {response.status_code}: {error_bytes.decode(errors='ignore')}]"
                    logger.error("Ollama returned HTTP %d: %s", response.status_code, error_msg)
                    yield error_msg
                    return

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
        "persona_id": PERSONA_CONFIG.get("id"),
        "persona_name": PERSONA_CONFIG.get("name"),
        "model": PERSONA_CONFIG.get("model"),
        "context_window": PERSONA_CONFIG.get("num_ctx"),
    }


@app.get("/api/persona")
async def get_persona_metadata():
    """Returns the current data-driven persona configuration."""
    return {
        "id": PERSONA_CONFIG.get("id"),
        "name": PERSONA_CONFIG.get("name"),
        "model": PERSONA_CONFIG.get("model"),
        "temperature": PERSONA_CONFIG.get("temperature"),
        "num_ctx": PERSONA_CONFIG.get("num_ctx"),
        "num_predict": PERSONA_CONFIG.get("num_predict"),
    }


@app.post("/api/chat/stream")
async def chat_stream(request: ChatStreamRequest):
    """
    Primary chat streaming endpoint.
    Extracts user/assistant messages and injects the loaded persona system prompt
    at index 0 before relaying to Ollama.
    """
    if not request.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message history cannot be empty."
        )

    # Convert Pydantic models to dicts and filter out any client-sent system messages
    user_assistant_messages = [
        msg.model_dump() for msg in request.messages
        if msg.role != "system"
    ]

    # Prepend backend data-driven system prompt
    final_messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ] + user_assistant_messages

    return StreamingResponse(
        stream_ollama_tokens(final_messages),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# -----------------------------------------------------------------------------
# Standalone Execution
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
