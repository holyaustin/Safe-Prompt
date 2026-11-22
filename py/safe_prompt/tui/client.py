"""Gateway client for the TUI — talks to the local FastAPI proxy."""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx


class GatewayError(Exception):
    pass


class GatewayClient:
    """Client for the Safe Prompt FastAPI gateway."""

    def __init__(self, base_url: str = "http://127.0.0.1:8787"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=120.0)
        self.session = "tui"
        self.last_detections: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def health(self) -> dict:
        resp = await self.client.get(f"{self.base_url}/health")
        resp.raise_for_status()
        return resp.json()

    async def models(self) -> dict:
        resp = await self.client.get(f"{self.base_url}/v1/models")
        resp.raise_for_status()
        return resp.json()

    async def get_redacted(self, prompt: str, session: str) -> str:
        """Get the redacted version of a prompt without sending to LLM."""
        resp = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": "safe-prompt-redact",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            headers={"X-Veil-Session": session},
        )
        if resp.status_code == 422:
            # Fail-closed blocked
            raise GatewayError(f"Request blocked (leak detected): {resp.text}")
        resp.raise_for_status()
        data = resp.json()
        # Extract content from choices
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        self.last_detections = getattr(self, "last_detections", [])
        return content

    async def chat(
        self,
        history: list[dict],
        model: str,
        redacted_prompt: str,
    ) -> tuple[str, str]:
        """Send chat completion through gateway. Returns (you_reply, wire_reply)."""
        messages = history + [{"role": "user", "content": redacted_prompt}]

        resp = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": model or "safe-prompt",
                "messages": messages,
                "stream": True,
            },
            headers={"X-Veil-Session": self.session},
            timeout=120.0,
        )
        resp.raise_for_status()

        you_chunks = []
        wire_chunks = []

        async for line in resp.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    you_chunks.append(content)
                    wire_chunks.append(content)  # In real use, wire would differ
            except json.JSONDecodeError:
                pass

        you_reply = "".join(you_chunks)
        wire_reply = "".join(wire_chunks)
        return you_reply, wire_reply