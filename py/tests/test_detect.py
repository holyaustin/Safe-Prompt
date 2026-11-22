"""Safe Prompt — detection engine tests."""

import pytest

from safe_prompt.detect.engine import Detector, PLACEHOLDER_RE, shannon


class TestDetector:
    def setup_method(self):
        self.detector = Detector()

    def test_detects_private_key(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
        matches = self.detector.find(text)
        assert len(matches) == 1
        assert matches[0].kind == "PRIVATEKEY"

    def test_detects_jwt(self):
        text = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0GEsI"
        matches = self.detector.find(text)
        assert any(m.kind == "JWT" for m in matches)

    def test_detects_aws_key(self):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        matches = self.detector.find(text)
        assert any(m.kind == "AWSKEY" for m in matches)

    def test_detects_api_key(self):
        text = "sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk9fQ2aBcDeFgHiJkLm"
        matches = self.detector.find(text)
        assert any(m.kind == "APIKEY" for m in matches)

    def test_detects_credit_card(self):
        # Visa test number
        text = "My card is 4111 1111 1111 1111"
        matches = self.detector.find(text)
        assert any(m.kind == "CARD" for m in matches)

    def test_detects_iban(self):
        text = "IBAN: GB82 WEST 1234 5698 7654 32"
        matches = self.detector.find(text)
        assert any(m.kind == "IBAN" for m in matches)

    def test_detects_email(self):
        text = "Contact ada.obi@example.com for details"
        matches = self.detector.find(text)
        assert any(m.kind == "EMAIL" for m in matches)

    def test_detects_password_assignment(self):
        text = "DATABASE_URL=postgres://admin:s3cr3tpw@db.internal/prod"
        matches = self.detector.find(text)
        assert any(m.kind == "URLCRED" for m in matches)

    def test_clean_text_returns_no_matches(self):
        text = "Hello team, please review the latest deployment."
        assert self.detector.find(text) == []

    def test_placeholder_format(self):
        assert PLACEHOLDER_RE.fullmatch("[APIKEY_1]") is not None
        assert PLACEHOLDER_RE.fullmatch("[EMAIL_2]") is not None
        assert PLACEHOLDER_RE.fullmatch("[FAKE") is None


def test_shannon_entropy():
    assert shannon("abcdefghij") > 0
    assert shannon("") == 0.0
