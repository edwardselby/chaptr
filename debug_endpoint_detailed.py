#!/usr/bin/env python
"""Detailed debugging of projection endpoint to find 500 error cause."""

import asyncio
from datetime import date
from decimal import Decimal
from api.config import MongoDB
from api.models import ProjectionResponse
from core.projection import calculate_global_projection, convert_to_base_currency

async def debug_endpoint_detailed():
    """Debug each step of the projection endpoint."""
    print("🔍 Detailed Endpoint Debugging\n")

    MongoDB.connect()
    db = MongoDB.get_database()

    try:
        # Step 1: Get settings
        print("Step 1: Get settings...")
        settings = await db.settings.find_one()
        base_currency = settings.get("base_currency", "GBP")
        print(f"✅ Base currency: {base_currency}\n")

        # Step 2: Calculate starting balance
        print("Step 2: Calculate starting balance...")
        accounts = await db.accounts.find({"is_archived": False}).to_list()
        starting_balance = Decimal("0")

        for acc in accounts:
            balance = Decimal(str(acc.get("current_balance", "0")))
            rate_to_base = Decimal(str(acc.get("rate_to_base", "1")))
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
        print(f"✅ Retrieved {len(events)} events\n")

        # Step 4: Check event structure
        print("Step 4: Checking event structure...")
        if events:
            first_event = events[0]
            print(f"First event fields:")
            for key, value in first_event.items():
                print(f"  {key}: {value} (type: {type(value).__name__})")
            print()

        # Step 5: Try to create ProjectionResponse
        print("Step 5: Creating ProjectionResponse...")
        try:
            response = ProjectionResponse(
                view="all",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
                starting_balance=starting_balance,
                events=events,
                warnings=None,
                display_currency=base_currency
            )
            print(f"✅ ProjectionResponse created successfully\n")

            # Step 6: Try to serialize to JSON
            print("Step 6: Serializing to JSON...")
            json_data = response.model_dump(mode='json')
            print(f"✅ JSON serialization successful\n")
            print(f"Keys: {list(json_data.keys())}")
            print(f"Events count in JSON: {len(json_data['events'])}")

        except Exception as e:
            print(f"❌ Error in ProjectionResponse creation or serialization:")
            print(f"   Type: {type(e).__name__}")
            print(f"   Message: {str(e)}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        print(f"❌ Error occurred:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        MongoDB.close()

if __name__ == "__main__":
    asyncio.run(debug_endpoint_detailed())
