#!/usr/bin/env python
"""Debug API route to identify error difference from core function."""

import asyncio
from datetime import date
from decimal import Decimal
from api.config import MongoDB
from core.projection import calculate_global_projection, convert_to_base_currency

async def debug_api_route():
    """Simulate what the API route does."""
    print("🔍 Debugging API Route Logic\n")

    MongoDB.connect()
    db = MongoDB.get_database()

    try:
        # Step 1: Get settings
        print("Step 1: Get settings...")
        settings = await db.settings.find_one()
        if not settings:
            print("❌ Settings not found!")
            return

        base_currency = settings.get("base_currency", "GBP")
        print(f"✅ Base currency: {base_currency}\n")

        # Step 2: Calculate starting balance
        print("Step 2: Calculate starting balance...")
        accounts = await db.accounts.find({"is_archived": False}).to_list()
        starting_balance = Decimal("0")

        for acc in accounts:
            # Convert MongoDB Decimal128 to Python Decimal
            balance = Decimal(str(acc.get("current_balance", "0")))
            rate_to_base = Decimal(str(acc.get("rate_to_base", "1")))
            print(f"  Account {acc.get('name')}: balance={balance} (type: {type(balance)}), rate={rate_to_base} (type: {type(rate_to_base)})")

            base_balance = convert_to_base_currency(balance, rate_to_base)
            starting_balance += base_balance

        print(f"✅ Starting balance: {starting_balance}\n")

        # Step 3: Call projection
        print("Step 3: Call projection...")
        events = await calculate_global_projection(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            db=db
        )

        print(f"✅ Success! Retrieved {len(events)} events\n")

    except Exception as e:
        print(f"❌ Error occurred:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        print(f"\n📋 Full traceback:")
        import traceback
        traceback.print_exc()

    finally:
        MongoDB.close()

if __name__ == "__main__":
    asyncio.run(debug_api_route())
