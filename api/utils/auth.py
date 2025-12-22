"""
Authentication utilities for CHAPTR API.

Provides password hashing, JWT token creation/validation, and FastAPI dependencies
for authentication and authorization.

Security:
- Passwords hashed using bcrypt (auto-salted, industry standard)
- JWT tokens signed with HS256 algorithm
- Token expiration enforced (configurable, default 24 hours)
- Role-based access control via dependencies
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from api.config import settings
from api.utils.errors import AuthenticationError, AuthorizationError


#: Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

#: HTTP Bearer security scheme for extracting tokens from Authorization header
security = HTTPBearer()


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt.

    Bcrypt automatically generates a salt and embeds it in the hash.
    The resulting hash starts with '$2b$' and is safe to store.

    :param password: Plain text password to hash
    :type password: str
    :return: Bcrypt hashed password (includes salt)
    :rtype: str

    :Example:

    >>> hash_password("mysecretpassword")
    '$2b$12$...'  # 60-character bcrypt hash
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    Verify a plain text password against a bcrypt hash.

    Extracts the salt from the hash and compares the hashed plain password
    against the stored hash using constant-time comparison.

    :param plain_password: Plain text password to verify
    :type plain_password: str
    :param password_hash: Bcrypt hash to verify against
    :type password_hash: str
    :return: True if password matches hash, False otherwise
    :rtype: bool

    :Example:

    >>> password_hash = hash_password("secret")
    >>> verify_password("secret", password_hash)
    True
    >>> verify_password("wrong", password_hash)
    False
    """
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(
    user_id: UUID,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token for authenticated user.

    Token payload includes:
    - sub (subject): User ID as string
    - username: Display name
    - role: User role (admin/user)
    - exp (expiration): UTC timestamp

    Token is signed with SECRET_KEY using HS256 algorithm.

    Role-based expiration (Phase 1.5 enhancement):
    - Admin users: 7 days (10080 minutes) for convenience
    - Regular users: 24 hours (1440 minutes) default
    - Can be overridden with expires_delta parameter

    :param user_id: Unique user identifier
    :type user_id: UUID
    :param username: User display name
    :type username: str
    :param role: User role (admin or user)
    :type role: str
    :param expires_delta: Optional custom expiration timedelta (defaults to role-based)
    :type expires_delta: Optional[timedelta]
    :return: Encoded JWT token
    :rtype: str

    :Example:

    >>> from uuid import uuid4
    >>> user_id = uuid4()
    >>> token = create_access_token(user_id, "Edward", "admin")
    >>> # Admin gets 7-day token
    >>> token = create_access_token(user_id, "User", "user")
    >>> # Regular user gets 24-hour token
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Role-based token expiration
        # Admin: 7 days (convenient for home use)
        # User: 24 hours (standard session)
        expiration_minutes = 10080 if role == "admin" else settings.access_token_expire_minutes
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=expiration_minutes
        )

    to_encode = {
        "sub": str(user_id),  # Convert UUID to string for JSON serialization
        "username": username,
        "role": role,
        "exp": expire
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm
    )

    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT access token.

    Validates:
    - Token signature (ensures not tampered)
    - Token expiration (ensures not expired)
    - Presence of required claims (sub)

    :param token: Encoded JWT token
    :type token: str
    :return: Decoded token payload with user info
    :rtype: Dict[str, Any]
    :raises AuthenticationError: If token is invalid, expired, or missing claims

    :Example:

    >>> token = create_access_token(user_id, "Edward", "admin")
    >>> payload = decode_access_token(token)
    >>> payload["username"]
    'Edward'
    >>> payload["role"]
    'admin'

    # Invalid token raises AuthenticationError
    >>> decode_access_token("invalid_token")
    AuthenticationError: Invalid token
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )

        # Validate required claim (sub = user_id)
        if payload.get("sub") is None:
            raise AuthenticationError("Invalid token: missing user ID")

        return payload

    except JWTError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    FastAPI dependency: Extract and validate current user from JWT token.

    Extracts token from Authorization header (Bearer scheme), decodes it,
    and returns user information for use in protected endpoints.

    :param credentials: HTTP Bearer credentials from Authorization header
    :type credentials: HTTPAuthorizationCredentials
    :return: User information dict with id, username, role
    :rtype: Dict[str, Any]
    :raises AuthenticationError: If token is missing, invalid, or expired

    :Example:

    >>> from fastapi import Depends
    >>>
    >>> @router.get("/protected")
    >>> async def protected_endpoint(current_user: dict = Depends(get_current_user)):
    >>>     return {"message": f"Hello {current_user['username']}!"}
    """
    payload = decode_access_token(credentials.credentials)

    return {
        "id": payload.get("sub"),
        "username": payload.get("username"),
        "role": payload.get("role")
    }


async def get_current_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency: Require admin role for protected endpoint.

    Builds on get_current_user dependency to enforce admin-only access.
    Used for administrative endpoints like settings updates.

    :param current_user: Current user from get_current_user dependency
    :type current_user: Dict[str, Any]
    :return: User information (same as current_user)
    :rtype: Dict[str, Any]
    :raises AuthorizationError: If user is not admin

    :Example:

    >>> from fastapi import Depends
    >>>
    >>> @router.put("/settings")
    >>> async def update_settings(
    >>>     data: SettingsUpdate,
    >>>     current_user: dict = Depends(get_current_admin_user)
    >>> ):
    >>>     # Only admin users can reach this code
    >>>     return await repo.update(data)
    """
    if current_user["role"] != "admin":
        raise AuthorizationError("Admin access required")

    return current_user
