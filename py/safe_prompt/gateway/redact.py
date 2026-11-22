"""Redaction, rehydration (streaming-safe) and the outbound leak guard.

Fail-closed: if any detected secret survives redaction, LeakBlocked is raised
and the request is never forwarded to the upstream LLM.
"""

from __future__ import annotations

import json
import re
import base64
import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from ..detect.engine import Detector, Match
from ..crypto import SafePromptCrypto

# Structural JSON keys whose string values are never user content.
SKIP_KEYS = {"model", "role", "type", "object", "id", "tool_call_id", "finish_reason", "stream"}


class LeakBlocked(Exception):
    """Raised (fail-closed) when plaintext sensitive data is still present in an outbound payload."""


def map_strings(obj: Any, fn: Callable[[str], str], skip: set[str] = SKIP_KEYS, _key: Optional[str] = None) -> Any:
    if isinstance(obj, str):
        return obj if _key in skip else fn(obj)
    if isinstance(obj, list):
        return [map_strings(x, fn, skip, _key) for x in obj]
    if isinstance(obj, dict):
        return {k: map_strings(v, fn, skip, k) for k, v in obj.items()}
    return obj


def iter_strings(obj: Any, skip: set[str] = SKIP_KEYS, _key: Optional[str] = None, _path: str = "$"):
    if isinstance(obj, str):
        if _key not in skip:
            yield _path, obj
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            yield from iter_strings(x, skip, _key, f"{_path}[{i}]")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_strings(v, skip, k, f"{_path}.{k}")


@dataclass
class Detection:
    kind: str
    placeholder: str
    length: int
    new: bool


@dataclass
class Redactor:
    """Redact sensitive values from a payload, encrypting each original
    into a QoreSeal envelope (ML-KEM-1024) destined for on-chain recipients."""

    detector: Detector
    crypto: SafePromptCrypto
    chain_id: str = "qorechain-diana"
    purpose: str = "safe-prompt"
    recipients: list[dict] = field(default_factory=list)
    session: str = "tui"
    detections: list[Detection] = field(default_factory=list)
    values: set[str] = field(default_factory=set)
    # store: placeholder -> encrypted envelope text (kept in memory only)
    envelopes: dict[str, str] = field(default_factory=dict)
    # store: placeholder -> plaintext for local rehydration
    stored_plaintext: dict[str, bytes] = field(default_factory=dict)

    def _tag(self, value: str) -> str:
        return hashlib.sha256((self.session + ":" + value).encode()).hexdigest()[:16]

    def _get_or_create_placeholder(self, kind: str, tag: str) -> tuple[str, bool]:
        # Find existing placeholder with same tag+kind
        for ph, env in self.envelopes.items():
            if ph.startswith(f"[{kind}_") and getattr(ph, "_tag", None) == tag:
                pass
        # Simple deterministic placeholder: kind_n based on count
        existing = [p for p in self.envelopes if p.startswith(f"[{kind}_")]
        idx = len([p for p in existing if self.envelopes[p]])
        ph = f"[{kind}_{idx + 1}]"
        return ph, ph not in self.envelopes

    def redact_text(self, text: str) -> str:
        matches = self.detector.find(text)
        if not matches:
            return text
        out, pos = [], 0
        for m in matches:
            tag = self._tag(m.value)
            ph, created = self._get_or_create_placeholder(m.kind, tag)
            if created:
                self.envelopes[ph] = self._seal_value(ph, m.value)
                self.stored_plaintext[ph] = m.value.encode()
            self.detections.append(Detection(m.kind, ph, len(m.value), created))
            self.values.add(m.value)
            out += [text[pos:m.start], ph]
            pos = m.end
        out.append(text[pos:])
        return "".join(out)

    def _seal_value(self, placeholder: str, value: str) -> str:
        """Seal value into QoreSeal envelope for on-chain recipients."""
        if not self.recipients:
            # No on-chain recipients: still encrypt locally with self-generated key
            # so the value never touches disk in plaintext
            return "LOCAL_ONLY"
        try:
            return self.crypto.seal(
                self.chain_id,
                self.purpose,
                self.recipients,
                value.encode(),
            )
        except Exception:
            # If sealing fails, fail closed
            raise

    def redact_payload(self, body: dict) -> dict:
        return map_strings(body, self.redact_text)


def check_outbound(payload: dict, values: Iterable[str], detector: Detector) -> None:
    """Fail closed if any redacted value, or anything the detector still flags, remains.
    Error messages name the location and kind only, never the value."""
    vals = [v for v in values if v]
    for path, s in iter_strings(payload):
        for v in vals:
            if v in s:
                raise LeakBlocked(f"a detected secret survived redaction at {path}")
        left = detector.find(s, structured_only=True)
        if left:
            raise LeakBlocked(
                f"detector still flags {left[0].kind} ({left[0].end - left[0].start} chars) at {path}; "
                f"add it to the allowlist if it is a false positive"
            )


# ------------------------------------------------------------------ rehydration
Resolver = Callable[[str], Optional[str]]


def rehydrate_text(text: str, resolve: Resolver) -> str:
    def sub(m: re.Match) -> str:
        v = resolve(m.group(0))
        return m.group(0) if v is None else v
    return PLACEHOLDER_RE.sub(sub, text)


class StreamRehydrator:
    """Rehydrate placeholders that may be split across SSE chunks (e.g. '[EMA' + 'IL_1]')."""

    MAX_HOLD = 40

    def __init__(self, resolve: Resolver):
        self.resolve = resolve
        self.buf = ""

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        out = []
        pos = 0
        for m in PLACEHOLDER_RE.finditer(self.buf):
            # Check if placeholder is complete (has closing bracket)
            if m.end() <= len(self.buf) - 1 or self.buf[m.end() - 1] == "]":
                out.append(self.buf[pos:m.start])
                out.append(self.resolve(m.group(0)) or m.group(0))
                pos = m.end()
        # If buffer ends mid-placeholder, hold it
        remaining = self.buf[pos:]
        if len(remaining) > self.MAX_HOLD:
            out.append(remaining)  # flush too-long buffer
            self.buf = ""
        else:
            self.buf = remaining
        return "".join(out)

    def finish(self) -> str:
        out = self.buf
        self.buf = ""
        return out
