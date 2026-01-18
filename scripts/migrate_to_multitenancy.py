#!/usr/bin/env python3
"""
Multi-tenancy migration script for CHAPTR.

Migrates existing single-tenant data to multi-tenant architecture:
1. Promotes first admin to super_admin
2. Assigns tenant_id to all existing entities
3. Updates change_log with tenant_id

Usage:
    # Dry run (preview changes)
    python scripts/migrate_to_multitenancy.py

    # Execute migration
    python scripts/migrate_to_multitenancy.py --execute

Requirements:
    - Must have at least one admin user in the system
    - Backup your database before running with --execute

Notes:
    - Safe to run multiple times (idempotent)
    - Entities without tenant_id will be assigned to the super_admin's tenant
"""

import asyncio
import argparse
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.config import MongoDB, settings


async def get_first_admin(db):
    """
    Find the first admin user in the system.

    Returns the admin user document or None if not found.
    """
    # First check for existing super_admin (already migrated)
    super_admin = await db.users.find_one({"role": "super_admin"})
    if super_admin:
        return super_admin, True  # Already migrated

    # Find first admin user
    admin = await db.users.find_one({"role": "admin"})
    return admin, False


async def count_entities_without_tenant(db, collection_name: str) -> int:
    """Count entities in a collection that don't have tenant_id."""
    return await db[collection_name].count_documents({
        "$or": [
            {"tenant_id": {"$exists": False}},
            {"tenant_id": None}
        ]
    })


async def migrate_collection(db, collection_name: str, tenant_id: str, dry_run: bool) -> int:
    """
    Add tenant_id to all documents in a collection that don't have it.

    Returns the number of documents updated.
    """
    query = {
        "$or": [
            {"tenant_id": {"$exists": False}},
            {"tenant_id": None}
        ]
    }

    count = await db[collection_name].count_documents(query)

    if count == 0:
        return 0

    if not dry_run:
        await db[collection_name].update_many(
            query,
            {"$set": {"tenant_id": tenant_id}}
        )

    return count


async def migrate_users(db, tenant_id: str, dry_run: bool) -> tuple[int, int]:
    """
    Migrate users without tenant_id.

    Users with role='user' get the super_admin's tenant_id.
    Returns (regular_users_updated, admins_updated).
    """
    # Count regular users without tenant_id
    regular_user_query = {
        "role": "user",
        "$or": [
            {"tenant_id": {"$exists": False}},
            {"tenant_id": None}
        ]
    }
    regular_count = await db.users.count_documents(regular_user_query)

    if regular_count > 0 and not dry_run:
        await db.users.update_many(
            regular_user_query,
            {"$set": {"tenant_id": tenant_id}}
        )

    # Count admin users without tenant_id (excluding the super_admin)
    admin_query = {
        "role": "admin",
        "$or": [
            {"tenant_id": {"$exists": False}},
            {"tenant_id": None}
        ]
    }
    admin_count = await db.users.count_documents(admin_query)

    # Each admin becomes anchor of their own tenant
    if admin_count > 0 and not dry_run:
        # For each admin without tenant_id, set tenant_id = their own id
        cursor = db.users.find(admin_query)
        async for admin in cursor:
            await db.users.update_one(
                {"id": admin["id"]},
                {"$set": {"tenant_id": admin["id"]}}
            )

    return regular_count, admin_count


async def run_migration(dry_run: bool = True):
    """
    Main migration function.

    Args:
        dry_run: If True, only report what would be done. If False, execute changes.
    """
    print("=" * 60)
    print("CHAPTR Multi-Tenancy Migration")
    print("=" * 60)
    print(f"\nMode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (making changes)'}")
    print()

    # Connect to MongoDB
    try:
        MongoDB.connect()
        db = MongoDB.get_database()
        print(f"Connected to database: {settings.mongodb_db_name}")
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    try:
        # Step 1: Find or create super_admin
        print("\n--- Step 1: Identify Super Admin ---")
        admin, already_migrated = await get_first_admin(db)

        if not admin:
            print("ERROR: No admin user found in the system")
            print("       Run create_first_user.py first to create an admin")
            sys.exit(1)

        tenant_id = admin["id"]

        if already_migrated:
            print(f"Found existing super_admin: {admin['username']}")
            print(f"Tenant ID: {tenant_id}")
        else:
            print(f"Found admin to promote: {admin['username']}")
            print(f"Will become super_admin with tenant_id: {tenant_id}")

            if not dry_run:
                # Promote admin to super_admin and set tenant_id
                await db.users.update_one(
                    {"id": admin["id"]},
                    {"$set": {
                        "role": "super_admin",
                        "tenant_id": tenant_id
                    }}
                )
                print("  -> Admin promoted to super_admin")

        # Step 2: Migrate users
        print("\n--- Step 2: Migrate Users ---")
        regular_count, admin_count = await migrate_users(db, tenant_id, dry_run)
        print(f"Regular users without tenant_id: {regular_count}")
        print(f"Admin users without tenant_id: {admin_count}")
        if not dry_run and (regular_count > 0 or admin_count > 0):
            print("  -> Users migrated")

        # Step 3: Migrate entity collections
        print("\n--- Step 3: Migrate Entity Collections ---")
        collections = ["accounts", "stories", "events", "recurring_rules", "settings"]

        for collection in collections:
            count = await migrate_collection(db, collection, tenant_id, dry_run)
            status = f"  -> {count} migrated" if not dry_run and count > 0 else ""
            print(f"{collection}: {count} documents without tenant_id{status}")

        # Step 4: Migrate change_log
        print("\n--- Step 4: Migrate Change Log ---")
        change_log_count = await migrate_collection(db, "change_log", tenant_id, dry_run)
        status = "  -> migrated" if not dry_run and change_log_count > 0 else ""
        print(f"change_log entries without tenant_id: {change_log_count}{status}")

        # Summary
        print("\n" + "=" * 60)
        if dry_run:
            print("DRY RUN COMPLETE - No changes made")
            print("\nTo execute the migration, run:")
            print("  python scripts/migrate_to_multitenancy.py --execute")
        else:
            print("MIGRATION COMPLETE")
            print("\nAll existing data has been assigned to the super_admin's tenant.")
            print("The system is now ready for multi-tenancy.")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR during migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        MongoDB.close()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate CHAPTR to multi-tenant architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes (dry run)
  python scripts/migrate_to_multitenancy.py

  # Execute migration
  python scripts/migrate_to_multitenancy.py --execute

Safety Notes:
  - Always backup your database before running with --execute
  - The script is idempotent (safe to run multiple times)
  - Already migrated entities are skipped

What this script does:
  1. Finds the first admin user and promotes to super_admin
  2. Sets tenant_id on all existing users
  3. Sets tenant_id on all accounts, stories, events, recurring_rules, settings
  4. Sets tenant_id on all change_log entries
        """
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the migration (default is dry run)"
    )

    args = parser.parse_args()

    asyncio.run(run_migration(dry_run=not args.execute))


if __name__ == "__main__":
    main()
