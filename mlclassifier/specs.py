"""
Classification specs — the pluggable "what am I looking for?" for the LLM
reviewer (:mod:`mlclassifier.llm_review`).

The LLM second-stage reviewer is use-case-agnostic: it sends a document's text to
Claude and asks "does this match the target class?". *What* the target class is
lives here, as data — one :class:`ClassificationSpec` per use case, in a registry.
Add a new document type (or a completely different use case such as news articles)
by registering another spec; no reviewer code changes. This mirrors the crawler's
pluggable :class:`~webscraper.profiles.base.ExtractionProfile` seam so a use case
is described in one place across the whole pipeline.

Register a spec::

    from mlclassifier.specs import ClassificationSpec, register
    register(ClassificationSpec(
        name="news_article",
        definition="a journalistic news article reporting a current event…",
        counter_examples="NOT an opinion column, ad, product page, or navigation index",
    ))

then run: ``python -m mlclassifier.llm_review --spec news_article …``
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationSpec:
    """A binary classification target, described for an LLM in plain language.

    ``definition`` says what the class *is*; ``counter_examples`` says what looks
    similar but is *not* it (this is what cuts false positives). The reviewer wraps
    both in a fixed JSON-output instruction, so specs stay declarative.
    """

    name: str
    definition: str
    counter_examples: str = ""

    def system_prompt(self) -> str:
        """Build the reviewer's system prompt from the spec (JSON-only output)."""
        counter = (f" It does NOT match if it is: {self.counter_examples}."
                   if self.counter_examples else "")
        return (
            "You decide whether a document matches a target class.\n"
            f"The document MATCHES if it is: {self.definition}.{counter}\n"
            "Judge from the actual text, not the filename. Answer with ONE compact "
            "JSON object and nothing else: "
            '{"is_match": true|false, "confidence": 0.0-1.0, "reason": "<=12 words"}'
        )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

_REGISTRY: dict[str, ClassificationSpec] = {}


def register(spec: ClassificationSpec) -> ClassificationSpec:
    """Add a spec to the registry (last registration under a name wins)."""
    _REGISTRY[spec.name] = spec
    return spec


def get_spec(name: str) -> ClassificationSpec:
    """Look up a registered spec by name, or raise with the available names."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown classification spec {name!r}; "
            f"registered: {sorted(_REGISTRY)}"
        ) from None


def available() -> list[str]:
    return sorted(_REGISTRY)


# --------------------------------------------------------------------------- #
# Built-in specs
# --------------------------------------------------------------------------- #

register(ClassificationSpec(
    name="modulhandbuch",
    definition=(
        "a German university 'Modulhandbuch' (module handbook) that systematically "
        "describes the modules of a degree programme — per module listing learning "
        "outcomes/competencies (Lernergebnisse/Qualifikationsziele), contents "
        "(Inhalte), workload/credits (ECTS/SWS) and exam form (Prüfungsform), "
        "usually for many modules of one Studiengang"
    ),
    counter_examples=(
        "a Prüfungsordnung/Studienordnung (regulations only), a single module "
        "datasheet, a timetable/Vorlesungsverzeichnis, a flyer, an application "
        "form, or general programme information"
    ),
))
