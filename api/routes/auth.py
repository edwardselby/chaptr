"""
Authentication routes for CHAPTR API.

Provides endpoints for user authentication:
- POST /api/auth/login - Username/password authentication → JWT token
- GET /api/auth/me - Get current authenticated user info

Security:
- Login endpoint validates credentials and issues JWT token
- /me endpoint requires valid JWT token in Authorization header
- Token expires after configured duration (default 24 hours)
"""

from fastapi import APIRouter, Depends

from api.config import MongoDB
from api.models import LoginRequest, LoginResponse
from api.repositories.users import UserRepository
from api.utils.auth import create_access_token, get_current_user
from api.utils.errors import AuthenticationError


router = APIRouter()


def get_user_repo() -> UserRepository:
    """
    Dependency: Get UserRepository instance.

    :return: UserRepository with database connection
    :rtype: UserRepository
    """
    db = MongoDB.get_database()
    return UserRepository(db)


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    repo: UserRepository = Depends(get_user_repo)
):
    """
    Authenticate user and issue JWT access token.

    Business Logic:
    1. Validate username and password against database
    2. Generate JWT token with user_id, username, role
    3. Return token + user info for client storage

    The client should:
    - Store access_token in localStorage
    - Include token in Authorization header: 'Bearer <token>'
    - Store user info for UI display

    :param credentials: Username and password
    :type credentials: LoginRequest
    :param repo: User repository (injected)
    :type repo: UserRepository
    :return: JWT token and user information
    :rtype: LoginResponse
    :raises AuthenticationError: If credentials are invalid (401)

    :Example:

    Request:
    >>> POST /api/auth/login
    >>> {
    ...     "username": "Edward",
    ...     "password": "password123"
    ... }

    Success Response (200):
    >>> {
    ...     "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    ...     "token_type": "bearer",
    ...     "user": {
    ...         "id": "550e8400-e29b-41d4-a716-446655440000",
    ...         "username": "Edward",
    ...         "role": "admin"
    ...     }
    ... }

    Failure Response (401):
    >>> {
    ...     "detail": "Invalid credentials"
    ... }
    """
    # Authenticate user (username + password verification)
    user = await repo.authenticate(
        username=credentials.username,
        password=credentials.password
    )

    # Authentication failed
    if not user:
        raise AuthenticationError("Invalid credentials")

    # Create JWT access token
    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role
    )

    # Return token + user info
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": str(user.id),
            "username": user.username,
            "role": user.role
        }
    )


@router.get("/auth/me", response_model=dict)
async def get_me(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current authenticated user information.

    Extracts user from JWT token in Authorization header.
    Used for:
    - Verifying token validity
    - Getting current user info for UI
    - Checking user role

    :param current_user: Current user from JWT token (injected)
    :type current_user: dict
    :return: User information (id, username, role)
    :rtype: dict
    :raises AuthenticationError: If token is missing, invalid, or expired (401)

    :Example:

    Request:
    >>> GET /api/auth/me
    >>> Headers: Authorization: Bearer eyJhbGci...

    Success Response (200):
    >>> {
    ...     "id": "550e8400-e29b-41d4-a716-446655440000",
    ...     "username": "Edward",
    ...     "role": "admin"
    ... }

    Failure Response (401 - missing token):
    >>> {
    ...     "detail": "Not authenticated"
    ... }

    Failure Response (401 - invalid token):
    >>> {
    ...     "detail": "Invalid token: Signature verification failed"
    ... }

    Failure Response (401 - expired token):
    >>> {
    ...     "detail": "Invalid token: Signature has expired"
    ... }
    """
    return current_user
