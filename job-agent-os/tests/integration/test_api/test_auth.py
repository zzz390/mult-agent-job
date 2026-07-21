"""Integration tests for Authentication API."""


class TestRegister:
    """Test user registration."""

    async def test_register_success(self, client):
        """Should register a new user and return tokens."""
        response = await client.post(
            "/v1/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["access_token"] is not None
        assert data["data"]["refresh_token"] is not None
        assert data["data"]["username"] == "newuser"
        assert data["data"]["token_type"] == "bearer"

    async def test_register_with_phone(self, client):
        """Should register with optional phone field."""
        response = await client.post(
            "/v1/auth/register",
            json={
                "username": "phoneuser",
                "email": "phoneuser@example.com",
                "password": "password123",
                "phone": "13800138000",
            },
        )
        assert response.status_code == 201

    async def test_register_duplicate_email(self, client):
        """Should reject duplicate email registration."""
        payload = {
            "username": "user1",
            "email": "dup@example.com",
            "password": "password123",
        }
        # First registration
        response1 = await client.post("/v1/auth/register", json=payload)
        assert response1.status_code == 201

        # Duplicate email
        payload2 = {
            "username": "user2",
            "email": "dup@example.com",
            "password": "password456",
        }
        response2 = await client.post("/v1/auth/register", json=payload2)
        assert response2.status_code == 409

    async def test_register_duplicate_username(self, client):
        """Should reject duplicate username registration."""
        payload1 = {
            "username": "sameuser",
            "email": "first@example.com",
            "password": "password123",
        }
        response1 = await client.post("/v1/auth/register", json=payload1)
        assert response1.status_code == 201

        payload2 = {
            "username": "sameuser",
            "email": "second@example.com",
            "password": "password456",
        }
        response2 = await client.post("/v1/auth/register", json=payload2)
        assert response2.status_code == 409

    async def test_register_invalid_email(self, client):
        """Should reject invalid email format."""
        response = await client.post(
            "/v1/auth/register",
            json={
                "username": "baduser",
                "email": "not-an-email",
                "password": "password123",
            },
        )
        assert response.status_code == 422

    async def test_register_short_password(self, client):
        """Should reject password shorter than 8 chars."""
        response = await client.post(
            "/v1/auth/register",
            json={
                "username": "shortpw",
                "email": "shortpw@example.com",
                "password": "short",
            },
        )
        assert response.status_code == 422


class TestLogin:
    """Test user login."""

    async def test_login_success(self, client):
        """Should login with valid credentials."""
        # Register first
        await client.post(
            "/v1/auth/register",
            json={
                "username": "loginuser",
                "email": "login@example.com",
                "password": "password123",
            },
        )

        # Login
        response = await client.post(
            "/v1/auth/login",
            json={
                "email": "login@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["access_token"] is not None
        assert data["data"]["username"] == "loginuser"

    async def test_login_wrong_password(self, client):
        """Should reject wrong password."""
        # Register first
        await client.post(
            "/v1/auth/register",
            json={
                "username": "wrongpw",
                "email": "wrongpw@example.com",
                "password": "correctpass",
            },
        )

        # Login with wrong password
        response = await client.post(
            "/v1/auth/login",
            json={
                "email": "wrongpw@example.com",
                "password": "wrongpass",
            },
        )
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client):
        """Should reject login for non-existent user."""
        response = await client.post(
            "/v1/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 401


class TestRefreshToken:
    """Test token refresh."""

    async def test_refresh_token_success(self, client):
        """Should refresh access token with valid refresh token."""
        # Register and get tokens
        reg_response = await client.post(
            "/v1/auth/register",
            json={
                "username": "refreshuser",
                "email": "refresh@example.com",
                "password": "password123",
            },
        )
        tokens = reg_response.json()["data"]

        # Refresh
        response = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["access_token"] is not None
        assert data["data"]["refresh_token"] is not None
        assert data["data"]["token_type"] == "bearer"

    async def test_refresh_with_invalid_token(self, client):
        """Should reject invalid refresh token."""
        response = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": "invalid-token-string"},
        )
        assert response.status_code == 401

    async def test_refresh_with_access_token_fails(self, client):
        """Should reject access token used as refresh token."""
        # Register and get tokens
        reg_response = await client.post(
            "/v1/auth/register",
            json={
                "username": "mixuptoken",
                "email": "mixup@example.com",
                "password": "password123",
            },
        )
        tokens = reg_response.json()["data"]

        # Try to refresh with access token (should fail)
        response = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": tokens["access_token"]},
        )
        assert response.status_code == 401


class TestLogout:
    """Test logout."""

    async def test_logout_success(self, client):
        """Should return success on logout."""
        response = await client.post("/v1/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
