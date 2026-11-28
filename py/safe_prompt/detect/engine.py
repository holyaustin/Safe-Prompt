"""Secret / PII detection engine — fail-closed philosophy.

Detects sensitive values before they leave the machine:
API keys, JWTs, private keys, cards, emails, passwords, phones, IP addresses,
URL credentials, SSNs, IBANs, environment variable strings.

Inspired by VeilProxy's detection pipeline but freshly written for Safe Prompt.
All detection happens locally; nothing touches disk except audit logs.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional


PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z0-9]*_\d+\]")


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    kind: str
    value: str
    priority: int = 0
    source: str = "regex"


# ------------------------------------------------------------------ validators
def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _card_ok(v: str) -> bool:
    d = re.sub(r"[ -]", "", v)
    return d.isdigit() and 13 <= len(d) <= 19 and luhn_ok(d) and len(set(d)) > 1


def _iban_ok(v: str) -> bool:
    s = v.replace(" ", "").upper()
    if not (15 <= len(s) <= 34) or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    r = s[4:] + s[:4]
    try:
        return int("".join(str(int(c, 36)) for c in r)) % 97 == 1
    except ValueError:
        return False


def _ssn_ok(v: str) -> bool:
    parts = v.split("-")
    if len(parts) != 3:
        return False
    a, g, s = parts
    return a not in ("000", "666") and not a.startswith("9") and g != "00" and s != "0000"


def _phone_ok(v: str) -> bool:
    digits = re.sub(r"\D", "", v)
    return 10 <= len(digits) <= 15


def _ip_ok(v: str) -> bool:
    return v not in ("0.0.0.0", "127.0.0.1", "255.255.255.255")


def _not_placeholder(v: str) -> bool:
    return not PLACEHOLDER_RE.fullmatch(v) and not (v.startswith("[") and v.endswith("]"))


def shannon(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((s.count(c) / n) * math.log2(s.count(c) / n) for c in set(s))


# ------------------------------------------------------------------ rules
@dataclass(frozen=True)
class Rule:
    kind: str
    pattern: re.Pattern
    priority: int
    group: int = 0
    validate: Optional[Callable[[str], bool]] = None


def _r(kind: str, rx: str, prio: int, group: int = 0, validate=None, flags: int = 0) -> Rule:
    return Rule(kind, re.compile(rx, flags), prio, group, validate)


BUILTIN_RULES: list[Rule] = [
    _r("PRIVATEKEY", r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z ]+ )?PRIVATE KEY-----", 100),
    _r("JWT", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", 90),
    _r("URLCRED", r"(?<=://)[^\s/:@]+:[^\s/@]+(?=@)", 85),
    _r("AWSKEY", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", 80),
    _r("APIKEY", r"\bsk-(?:proj-|ant-|or-v1-|svcacct-)?[A-Za-z0-9_-]{20,}", 80),
    _r("CARD", r"\b(?:\d[ -]?){13,19}\b", 75, validate=_card_ok),
    _r("SSN", r"\b\d{3}-\d{2}-\d{4}\b", 70, validate=_ssn_ok),
    _r("IBAN", r"\b[A-Z]{2}[0-9]{2}[A-Z0-9 ]{10,30}\b", 65, validate=_iban_ok),
    _r("PHONE", r"(?<![A-Za-z0-9])\+?\d[\d .()\-]{8,}\d(?![A-Za-z0-9])", 60, validate=_phone_ok),
    _r("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", 55),
    _r("IPADDR", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 50, validate=_ip_ok),
    _r("PASSWORD", r"(?i)(?:password|passwd|pwd|secret|token|api[_-]?key)[ :='\"]+([^\s,;]+)", 45, group=1),
    _r("ENTROPY", r"\b[A-Za-z0-9+/=]{40,}\b", 20, validate=lambda v: shannon(v) > 4.2),
]


class Detector:
    """Run detection rules against text and return non-overlapping matches sorted by start."""

    def __init__(self, rules: Optional[Iterable[Rule]] = None):
        self.rules = list(rules) if rules else BUILTIN_RULES

    def find(self, text: str, structured_only: bool = False) -> list[Match]:
        matches: list[Match] = []
        for rule in self.rules:
            for m in rule.pattern.finditer(text):
                value = m.group(rule.group) if rule.group > 0 else m.group(0)
                if not _not_placeholder(value):
                    continue
                if rule.validate and not rule.validate(value):
                    continue
                matches.append(Match(m.start(), m.end(), rule.kind, value, rule.priority, "regex"))

        # Sort by start position, then dedupe overlaps keeping highest priority
        matches.sort(key=lambda m: (m.start, -m.priority))
        deduped: list[Match] = []
        for m in matches:
            if deduped and m.start < deduped[-1].end:
                # Overlapping: keep higher priority (already sorted by start)
                if m.priority > deduped[-1].priority:
                    deduped[-1] = m
                continue
            deduped.append(m)

        if structured_only:
            # Only kinds that are "structured" secrets (keys, JWTs, cards, SSN, IBAN, etc.)
            structured = {"PRIVATEKEY", "JWT", "URLCRED", "AWSKEY", "APIKEY", "CARD", "SSN", "IBAN", "PHONE", "PASSWORD", "ENTROPY"}
            deduped = [m for m in deduped if m.kind in structured]

        return deduped
