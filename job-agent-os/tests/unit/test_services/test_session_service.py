"""Focused tests for session result serialization."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from job_agent_os.services.session_service import SessionService


async def test_get_recommendations_adapts_graph_result_to_api_contract():
    user_id = uuid4()
    session_id = uuid4()
    service = SessionService(AsyncMock())
    service.store = AsyncMock()
    service.store.get.return_value = {
        "user_id": str(user_id),
        "results_summary": {
            "recommendations": [
                {
                    "overall_score": 20,
                    "matched_skills": {},
                    "missing_skills": {},
                    "risk_factors": ["未提供用户简历"],
                    "job": {
                        "id": str(uuid4()),
                        "title": "Python 工程师",
                        "salary": "15k-23k",
                        "skills_required": {},
                    },
                }
            ]
        },
    }

    items = await service.get_recommendations(
        SimpleNamespace(id=user_id), session_id
    )

    assert items[0]["match_score"] == 20
    assert items[0]["matched_skills"] == []
    assert items[0]["missing_skills"] == []
    assert items[0]["job"]["salary_range"] == "15k-23k"
    assert items[0]["job"]["skills_required"] == []

