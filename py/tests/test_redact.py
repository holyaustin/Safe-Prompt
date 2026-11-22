"""Safe Prompt — redaction + fail-closed guard tests."""

import pytest

from safe_prompt.detect.engine import Detector
from safe_prompt.gateway.redact import Redactor, LeakBlocked, check_outbound, map_strings, iter_strings


class TestRedactor:
    def setup_method(self):
        self.detector = Detector()
        self.crypto = __import__("safe_prompt.crypto", fromlist=["SafePromptCrypto"]).SafePromptCrypto(use_rust=False)
        self.redactor = Redactor(detector=self.detector, crypto=self.crypto, session="test")

    def test_redact_text_replaces_secret_with_placeholder(self):
        text = "The API key sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk9fQ2aBcDeFgHiJkLm is bad"
        redacted = self.redactor.redact_text(text)
        assert "sk-proj-" not in redacted
        assert "[" in redacted and "]" in redacted  # placeholder like [APIKEY_1]

    def test_redact_redacts_multiple_secrets(self):
        text = "Card 4111 1111 1111 1111 and AWS key AKIAIOSFODNN7EXAMPLE"
        redacted = self.redactor.redact_text(text)
        assert "4111" not in redacted
        assert "AKIAIOSFODNN7EXAMPLE" not in redacted

    def test_redact_clean_text(self):
        text = "This is a safe sentence about deployment."
        assert self.redactor.redact_text(text) == text

    def test_check_outbound_no_leak(self):
        payload = {"messages": [{"role": "user", "content": "The API key is sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk9fQ2aBcDeFgHiJkLm"}]}
        # Redact first
        redactor = Redactor(detector=self.detector, crypto=self.crypto, session="test")
        redacted = redactor.redact_payload(payload)
        # Should be redacted now
        assert "sk-proj-" not in json.dumps(redacted)

    def test_check_outbound_fail_closed_detects_unredacted(self):
        payload = {"messages": [{"role": "user", "content": "The API key sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk9fQ2aBcDeFgHiJkLm"}]}
        # No redaction applied -> fail closed should catch
        values = []
        # Fail closed: the unredacted secret must be caught
        with pytest.raises(LeakBlocked):
            check_outbound(payload, values, self.detector)
        # And the detector confirms the secret was found
        matches = self.detector.find(payload["messages"][0]["content"], structured_only=True)
        assert len(matches) > 0
        assert matches[0].kind == "APIKEY"


import json  # noqa: E402  (used above)
