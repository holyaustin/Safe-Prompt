"""Safe Prompt test configuration."""

import pytest

from safe_prompt.crypto import SafePromptCrypto

@pytest.fixture
def crypto():
    """Rust core or Python fallback."""
    return SafePromptCrypto(use_rust=False)