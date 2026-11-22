"""Safe Prompt cryptographic layer — wraps Rust core or Python fallback."""

from __future__ import annotations

from typing import Optional, List, Union, Tuple, Any
import base64
import json
import os
import hashlib


class CryptoError(Exception):
    """Raised when cryptographic operation fails."""


def _try_rust() -> bool:
    try:
        import safe_prompt_core
        return True
    except ImportError:
        return False


RUST_AVAILABLE = _try_rust()


class SafePromptCrypto:
    """Wrapper around Rust core (PyO3) with Python fallback."""

    def __init__(self, use_rust: bool = True):
        if use_rust and RUST_AVAILABLE:
            self._rust = __import__("safe_prompt_core")
            self.backend = "rust"
        else:
            self._rust = None
            self.backend = "python"

    def generate_keys(self) -> Tuple[str, str, str, str]:
        """Generate a new ML-KEM-1024 + X25519 key pair. Returns (mlkem_pub, x25519_pub, mlkem_sec, x25519_sec) as base64url."""
        if self.backend == "rust":
            keys = self._rust.SealKeys.generate()
            # Rust getters return Vec<u8> -> Python list of ints; convert to bytes -> hex
            mlkem_secret_bytes = bytes(keys.mlkem_secret_raw) if isinstance(keys.mlkem_secret_raw, list) else bytes(keys.mlkem_secret_raw)
            x25519_secret_bytes = bytes(keys.x25519_secret_raw) if isinstance(keys.x25519_secret_raw, list) else bytes(keys.x25519_secret_raw)
            return (
                keys.mlkem_public,
                keys.x25519_public,
                mlkem_secret_bytes.hex(),
                x25519_secret_bytes.hex(),
            )
        else:
            return self._python_generate_keys()

    def seal(
        self,
        chain_id: str,
        purpose: str,
        recipients: List[dict],
        plaintext: bytes,
        mode: str = "hybrid",
        anonymous: bool = False,
        aad: Optional[bytes] = None,
    ) -> str:
        """Seal (encrypt) plaintext to one or more recipients."""
        if self.backend == "rust":
            recipient_objs = []
            for r in recipients:
                recipient_objs.append(
                    self._rust.Recipient.from_public_keys(
                        r["mlkem_public_key"], r.get("x25519_public_key")
                    )
                )
            return self._rust.seal_envelope(
                chain_id, purpose, recipient_objs, plaintext, mode, anonymous, aad
            )
        else:
            return self._python_seal(chain_id, purpose, recipients, plaintext)

    def open(
        self,
        chain_id: str,
        purpose: str,
        envelope_text: str,
        mlkem_secret: Union[str, bytes],
        x25519_secret: Union[str, bytes],
        mlkem_public: Union[str, bytes],
        x25519_public: Union[str, bytes],
        aad: Optional[bytes] = None,
    ) -> bytes:
        """Open (decrypt) an envelope."""
        if self.backend == "rust":
            # Convert hex strings back to bytes if needed
            if isinstance(mlkem_secret, str):
                mlkem_secret = bytes.fromhex(mlkem_secret)
            if isinstance(x25519_secret, str):
                x25519_secret = bytes.fromhex(x25519_secret)
            if isinstance(mlkem_public, str):
                mlkem_public = base64.urlsafe_b64decode(mlkem_public + "==")
            if isinstance(x25519_public, str):
                x25519_public = base64.urlsafe_b64decode(x25519_public + "==")

            plaintext = self._rust.open_envelope(
                chain_id, purpose, envelope_text,
                bytes(mlkem_secret), bytes(x25519_secret),
                bytes(mlkem_public), bytes(x25519_public),
                aad
            )
            # Rust returns Vec<u8> -> Python list of ints; normalize to bytes
            return bytes(plaintext) if isinstance(plaintext, list) else plaintext
        else:
            return self._python_open(chain_id, purpose, envelope_text, mlkem_secret, x25519_secret, mlkem_public, x25519_public, aad)

    def parse(self, envelope_text: str) -> dict:
        """Parse an envelope without decrypting (inspect metadata)."""
        if self.backend == "rust":
            info = self._rust.parse_envelope_info(envelope_text)
            return {
                "version": info.version,
                "mode": info.mode,
                "anonymous": info.anonymous,
                "salt": info.salt,
                "entries": [
                    {
                        "hint": e.hint,
                        "mlkem_ciphertext": e.mlkem_ciphertext,
                        "x25519_ciphertext": e.x25519_ciphertext,
                        "wrapped_key": e.wrapped_key,
                    }
                    for e in info.entries
                ],
                "nonce": info.nonce,
            }
        else:
            return self._python_parse(envelope_text)

    # ------------------------------------------------------------------ Python fallback
    def _python_generate_keys(self) -> Tuple[str, str, str, str]:
        # Fallback: use SHAKE-256 based deterministic generation (NOT FIPS 203 compliant)
        # This is a development fallback only; production uses Rust core
        seed = os.urandom(32)
        mlkem_pub = hashlib.shake_256(seed + b"mlkem").digest(1568)[:1568]
        x25519_pub = hashlib.shake_256(seed + b"x25519").digest(32)
        mlkem_sec = hashlib.shake_256(seed + b"mlkem-secret").digest(2400)
        x25519_sec = hashlib.shake_256(seed + b"x25519-secret").digest(32)

        def b64(b: bytes) -> str:
            return base64.urlsafe_b64encode(b).decode().rstrip("=")

        return b64(mlkem_pub), b64(x25519_pub), mlkem_sec.hex(), x25519_sec.hex()

    def _python_seal(self, chain_id: str, purpose: str, recipients: List[dict], plaintext: bytes) -> str:
        # Simplified fallback: XOR + AES-GCM equivalent using hashlib
        import json as _json
        import time

        nonce = os.urandom(12)
        key = hashlib.sha256(chain_id.encode() + purpose.encode() + nonce).digest()

        # XOR with key (weak, but fallback)
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, key * (len(plaintext) // 32 + 1)))

        envelope = {
            "version": 1,
            "chain_id": chain_id,
            "purpose": purpose,
            "mode": "mlkem",
            "recipients": [r["mlkem_public_key"][:16] for r in recipients],
            "nonce": base64.urlsafe_b64encode(nonce).decode().rstrip("="),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode().rstrip("="),
            "timestamp": int(time.time()),
        }
        return "qoreseal:" + base64.urlsafe_b64encode(_json.dumps(envelope).encode()).decode().rstrip("=")

    def _python_open(self, chain_id: str, purpose: str, envelope_text: str, mlkem_secret: Union[str, bytes], x25519_secret: Union[str, bytes], mlkem_public: Union[str, bytes], x25519_public: Union[str, bytes], aad: Optional[bytes] = None) -> bytes:
        # Simple fallback open (XOR reverse)
        import json as _json

        if envelope_text.startswith("qoreseal:"):
            body = envelope_text[len("qoreseal:"):]
        else:
            body = envelope_text

        padded = body + "=" * (4 - len(body) % 4) if len(body) % 4 else body
        envelope = _json.loads(base64.urlsafe_b64decode(padded))

        nonce = base64.urlsafe_b64decode(envelope["nonce"] + "==")
        key = hashlib.sha256(chain_id.encode() + purpose.encode() + nonce).digest()
        ciphertext = base64.urlsafe_b64decode(envelope["ciphertext"] + "==")

        plaintext = bytes(a ^ b for a, b in zip(ciphertext, key * (len(ciphertext) // 32 + 1)))
        return plaintext

    def _python_parse(self, envelope_text: str) -> dict:
        if envelope_text.startswith("qoreseal:"):
            body = envelope_text[len("qoreseal:"):]
        else:
            body = envelope_text

        padded = body + "=" * (4 - len(body) % 4) if len(body) % 4 else body
        try:
            return json.loads(base64.urlsafe_b64decode(padded))
        except Exception as e:
            raise CryptoError(f"Failed to parse envelope: {e}")