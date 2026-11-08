import pytest
from backend.app.core.database import Base
from backend.app.core.security import create_access_token, decode_access_token, get_password_hash, verify_password


@pytest.mark.asyncio
async def test_database_tables_registered():
    """Verify that all 13 core tables plus users are registered on Base metadata."""
    expected_tables = {
        "products",
        "warehouses",
        "inventory_transactions",
        "stock_levels",
        "orders",
        "order_items",
        "suppliers",
        "purchase_orders",
        "po_items",
        "forecasts",
        "reorder_policies",
        "alerts",
        "audit_logs",
        "users",
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables), f"Missing tables: {expected_tables - actual_tables}"


def test_password_hashing():
    """Verify bcrypt password hashing and verification."""
    password = "SuperSecurePassword123!"
    hashed = get_password_hash(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_flow():
    """Verify JWT access token creation and payload decoding."""
    user_id = "user-12345"
    role = "admin"
    token = create_access_token(subject=user_id, role=role)
    assert isinstance(token, str)
    
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["role"] == role
    assert "exp" in payload


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client):
    """Test health check endpoint."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data


@pytest.mark.asyncio
async def test_auth_registration_and_login(async_client):
    """Test user registration, login, and protected /me endpoint."""
    # 1. Register admin user
    reg_payload = {
        "email": "admin@example.com",
        "password": "AdminPassword123!",
        "full_name": "Chief Inventory Officer",
        "role": "admin"
    }
    reg_response = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_response.status_code == 201
    user_data = reg_response.json()
    assert user_data["email"] == reg_payload["email"]
    assert user_data["role"] == "admin"
    assert "id" in user_data

    # 2. Login with credentials
    login_payload = {
        "email": "admin@example.com",
        "password": "AdminPassword123!"
    }
    login_response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert login_response.status_code == 200
    token_data = login_response.json()
    assert "access_token" in token_data
    assert token_data["role"] == "admin"
    token = token_data["access_token"]

    # 3. Access protected /me endpoint
    headers = {"Authorization": f"Bearer {token}"}
    me_response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == reg_payload["email"]
    assert me_data["role"] == "admin"

    # 4. Attempt login with invalid password
    bad_login = {
        "email": "admin@example.com",
        "password": "WrongPassword!"
    }
    bad_response = await async_client.post("/api/v1/auth/login", json=bad_login)
    assert bad_response.status_code == 401
