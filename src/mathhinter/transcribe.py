"""Read a photographed exercise and attempt with a vision model, keeping the student's mistakes.

The review only means something if the transcription is faithful, so the prompt forbids correcting anything, and the
visitor sees the transcription and can fix it before or after the review. How often a planted error survives is
measured by scripts/eval_transcription.py.
"""

from __future__ import annotations

import base64
import binascii
import json
import re

VISION_MODEL = "qwen/qwen3.8-27b"
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 1_500_000
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")

PROMPT = """Tu recopies la photo d'une copie d'étudiant en mathématiques, pour qu'un correcteur la relise ensuite.

Recopie exactement ce qui est écrit, erreurs comprises. C'est essentiel : ne corrige rien, même une faute évidente
(un signe, un exposant, un coefficient, une formule fausse), ne complète rien, ne résous rien, n'ajoute aucune étape.
Si un passage est illisible, écris [?] à sa place plutôt que de deviner.

- L'énoncé de l'exercice, s'il est visible (souvent imprimé ou en tête), va dans "statement". Sinon "".
- La rédaction de l'étudiant va dans "lines" : une entrée par ligne ou étape, dans l'ordre de la copie. Ignore les
  ratures et ce qui est barré.
- Écris les mathématiques en LaTeX entre $...$ et le texte normalement, avec les accents (é, è, à) en clair.
- Garde les primes (f', v'), les indices, les bornes d'intégrales et les signes exactement comme sur la copie.
- "unclear" : les numéros (à partir de 0) des lignes dont tu n'es pas sûr.

Réponds uniquement avec ce JSON : {"statement": "...", "lines": ["...", "..."], "unclear": []}"""

_ACCENTS = {"\\`e": "è", "\\'e": "é", "\\`a": "à", "\\^e": "ê", "\\^o": "ô", "\\^i": "î", "\\`u": "ù", "\\c{c}": "ç",
            "\\'E": "É", "\\`{e}": "è", "\\'{e}": "é", "\\`{a}": "à", "\\^{e}": "ê"}


class BadImage(ValueError):
    """The images can't be read. The message is shown to the visitor, in French."""


def check_images(images: object) -> list[str]:
    """The data URLs to send, after checking their type and size."""
    if not isinstance(images, list) or not images:
        raise BadImage("Ajoutez une photo de votre copie.")
    if len(images) > MAX_IMAGES:
        raise BadImage(f"Envoyez au plus {MAX_IMAGES} photos.")
    checked = []
    for image in images:
        match = re.fullmatch(r"data:(image/[a-z]+);base64,([A-Za-z0-9+/=]+)", str(image))
        if not match or match[1] not in IMAGE_TYPES:
            raise BadImage("Format d'image non pris en charge : utilisez une photo JPEG ou PNG.")
        try:
            size = len(base64.b64decode(match[2], validate=True))
        except binascii.Error:
            raise BadImage("Une des photos est abîmée.") from None
        if size > MAX_IMAGE_BYTES:
            raise BadImage("Une des photos est trop lourde.")
        checked.append(str(image))
    return checked


def messages(images: list[str]) -> list[dict]:
    content = [{"type": "text", "text": PROMPT}]
    content += [{"type": "image_url", "image_url": {"url": image}} for image in images]
    return [{"role": "user", "content": content}]


def _plain(text: str) -> str:
    for code, letter in _ACCENTS.items():
        text = text.replace(code, letter)
    return text.strip()


def parse(content: str) -> dict:
    """The transcription from the model's reply. Raises ValueError if there is none."""
    match = re.search(r"\{.*\}", content or "", re.S)
    if not match:
        raise ValueError("no JSON in the reply")
    data = json.loads(match[0])
    lines = [_plain(str(line)) for line in data.get("lines") or [] if str(line).strip()]
    if not lines:
        raise ValueError("no lines")
    unclear = sorted({int(i) for i in data.get("unclear") or [] if str(i).isdigit() and int(i) < len(lines)})
    return {"statement": _plain(str(data.get("statement") or "")), "lines": lines, "unclear": unclear}


def transcribe(client, images: list[str]) -> dict:
    response = client.chat(VISION_MODEL, messages(images), temperature=0.0, max_tokens=2500)
    message = response["choices"][0]["message"]
    try:
        result = parse(message.get("content") or "")
    except (ValueError, json.JSONDecodeError):
        result = parse(message.get("reasoning") or "")  # some replies put the JSON in the reasoning only
    result["tokens"] = response.get("usage", {}).get("total_tokens")
    return result
