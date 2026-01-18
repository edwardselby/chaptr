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
    tenant_id: UUID,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token for authenticated user.

    Token payload includes:
    - sub (subject): User ID as string
    - username: Display name
    - role: User role (super_admin/admin/user)
    - tenant_id: Tenant identifier for multi-tenancy
    - exp (expiration): UTC timestamp

    Token is signed with SECRET_KEY using HS256 algorithm.

    Token expiration (spec v3.0):
    - All users: 24 hours (1440 minutes) default
    - Can be overridden with expires_delta parameter

    :param user_id: Unique user identifier
    :type user_id: UUID
    :param username: User display name
    :type username: str
    :param role: User role (super_admin, admin, or user)
    :type role: str
    :param tenant_id: Tenant identifier (admin's user_id)
    :type tenant_id: UUID
    :param expires_delta: Optional custom expiration timedelta (defaults to 24 hours)
    :type expires_delta: Optional[timedelta]
    :return: Encoded JWT token
    :rtype: str

    :Example:

    >>> from uuid import uuid4
    >>> user_id = uuid4()
    >>> tenant_id = uuid4()
    >>> token = create_access_token(user_id, "Edward", "admin", tenant_id)
    >>> # All users get 24-hour tokens per spec v3.0
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Standard 24-hour expiration for all users (spec v3.0)
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode = {
        "sub": str(user_id),  # Convert UUID to string for JSON serialization
        "username": username,
        "role": role,
        "tenant_id": str(tenant_id),  # Include tenant_id for multi-tenancy
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
    :return: User information dict with id, username, role, tenant_id
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
        "role": payload.get("role"),
        "tenant_id": payload.get("tenant_id")  # Include tenant_id for multi-tenancy
    }


async def get_current_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency: Require admin or super_admin role for protected endpoint.

    Builds on get_current_user dependency to enforce admin-level access.
    Used for administrative endpoints like settings updates and user management.

    :param current_user: Current user from get_current_user dependency
    :type current_user: Dict[str, Any]
    :return: User information (same as current_user)
    :rtype: Dict[str, Any]
    :raises AuthorizationError: If user is not admin or super_admin

    :Example:

    >>> from fastapi import Depends
    >>>
    >>> @router.put("/settings")
    >>> async def update_settings(
    >>>     data: SettingsUpdate,
    >>>     current_user: dict = Depends(get_current_admin_user)
    >>> ):
    >>>     # Only admin or super_admin users can reach this code
    >>>     return await repo.update(data)
    """
    if current_user["role"] not in ["admin", "super_admin"]:
        raise AuthorizationError("Admin access required")

    return current_user


async def get_current_super_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency: Require super_admin role for system-level operations.

    Builds on get_current_user dependency to enforce super_admin-only access.
    Used for system-level operations like creating new tenants (admin users).

    :param current_user: Current user from get_current_user dependency
    :type current_user: Dict[str, Any]
    :return: User information (same as current_user)
    :rtype: Dict[str, Any]
    :raises AuthorizationError: If user is not super_admin

    :Example:

    >>> from fastapi import Depends
    >>>
    >>> @router.post("/admin/users")
    >>> async def create_admin(
    >>>     data: UserCreate,
    >>>     current_user: dict = Depends(get_current_super_admin_user)
    >>> ):
    >>>     # Only super_admin users can create new admin (tenants)
    >>>     return await repo.create(data)
    """
    if current_user["role"] != "super_admin":
        raise AuthorizationError("Super admin access required")

    return current_user
