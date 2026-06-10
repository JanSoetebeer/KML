import logging
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}


class URLValidationError(ValueError):
    """Raised when a URL fails validation."""


def validate(url: str, ping: bool = True, timeout: int = 10) -> str:
    """
    Validate *url* and return the normalised URL string.

    Steps
    -----
    1. Parse and check scheme (http / https only).
    2. Ensure a non-empty hostname is present.
    3. Resolve the hostname via DNS.
    4. Optionally probe the server to confirm it is reachable:
       - Tries HEAD first (lightweight).
       - Falls back to GET (headers only) if the server returns 405 / 501.
       - Only raises on *connection-level* failures (timeout, refused, DNS).
       - HTTP 4xx / 5xx status codes are logged as warnings but do not abort
         validation — Scrapy handles those during the actual crawl.

    Parameters
    ----------
    url:
        Raw URL string provided by the caller.
    ping:
        When ``True`` (default) a probe request is sent to verify the server
        responds before starting a full crawl.
    timeout:
        Seconds to wait for the probe request / DNS lookup.

    Returns
    -------
    str
        The validated, normalised URL.

    Raises
    ------
    URLValidationError
        On scheme / hostname / DNS / connection-level failures.
    """
    url = url.strip()

    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise URLValidationError(
            f"Unsupported scheme '{parsed.scheme}'. Only {ALLOWED_SCHEMES} are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError(f"No hostname found in URL: {url!r}")

    try:
        socket.getaddrinfo(hostname, None)
        logger.debug("DNS resolved '%s' successfully.", hostname)
    except socket.gaierror as exc:
        raise URLValidationError(
            f"DNS resolution failed for '{hostname}': {exc}"
        ) from exc

    if ping:
        _probe(url, timeout)

    logger.info("URL validated: %s", url)
    return url


def _probe(url: str, timeout: int) -> None:
    """
    Send a lightweight probe to verify the server is reachable.

    Tries HEAD; falls back to a streaming GET on 405 / 501.
    Only raises :class:`URLValidationError` on connection-level errors.
    HTTP status codes are warnings — the scraper may still succeed.
    """
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        status = response.status_code
        logger.debug("HEAD %s -> HTTP %s", url, status)

        if status in (405, 501):
            logger.debug(
                "Server does not support HEAD (%s); retrying with GET.", status
            )
            response = requests.get(
                url, timeout=timeout, allow_redirects=True, stream=True
            )
            response.close()
            status = response.status_code
            logger.debug("GET %s -> HTTP %s", url, status)

        if status >= 400:
            logger.warning(
                "Probe returned HTTP %s for %r — proceeding anyway; "
                "Scrapy will handle the response during the crawl.",
                status,
                url,
            )

    except requests.ConnectionError as exc:
        raise URLValidationError(
            f"Could not connect to '{url}': {exc}"
        ) from exc
    except requests.Timeout as exc:
        raise URLValidationError(
            f"Connection timed out for '{url}': {exc}"
        ) from exc
    except requests.RequestException as exc:
        raise URLValidationError(
            f"Probe failed for '{url}': {exc}"
        ) from exc
