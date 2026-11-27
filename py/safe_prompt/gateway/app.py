"""FastAPI gateway — OpenAI-compatible /v1/chat/completions with PQC redaction."""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import Settings, load_settings
from ..crypto import SafePromptCrypto
from ..detect.engine import Detector
from .redact import (
    LeakBlocked,
    Redactor,
    StreamRehydrator,
    check_outbound,
    rehydrate_text,
)


class ChatMessage(BaseModel):
    role: str
    content: Any  # string or list of content parts
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    stream: Optional[bool] = False
    stream_options: Optional[dict] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    user: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: Optional[dict] = None


# Global state
settings = load_settings()
detector = Detector()
crypto = SafePromptCrypto(use_rust=settings.use_rust_core)
upstream_client: Optional[httpx.AsyncClient] = None
session_store: Dict[str, Redactor] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global upstream_client
    upstream_client = httpx.AsyncClient(timeout=120.0)
    yield
    await upstream_client.aclose()


app = FastAPI(title="Safe Prompt Gateway", lifespan=lifespan)


def get_session_id(x_veil_session: Optional[str] = Header(None)) -> str:
    return x_veil_session or "default"


def get_or_create_redactor(session: str) -> Redactor:
    if session not in session_store:
        # Recipients from env (base64url-encoded ML-KEM public keys)
        recipients = []
        if os.environ.get("SAFE_PROMPT_RECIPIENTS"):
            for r in os.environ["SAFE_PROMPT_RECIPIENTS"].split(","):
                r = r.strip()
                if r:
                    recipients.append({"mlkem_public_key": r})
        session_store[session] = Redactor(
            detector=detector,
            crypto=crypto,
            chain_id=settings.qorechain_network,
            purpose="safe-prompt",
            recipients=recipients,
            session=session,
        )
    return session_store[session]


def resolve_placeholder(ph: str, redactor: Redactor) -> Optional[str]:
    return redactor.stored_plaintext.get(ph, b"").decode() or None


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    req: Request,
    x_veil_session: Optional[str] = Header(None),
):
    session = get_session_id(x_veil_session)
    redactor = get_or_create_redactor(session)

    # Redact the request payload
    try:
        body = request.model_dump(exclude_none=True)
        redacted_body = redactor.redact_payload(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redaction failed: {e}")

    # FAIL-CLOSED: Check outbound payload for any leaks
    try:
        check_outbound(redacted_body, redactor.values, detector)
    except LeakBlocked as e:
        raise HTTPException(status_code=422, detail=str(e))

    requested_model = redacted_body.get("model")

    # Redact-only mode: return the redacted transcript locally, never call
    # upstream. Used by the TUI "Wire" preview and for demos without a key.
    if requested_model == "safe-prompt-redact":
        redacted_text = "\n".join(
            m["content"]
            if isinstance(m.get("content"), str)
            else json.dumps(m.get("content"))
            for m in redacted_body.get("messages", [])
            if m.get("content") is not None
        )
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "safe-prompt-redact",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": redacted_text},
                    "finish_reason": "stop",
                }
            ],
        }

    # Resolve the internal alias ("safe-prompt") to the configured upstream model.
    if not requested_model or requested_model == "safe-prompt":
        redacted_body["model"] = settings.default_model

    # Forward to upstream
    if not upstream_client:
        raise HTTPException(status_code=503, detail="Upstream client not initialized")

    upstream_url = settings.upstream_llm_url or "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.upstream_api_key or 'mock'}",
        "Content-Type": "application/json",
    }
    if settings.upstream_referer:
        headers["HTTP-Referer"] = settings.upstream_referer
    if settings.upstream_title:
        headers["X-Title"] = settings.upstream_title

    if request.stream:
        return StreamingResponse(
            stream_upstream(upstream_url, redacted_body, headers, redactor),
            media_type="text/event-stream",
        )

    try:
        resp = await upstream_client.post(upstream_url, json=redacted_body, headers=headers)
        resp.raise_for_status()
        upstream_resp = resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

    # Rehydrate response
    rehydrated = rehydrate_text(json.dumps(upstream_resp), lambda ph: resolve_placeholder(ph, redactor))
    return Response(content=rehydrated, media_type="application/json")


async def stream_upstream(
    url: str, body: dict, headers: dict, redactor: Redactor
) -> AsyncGenerator[str, None]:
    """Stream from upstream, rehydrating placeholders in SSE chunks."""
    try:
        async with upstream_client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode(errors="replace")
                yield f"data: {json.dumps({'error': {'status': resp.status_code, 'message': detail}})}\n\n"
                yield "data: [DONE]\n\n"
                return
            rehydrator = StreamRehydrator(lambda ph: resolve_placeholder(ph, redactor))
            async for line in resp.aiter_lines():
                if not line:
                    yield "\n"
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        yield f"data: {data}\n\n"
                        break
                    try:
                        chunk = json.loads(data)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            chunk["choices"][0]["delta"]["content"] = rehydrator.feed(content)
                        yield f"data: {json.dumps(chunk)}\n\n"
                    except json.JSONDecodeError:
                        yield f"data: {data}\n\n"
            # Flush any remaining buffered partial placeholder
            final = rehydrator.finish()
            if final:
                yield f"data: {json.dumps({'choices': [{'delta': {'content': final}}]})}\n\n"
            yield "data: [DONE]\n\n"
    except Exception as e:  # network/transport failure mid-stream
        yield f"data: {json.dumps({'error': {'message': str(e)}})}\n\n"
        yield "data: [DONE]\n\n"


@app.get("/v1/models")
async def list_models():
    """Proxy /v1/models to upstream or return local mock."""
    if not settings.upstream_llm_url:
        return {
            "object": "list",
            "data": [
                {"id": "safe-prompt-local", "object": "model", "owned_by": "safe-prompt"},
                {"id": settings.default_model, "object": "model", "owned_by": "qorechain"},
            ],
        }
    if not upstream_client:
        raise HTTPException(status_code=503, detail="Upstream not ready")
    upstream_url = settings.upstream_llm_url.rsplit("/", 1)[0] + "/models"
    try:
        resp = await upstream_client.get(upstream_url, headers={"Authorization": f"Bearer {settings.upstream_api_key}"})
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError:
        return {"object": "list", "data": []}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "crypto_backend": crypto.backend,
        "network": settings.qorechain_network,
    }


def main():
    import uvicorn
    uvicorn.run(
        "safe_prompt.gateway.app:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        reload=False,
    )


if __name__ == "__main__":
    main()