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
from datetime import datetime, date, timedelta, timezone
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
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
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

        # Currency distribution - scale with account count, bias toward base currency
        # Get available currencies from settings
        available_currencies = [self.settings.base_currency] + list(self.settings.rates.keys())

        # Distribute currencies: 40% base currency, 60% others
        currencies = []
        base_count = max(1, int(count * 0.4))  # At least 1 base currency account

        # Add base currency accounts
        currencies.extend([self.settings.base_currency] * base_count)

        # Fill remaining with other currencies (cycle through available)
        other_count = count - base_count
        for i in range(other_count):
            other_currencies = [c for c in available_currencies if c != self.settings.base_currency]
            currencies.append(other_currencies[i % len(other_currencies)])

        # Shuffle for variety
        random.shuffle(currencies)

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

            currency = currencies[i]

            account_id = uuid4()
            account_data = {
                "id": str(account_id),  # Convert UUID to string
                "name": bank_names[i % len(bank_names)],
                "currency": currency,
                "current_balance": str(Decimal(str(round(balance, 2)))),
                "balance_updated_at": datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 48)),
                "is_default": is_default,
                "is_archived": False,
                "pending_reconciliation": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }

            await self.accounts_coll.insert_one(account_data)
            account = Account(**account_data)
            accounts.append(account)

            print(f"  {account.name} ({account.currency}): £{balance:.2f}" +
                  (" [DEFAULT]" if is_default else ""))

        self.accounts = accounts
        print(f"✅ Created {len(accounts)} accounts")
        return accounts

    async def generate_stories(self, count: int, user_id: Optional[str] = None) -> List[Story]:
        """
        Generate realistic BIG-TICKET stories (not daily spending).

        CHAPTR is for projecting significant expenses over weeks/months/years.
        Stories represent major life events or purchases, not day-to-day spending.

        Args:
            count: Number of stories to create (recommended: 3)
            user_id: User ID to set as created_by (required for sync)

        Returns:
            List of created stories
        """
        print(f"\n📖 Generating {count} major life event stories...")

        # Major life events and significant purchases only
        story_templates = [
            "canada-trip-2025", "house-deposit-fund", "car-replacement"
        ]

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
        # Use 2026 calendar year for realistic testing
        year_2026_start = date(2026, 1, 1)
        default_account = self.accounts[0] if self.accounts else None

        # Define specific realistic stories with varied durations
        story_configs = [
            {
                "name": "canada-ski-trip",
                "start_date": date(2026, 1, 1),   # 1 month: Jan 2026
                "end_date": date(2026, 1, 31),
                "funding_mode": FundingMode.PROJECTED,
                "funding_amount": None,
                "goal_type": GoalType.SPEND_UP_TO,
                "goal_amount": Decimal("4500"),
            },
            {
                "name": "car-maintenance",
                "start_date": date(2026, 1, 1),   # 3 months: Jan-Mar 2026
                "end_date": date(2026, 3, 31),
                "funding_mode": FundingMode.PROJECTED,
                "funding_amount": None,
                "goal_type": GoalType.SPEND_UP_TO,
                "goal_amount": Decimal("2500"),
            },
            {
                "name": "house-renovation",
                "start_date": date(2026, 1, 1),   # 12 months: Full year 2026
                "end_date": date(2026, 12, 31),
                "funding_mode": FundingMode.PROJECTED,
                "funding_amount": None,
                "goal_type": GoalType.SPEND_UP_TO,
                "goal_amount": Decimal("18000"),
            },
        ]

        for config in story_configs[:count]:  # Only create up to 'count' stories
            story_id = uuid4()
            story_data = {
                "id": str(story_id),
                "name": config["name"],
                "start_date": config["start_date"].isoformat(),
                "end_date": config["end_date"].isoformat(),
                "default_account_id": str(default_account.id) if default_account else None,
                "funding_mode": config["funding_mode"].value,
                "funding_amount": str(config["funding_amount"]) if config["funding_amount"] else None,
                "goal_type": config["goal_type"].value,
                "goal_amount": str(config["goal_amount"]) if config["goal_amount"] else None,
                "display_currency": "GBP",
                "created_at": datetime.now(timezone.utc),
                "created_by": user_id,
                "updated_at": datetime.now(timezone.utc),
                "updated_by": user_id
            }

            await self.stories_coll.insert_one(story_data)
            story = Story(**story_data)
            stories.append(story)

            funding_info = f"£{config['funding_amount']}" if config['funding_amount'] else "projected"
            goal_info = f" | Goal: {config['goal_type'].value}"
            if config['goal_amount']:
                goal_info += f" £{config['goal_amount']}"

            print(f"  {story.name}: {config['funding_mode'].value} ({funding_info}){goal_info}")

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
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }

            await self.rules_coll.insert_one(rule_data)
            rule = RecurringRule(**rule_data)
            rules.append(rule)

            print(f"  {rule.description}: £{pattern['amount']:.2f} {pattern['frequency'].value}")

        print(f"✅ Created {len(rules)} recurring rules")
        return rules

    async def generate_events(self, count: int, user_id: Optional[str] = None) -> List[Event]:
        """
        Generate BIG-TICKET baseline and story events.

        CHAPTR is for projecting SIGNIFICANT expenses, not daily coffee purchases.

        Baseline = Recurring monthly bills (rent, utilities, insurance)
        Story events = Chunky one-time expenses (flight £800, car £7500)

        Args:
            count: Ignored - generates realistic number based on stories
            user_id: User ID to set as created_by (required for sync)

        Returns:
            List of created events
        """
        print(f"\n📅 Generating BIG-TICKET events...")

        # BASELINE: Recurring monthly bills spanning 2026
        # These are predictable recurring expenses - mortgage, utilities, subscriptions
        baseline_bills = [
            {"description": "Mortgage payment", "amount": -1350},
            {"description": "Council Tax", "amount": -180},
            {"description": "Gas & Electric", "amount": -145},
            {"description": "Water bill", "amount": -45},
            {"description": "Internet & Broadband", "amount": -40},
            {"description": "Mobile Phone", "amount": -35},
            {"description": "Netflix & Streaming", "amount": -25},
            {"description": "Groceries (monthly bulk)", "amount": -450},  # Bulk monthly estimate, not itemized
        ]

        # STORY EVENTS: Chunky expenses for each story spanning different time periods in 2026
        story_expense_patterns = {
            "canada-ski-trip": [
                # 1 month trip (Jan 2026) - spread events across the month
                {"date": date(2026, 1, 2), "description": "Return flights to Vancouver", "amount": -950},
                {"date": date(2026, 1, 5), "description": "Hotel accommodation (3 weeks)", "amount": -1800},
                {"date": date(2026, 1, 8), "description": "Ski equipment rental", "amount": -350},
                {"date": date(2026, 1, 10), "description": "Lift passes & ski lessons", "amount": -600},
                {"date": date(2026, 1, 15), "description": "Taxi & transport (bulk estimate)", "amount": -250},
                {"date": date(2026, 1, 20), "description": "Activities & excursions", "amount": -400},
                {"date": date(2026, 1, 28), "description": "Travel insurance", "amount": -150},
            ],
            "car-maintenance": [
                # 3 months (Jan-Mar 2026) - spread maintenance across quarter
                {"date": date(2026, 1, 15), "description": "New winter tires (set of 4)", "amount": -480},
                {"date": date(2026, 1, 22), "description": "Brake pads & discs replacement", "amount": -320},
                {"date": date(2026, 2, 5), "description": "Full service & oil change", "amount": -180},
                {"date": date(2026, 2, 18), "description": "Spark plugs & air filter", "amount": -95},
                {"date": date(2026, 3, 3), "description": "Wheel alignment & balancing", "amount": -85},
                {"date": date(2026, 3, 12), "description": "Replacement wiper blades", "amount": -35},
                {"date": date(2026, 3, 20), "description": "MOT test & minor repairs", "amount": -125},
                {"date": date(2026, 3, 28), "description": "Car tools & maintenance kit", "amount": -140},
            ],
            "house-renovation": [
                # 12 months (Jan-Dec 2026) - spread major work across the year
                {"date": date(2026, 1, 20), "description": "Boiler service & safety check", "amount": -180},
                {"date": date(2026, 2, 10), "description": "Kitchen renovation deposit", "amount": -3500},
                {"date": date(2026, 3, 5), "description": "Bathroom tiling & waterproofing", "amount": -1200},
                {"date": date(2026, 4, 15), "description": "Kitchen fitting & installation", "amount": -4500},
                {"date": date(2026, 5, 8), "description": "Painting & decorating (3 rooms)", "amount": -850},
                {"date": date(2026, 6, 12), "description": "New carpets & flooring", "amount": -1600},
                {"date": date(2026, 7, 18), "description": "Plumbing repairs & upgrades", "amount": -720},
                {"date": date(2026, 8, 25), "description": "Electrical rewiring (partial)", "amount": -950},
                {"date": date(2026, 9, 10), "description": "Garden landscaping", "amount": -1400},
                {"date": date(2026, 10, 5), "description": "Roof repairs & gutter cleaning", "amount": -580},
                {"date": date(2026, 11, 15), "description": "New boiler installation", "amount": -2800},
                {"date": date(2026, 12, 8), "description": "Final decorating & touch-ups", "amount": -720},
            ],
        }

        events = []
        today = date.today()
        account = self.accounts[0] if self.accounts else None

        if not account:
            print("  ⚠️  No accounts found, skipping event generation")
            return events

        # Get rate to base for currency conversion
        # rates are stored as "1 base = X foreign", invert to get "1 foreign = X base"
        if account.currency == self.settings.base_currency:
            rate_to_base = Decimal("1.0")
        else:
            stored_rate = self.settings.rates.get(account.currency, Decimal("1.0"))
            # Round to 8 decimal places to match model constraints
            rate_to_base = round(Decimal("1.0") / stored_rate, 8) if stored_rate else Decimal("1.0")

        # Generate baseline events (recurring monthly bills spanning whole year 2026)
        baseline_count = 0
        for month in range(1, 13):  # All 12 months of 2026
            # Use 1st of each month for bills
            bill_date = date(2026, month, 1)

            for bill in baseline_bills:
                event_id = uuid4()
                event_data = {
                    "id": str(event_id),
                    "event_date": bill_date.isoformat(),
                    "description": bill["description"],
                    "amount": str(Decimal(str(bill["amount"]))),
                    "currency": account.currency,
                    "rate_to_base": str(rate_to_base),
                    "account_id": str(account.id),
                    "story_id": None,
                    "is_baseline": True,
                    "is_hypothetical": False,
                    "is_auto_adjustment": False,
                    "created_at": datetime.now(timezone.utc),
                    "created_by": user_id,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": user_id,
                    "recurring_rule_id": None
                }

                await self.events_coll.insert_one(event_data)
                events.append(Event(**event_data))
                baseline_count += 1

        # Generate story events (chunky expenses with specific dates)
        story_event_count = 0
        for story in self.stories:
            # Get expenses for this story
            story_expenses = story_expense_patterns.get(story.name, [])

            if not story_expenses:
                print(f"  ⚠️  No expense patterns defined for story: {story.name}")
                continue

            for expense in story_expenses:
                # Use the specific date defined in the pattern
                event_date = expense["date"]

                event_id = uuid4()
                event_data = {
                    "id": str(event_id),
                    "event_date": event_date.isoformat(),
                    "description": expense["description"],
                    "amount": str(Decimal(str(expense["amount"]))),
                    "currency": account.currency,
                    "rate_to_base": str(rate_to_base),
                    "account_id": str(account.id),
                    "story_id": str(story.id),
                    "is_baseline": False,
                    "is_hypothetical": False,
                    "is_auto_adjustment": False,
                    "created_at": datetime.now(timezone.utc),
                    "created_by": user_id,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": user_id,
                    "recurring_rule_id": None
                }

                await self.events_coll.insert_one(event_data)
                events.append(Event(**event_data))
                story_event_count += 1

        print(f"✅ Created {len(events)} BIG-TICKET events spanning 2026:")
        print(f"    Baseline: {baseline_count} recurring monthly bills (mortgage, utilities, groceries)")
        print(f"    Stories: {story_event_count} chunky expenses across {len(self.stories)} stories:")
        for story in self.stories:
            expenses = story_expense_patterns.get(story.name, [])
            print(f"      - {story.name}: {len(expenses)} events")
        return events

    async def generate_all(
        self,
        account_count: int = 5,
        story_count: int = 3,
        rule_count: int = 5,
        event_count: int = 0  # Auto-generated based on stories
    ) -> Dict[str, int]:
        """
        Generate all test data in correct dependency order.

        CHAPTR focuses on BIG-TICKET expenses over weeks/months/years.
        This generates realistic fixture data matching that purpose.

        Args:
            account_count: Number of accounts (default: 5)
            story_count: Number of MAJOR life events (recommended: 3, max: 3)
            rule_count: Number of recurring rules (default: 5)
            event_count: Ignored - auto-generated based on stories

        Returns:
            Dictionary with counts of created entities
        """
        print("\n" + "=" * 60)
        print("🚀 CHAPTR Test Data Generator")
        print("=" * 60)

        # Get user ID from database for created_by field
        # This is required for sync filtering (full_sync filters by created_by)
        user = await self.db["users"].find_one()
        user_id = None
        if user:
            user_id = user["id"]
            print(f"\n👤 Using user: {user['username']} ({user_id})")
        else:
            print("\n⚠️  Warning: No user found in database. Stories/events will have created_by: None")
            print("   Run /api/auth/create-first-user first to create a user.")

        # Generate in dependency order
        settings = await self.generate_settings()
        accounts = await self.generate_accounts(account_count)
        stories = await self.generate_stories(story_count, user_id=user_id)
        rules = await self.generate_recurring_rules(rule_count)
        events = await self.generate_events(event_count, user_id=user_id)

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
    parser.add_argument("--stories", type=int, help="Number of MAJOR life event stories (recommended: 3, max: 3)")
    parser.add_argument("--rules", type=int, help="Number of recurring rules (3-7)")
    parser.add_argument("--events", type=int, help="Ignored - events auto-generated based on stories")

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
            "small": {"accounts": 3, "stories": 2, "rules": 3, "events": 0},  # 2 major stories
            "medium": {"accounts": 5, "stories": 3, "rules": 5, "events": 0},  # 3 major stories (recommended)
            "large": {"accounts": 8, "stories": 3, "rules": 7, "events": 0}   # 3 major stories + more accounts/rules
        }
        counts = presets[args.preset]
        print(f"\nUsing preset: {args.preset} (BIG-TICKET expenses only)")
    else:
        # Custom or defaults
        counts = {
            "accounts": args.accounts or 5,
            "stories": args.stories or 3,  # Default to 3 major stories
            "rules": args.rules or 5,
            "events": args.events or 0  # Auto-generated
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
