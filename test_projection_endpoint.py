#!/usr/bin/env python
"""Test projection endpoint after bug fixes."""

import asyncio
import httpx
import json

async def test_projection_endpoint():
    """Test projection endpoint with authenticated request."""

    # Read token
    with open('/tmp/token.json', 'r') as f:
        auth_data = json.load(f)
        token = auth_data['access_token']

    # Test projection endpoint
    url = "http://localhost:5000/api/projection"
    params = {
        "view": "all",
        "start": "2025-01-01",
        "end": "2025-12-31"
    }
    headers = {
        "Authorization": f"Bearer {token}"
    }

    print("🧪 Testing Projection Endpoint After Bug Fixes\n")
    print(f"URL: {url}")
    print(f"Params: {params}\n")

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers)

        print(f"Status Code: {response.status_code}\n")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS!")
            print(f"\nResponse Structure:")
            print(f"  Starting Balance: {data.get('starting_balance')}")
            print(f"  Base Currency: {data.get('base_currency')}")
            print(f"  Display Currency: {data.get('display_currency')}")
            print(f"  Events Count: {len(data.get('events', []))}")
            print(f"  Warnings: {data.get('warnings')}")

            # Show first few events
            events = data.get('events', [])
            if events:
                print(f"\n📊 First 5 Events:")
                for i, event in enumerate(events[:5], 1):
                    print(f"  {i}. {event.get('date')} - {event.get('description'):30s} - {event.get('amount'):>10} {event.get('currency')} (Balance: {event.get('running_balance')})")
        else:
            print(f"❌ ERROR!")
            print(f"Response: {response.text}")

if __name__ == "__main__":
    asyncio.run(test_projection_endpoint())
