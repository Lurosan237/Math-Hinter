"""The live tutor behind the public site: checks a request, applies the usage limits and runs one review.

The tutor is the evaluated one, unchanged: same model, prompts, search and checker. Only the course differs, because
the evaluation books are licensed: the site searches Exo7's openly licensed courses instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .agent.course import CourseSearch
from .agent.tutor import Tutor
from .llm.client import Client, LLMError, QuotaExhausted

MODEL = "openai/gpt-oss-120b"
CONFIGS = ("llm_only", "rag", "agent")
MAX_STATEMENT = 1500
MAX_ATTEMPT = 2500
MAX_LINES = 40
VISITOR_LIMIT = int(os.environ.get("MH_VISITOR_LIMIT", "5"))  # reviews per visitor per day on the site's key
SITE_LIMIT = int(os.environ.get("MH_SITE_LIMIT", "40"))  # reviews per day on the site's key, per running instance


class BadRequest(ValueError):
    """The request can't be reviewed. The message is shown to the visitor, in French."""


@dataclass
class Limiter:
    """Daily counts kept in memory. Instances restart, so this is a courtesy limit: Groq's daily quota on the site's
    key is the real ceiling. Visitors are counted by a salted hash of their address, which is never stored."""

    visitor_limit: int
    site_limit: int
    clock: object = time.time
    day: int = -1
    counts: dict = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, address: str) -> str | None:
        """None if the review may go ahead, otherwise why not."""
        with self.lock:
            today = int(self.clock() // 86400)
            if today != self.day:
                self.day, self.counts = today, {}
            visitor = hashlib.sha256(f"{today}:{address}".encode()).hexdigest()[:16]
            if self.counts.get("*", 0) >= self.site_limit:
                return "site"
            if self.counts.get(visitor, 0) >= self.visitor_limit:
                return "visitor"
            self.counts["*"] = self.counts.get("*", 0) + 1
            self.counts[visitor] = self.counts.get(visitor, 0) + 1
            return None

    def remaining(self, address: str) -> int:
        with self.lock:
            visitor = hashlib.sha256(f"{self.day}:{address}".encode()).hexdigest()[:16]
            return max(0, min(self.visitor_limit - self.counts.get(visitor, 0),
                              self.site_limit - self.counts.get("*", 0)))


def read_request(body: bytes) -> dict:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BadRequest("La requête n'est pas lisible.") from None
    if not isinstance(data, dict):
        raise BadRequest("La requête n'est pas lisible.")
    statement = str(data.get("statement") or "").strip()
    attempt = "\n".join(line.rstrip() for line in str(data.get("attempt") or "").strip().splitlines() if line.strip())
    config = data.get("config") or "rag"
    key = str(data.get("key") or "").strip()
    if not statement:
        raise BadRequest("Écrivez l'énoncé de l'exercice.")
    if not attempt:
        raise BadRequest("Écrivez votre rédaction, une étape par ligne.")
    if len(statement) > MAX_STATEMENT:
        raise BadRequest(f"L'énoncé dépasse {MAX_STATEMENT} caractères.")
    if len(attempt) > MAX_ATTEMPT or attempt.count("\n") + 1 > MAX_LINES:
        raise BadRequest(f"La rédaction dépasse {MAX_ATTEMPT} caractères ou {MAX_LINES} lignes.")
    if config not in CONFIGS:
        raise BadRequest("Version inconnue.")
    if key and not (key.startswith("gsk_") and len(key) < 200 and key.isascii()):
        raise BadRequest("Cette clé ne ressemble pas à une clé Groq (elle commence par gsk_).")
    return {"statement": statement, "attempt": attempt, "config": config, "key": key}


class Service:
    def __init__(self, units: list[dict], site_key: str, cache_dir: Path | None = None, limiter: Limiter | None = None,
                 client_factory=None):
        self.units = {u["id"]: u for u in units}
        self.course = CourseSearch(units)
        self.site_key = site_key
        self.cache_dir = cache_dir
        self.limiter = limiter or Limiter(VISITOR_LIMIT, SITE_LIMIT)
        self.client_factory = client_factory or (
            lambda key: Client(key, cache_dir=self.cache_dir, max_retries=3, max_wait=20))

    def review(self, request: dict, address: str) -> tuple[int, dict]:
        """HTTP status and JSON body. A visitor's own key is used for this request only and never kept."""
        own_key = request["key"]
        if not own_key:
            if not self.site_key:
                return 503, {"error": "Le site n'a pas de clé configurée. Ajoutez votre propre clé Groq.",
                             "code": "nokey"}
            refused = self.limiter.take(address)
            if refused == "visitor":
                return 429, {"error": f"Vous avez utilisé vos {self.limiter.visitor_limit} relectures du jour avec "
                                      "la clé du site. Ajoutez votre propre clé Groq gratuite pour continuer.",
                             "code": "visitor"}
            if refused == "site":
                return 429, {"error": "Le quota du jour du site est épuisé. Ajoutez votre propre clé Groq gratuite "
                                      "pour continuer, ou revenez demain.", "code": "site"}
        tutor = Tutor(self.client_factory(own_key or self.site_key), MODEL, self.course)
        statement, attempt = request["statement"], request["attempt"]
        started = time.time()
        try:
            if request["config"] == "llm_only":
                review = tutor.llm_only(statement, attempt)
            elif request["config"] == "rag":
                review = tutor.rag(statement, attempt, "web", solution="")
            else:
                review = tutor.agent(statement, attempt, "web", solution="")
        except QuotaExhausted:
            whose = "votre clé" if own_key else "la clé du site"
            then = "." if own_key else " ou ajoutez votre propre clé."
            return 429, {"error": f"Groq refuse pour l'instant : la limite de {whose} est atteinte. Réessayez plus "
                                  f"tard{then}", "code": "groq"}
        except LLMError as error:
            message = "Votre clé Groq a été refusée." if own_key and "401" in str(error) else \
                "Groq n'a pas répondu correctement. Réessayez dans un instant."
            return 502, {"error": message, "code": "api"}
        if (review.failure or "").startswith("api:"):
            refused = own_key and "401" in review.failure
            return 502, {"error": "Votre clé Groq a été refusée." if refused else
                         "Groq n'a pas répondu correctement. Réessayez dans un instant.", "code": "api"}
        record = review.record()
        record.pop("llm_calls", None)
        ids = list(dict.fromkeys(record["citations"] + record["shown"]))
        passages = {i: {"label": self.units[i].get("label", i), "kind": self.units[i]["kind"],
                        "text": self.units[i]["text"][:1500]} for i in ids if i in self.units}
        body = {"review": record, "passages": passages, "lines": attempt.split("\n"), "model": MODEL,
                "seconds": round(time.time() - started, 1)}
        if not own_key:
            body["remaining"] = self.limiter.remaining(address)
        return 200, body
