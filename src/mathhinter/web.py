"""The live tutor behind the public site: checks a request, applies the usage limits and runs one review.

The tutor is the evaluated one, unchanged: same model, prompts, search and checker. Only the course differs, because
the evaluation books are licensed: the site searches Exo7's openly licensed courses instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .agent.course import CourseSearch
from .hints import MAX_LEVEL, next_hint
from .llm.client import Client, LLMError, QuotaExhausted
from .pipeline.orchestrate import PipelineTutor
from .seal import BadSeal, seal, unseal
from .study import MAX_TURNS, check_answer, explain, similar_exercise
from .transcribe import BadImage, check_images, transcribe

MODEL = "openai/gpt-oss-120b"
CONFIGS = ("pipeline", "llm_only", "rag", "agent")
MAX_STATEMENT = 1500
MAX_ATTEMPT = 2500
MAX_LINES = 40
VISITOR_LIMIT = int(os.environ.get("MH_VISITOR_LIMIT", "5"))  # reviews per visitor per day on the site's key
SITE_LIMIT = int(os.environ.get("MH_SITE_LIMIT", "40"))  # reviews per day on the site's key, per running instance
HINT_VISITOR_LIMIT = int(os.environ.get("MH_HINT_VISITOR_LIMIT", "12"))  # further hints, same idea
HINT_SITE_LIMIT = int(os.environ.get("MH_HINT_SITE_LIMIT", "120"))
STUDY_VISITOR_LIMIT = int(os.environ.get("MH_STUDY_VISITOR_LIMIT", "40"))  # similar exercises and explanations
STUDY_SITE_LIMIT = int(os.environ.get("MH_STUDY_SITE_LIMIT", "400"))
PHOTO_VISITOR_LIMIT = int(os.environ.get("MH_PHOTO_VISITOR_LIMIT", "10"))  # photo readings, same idea
PHOTO_SITE_LIMIT = int(os.environ.get("MH_PHOTO_SITE_LIMIT", "100"))


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
    config = data.get("config") or "pipeline"
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


def api_error(failure: str, own_key: str) -> tuple[int, dict]:
    """Groq's status code is logged and returned so failures can be diagnosed. Its text, which can quote the
    request, is not."""
    found = re.search(r"HTTP (\d{3})", failure)
    status = found[1] if found else "connexion"
    print(f"groq error: {status} ({'visitor' if own_key else 'site'} key)", file=sys.stderr)
    if status == "401":
        message = "Votre clé Groq a été refusée." if own_key else "La clé du site est refusée par Groq."
    else:
        message = "Groq n'a pas répondu correctement. Réessayez dans un instant."
    return 502, {"error": message, "code": "api", "groq_status": status}


class Service:
    def __init__(self, units: list[dict], site_key: str, cache_dir: Path | None = None, limiter: Limiter | None = None,
                 client_factory=None):
        self.units = {u["id"]: u for u in units}
        self.course = CourseSearch(units)
        self.site_key = site_key
        self.cache_dir = cache_dir
        self.limiter = limiter or Limiter(VISITOR_LIMIT, SITE_LIMIT)
        self.hint_limiter = Limiter(HINT_VISITOR_LIMIT, HINT_SITE_LIMIT)
        self.study_limiter = Limiter(STUDY_VISITOR_LIMIT, STUDY_SITE_LIMIT)
        self.secret = os.environ.get("MH_SECRET") or site_key or "math-hinter-local"
        self.client_factory = client_factory or (
            lambda key: Client(key, cache_dir=self.cache_dir, max_retries=3, max_wait=20))

    def _label(self, ident: str) -> str:
        unit = self.units.get(ident)
        return unit.get("label", ident) if unit else ident

    def _progress(self, on_step):
        """The tutor's steps, with passage ids turned into readable sources, for the page to show as they happen."""
        if on_step is None:
            return None

        def report(event: dict) -> None:
            event = dict(event)
            if "found" in event:
                event["found"] = [self._label(i) for i in event["found"]]
            on_step(event)
        return report

    def review(self, request: dict, address: str, on_step=None) -> tuple[int, dict]:
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
        tutor = PipelineTutor(self.client_factory(own_key or self.site_key), MODEL, self.course,
                              self._progress(on_step))
        statement, attempt = request["statement"], request["attempt"]
        started = time.time()
        try:
            if request["config"] == "pipeline":
                review = tutor.pipeline(statement, attempt)
            elif request["config"] == "llm_only":
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
            return api_error(str(error), own_key)
        if (review.failure or "").startswith("api:"):
            return api_error(review.failure, own_key)
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


    def hint(self, body: bytes, address: str) -> tuple[int, dict]:
        """The next, more explicit hint for a line the review flagged."""
        try:
            data = json.loads(body.decode("utf-8"))
            base = read_request(json.dumps({k: data.get(k) for k in ("statement", "attempt", "key")}).encode())
            line, hints = int(data["line"]), [str(h)[:600] for h in data.get("hints") or []]
        except BadRequest as error:
            return 400, {"error": str(error), "code": "input"}
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
            return 400, {"error": "La requête n'est pas lisible.", "code": "input"}
        lines = base["attempt"].split("\n")
        if not 0 <= line < len(lines) or not 1 <= len(hints) < MAX_LEVEL:
            return 400, {"error": "Il n'y a pas d'autre indice pour cette relecture.", "code": "input"}
        own_key = base["key"]
        if not own_key:
            if not self.site_key:
                return 503, {"error": "Le site n'a pas de clé configurée.", "code": "nokey"}
            if self.hint_limiter.take(address):
                return 429, {"error": "Le quota d'indices du jour est atteint. Ajoutez votre propre clé Groq gratuite "
                                      "pour continuer.", "code": "visitor"}
        passages = [{"label": self._label(i), "text": self.units[i]["text"][:1200]}
                    for i in (data.get("citations") or [])[:3] if i in self.units]
        try:
            hint = next_hint(self.client_factory(own_key or self.site_key), base["statement"], base["attempt"], line,
                             hints, str(data.get("explanation") or "")[:1500], passages)
        except QuotaExhausted:
            return 429, {"error": "Groq refuse pour l'instant. Réessayez dans une minute.", "code": "groq"}
        except LLMError as error:
            return api_error(str(error), own_key)
        except (ValueError, KeyError):
            return 422, {"error": "Le modèle n'a pas formulé d'indice. Réessayez.", "code": "unreadable"}
        return 200, {"hint": hint, "level": len(hints) + 1, "last": len(hints) + 1 >= MAX_LEVEL}


    def _study_request(self, body: bytes, address: str, fields: tuple[str, ...]) -> tuple[dict | None, tuple | None]:
        """The request's fields and the client to use, or the error to send."""
        try:
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None, (400, {"error": "La requête n'est pas lisible.", "code": "input"})
        missing = [f for f in fields if not str(data.get(f) or "").strip()]
        if missing:
            return None, (400, {"error": "Il manque des éléments à la demande.", "code": "input"})
        own_key = str(data.get("key") or "").strip()
        if own_key and not (own_key.startswith("gsk_") and len(own_key) < 200 and own_key.isascii()):
            return None, (400, {"error": "Cette clé ne ressemble pas à une clé Groq.", "code": "input"})
        if not own_key:
            if not self.site_key:
                return None, (503, {"error": "Le site n'a pas de clé configurée.", "code": "nokey"})
            if self.study_limiter.take(address):
                return None, (429, {"error": "La limite du jour est atteinte. Ajoutez votre propre clé Groq gratuite "
                                             "pour continuer.", "code": "visitor"})
        data["client"] = self.client_factory(own_key or self.site_key)
        data["own_key"] = own_key
        return data, None

    def similar(self, body: bytes, address: str) -> tuple[int, dict]:
        """A new exercise on the skill the student got wrong. Its answer, checked by the computer, travels sealed."""
        data, error = self._study_request(body, address, ("statement", "line", "explanation"))
        if error:
            return error
        try:
            exercise = similar_exercise(data["client"], str(data["statement"])[:1500], str(data["line"])[:600],
                                        str(data["explanation"])[:1500])
        except QuotaExhausted:
            return 429, {"error": "Groq refuse pour l'instant. Réessayez dans une minute.", "code": "groq"}
        except LLMError as failure:
            return api_error(str(failure), data["own_key"])
        except ValueError:
            return 422, {"error": "Pas d'exercice vérifiable cette fois. Réessayez.", "code": "unreadable"}
        token = seal(exercise["check"], self.secret)
        return 200, {"statement": exercise["statement"], "skill": exercise["skill"],
                     "answer_label": exercise["answer_label"], "token": token}

    def answer(self, body: bytes) -> tuple[int, dict]:
        """Check the student's answer to a similar exercise. No model call, so no limit."""
        try:
            data = json.loads(body.decode("utf-8"))
            claim = unseal(data["token"], self.secret)
            answer = str(data["answer"]).strip().strip("$")[:300]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, BadSeal):
            return 400, {"error": "La requête n'est pas lisible.", "code": "input"}
        if not answer:
            return 400, {"error": "Écrivez votre réponse.", "code": "input"}
        return 200, {"status": check_answer(claim, answer)}

    def explain(self, body: bytes, address: str) -> tuple[int, dict]:
        """One turn of a short guided conversation about the flagged line."""
        data, error = self._study_request(body, address, ("statement", "attempt", "explanation"))
        if error:
            return error
        history = [h for h in data.get("history") or [] if isinstance(h, dict)]
        if len(history) > 2 * MAX_TURNS:
            return 400, {"error": "La conversation est terminée : relancez une relecture.", "code": "input"}
        try:
            line = int(data.get("line"))
            reply = explain(data["client"], str(data["statement"])[:1500], str(data["attempt"])[:2500], line,
                            str(data["explanation"])[:1500], history)
        except (TypeError, ValueError):
            return 422, {"error": "Pas de réponse cette fois. Réessayez.", "code": "unreadable"}
        except QuotaExhausted:
            return 429, {"error": "Groq refuse pour l'instant. Réessayez dans une minute.", "code": "groq"}
        except LLMError as failure:
            return api_error(str(failure), data["own_key"])
        return 200, {"reply": reply}


class PhotoService:
    """Reads photographed pages. Kept apart from Service so the photo function doesn't load the course."""

    def __init__(self, site_key: str, limiter: Limiter | None = None, client_factory=None):
        self.site_key = site_key
        self.photo_limiter = limiter or Limiter(PHOTO_VISITOR_LIMIT, PHOTO_SITE_LIMIT)
        # A student waits for the photo, so a busy Groq means a quick "try again" rather than a minute of retries.
        self.client_factory = client_factory or (lambda key: Client(key, cache_dir=None, max_retries=1, max_wait=8))

    def read_photos(self, body: bytes, address: str) -> tuple[int, dict]:
        """Transcribe photographed pages. The images go to Groq and are not kept."""
        try:
            data = json.loads(body.decode("utf-8"))
            images = check_images(data.get("images") if isinstance(data, dict) else None)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400, {"error": "La requête n'est pas lisible.", "code": "input"}
        except BadImage as error:
            return 400, {"error": str(error), "code": "input"}
        own_key = str(data.get("key") or "").strip()
        if own_key and not (own_key.startswith("gsk_") and len(own_key) < 200 and own_key.isascii()):
            return 400, {"error": "Cette clé ne ressemble pas à une clé Groq (elle commence par gsk_).",
                         "code": "input"}
        if not own_key:
            if not self.site_key:
                return 503, {"error": "Le site n'a pas de clé configurée. Ajoutez votre propre clé Groq.",
                             "code": "nokey"}
            refused = self.photo_limiter.take(address)
            if refused:
                return 429, {"error": "Le quota de photos du jour est atteint. Tapez votre rédaction, ou ajoutez votre "
                                      "propre clé Groq gratuite.",
                             "code": "visitor" if refused == "visitor" else "site"}
        started = time.time()
        try:
            result = transcribe(self.client_factory(own_key or self.site_key), images)
        except QuotaExhausted:
            return 429, {"error": "Groq refuse pour l'instant de lire les photos. Réessayez plus tard ou tapez votre "
                                  "rédaction.", "code": "groq"}
        except LLMError as error:
            return api_error(str(error), own_key)
        except (ValueError, json.JSONDecodeError, KeyError):
            return 422, {"error": "Le modèle n'a pas réussi à lire la photo. Reprenez-la de face, bien éclairée et "
                                  "nette, ou tapez votre rédaction.", "code": "unreadable"}
        result["seconds"] = round(time.time() - started, 1)
        return 200, result
