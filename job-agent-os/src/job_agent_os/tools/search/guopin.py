"""国聘 public job API adapter.

The current website loads jobs through a public JSON endpoint. Using that
protocol directly is faster and more stable than launching a browser and does
not depend on CAPTCHA handling, automation fingerprints, or disabled TLS
verification.
"""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import quote

import httpx

from job_agent_os.tools.search.base import PlatformAdapter


class GuopinAdapter(PlatformAdapter):
    """Low-frequency adapter for public state-owned-enterprise job data."""

    platform_name = "guopin"
    rate_limit = 5
    base_url = "https://www.iguopin.com"
    api_base_url = "https://gp-api.iguopin.com"
    render_with_playwright = False

    _district_paths: ClassVar[dict[str, str] | None] = None

    def _build_search_url(self, query: dict) -> str:
        """Return the current human-facing result URL for provenance/debugging."""
        keyword = self._extract_keyword(query)
        return f"{self.base_url}/job/list?keyword={quote(keyword)}"

    async def search(self, query: dict) -> list[dict]:
        """Search the public `/api/jobs/v1/recom-job` endpoint."""
        async with self._single_flight_search():
            return await self._search_once(query)

    async def _search_once(self, query: dict) -> list[dict]:
        """Run one Guopin query while holding its platform-wide search slot."""
        search_filters: dict[str, Any] = {
            "page": 1,
            "page_size": 20,
            "keyword": self._extract_keyword(query),
        }
        regions = [str(item).strip() for item in query.get("region", []) if item]
        if regions:
            district_path = await self._resolve_district_path(regions[0])
            if district_path:
                search_filters["district"] = [district_path]

        payload = {
            "search": search_filters,
            "recom": {
                "update_time": True,
                "company_nature": True,
                "hot_job": True,
            },
        }
        response_data = await self._request_jobs(payload)
        data = response_data.get("data") or {}
        raw_jobs = data.get("list") or []
        requested_types = {str(item).strip() for item in query.get("company_type", []) if item}

        jobs: list[dict] = []
        for raw in raw_jobs:
            job = self._parse_api_job(raw)
            if not job:
                continue
            if requested_types and not self._matches_company_type(str(job.get("company_type") or ""), requested_types):
                continue
            jobs.append(job)
        return jobs

    async def _request_jobs(self, payload: dict) -> dict:
        await self._rate_limit_wait()
        async with httpx.AsyncClient(**self._httpx_client_kwargs()) as client:
            response = await client.post(
                f"{self.api_base_url}/api/jobs/v1/recom-job",
                json=payload,
                headers=self._api_headers(),
            )
            response.raise_for_status()
            result = response.json()
        if result.get("code") != 200:
            raise ConnectionError(result.get("msg") or "Guopin API request failed")
        return result

    async def _resolve_district_path(self, region: str) -> str | None:
        if self.__class__._district_paths is None:
            await self._rate_limit_wait()
            async with httpx.AsyncClient(**self._httpx_client_kwargs()) as client:
                response = await client.get(
                    f"{self.api_base_url}/api/base/districts/v1/tree",
                    headers=self._api_headers(),
                )
                response.raise_for_status()
                result = response.json()
            if result.get("code") != 200:
                raise ConnectionError(result.get("msg") or "Guopin district API request failed")
            self.__class__._district_paths = self._build_district_paths(result.get("data") or [])

        normalized = self._normalize_region(region)
        return (self.__class__._district_paths or {}).get(normalized)

    @classmethod
    def _build_district_paths(cls, tree: list[dict]) -> dict[str, str]:
        paths: dict[str, str] = {}

        def walk(nodes: list[dict], parents: tuple[str, ...] = ()) -> None:
            for node in nodes:
                value = str(node.get("value") or "").strip()
                if not value:
                    continue
                current = (*parents, value)
                path = ".".join(current)
                for key in (node.get("label"), node.get("name")):
                    if key:
                        # Deeper paths intentionally replace province-level
                        # aliases such as 北京 with the more precise city path.
                        paths[cls._normalize_region(str(key))] = path
                children = node.get("children") or []
                if isinstance(children, list):
                    walk(children, current)

        walk(tree)
        return paths

    @staticmethod
    def _normalize_region(region: str) -> str:
        return str(region).strip().removesuffix("省").removesuffix("市")

    def _api_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._random_ua(),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "Device": "pc",
            "Version": "5.2.300",
            "Subsite": "iguopin",
        }

    def _parse_api_job(self, raw: dict) -> dict | None:
        title = str(raw.get("job_name") or "").strip()
        company = str(raw.get("company_name") or "").strip()
        job_id = str(raw.get("job_id") or "").strip()
        if not title or not company or not job_id:
            return None

        districts = raw.get("district_list") or []
        locations = [
            str(item.get("area_cn") or "").strip()
            for item in districts
            if isinstance(item, dict) and item.get("area_cn")
        ]
        company_info = raw.get("company_info") or {}
        salary = self._format_salary(raw)
        deadline = str(raw.get("end_time") or "")[:10]
        majors = [str(item) for item in raw.get("major_cn") or [] if item]

        return {
            "title": title,
            "company": company,
            "company_type": str(company_info.get("nature_cn") or ""),
            "location": "、".join(dict.fromkeys(locations)),
            "salary": salary,
            "salary_min": raw.get("min_wage"),
            "salary_max": raw.get("max_wage"),
            "education": str(raw.get("education_cn") or ""),
            "experience": str(raw.get("experience_cn") or ""),
            "skills_required": majors,
            "raw_description": str(raw.get("contents") or ""),
            "deadline": deadline,
            "source_url": f"{self.base_url}/job/detail?id={quote(job_id)}",
            "source_platform": self.platform_name,
        }

    @staticmethod
    def _format_salary(raw: dict) -> str:
        if raw.get("is_negotiable"):
            return "面议"
        minimum = raw.get("min_wage")
        maximum = raw.get("max_wage")
        if minimum is None and maximum is None:
            return ""
        unit = str(raw.get("wage_unit_cn") or "元/月")
        if minimum == maximum:
            return f"{minimum}{unit}"
        return f"{minimum or 0}-{maximum or 0}{unit}"

    @staticmethod
    def _matches_company_type(actual: str, requested: set[str]) -> bool:
        if not requested:
            return True
        if any(item in actual for item in requested):
            return True
        state_owned = {"国企", "央企", "国有企业", "中央企业"}
        return bool(requested & state_owned) and actual in state_owned

    async def parse_result(self, raw: dict) -> dict:
        return self._parse_api_job(raw) or raw
