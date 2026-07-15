"""
Pytest Fixtures & Application Factory for Testing
===================================================
Provides:
  - Flask test app with mocked Cognito auth
  - Database fixtures (test DB with fresh schema per session)
  - Auth helper to inject user_id into requests
  - Reusable test data factories
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

# Set test environment BEFORE importing app
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    # Neutral local default; set TEST_DATABASE_URL to your own test DB.
    "postgresql://postgres:postgres@localhost:5432/expense_tracker_test"
)
os.environ["COGNITO_USER_POOL_ID"] = "ap-south-1_TestPool"
os.environ["COGNITO_REGION"] = "ap-south-1"
os.environ["COGNITO_APP_CLIENT_ID"] = "test-client-id"
os.environ["FLASK_DEBUG"] = "true"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["FRONTEND_ORIGINS"] = "http://localhost:5173"


# ---- Fake user IDs for testing ----
TEST_USER_ID = "a1b2c3d4-e5f6-4a7b-89c0-d1e2f3a4b5c6"
TEST_USER_ID_2 = "f6e5d4c3-b2a1-4987-6543-210fedcba987"


@pytest.fixture(scope="session")
def app():
    """Create the Flask application for testing."""
    # Mock the JWKS fetching so we don't hit AWS
    with patch("auth.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = lambda s, *a: None
        mock_urlopen.return_value.read.return_value = json.dumps({"keys": []}).encode()

        from app import create_app
        test_app = create_app()
        test_app.config["TESTING"] = True

        yield test_app


@pytest.fixture(scope="session")
def _db_init(app):
    """Initialize test database once per test session."""
    from database import init_pool, run_migrations, shutdown_pool

    init_pool(app)
    run_migrations()

    yield

    shutdown_pool()


@pytest.fixture
def client(app, _db_init):
    """Flask test client with fresh transaction per test."""
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers():
    """
    Returns a function that patches auth to inject a specific user_id.
    
    Usage:
        def test_something(client, auth_headers):
            headers = auth_headers(TEST_USER_ID)
            response = client.get("/expenses", headers=headers)
    """
    def _make_headers(user_id=TEST_USER_ID):
        return {
            "Authorization": f"Bearer test-token-{user_id}",
            "Content-Type": "application/json",
        }
    return _make_headers


@pytest.fixture(autouse=True)
def mock_auth():
    """
    Auto-mock the auth decorator for all tests.
    Extracts user_id from the test token format.
    """
    def fake_require_auth(f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            from flask import request, g
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer test-token-"):
                user_id = auth_header.replace("Bearer test-token-", "")
                g.user_id = user_id
            else:
                from flask import jsonify
                return jsonify({
                    "success": False,
                    "error": {"code": "UNAUTHORIZED", "message": "Missing auth token"}
                }), 401
            return f(*args, **kwargs)
        return decorated

    with patch("auth.require_auth", side_effect=fake_require_auth):
        with patch("auth.get_current_user_id") as mock_get_user:
            # Default to TEST_USER_ID
            from flask import g
            mock_get_user.side_effect = lambda: getattr(g, "user_id", TEST_USER_ID)
            yield


# ---- Test Data Factories ----

class TestDataFactory:
    """Helper to create test data."""

    @staticmethod
    def expense_data(
        date="2026-01-15",
        amount="100.00",
        category_id=None,
        note="Test expense",
    ):
        return {
            "date": date,
            "amount": amount,
            "category_id": category_id or "placeholder-will-be-replaced",
            "note": note,
        }

    @staticmethod
    def category_data(name="Test Category"):
        return {"name": name}

    @staticmethod
    def income_data(
        date="2026-01-15",
        amount="5000.00",
        source="Salary",
        description="Monthly salary",
    ):
        return {
            "date": date,
            "amount": amount,
            "source": source,
            "description": description,
        }

    @staticmethod
    def budget_data(category_id=None, amount="1000.00"):
        return {
            "category_id": category_id or "placeholder",
            "amount": amount,
        }


@pytest.fixture
def factory():
    """Test data factory fixture."""
    return TestDataFactory()
