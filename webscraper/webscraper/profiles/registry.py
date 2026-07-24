"""
Profile registry — resolve a profile by name for ``CRAWL_PROFILE`` / ``--profile``.

Register a new extraction need by importing its class and adding it to
``_PROFILES``; it is then selectable by ``name`` everywhere (CLI, env, Lambda
event) with no other wiring.
"""

import logging

from webscraper.profiles.base import ExtractionProfile
from webscraper.profiles.html_content import HTMLContentProfile
from webscraper.profiles.modulhandbuch import ModulhandbuchProfile

logger = logging.getLogger(__name__)

# Profile name → class. Add new profiles here.
_PROFILES: dict[str, type[ExtractionProfile]] = {
    ExtractionProfile.name: ExtractionProfile,     # "generic"
    ModulhandbuchProfile.name: ModulhandbuchProfile,
    HTMLContentProfile.name: HTMLContentProfile,
}

# Default when none is specified. Kept as "modulhandbuch" so existing crawls
# behave unchanged; switch via CRAWL_PROFILE / --profile.
DEFAULT_PROFILE = "modulhandbuch"


def available_profiles() -> list[str]:
    """Sorted list of registered profile names."""
    return sorted(_PROFILES)


def get_profile(name: str | None = None) -> ExtractionProfile:
    """
    Return an instance of the named profile (falling back to the default).

    An unknown name logs a warning and falls back to the default rather than
    aborting the crawl — a typo should degrade, not crash a batch.
    """
    key = (name or DEFAULT_PROFILE).strip().lower()
    cls = _PROFILES.get(key)
    if cls is None:
        logger.warning(
            "Unknown crawl profile %r — falling back to %r. Available: %s",
            name, DEFAULT_PROFILE, ", ".join(available_profiles()),
        )
        cls = _PROFILES[DEFAULT_PROFILE]
    return cls()
