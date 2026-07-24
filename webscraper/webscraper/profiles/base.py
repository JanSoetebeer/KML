"""
The :class:`ExtractionProfile` contract and shared scoring helpers.

A profile is the swappable, use-case-specific layer the generic crawl engine
delegates to. It answers four questions about the crawl:

* ``score_link(url, anchor)``   — how promising is this link? (frontier priority)
* ``is_target(url, anchor)``    — is this link a resource to *fetch and extract*?
* ``extract_target(resp, ...)`` — turn a fetched **binary resource** into item(s)
* ``extract_page(resp, ...)``   — turn a fetched **HTML page** into item(s)

The three extraction shapes map onto these hooks:

* **Document harvesting** — ``is_target`` picks file links (PDF/DOCX/…) and
  ``extract_target`` yields a :class:`~webscraper.items.DocumentItem`. (The base
  class already implements exactly this — a neutral, no-keyword harvester.)
* **HTML content extraction** — ``target_extensions`` is empty (nothing is
  downloaded) and ``extract_page`` yields a
  :class:`~webscraper.items.ContentItem` per crawled page.
* **Structured field extraction** — same as above but ``extract_page`` fills the
  ``fields`` slot with values pulled from the page via CSS/XPath.

Profiles that steer the crawl by keyword can subclass
:class:`KeywordScoredProfile` and just declare token → weight maps.
"""

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

from webscraper.items import DocumentItem

# Neutral default: harvest common document types with no keyword bias.
DEFAULT_TARGET_EXTENSIONS = frozenset({".pdf", ".doc", ".docx"})

# Document extension → Content-Type, so a link that resolves to a document but
# has no usable extension in its URL (a script-served download such as
# ``…/show_document.asp?id=…`` or ``download.php?id=…``) is still recognised by
# the response's Content-Type. The reverse map drives that lookup.
_EXT_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
}
_MIME_EXT = {mime: ext for ext, mime in _EXT_MIME.items()}
_MIME_EXT.update({"text/rtf": ".rtf", "application/x-pdf": ".pdf"})


def _ext_from_content_type(response) -> str:
    """Map a response's Content-Type to a document extension (e.g. ``.pdf``), or ``""``."""
    ctype = response.headers.get("Content-Type", b"")
    if isinstance(ctype, (bytes, bytearray)):
        ctype = ctype.decode("latin-1", "ignore")
    ctype = ctype.split(";")[0].strip().lower()
    return _MIME_EXT.get(ctype, "")

# Umlaut / ß folding so German anchor text ("Modulhandbücher",
# "Prüfungsordnung") matches ASCII keyword tokens.
_FOLD_MAP = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})


def fold(text: str) -> str:
    """Lowercase and fold German umlauts/ß for keyword matching."""
    if not text:
        return ""
    return text.translate(_FOLD_MAP).lower()


def keyword_score(url: str, anchor_text: str, positive: dict, negative: dict) -> int:
    """Sum token weights found in a link's (folded) URL + anchor text."""
    hay = fold(url) + " ␟ " + fold(anchor_text)
    score = 0
    for token, weight in positive.items():
        if token in hay:
            score += weight
    for token, weight in negative.items():
        if token in hay:
            score += weight
    return score


class ExtractionProfile:
    """
    Base profile: a neutral document harvester.

    Out of the box this downloads every ``target_extensions`` file it finds,
    with no keyword steering (``score_link`` returns 0, so the crawl explores
    breadth-first within its budget). Subclass to specialise any hook.
    """

    #: Registry key used for ``CRAWL_PROFILE`` / ``--profile``.
    name = "generic"
    #: File extensions treated as downloadable target resources. Empty ⇒ the
    #: profile downloads nothing and works purely via ``extract_page``.
    target_extensions = DEFAULT_TARGET_EXTENSIONS

    # -- frontier control ------------------------------------------------------

    def score_link(self, url: str, anchor_text: str = "") -> int:
        """Priority for a follow/target link. Higher = fetched sooner. 0 = neutral."""
        return 0

    def is_target(self, url: str, anchor_text: str = "") -> bool:
        """True if *url* is a resource to fetch and hand to ``extract_target``."""
        if not self.target_extensions:
            return False
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in self.target_extensions)

    def is_target_response(self, response) -> bool:
        """
        True if a *fetched* response is a target document, judged by its
        Content-Type. Catches documents whose URL has no usable extension — a
        script-served download like ``…/show_document.asp?id=…`` — which
        ``is_target`` (URL-only) cannot see until the response is in hand.
        """
        if not self.target_extensions:
            return False
        ext = _ext_from_content_type(response)
        return bool(ext) and ext in self.target_extensions

    # -- extraction ------------------------------------------------------------

    def extract_target(self, response, source_page: str, spider):
        """
        Turn a fetched binary resource into item(s). Default: one
        :class:`DocumentItem` carrying the raw bytes (document harvesting).
        """
        url = response.url
        filename = urlparse(url).path.split("/")[-1] or "unknown"
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        # Script-served document (URL has no document extension): infer the type
        # from the Content-Type and give it a collision-free filename — such URLs
        # share a path (…/show_document.asp) and differ only by query string, so a
        # bare basename would overwrite in S3/on disk.
        if extension not in self.target_extensions:
            inferred = _ext_from_content_type(response)
            if inferred:
                stem = (filename.rsplit(".", 1)[0] if "." in filename else filename) or "document"
                digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
                filename = f"{stem}-{digest}{inferred}"
                extension = inferred
        content = response.body
        yield DocumentItem(
            url=url,
            filename=filename,
            source_page=source_page,
            file_type=extension.lstrip("."),
            content=content,
            size_bytes=len(content),
            crawled_at=datetime.now(timezone.utc).isoformat(),
            job_id=spider.job_id,
            extra={},
        )

    def extract_page(self, response, spider):
        """
        Turn a fetched HTML page into item(s). Default: none (document-harvesting
        profiles act only on target resources). Override for HTML-content or
        structured-field extraction.
        """
        return ()


class KeywordScoredProfile(ExtractionProfile):
    """
    A profile whose frontier priority comes from keyword token → weight maps.

    Subclasses declare :attr:`POSITIVE_TOKENS` and :attr:`NEGATIVE_TOKENS`
    (matched as substrings against the folded URL + anchor text). This is how a
    profile steers a small crawl budget toward the pages that matter.
    """

    POSITIVE_TOKENS: dict = {}
    NEGATIVE_TOKENS: dict = {}

    def score_link(self, url: str, anchor_text: str = "") -> int:
        return keyword_score(url, anchor_text, self.POSITIVE_TOKENS, self.NEGATIVE_TOKENS)
