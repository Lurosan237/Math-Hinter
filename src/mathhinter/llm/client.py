"""A small client for OpenAI-style chat APIs, using only the standard library so it runs anywhere.

Every response is cached by its full request. Free models change without notice, so the cache is what lets an
evaluation be re-scored later, and it stops a re-run from spending free quota twice.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

GROQ_URL = "https://api.groq.com/openai/v1"
# Without this, some API front ends refuse Python's default client name.
USER_AGENT = "math-hinter/0.1"
RETRYABLE = {429, 500, 502, 503, 504}
MAX_WAIT_SECONDS = 120


class LLMError(RuntimeError):
    """The API refused or failed. The message never contains the key."""


class QuotaExhausted(LLMError):
    """A long wait is needed, such as for a daily limit. A run should stop here and resume later."""


def read_env(path: Path) -> dict[str, str]:
    """KEY=value lines. Notepad may add a byte-order mark, and utf-8-sig removes it."""
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def cache_key(request: dict) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass
class Client:
    api_key: str = field(repr=False)
    cache_dir: Path | None = None
    base_url: str = GROQ_URL
    max_retries: int = 8
    max_wait: float = MAX_WAIT_SECONDS  # longer waits raise QuotaExhausted; a web request can't wait two minutes
    opener: object = urllib.request.urlopen
    sleep: object = time.sleep

    def _call(self, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "User-Agent": USER_AGENT})
        for attempt in range(self.max_retries + 1):
            try:
                with self.opener(request, timeout=120) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors="replace")[:300]
                if error.code not in RETRYABLE or attempt == self.max_retries:
                    raise LLMError(f"HTTP {error.code}: {detail}".replace(self.api_key, "***")) from None
                wait = float(error.headers.get("retry-after") or 0) if error.headers else 0
                if wait > self.max_wait:
                    raise QuotaExhausted(f"limit reached, try again in {wait:.0f}s") from None
                self.sleep(wait + 1 if wait else 2**attempt)
            except urllib.error.URLError as error:
                if attempt == self.max_retries:
                    raise LLMError(f"could not connect: {error.reason}") from None
                self.sleep(2**attempt)
        raise LLMError("no response")

    def models(self) -> list[str]:
        return sorted(item["id"] for item in self._call("/models")["data"])

    def chat(self, model: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 1024) -> dict:
        """The API's answer, from the cache if this exact request was made before."""
        request = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        path = self.cache_dir / f"{cache_key(request)}.json" if self.cache_dir else None
        if path and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        response = self._call("/chat/completions", request)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"request": request, "response": response}, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        return response
