"""URL safety diagnostics should distinguish DNS failures from SSRF blocks."""

import logging
import socket
from unittest.mock import patch

from job_agent_os.tools.parse.html_parser import _assert_safe_url, fetch_and_extract_html


async def test_dns_failure_is_not_reported_as_ssrf(caplog):
    with (
        patch("job_agent_os.tools.parse.html_parser.socket.getaddrinfo") as getaddrinfo,
        caplog.at_level(logging.WARNING),
    ):
        getaddrinfo.side_effect = socket.gaierror(-2, "Name or service not known")
        result = await fetch_and_extract_html("https://missing.example.invalid/jobs")

    assert result == ""
    assert "Unable to resolve URL" in caplog.text
    assert "SSRF" not in caplog.text


async def test_private_address_is_blocked_as_unsafe(caplog):
    with (
        patch(
            "job_agent_os.tools.parse.html_parser.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))],
        ),
        caplog.at_level(logging.WARNING),
    ):
        result = await fetch_and_extract_html("https://internal.example/jobs")

    assert result == ""
    assert "Blocked unsafe URL" in caplog.text


def test_proxy_fake_ip_is_allowed_only_for_domain_names():
    fake_ip_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.172", 0))]
    with patch(
        "job_agent_os.tools.parse.html_parser.socket.getaddrinfo",
        return_value=fake_ip_result,
    ):
        _assert_safe_url("https://www.example.com/jobs")

        try:
            _assert_safe_url("https://198.18.0.172/jobs")
        except ValueError:
            pass
        else:
            raise AssertionError("literal fake-IP URL must remain blocked")
