"""Natural language in, a typed constraint list out — the model boundary.

The one nondeterministic component in this app, deliberately confined to a
single file and a single job: turn "cà phê, không shopping, tối đa 3 chỗ" into

    [{"type": "min_category", "category": "coffee", "count": 1},
     {"type": "exclude_category", "category": "shopping"},
     {"type": "max_stops", "count": 3}]

and nothing else. **The model never selects or orders stops.** Choosing places
under hard budgets is the MILP's provable guarantee and the reason this app
exists; a model that merely sounds right would hand back a 240.000 ₫ plan for
a 200.000 ₫ budget. See ``wiki_storage/wiki/concepts/llm-in-the-loop-planning``.

This module talks to Gemini and returns **raw dicts**. It deliberately does not
import the API's Pydantic constraint models: ``api.py`` owns the vocabulary and
validates what comes back, so there is exactly one definition of what a valid
constraint is, and no import cycle.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

# Free of charge on Gemini's free tier (verified against Google's pricing page,
# 2026-08-24). Not a Flash-Lite: the hardest part of this task is negation
# ("no coffee" must become exclude_category, not min_category), and that is
# the first thing a smaller model gets wrong.
MODEL = "gemini-3.7-flash"

# A preference sentence, not an essay. Bounds cost and blocks prompt-stuffing.
MAX_MESSAGE_CHARS = 500

# The seven shapes the model may emit. Mirrors ConstraintIn in api.py, which is
# what actually validates them.
CONSTRAINT_TYPES = (
    "boost_category",
    "exclude_category",
    "exclude_place",
    "require_place",
    "min_category",
    "max_category",
    "max_stops",
)


class InterpretUnavailable(RuntimeError):
    """Raised when no API key is configured, so the caller can answer 503."""


class InterpretFailed(RuntimeError):
    """Raised when the model call fails or returns unusable output."""


def is_configured() -> bool:
    """Whether a Gemini key is present.

    Returns:
        True when ``GEMINI_API_KEY`` is set and non-empty. The endpoint answers
        503 rather than 500 when it isn't, so a deployment without a key is
        merely missing a feature rather than broken.
    """
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def response_schema(*, categories: list[str], place_ids: list[str]) -> dict:
    """Build the JSON schema the model's output is constrained to.

    Args:
        categories: the closed category vocabulary.
        place_ids: every real place id, from the seed.

    Returns:
        A JSON Schema dict for ``{constraints: [...], reply: str}``.

    Deliberately **flat** — one object shape with optional fields — rather than
    a seven-variant ``anyOf`` of the real constraint types. Gemini's structured
    output supports a subset of JSON Schema and warns that "very large or deeply
    nested schemas may be rejected"; a seven-way union each carrying a 100-value
    enum is exactly that shape. Flat keeps the enums (which is what stops
    hallucinated values) and lets Pydantic enforce which fields go with which
    type afterwards.

    The enums are the point: ``category`` and ``id`` can only be things that
    exist, so the most likely failure — a plausible-looking place id for a place
    we don't have — is impossible to generate rather than caught later.
    """
    return {
        "type": "object",
        "properties": {
            "constraints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": list(CONSTRAINT_TYPES)},
                        "category": {"type": "string", "enum": categories},
                        "id": {"type": "string", "enum": place_ids},
                        "count": {"type": "integer"},
                        "factor": {"type": "number"},
                    },
                    "required": ["type"],
                },
            },
            "reply": {"type": "string"},
        },
        "required": ["constraints", "reply"],
    }


def build_prompt(*, places: list, categories: list[str], current: list[dict] | None = None) -> str:
    """Compose the system prompt: the rules, the vocabulary, the catalogue.

    Args:
        places: the seed places, used to list real ids the model may name.
        categories: the closed category vocabulary.
        current: constraints already in force, so a follow-up like "make it 2
            coffees" can edit them instead of starting from nothing. This is
            the whole of the feature's "memory": the state carried between
            turns is the bounded constraint list, never a growing transcript.

    Returns:
        The instruction text sent ahead of the user's message.

    The catalogue is included so ``require_place`` / ``exclude_place`` can name
    real things. It is a large *stable* prefix, which is what makes this worth
    caching later if cost ever matters.
    """
    catalogue = "\n".join(f"  {p.id} | {p.name} | {p.category}" for p in places)
    already_set = json.dumps(current or [], ensure_ascii=False)
    return f"""You translate a person's request for an afternoon out in Sài Gòn into a\
 list of planning constraints. You do NOT plan the outing — an optimiser does that.

Emit ONLY constraints of these types:
  boost_category   {{category, factor}}  factor 0.5-1.5, a nudge in preference
  exclude_category {{category}}          never include this category
  exclude_place    {{id}}                never include this place
  require_place    {{id}}                this place must be included
  min_category     {{category, count}}   at least count of this category
  max_category     {{category, count}}   at most count of this category
  max_stops        {{count}}             at most count stops overall

Categories: {", ".join(categories)}

Rules:
- Negation matters more than anything else here. "no coffee" / "không cà phê"
  is exclude_category, NOT min_category. Read the polarity twice.
- Only emit a constraint the person actually asked for. Say nothing about
  budgets or time — those come from sliders the person already set.
- If the request mentions nothing you can express, return an empty list.
- ALREADY SET below is what the person has chosen so far. Return the COMPLETE
  updated list: keep everything they have not asked to change, and change only
  what this message asks for. "make it 2 coffees" edits the coffee constraint
  and leaves the rest alone. An empty ALREADY SET means they are starting over.
- "reply" is one short friendly sentence, in the language the person used,
  saying what you understood. No lists, no markdown.

ALREADY SET: {already_set}

Places you may name:
{catalogue}
"""


def interpret(
    message: str, *, places: list, categories: list[str], current: list[dict] | None = None
) -> tuple[list[dict], str]:
    """Ask the model to turn one message into constraints.

    Args:
        message: the person's words. Callers must enforce MAX_MESSAGE_CHARS.
        places: the seed places, for the id enum and the catalogue.
        categories: the closed category vocabulary.
        current: constraints already in force, as plain dicts. The returned
            list replaces them wholesale rather than describing edits — easier
            for the model to get right, and trivially validated.

    Returns:
        ``(raw_constraints, reply)`` — the constraints are unvalidated dicts;
        the caller validates them against the real vocabulary and drops any
        that fail.

    Raises:
        InterpretUnavailable: no API key configured.
        InterpretFailed: the call failed, or the output was not usable JSON.
    """
    if not is_configured():
        raise InterpretUnavailable("GEMINI_API_KEY is not set")

    # Imported here, not at module scope, so the app starts (and the whole test
    # suite runs) without the SDK's import-time credential handling.
    from google import genai

    place_ids = [p.id for p in places]
    try:
        client = genai.Client()
        interaction = client.interactions.create(
            model=MODEL,
            input=(
                f"{build_prompt(places=places, categories=categories, current=current)}"
                f"\n\nRequest: {message}"
            ),
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": response_schema(categories=categories, place_ids=place_ids),
            },
        )
        payload = json.loads(interaction.output_text)
    except Exception as exc:  # noqa: BLE001 - any SDK/network/parse failure degrades the same way
        logger.warning("interpret failed: %s", exc)
        raise InterpretFailed(str(exc)) from exc

    raw = payload.get("constraints") or []
    reply = str(payload.get("reply") or "")
    if not isinstance(raw, list):
        raise InterpretFailed("model returned a non-list for constraints")
    return [c for c in raw if isinstance(c, dict)], reply
