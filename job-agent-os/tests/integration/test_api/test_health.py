"""Integration tests for Health/Monitoring API."""


class TestHealthCheck:
    """Test health check endpoints."""

    async def test_root_health_endpoint(self, client):
        """Root /health should return ok status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    async def test_monitoring_health_endpoint(self, client, mock_redis):
        """GET /v1/monitoring/health should return service status."""
        response = await client.get("/v1/monitoring/health")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        health_data = data["data"]
        assert "status" in health_data
        assert "services" in health_data
        assert "timestamp" in health_data

    async def test_health_response_format(self, client):
        """Health response should follow unified format."""
        response = await client.get("/v1/monitoring/health")
        data = response.json()
        # Unified response format
        assert "code" in data
        assert "message" in data
        assert "data" in data
        assert "meta" in data
        assert "request_id" in data["meta"]
        assert "timestamp" in data["meta"]


class TestTokenUsage:
    """Test token usage endpoint."""

    async def test_token_usage_requires_auth(self, client):
        """Token usage should require authentication."""
        response = await client.get("/v1/monitoring/token-usage")
        assert response.status_code == 401

    async def test_token_usage_with_auth(self, client, auth_headers):
        """Token usage should return stats for authenticated user."""
        response = await client.get(
            "/v1/monitoring/token-usage",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "total_tokens" in data["data"]
        assert "by_agent" in data["data"]
        assert "budget_remaining" in data["data"]
