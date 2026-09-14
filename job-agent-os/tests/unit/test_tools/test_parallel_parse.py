"""Tests for concurrent JD structuring (issue #9)."""

from unittest.mock import patch

from job_agent_os.tools.parse.jd_structurer import structure_jds_parallel


def _make_jobs(n: int) -> list[dict]:
    return [
        {
            "title": f"工程师{i}",
            "company": f"公司{i}",
            "raw_description": "熟悉Python",
            "source_platform": "boss",
            "source_url": f"https://example.com/job/{i}",
        }
        for i in range(n)
    ]


class TestStructureJdsParallel:
    async def test_empty_input(self):
        parsed, failures = await structure_jds_parallel([])
        assert parsed == []
        assert failures == []

    async def test_all_parsed(self):
        async def fake_structure(**kwargs):
            return {
                "title": kwargs["title"],
                "company": kwargs["company"],
                "skills_required": ["Python"],
                "parse_confidence": 0.9,
            }

        with patch(
            "job_agent_os.tools.parse.jd_structurer.structure_jd",
            side_effect=fake_structure,
        ):
            parsed, failures = await structure_jds_parallel(_make_jobs(8))

        assert len(parsed) == 8
        assert failures == []
        assert all(p["parse_confidence"] == 0.9 for p in parsed)

    async def test_low_confidence_marked_as_failure(self):
        async def fake_structure(**kwargs):
            return {
                "title": kwargs["title"],
                "company": kwargs["company"],
                "parse_confidence": 0.4,  # below threshold
            }

        with patch(
            "job_agent_os.tools.parse.jd_structurer.structure_jd",
            side_effect=fake_structure,
        ):
            parsed, failures = await structure_jds_parallel(_make_jobs(3))

        # Low-confidence jobs stay as passthrough entries but are flagged
        assert len(parsed) == 3
        assert len(failures) == 3
        assert all(p["parse_note"] == "fallback_unparsed" for p in parsed)

    async def test_exceptions_dont_kill_batch(self):
        calls = {"n": 0}

        async def fake_structure(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("LLM exploded")
            return {
                "title": kwargs["title"],
                "company": kwargs["company"],
                "parse_confidence": 0.8,
            }

        with patch(
            "job_agent_os.tools.parse.jd_structurer.structure_jd",
            side_effect=fake_structure,
        ):
            parsed, failures = await structure_jds_parallel(_make_jobs(3))

        # Failed job becomes a passthrough entry; others succeed
        assert len(parsed) == 3
        assert len(failures) == 1

    async def test_concurrency_is_bounded(self):
        """No more than max_concurrency jobs run at the same time."""
        import asyncio

        active = {"current": 0, "max_seen": 0}

        async def fake_structure(**kwargs):
            active["current"] += 1
            active["max_seen"] = max(active["max_seen"], active["current"])
            await asyncio.sleep(0.01)
            active["current"] -= 1
            return {
                "title": kwargs["title"],
                "company": kwargs["company"],
                "parse_confidence": 0.9,
            }

        with patch(
            "job_agent_os.tools.parse.jd_structurer.structure_jd",
            side_effect=fake_structure,
        ):
            await structure_jds_parallel(_make_jobs(20), max_concurrency=5)

        assert active["max_seen"] <= 5
        assert active["max_seen"] >= 2  # sanity: it actually ran in parallel
