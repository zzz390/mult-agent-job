"""HTML parser tool for extracting job description content."""

import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 5
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_PROXY_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


class UnsafeUrlError(ValueError):
    """Raised when a URL resolves to a non-public network target."""


class DnsResolutionError(ConnectionError):
    """Raised when a public hostname cannot be resolved."""


def _assert_safe_url(url: str) -> None:
    """Validate scheme, credentials and every resolved IP address.

    DNS failures and SSRF blocks are intentionally different exceptions.  A
    temporary or misspelled hostname is not an SSRF attempt and should not be
    reported as one.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"Unsupported URL scheme: {parsed.scheme or '(missing)'}")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs containing credentials are not allowed")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL hostname is missing")
    try:
        ipaddress.ip_address(hostname)
        hostname_is_ip_literal = True
    except ValueError:
        hostname_is_ip_literal = False
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise DnsResolutionError(f"DNS resolution failed for {hostname}: {exc}") from exc

    for info in addr_info:
        ip = ipaddress.ip_address(info[4][0])
        # Clash/Mihomo fake-IP mode maps public domain names into the RFC 2544
        # benchmarking range and routes them through its DNS proxy.  Treat that
        # exact range as a domain-only proxy transport; a user-supplied literal
        # 198.18.x.x URL is still blocked below.
        if ip in _PROXY_FAKE_IP_NETWORK and not hostname_is_ip_literal:
            continue
        if not ip.is_global:
            raise UnsafeUrlError(f"Blocked non-public network address for {hostname}: {ip}")


def _validate_url(url: str) -> bool:
    """Backward-compatible boolean URL validator."""
    try:
        _assert_safe_url(url)
        return True
    except (UnsafeUrlError, DnsResolutionError, ValueError):
        return False


async def fetch_and_extract_html(url: str, timeout: float = 15.0) -> str:
    """Fetch a URL and extract main text content.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Extracted text content from the page
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        current_url = url
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, verify=True) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                _assert_safe_url(current_url)
                async with client.stream("GET", current_url, headers=headers) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Redirect response has no Location header")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not any(
                        item in content_type for item in ("text/html", "application/xhtml+xml", "text/plain")
                    ):
                        raise ValueError(f"Unsupported response type: {content_type}")
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
                        raise ValueError("Remote response exceeds size limit")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > _MAX_RESPONSE_BYTES:
                            raise ValueError("Remote response exceeds size limit")
                    encoding = response.encoding or "utf-8"
                    return extract_text_from_html(bytes(content).decode(encoding, errors="replace"))
            raise ValueError("Too many redirects")
    except UnsafeUrlError as e:
        logger.warning("Blocked unsafe URL %s: %s", url, e)
        return ""
    except DnsResolutionError as e:
        logger.warning("Unable to resolve URL %s: %s", url, e)
        return ""
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return ""


def extract_text_from_html(html: str) -> str:
    """Extract meaningful text from HTML content.

    Removes scripts, styles, navigation, and other non-content elements.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]):
        tag.decompose()

    # Try to find main content area
    main_content = soup.select_one(
        ".job-detail, .job-content, .position-detail, .job-description, main, article, .content"
    )

    if main_content:
        text = main_content.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)
