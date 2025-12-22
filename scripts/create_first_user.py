#!/usr/bin/env python3
"""
First user initialization CLI command.

Creates the first admin user for CHAPTR deployment.
Solves the authentication bootstrap problem.

Usage:
    # Interactive mode
    python scripts/create_first_user.py --confirm

    # Environment variables mode (Docker)
    ADMIN_USERNAME=admin ADMIN_PASSWORD=SecurePass123 \\
        python scripts/create_first_user.py --confirm

Requirements:
    - Must use --confirm flag (safety mechanism)
    - Password must meet strength requirements (8+ chars, uppercase, lowercase, digit)
    - Only works if NO users exist (prevents account hijacking)
"""

import asyncio
import argparse
import os
import sys
from getpass import getpass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.config import MongoDB, settings
from api.models import UserCreate, UserRole
from api.repositories.users import UserRepository
from api.utils.errors import ResourceConflictError
from pydantic import ValidationError


async def check_existing_users(repo: UserRepository) -> bool:
    """
    Check if any users already exist.

    Security: Only allows first user creation if database is empty.
    This prevents account hijacking - attacker would need to delete
    all users (requires admin access) before creating new admin.

    Returns True if any users exist, False otherwise.
    """
    user_count = await repo.count()
    return user_count > 0


async def get_credentials() -> tuple[str, str]:
    """
    Get admin credentials from environment or interactive prompts.

    Priority:
    1. Environment variables (ADMIN_USERNAME, ADMIN_PASSWORD)
    2. Interactive prompts

    Returns:
        tuple[str, str]: (username, password)
    """
    # Check environment variables first (Docker mode)
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")

    if username and password:
        # Validate username is not empty
        username = username.strip()
        if not username:
            print("❌ ADMIN_USERNAME cannot be empty")
            sys.exit(1)

        print(f"📋 Using credentials from environment variables")
        print(f"   Username: {username}")
        return username, password

    # Interactive mode
    print("🔐 Admin User Setup")
    print("=" * 50)
    username = input("Enter admin username: ").strip()

    if not username:
        print("❌ Username cannot be empty")
        sys.exit(1)

    password = getpass("Enter admin password: ").strip()
    password_confirm = getpass("Confirm password: ").strip()

    if password != password_confirm:
        print("❌ Passwords do not match")
        sys.exit(1)

    return username, password


async def create_admin_user(username: str, password: str) -> None:
    """
    Create admin user with validation and safety checks.

    Args:
        username: Admin username
        password: Admin password (plain text, will be hashed)

    Raises:
        ValidationError: If password doesn't meet strength requirements
        ResourceConflictError: If admin already exists
    """
    # Initialize MongoDB
    try:
        MongoDB.connect()
        db = MongoDB.get_database()
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB")
        print(f"   Error: {e}")
        print(f"\nConnection Details:")
        print(f"   MongoDB URL: {settings.mongodb_url}")
        print(f"   Database: {settings.mongodb_db_name}")
        print(f"\nTroubleshooting:")
        print(f"   - Verify MongoDB is running")
        print(f"   - Check connection string in .env file")
        print(f"   - Ensure network connectivity to database")
        sys.exit(3)

    try:
        # Create repository
        repo = UserRepository(db)

        # Check if any users exist (security measure)
        if await check_existing_users(repo):
            print("❌ Users already exist in the system")
            print("   This script only creates the FIRST user")
            print("   Use the API to manage additional users")
            sys.exit(1)

        # Validate and create user
        print(f"\n📝 Creating admin user: {username}")

        try:
            # Pydantic validation happens here
            user_data = UserCreate(
                username=username,
                password=password,
                role=UserRole.ADMIN
            )
        except ValidationError as e:
            print(f"❌ Password validation failed:")
            for error in e.errors():
                print(f"   - {error['msg']}")
            sys.exit(1)

        # Create user (password hashing happens in repository)
        user = await repo.create(user_data)

        print(f"✅ Admin user created successfully!")
        print(f"   User ID: {user.id}")
        print(f"   Username: {user.username}")
        print(f"   Role: {user.role}")
        print(f"\n🎉 You can now log in to CHAPTR")

    except ResourceConflictError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        MongoDB.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Initialize first admin user for CHAPTR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python scripts/create_first_user.py --confirm

  # Docker environment mode (single line)
  ADMIN_USERNAME=admin ADMIN_PASSWORD=SecurePass123 python scripts/create_first_user.py --confirm

  # Or using .env file
  # Set ADMIN_USERNAME and ADMIN_PASSWORD in .env, then:
  python scripts/create_first_user.py --confirm

Password Requirements:
  - Minimum 8 characters
  - At least one uppercase letter
  - At least one lowercase letter
  - At least one digit

Notes:
  - Only works if NO users exist (security measure)
  - Password is hashed using bcrypt before storage
  - Requires --confirm flag to prevent accidents
        """
    )

    parser.add_argument(
        "--confirm",
        action="store_true",
        required=True,
        help="Confirm admin user creation (required safety flag)"
    )

    args = parser.parse_args()

    # Get credentials
    username, password = asyncio.run(get_credentials())

    # Create admin user
    asyncio.run(create_admin_user(username, password))


if __name__ == "__main__":
    main()
