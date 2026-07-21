"""HTML parser tool for extracting job description content."""

import httpx
from bs4 import BeautifulSoup


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
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return extract_text_from_html(response.text)
    except Exception:
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
    main_content = (
        soup.select_one(".job-detail, .job-content, .position-detail, .job-description, main, article, .content")
    )

    if main_content:
        text = main_content.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)
