#!/usr/bin/env python
"""Debug script to reproduce projection endpoint error."""

import asyncio
from datetime import date
from api.config import MongoDB
from core.projection import calculate_global_projection

async def debug_projection():
    """Test projection calculation directly."""
    print("🔍 Debugging Projection Endpoint Error\n")

    # Connect to database
    MongoDB.connect()
    db = MongoDB.get_database()

    try:
        print("📊 Testing global projection calculation...")
        print(f"   Date range: 2025-01-01 to 2025-12-31")
        print(f"   View: all\n")

        result = await calculate_global_projection(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            view="all",
            db=db
        )

        print(f"✅ Success! Retrieved {len(result)} events")
        if len(result) > 0:
            print(f"\nFirst event:")
            print(f"   Date: {result[0].get('date')}")
            print(f"   Description: {result[0].get('description')}")
            print(f"   Amount: {result[0].get('amount')}")

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
    asyncio.run(debug_projection())
