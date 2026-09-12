"""Input and output guardrails for the /chat endpoint.

Four checks, in the order a request flows through them. Each one is small on
purpose: the app is the *target* of the pipeline, not the point of it. What
matters is that every refusal emits a security event (see events.py) that the
detection layer can correlate.

    1. size and type           input.oversize
    2. prompt injection        prompt.injection_detected
    3. rate limit per client   ratelimit.exceeded
    4. PII redaction on output output.pii_redacted
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass

MAX_PROMPT_CHARS = 4_000

# Patterns that try to override the system instruction or exfiltrate it.
# Conservative on purpose: a false refusal costs one retry, a miss costs the
# whole conversation. The patterns are the ones observed in public prompt
# injection corpora (ignore-previous, role hijack, prompt leak, delimiter
# escape).
_INJECTION = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?|rules)|"
    r"disregard\s+(your|the|all)\s+(instructions|rules|guidelines)|"
    r"you\s+are\s+now\s+(a|an|in)\b|"
    r"(reveal|print|show|repeat)\s+(your|the)\s+(system\s+)?(prompt|instructions)|"
    r"</?(system|assistant|instruction)>|"
    r"\[\s*(system|inst)\s*\]|"
    r"developer\s+mode|do\s+anything\s+now|jailbreak)",
    re.IGNORECASE,
)

# What we redact from model output before it leaves the service.
_PII = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<!\d)(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")),
    ("sin", re.compile(r"(?<!\d)\d{3}[\s-]\d{3}[\s-]\d{3}(?!\d)")),  # Canadian SIN
    ("card", re.compile(r"(?<!\d)(?:\d{4}[\s-]?){3}\d{4}(?!\d)")),
    ("api_key", re.compile(r"(?<![A-Za-z0-9_-])(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})")),
]


@dataclass
class Verdict:
    ok: bool
    event: str = ""         # event name when not ok (or when something was redacted)
    detail: str = ""


def check_input(prompt: str) -> Verdict:
    if not isinstance(prompt, str) or not prompt.strip():
        return Verdict(False, "input.invalid", "prompt must be a non-empty string")
    if len(prompt) > MAX_PROMPT_CHARS:
        return Verdict(False, "input.oversize", f"{len(prompt)} chars > {MAX_PROMPT_CHARS}")
    m = _INJECTION.search(prompt)
    if m:
        return Verdict(False, "prompt.injection_detected", m.group(0)[:60])
    return Verdict(True)


def redact_output(text: str) -> tuple[str, list[str]]:
    """Return (redacted_text, kinds_redacted)."""
    kinds: list[str] = []
    for kind, pattern in _PII:
        if pattern.search(text):
            kinds.append(kind)
            text = pattern.sub(f"[{kind} redacted]", text)
    return text, kinds


class RateLimiter:
    """Sliding window per client id. In-memory: one task, one process. For a
    multi-task service this moves to Redis or the ALB's own rate limiting;
    SCALE.md covers that."""

    def __init__(self, limit: int = 30, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, client_id: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits[client_id]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
