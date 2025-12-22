"""
Populate MongoDB with realistic test data for CHAPTR manual testing.

Generates realistic accounts, stories, events, and recurring rules with proper
referential integrity for manual API validation and demos.

Usage:
    # Presets
    python tests/utils/populate_test_data.py --preset small
    python tests/utils/populate_test_data.py --preset medium
    python tests/utils/populate_test_data.py --preset large

    # Custom configuration
    python tests/utils/populate_test_data.py --accounts 5 --stories 10 --events 100

    # Options
    python tests/utils/populate_test_data.py --preset small --clear-first --seed 42
"""

import argparse
import asyncio
import random
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Optional
from uuid import UUID, uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from faker import Faker
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from api.models import (
    Account, Story, Event, RecurringRule, Settings,
    FundingMode, GoalType, Frequency
)
from api.config import settings as app_settings


class TestDataGenerator:
    """
    Generate realistic test data with referential integrity.

    Maintains proper dependency order and realistic patterns for CHAPTR testing.
    """

    def __init__(self, db: AsyncIOMotorDatabase, seed: Optional[int] = None):
        """
        Initialize test data generator.

        Args:
            db: MongoDB database instance
            seed: Random seed for reproducible data generation
        """
        self.db = db
        self.faker = Faker()
        if seed is not None:
            Faker.seed(seed)
            random.seed(seed)

        # Collections
        self.accounts_coll = db.accounts
        self.stories_coll = db.stories
        self.events_coll = db.events
        self.rules_coll = db.recurring_rules
        self.settings_coll = db.settings

        # Data storage for referential integrity
        self.accounts: List[Account] = []
        self.stories: List[Story] = []
        self.settings: Optional[Settings] = None

    async def clear_database(self):
        """
        Clear all collections in database.

        ⚠️ WARNING: This is destructive and will delete all data!
        """
        print("⚠️  Clearing database...")
        await self.accounts_coll.delete_many({})
        await self.stories_coll.delete_many({})
        await self.events_coll.delete_many({})
        await self.rules_coll.delete_many({})
        await self.settings_coll.delete_many({})
        print("✅ Database cleared")

    async def generate_settings(self) -> Settings:
        """
        Generate default settings with realistic currency rates.

        Returns:
            Created settings document
        """
        print("\n📊 Generating settings...")

        # Realistic currency rates (GBP base)
        rates = {
            "USD": Decimal("1.27"),
            "EUR": Decimal("1.17"),
            "CAD": Decimal("1.71"),
            "AUD": Decimal("1.91"),
            "JPY": Decimal("189.50"),
        }

        settings_id = uuid4()
        settings_data = {
            "id": str(settings_id),  # Convert UUID to string
            "base_currency": "GBP",
            "default_currency": "GBP",
            "date_format": "DD/MM/YYYY",
            "baseline_display_months": 1,
            "rates": {k: str(v) for k, v in rates.items()},  # Convert to string for MongoDB
            "server_url": "",
            "last_backup_date": None,
            "version": "1.0.0",
            "created_at": datetime.now(),  # Use datetime.now() instead of utcnow()
            "updated_at": datetime.now()
        }

        await self.settings_coll.insert_one(settings_data)
        self.settings = Settings(**settings_data)
        print(f"✅ Created settings with {len(rates)} currency rates")

        return self.settings

    async def generate_accounts(self, count: int) -> List[Account]:
        """
        Generate realistic accounts with varied currencies and balances.

        Args:
            count: Number of accounts to create (3-8)

        Returns:
            List of created accounts
        """
        print(f"\n💰 Generating {count} accounts...")

        # Realistic bank names
        bank_names = [
            "Monzo", "HSBC", "Santander", "Barclays", "Nationwide",
            "Chase", "Lloyds", "NatWest"
        ]
        random.shuffle(bank_names)

        # Currency distribution (GBP bias)
        currencies = ["GBP", "GBP", "GBP", "USD", "EUR", "CAD"]

        accounts = []
        for i in range(count):
            # First account is always default
            is_default = (i == 0)

            # Balance distribution
            if is_default:
                # Default account: healthy balance
                balance = random.uniform(1000, 5000)
            elif random.random() < 0.1:
                # 10% chance overdraft
                balance = random.uniform(-500, 0)
            else:
                # Normal balance
                balance = random.uniform(100, 8000)

            currency = currencies[i % len(currencies)]

            account_id = uuid4()
            account_data = {
                "id": str(account_id),  # Convert UUID to string
                "name": bank_names[i % len(bank_names)],
                "currency": currency,
                "current_balance": str(Decimal(str(round(balance, 2)))),
                "balance_updated_at": datetime.now() - timedelta(hours=random.randint(1, 48)),
                "is_default": is_default,
                "is_archived": False,
                "pending_reconciliation": False,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }

            await self.accounts_coll.insert_one(account_data)
            account = Account(**account_data)
            accounts.append(account)

            print(f"  {account.name} ({account.currency}): £{balance:.2f}" +
                  (" [DEFAULT]" if is_default else ""))

        self.accounts = accounts
        print(f"✅ Created {len(accounts)} accounts")
        return accounts

    async def generate_stories(self, count: int) -> List[Story]:
        """
        Generate realistic stories with varied funding modes and goals.

        Args:
            count: Number of stories to create (5-15)

        Returns:
            List of created stories
        """
        print(f"\n📖 Generating {count} stories...")

        # Story name templates
        story_templates = [
            "canada-trip", "house-deposit", "volvo", "skiing-2025",
            "wedding", "kitchen-reno", "new-laptop", "emergency-fund",
            "vacation-spain", "car-repairs", "gym-membership", "study-fund"
        ]
        random.shuffle(story_templates)

        # Funding mode distribution (40% projected, 40% fixed, 20% projected_plus)
        funding_modes = [
            FundingMode.PROJECTED, FundingMode.PROJECTED, FundingMode.PROJECTED, FundingMode.PROJECTED,
            FundingMode.FIXED, FundingMode.FIXED, FundingMode.FIXED, FundingMode.FIXED,
            FundingMode.PROJECTED_PLUS, FundingMode.PROJECTED_PLUS
        ]

        # Goal type distribution
        goal_types = [
            GoalType.END_WITH_AT_LEAST, GoalType.END_WITH_AT_LEAST,
            GoalType.SPEND_UP_TO, GoalType.SPEND_UP_TO,
            GoalType.NONE, GoalType.NONE, GoalType.NONE
        ]

        stories = []
        today = date.today()

        for i in range(count):
            # Date ranges (±3-6 months)
            start_offset = random.randint(-90, 90)
            duration = random.randint(30, 180)
            start_date = today + timedelta(days=start_offset)
            end_date = start_date + timedelta(days=duration)

            # Funding mode
            funding_mode = random.choice(funding_modes)
            funding_amount = None
            if funding_mode in [FundingMode.FIXED, FundingMode.PROJECTED_PLUS]:
                if funding_mode == FundingMode.FIXED:
                    funding_amount = Decimal(str(random.randint(500, 5000)))
                else:  # PROJECTED_PLUS
                    funding_amount = Decimal(str(random.randint(100, 1000)))

            # Goal
            goal_type = random.choice(goal_types)
            goal_amount = None
            if goal_type != GoalType.NONE:
                if goal_type == GoalType.END_WITH_AT_LEAST:
                    goal_amount = Decimal(str(random.randint(500, 3000)))
                else:  # SPEND_UP_TO
                    goal_amount = Decimal(str(random.randint(1000, 10000)))

            # Default account (some stories have default, some don't)
            default_account_id = None
            if random.random() < 0.7:  # 70% have default account
                default_account_id = random.choice(self.accounts).id

            # Currency matches account if set, otherwise GBP
            if default_account_id:
                account = next(a for a in self.accounts if a.id == default_account_id)
                currency = account.currency
            else:
                currency = "GBP"

            story_id = uuid4()
            story_data = {
                "id": str(story_id),  # Convert UUID to string
                "name": story_templates[i % len(story_templates)],
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "default_account_id": str(default_account_id) if default_account_id else None,
                "funding_mode": funding_mode.value,
                "funding_amount": str(funding_amount) if funding_amount else None,
                "goal_type": goal_type.value,
                "goal_amount": str(goal_amount) if goal_amount else None,
                "display_currency": currency,
                "created_at": datetime.now(),
                "created_by": None,
                "updated_at": datetime.now(),
                "updated_by": None
            }

            await self.stories_coll.insert_one(story_data)
            story = Story(**story_data)
            stories.append(story)

            print(f"  {story.name}: {funding_mode.value}" +
                  (f" (£{funding_amount})" if funding_amount else ""))

        self.stories = stories
        print(f"✅ Created {len(stories)} stories")
        return stories

    async def generate_recurring_rules(self, count: int) -> List[RecurringRule]:
        """
        Generate common recurring rule patterns (salary, rent, subscriptions).

        Args:
            count: Number of rules to create (3-7)

        Returns:
            List of created recurring rules
        """
        print(f"\n🔁 Generating {count} recurring rules...")

        # Common patterns
        rule_patterns = [
            {"description": "Monthly Salary", "amount": 3000, "frequency": Frequency.MONTHLY, "day": 28},
            {"description": "Rent", "amount": -1500, "frequency": Frequency.MONTHLY, "day": 1},
            {"description": "Netflix", "amount": -15.99, "frequency": Frequency.MONTHLY, "day": 15},
            {"description": "Spotify", "amount": -9.99, "frequency": Frequency.MONTHLY, "day": 10},
            {"description": "Weekly Groceries", "amount": -80, "frequency": Frequency.WEEKLY, "day": 6},  # Saturday
            {"description": "Annual Insurance", "amount": -600, "frequency": Frequency.ANNUAL, "day": 1},
            {"description": "Gym Membership", "amount": -45, "frequency": Frequency.MONTHLY, "day": 1}
        ]
        random.shuffle(rule_patterns)

        rules = []
        today = date.today()

        for i in range(count):
            pattern = rule_patterns[i % len(rule_patterns)]

            # Account (use default account)
            account = self.accounts[0]  # Default account

            # Date range
            start_date = today - timedelta(days=random.randint(0, 90))
            end_date = None  # Ongoing by default
            if random.random() < 0.2:  # 20% have end date
                end_date = today + timedelta(days=random.randint(90, 365))

            rule_id = uuid4()
            rule_data = {
                "id": str(rule_id),  # Convert UUID to string
                "description": pattern["description"],
                "amount": str(Decimal(str(pattern["amount"]))),
                "currency": account.currency,
                "account_id": str(account.id),
                "frequency": pattern["frequency"].value,
                "day": pattern["day"],
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat() if end_date else None,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }

            await self.rules_coll.insert_one(rule_data)
            rule = RecurringRule(**rule_data)
            rules.append(rule)

            print(f"  {rule.description}: £{pattern['amount']:.2f} {pattern['frequency'].value}")

        print(f"✅ Created {len(rules)} recurring rules")
        return rules

    async def generate_events(self, count: int) -> List[Event]:
        """
        Generate realistic events (60% baseline, 40% story).

        Args:
            count: Number of events to create (30-200)

        Returns:
            List of created events
        """
        print(f"\n📅 Generating {count} events...")

        # Event description templates
        expense_descriptions = [
            "Groceries at Tesco", "Coffee at Starbucks", "Restaurant dinner",
            "Fuel at Shell", "Amazon purchase", "Train tickets",
            "Pharmacy", "Haircut", "Cinema tickets", "Pub lunch"
        ]
        income_descriptions = [
            "Freelance project", "Bonus payment", "Gift", "Cashback",
            "Side gig", "Consulting fee"
        ]

        events = []
        today = date.today()

        # Distribution: 60% baseline, 40% story
        baseline_count = int(count * 0.6)
        story_count = count - baseline_count

        for i in range(count):
            is_baseline = (i < baseline_count)

            # 85% expenses, 15% income
            is_income = random.random() < 0.15

            if is_income:
                amount = Decimal(str(random.randint(100, 2000)))
                description = random.choice(income_descriptions)
            else:
                amount = -Decimal(str(round(random.uniform(5, 300), 2)))
                description = random.choice(expense_descriptions)

            # Date within ±3 months
            event_date = today + timedelta(days=random.randint(-90, 90))

            # Account resolution
            if is_baseline:
                # Baseline: use default account
                account = self.accounts[0]
                story_id = None
            else:
                # Story event
                story = random.choice(self.stories)
                story_id = story.id

                # Use story's default account if set, otherwise default account
                if story.default_account_id:
                    account = next((a for a in self.accounts if a.id == story.default_account_id), self.accounts[0])
                else:
                    account = self.accounts[0]

            # Rate to base (using settings rates)
            if account.currency == self.settings.base_currency:
                rate_to_base = Decimal("1.0")
            else:
                # Get rate from settings
                rate_to_base = self.settings.rates.get(account.currency, Decimal("1.0"))

            event_id = uuid4()
            event_data = {
                "id": str(event_id),  # Convert UUID to string
                "date": event_date.isoformat(),
                "description": description,
                "amount": str(amount),
                "currency": account.currency,
                "rate_to_base": str(rate_to_base),
                "account_id": str(account.id),
                "story_id": str(story_id) if story_id else None,
                "is_baseline": is_baseline,
                "is_hypothetical": False,
                "is_auto_adjustment": False,
                "created_at": datetime.now(),
                "created_by": None,
                "updated_at": datetime.now(),
                "updated_by": None,
                "recurring_rule_id": None
            }

            await self.events_coll.insert_one(event_data)
            event = Event(**event_data)
            events.append(event)

        print(f"✅ Created {count} events ({baseline_count} baseline, {story_count} story)")
        return events

    async def generate_all(
        self,
        account_count: int = 5,
        story_count: int = 10,
        rule_count: int = 5,
        event_count: int = 100
    ) -> Dict[str, int]:
        """
        Generate all test data in correct dependency order.

        Args:
            account_count: Number of accounts (3-8)
            story_count: Number of stories (5-15)
            rule_count: Number of recurring rules (3-7)
            event_count: Number of events (30-200)

        Returns:
            Dictionary with counts of created entities
        """
        print("\n" + "=" * 60)
        print("🚀 CHAPTR Test Data Generator")
        print("=" * 60)

        # Generate in dependency order
        settings = await self.generate_settings()
        accounts = await self.generate_accounts(account_count)
        stories = await self.generate_stories(story_count)
        rules = await self.generate_recurring_rules(rule_count)
        events = await self.generate_events(event_count)

        # Summary
        summary = {
            "settings": 1,
            "accounts": len(accounts),
            "stories": len(stories),
            "recurring_rules": len(rules),
            "events": len(events)
        }

        print("\n" + "=" * 60)
        print("✅ Generation Complete!")
        print("=" * 60)
        print(f"Settings:        {summary['settings']}")
        print(f"Accounts:        {summary['accounts']}")
        print(f"Stories:         {summary['stories']}")
        print(f"Recurring Rules: {summary['recurring_rules']}")
        print(f"Events:          {summary['events']}")
        print("=" * 60)

        return summary


async def main():
    """Main async function with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Populate MongoDB with realistic CHAPTR test data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use presets
  python tests/utils/populate_test_data.py --preset small
  python tests/utils/populate_test_data.py --preset medium
  python tests/utils/populate_test_data.py --preset large

  # Custom configuration
  python tests/utils/populate_test_data.py --accounts 5 --stories 10 --events 100

  # With options
  python tests/utils/populate_test_data.py --preset small --clear-first --seed 42
        """
    )

    # Preset or custom
    parser.add_argument(
        "--preset",
        choices=["small", "medium", "large"],
        help="Use preset configuration (small/medium/large)"
    )

    # Custom counts
    parser.add_argument("--accounts", type=int, help="Number of accounts (3-8)")
    parser.add_argument("--stories", type=int, help="Number of stories (5-15)")
    parser.add_argument("--rules", type=int, help="Number of recurring rules (3-7)")
    parser.add_argument("--events", type=int, help="Number of events (30-200)")

    # Options
    parser.add_argument(
        "--clear-first",
        action="store_true",
        help="Clear database before populating (destructive!)"
    )
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    parser.add_argument(
        "--mongo-url",
        default=None,
        help=f"MongoDB connection URL (default: from .env or {app_settings.mongodb_url})"
    )
    parser.add_argument(
        "--mongo-db",
        default=None,
        help=f"MongoDB database name (default: from .env or {app_settings.mongodb_db_name})"
    )

    args = parser.parse_args()

    # Determine counts (preset vs custom)
    if args.preset:
        presets = {
            "small": {"accounts": 3, "stories": 5, "rules": 3, "events": 30},
            "medium": {"accounts": 5, "stories": 10, "rules": 5, "events": 100},
            "large": {"accounts": 8, "stories": 15, "rules": 7, "events": 200}
        }
        counts = presets[args.preset]
        print(f"\nUsing preset: {args.preset}")
    else:
        # Custom or defaults
        counts = {
            "accounts": args.accounts or 5,
            "stories": args.stories or 10,
            "rules": args.rules or 5,
            "events": args.events or 100
        }

    # Use config defaults if not provided
    mongo_url = args.mongo_url or app_settings.mongodb_url
    mongo_db = args.mongo_db or app_settings.mongodb_db_name

    # Connect to MongoDB
    print(f"\nConnecting to MongoDB: {mongo_url}/{mongo_db}")
    client = AsyncIOMotorClient(mongo_url)
    db = client[mongo_db]

    # Test connection
    try:
        await client.admin.command('ping')
        print("✅ MongoDB connection successful")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return

    # Create generator
    generator = TestDataGenerator(db, seed=args.seed)

    # Clear if requested
    if args.clear_first:
        confirm = input("\n⚠️  This will DELETE all data in the database. Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("❌ Aborted")
            return
        await generator.clear_database()

    # Generate data
    try:
        await generator.generate_all(
            account_count=counts["accounts"],
            story_count=counts["stories"],
            rule_count=counts["rules"],
            event_count=counts["events"]
        )
    except Exception as e:
        print(f"\n❌ Generation failed: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        client.close()

    print("\n🎉 Done!\n")


if __name__ == "__main__":
    asyncio.run(main())
