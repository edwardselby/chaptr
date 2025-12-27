# CHAPTR API - Manual Testing Guide

**Version:** 1.0
**Last Updated:** December 2024
**API Base URL:** `http://localhost:8000`

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Testing Scenarios](#testing-scenarios)
   - [Scenario 1: Account Setup & Default Enforcement](#scenario-1-account-setup--default-enforcement)
   - [Scenario 2: Story Creation with Funding Modes](#scenario-2-story-creation-with-funding-modes)
   - [Scenario 3: Event Account Resolution](#scenario-3-event-account-resolution)
   - [Scenario 4: Recurring Rules CRUD](#scenario-4-recurring-rules-crud)
   - [Scenario 5: Settings Singleton Pattern](#scenario-5-settings-singleton-pattern)
   - [Scenario 6: Story Cascade Delete](#scenario-6-story-cascade-delete)
4. [API Endpoint Reference](#api-endpoint-reference)
   - [Account Endpoints](#account-endpoints)
   - [Story Endpoints](#story-endpoints)
   - [Event Endpoints](#event-endpoints)
   - [Recurring Rule Endpoints](#recurring-rule-endpoints)
   - [Settings Endpoints](#settings-endpoints)
5. [Error Response Reference](#error-response-reference)

---

## Prerequisites

Before testing the CHAPTR API, ensure you have:

### 1. Running Services

```bash
# Start FastAPI server
uvicorn api.main:app --reload --port 8000

# Verify MongoDB is running (port 63000 from .env)
mongosh mongodb://localhost:63000/chaptr --eval "db.adminCommand('ping')"
```

### 2. Testing Tools

- **curl**: Command-line HTTP client (pre-installed on macOS/Linux)
- **jq** (optional): JSON pretty-printer
  ```bash
  brew install jq  # macOS
  ```

### 3. Test Data (Optional)

Generate realistic test data:

```bash
# Small dataset (3 accounts, 5 stories, 30 events)
python tests/utils/populate_test_data.py --preset small --clear-first

# Medium dataset (5 accounts, 10 stories, 100 events)
python tests/utils/populate_test_data.py --preset medium --clear-first

# Large dataset (8 accounts, 15 stories, 200 events)
python tests/utils/populate_test_data.py --preset large --clear-first
```

---

## Quick Start

### Health Check

Verify the API is running:

```bash
curl http://localhost:8000/
```

**Expected Response:**
```json
{
  "message": "CHAPTR API v1.0",
  "status": "running"
}
```

### Basic Workflow

**Step 1: Create an account**
```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Monzo",
    "currency": "GBP",
    "current_balance": 2500.00,
    "is_default": true
  }'
```

**Step 2: Create a story**
```bash
# Save account ID from step 1
ACCOUNT_ID="<uuid-from-step-1>"

curl -X POST http://localhost:8000/api/stories \
  -H "Content-Type: application/json" \
  -d '{
    "name": "canada-trip",
    "start_date": "2025-01-15",
    "end_date": "2025-02-15",
    "default_account_id": "'$ACCOUNT_ID'",
    "funding_mode": "projected",
    "goal_type": "spend_up_to",
    "goal_amount": 5000.00,
    "display_currency": "GBP"
  }'
```

**Step 3: Create an event**
```bash
# Save story ID from step 2
STORY_ID="<uuid-from-step-2>"

curl -X POST http://localhost:8000/api/events?story_id=$STORY_ID \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-01-20",
    "description": "Flight to Vancouver",
    "amount": -450.00,
    "currency": "GBP",
    "is_baseline": false,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }'
```

---

## Testing Scenarios

### Scenario 1: Account Setup & Default Enforcement

**Purpose:** Verify that exactly one account has `is_default=true` at all times.

**Step 1.1: Create first account (auto-default)**

```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Monzo",
    "currency": "GBP",
    "current_balance": 3000.00
  }' | jq '.'
```

**Expected:**
- Status: `201 Created`
- Response includes: `"is_default": true` (automatically set)

**Step 1.2: Verify only one default**

```bash
curl http://localhost:8000/api/accounts | jq '[.[] | {name: .name, is_default: .is_default}]'
```

**Expected:**
- Only Monzo has `"is_default": true`

**Step 1.3: Create second account**

```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "HSBC",
    "currency": "USD",
    "current_balance": 5000.00,
    "is_default": false
  }' | jq '.'
```

**Expected:**
- Status: `201 Created`
- Response: `"is_default": false`

**Step 1.4: Change default to HSBC**

```bash
# Save HSBC account ID from Step 1.3
HSBC_ID="<uuid>"

curl -X PUT http://localhost:8000/api/accounts/$HSBC_ID \
  -H "Content-Type: application/json" \
  -d '{"is_default": true}' | jq '.'
```

**Expected:**
- Status: `200 OK`
- HSBC now has `"is_default": true`
- Monzo automatically unset to `"is_default": false`

**Step 1.5: Verify default switched**

```bash
curl http://localhost:8000/api/accounts | jq '[.[] | {name: .name, is_default: .is_default}]'
```

**Expected:**
```json
[
  {"name": "Monzo", "is_default": false},
  {"name": "HSBC", "is_default": true}
]
```

**Step 1.6: Try to archive default account (should fail)**

```bash
curl -X DELETE http://localhost:8000/api/accounts/$HSBC_ID | jq '.'
```

**Expected:**
- Status: `409 Conflict`
- Error message: Cannot archive the default account

**Step 1.7: Proper default account archival workflow**

To properly archive a default account, first transfer default status to another account:

```bash
# Transfer default status to Monzo first
MONZO_ID="<uuid-from-step-1>"

curl -X PUT http://localhost:8000/api/accounts/$MONZO_ID \
  -H "Content-Type: application/json" \
  -d '{"is_default": true}' | jq '.'
```

**Expected:**
- Status: `200 OK`
- Monzo now has `"is_default": true`
- HSBC automatically unset to `"is_default": false`

```bash
# Now archive HSBC (safe since not default)
curl -X DELETE http://localhost:8000/api/accounts/$HSBC_ID
```

**Expected:**
- Status: `204 No Content`

```bash
# Verify archival worked correctly
curl http://localhost:8000/api/accounts | jq '[.[] | {name: .name, is_default: .is_default, is_archived: .is_archived}]'
```

**Expected:**
```json
[
  {"name": "Monzo", "is_default": true, "is_archived": false},
  {"name": "HSBC", "is_default": false, "is_archived": true}
]
```

**Business Rules Verified:**
- ✅ Exactly one account is always default
- ✅ Can archive non-default accounts
- ✅ Must transfer default status before archiving default account

---

### Scenario 2: Story Creation with Funding Modes

**Purpose:** Verify funding mode validation (`FIXED` and `PROJECTED_PLUS` require `funding_amount`).

**Step 2.1: Create account for stories**

```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Santander",
    "currency": "GBP",
    "current_balance": 10000.00,
    "is_default": true
  }' | jq '.id'
```

Save account ID: `ACCOUNT_ID="<uuid>"`

**Step 2.2: Story with PROJECTED mode (no funding_amount required)**

```bash
curl -X POST http://localhost:8000/api/stories \
  -H "Content-Type: application/json" \
  -d '{
    "name": "house-deposit",
    "start_date": "2025-03-01",
    "end_date": "2025-12-31",
    "default_account_id": "'$ACCOUNT_ID'",
    "funding_mode": "projected",
    "goal_type": "end_with_at_least",
    "goal_amount": 20000.00,
    "display_currency": "GBP"
  }' | jq '.'
```

**Expected:**
- Status: `201 Created`
- `"funding_mode": "projected"`
- `"funding_amount": null`

**Step 2.3: Story with FIXED mode WITHOUT funding_amount (should fail)**

```bash
curl -X POST http://localhost:8000/api/stories \
  -H "Content-Type: application/json" \
  -d '{
    "name": "volvo",
    "start_date": "2025-02-01",
    "end_date": "2025-06-30",
    "default_account_id": "'$ACCOUNT_ID'",
    "funding_mode": "fixed",
    "goal_type": "spend_up_to",
    "goal_amount": 15000.00,
    "display_currency": "GBP"
  }' | jq '.'
```

**Expected:**
- Status: `422 Unprocessable Entity`
- Error: `funding_amount required for fixed mode`

**Step 2.4: Story with FIXED mode WITH funding_amount (should succeed)**

```bash
curl -X POST http://localhost:8000/api/stories \
  -H "Content-Type: application/json" \
  -d '{
    "name": "volvo",
    "start_date": "2025-02-01",
    "end_date": "2025-06-30",
    "default_account_id": "'$ACCOUNT_ID'",
    "funding_mode": "fixed",
    "funding_amount": 12000.00,
    "goal_type": "spend_up_to",
    "goal_amount": 15000.00,
    "display_currency": "GBP"
  }' | jq '.'
```

**Expected:**
- Status: `201 Created`
- `"funding_mode": "fixed"`
- `"funding_amount": "12000.0"`

**Step 2.5: Story with PROJECTED_PLUS mode WITH funding_amount**

```bash
curl -X POST http://localhost:8000/api/stories \
  -H "Content-Type: application/json" \
  -d '{
    "name": "skiing-2025",
    "start_date": "2025-01-10",
    "end_date": "2025-01-20",
    "default_account_id": "'$ACCOUNT_ID'",
    "funding_mode": "projected_plus",
    "funding_amount": 2000.00,
    "goal_type": "spend_up_to",
    "goal_amount": 3500.00,
    "display_currency": "GBP"
  }' | jq '.'
```

**Expected:**
- Status: `201 Created`
- `"funding_mode": "projected_plus"`
- `"funding_amount": "2000.0"`

**Business Rule Verified:** ✅ FIXED and PROJECTED_PLUS modes require funding_amount

---

### Scenario 3: Event Account Resolution

**Purpose:** Verify 3-level account resolution hierarchy:
1. Explicit `account_id` → use it
2. Story's `default_account_id` → use it
3. Global default account → fallback

**Step 3.1: Setup - Create two accounts**

```bash
# Account 1: GBP (default)
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Monzo GBP",
    "currency": "GBP",
    "current_balance": 5000.00,
    "is_default": true
  }' | jq '.id'
```

Save: `GBP_ACCOUNT_ID="<uuid>"`

```bash
# Account 2: USD (not default)
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Chase USD",
    "currency": "USD",
    "current_balance": 8000.00,
    "is_default": false
  }' | jq '.id'
```

Save: `USD_ACCOUNT_ID="<uuid>"`

**Step 3.2: Create story with USD account as default**

```bash
curl -X POST http://localhost:8000/api/stories \
  -H "Content-Type: application/json" \
  -d '{
    "name": "new-york-trip",
    "start_date": "2025-05-01",
    "end_date": "2025-05-15",
    "default_account_id": "'$USD_ACCOUNT_ID'",
    "funding_mode": "projected",
    "goal_type": "spend_up_to",
    "goal_amount": 4000.00,
    "display_currency": "USD"
  }' | jq '.id'
```

Save: `STORY_ID="<uuid>"`

**Step 3.3: Level 1 - Explicit account_id takes precedence**

```bash
# Create event with explicit GBP account, but story has USD default
curl -X POST http://localhost:8000/api/events?story_id=$STORY_ID \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-05-05",
    "description": "Hotel (paid from GBP account)",
    "amount": -300.00,
    "currency": "GBP",
    "account_id": "'$GBP_ACCOUNT_ID'",
    "is_baseline": false,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.account_id'
```

**Expected:**
- `account_id` matches `$GBP_ACCOUNT_ID` (explicit overrides story default)

**Step 3.4: Level 2 - Story's default_account_id**

```bash
# Create event WITHOUT account_id - should use story's default
curl -X POST http://localhost:8000/api/events?story_id=$STORY_ID \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-05-06",
    "description": "Restaurant",
    "amount": -85.00,
    "currency": "USD",
    "is_baseline": false,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.account_id'
```

**Expected:**
- `account_id` matches `$USD_ACCOUNT_ID` (story's default account)

**Step 3.5: Level 3 - Global default account**

```bash
# Create baseline event (no story, no explicit account) - uses global default
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-01-15",
    "description": "Grocery shopping",
    "amount": -75.00,
    "currency": "GBP",
    "is_baseline": true,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.account_id'
```

**Expected:**
- `account_id` matches `$GBP_ACCOUNT_ID` (global default account)

**Business Rule Verified:** ✅ 3-level account resolution hierarchy working correctly

---

### Scenario 4: Recurring Rules CRUD

**Purpose:** Verify recurring rule creation, listing, update, and deletion.

**Step 4.1: Setup - Get default account**

```bash
curl http://localhost:8000/api/accounts | jq '.[] | select(.is_default==true) | .id'
```

Save: `ACCOUNT_ID="<uuid>"`

**Step 4.2: Create monthly recurring rule (salary)**

```bash
curl -X POST http://localhost:8000/api/recurring_rules \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Monthly Salary",
    "amount": 3500.00,
    "currency": "GBP",
    "account_id": "'$ACCOUNT_ID'",
    "frequency": "monthly",
    "day": 28,
    "start_date": "2025-01-01",
    "end_date": null
  }' | jq '.'
```

**Expected:**
- Status: `201 Created`
- `"frequency": "monthly"`
- `"day": 28`
- Response includes `id`, `created_at`, `updated_at`

Save: `RULE_ID="<uuid>"`

**Step 4.3: Create weekly recurring rule (groceries)**

```bash
curl -X POST http://localhost:8000/api/recurring_rules \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Weekly Groceries",
    "amount": -120.00,
    "currency": "GBP",
    "account_id": "'$ACCOUNT_ID'",
    "frequency": "weekly",
    "day": 6,
    "start_date": "2025-01-04",
    "end_date": null
  }' | jq '.'
```

**Expected:**
- Status: `201 Created`
- `"frequency": "weekly"`
- `"day": 6` (Saturday)

**Step 4.4: List all recurring rules**

```bash
curl http://localhost:8000/api/recurring_rules | jq '.'
```

**Expected:**
- Status: `200 OK`
- Array with 2 rules (Monthly Salary, Weekly Groceries)

**Step 4.5: Get single recurring rule**

```bash
curl http://localhost:8000/api/recurring_rules/$RULE_ID | jq '.'
```

**Expected:**
- Status: `200 OK`
- Full rule details for Monthly Salary

**Step 4.6: Update recurring rule amount**

```bash
curl -X PUT http://localhost:8000/api/recurring_rules/$RULE_ID \
  -H "Content-Type: application/json" \
  -d '{"amount": 3750.00}' | jq '.'
```

**Expected:**
- Status: `200 OK`
- `"amount": "3750.0"` (updated)
- `updated_at` timestamp changed

**Step 4.7: Try to create rule with invalid account (should fail)**

```bash
curl -X POST http://localhost:8000/api/recurring_rules \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Test Invalid Account",
    "amount": -50.00,
    "currency": "GBP",
    "account_id": "00000000-0000-0000-0000-000000000000",
    "frequency": "monthly",
    "day": 15,
    "start_date": "2025-01-01"
  }' | jq '.'
```

**Expected:**
- Status: `404 Not Found` or `422 Unprocessable Entity`
- Error message: Account not found or invalid account_id

**Step 4.8: Delete recurring rule**

```bash
curl -X DELETE http://localhost:8000/api/recurring_rules/$RULE_ID
```

**Expected:**
- Status: `204 No Content`
- Empty response body

**Step 4.9: Verify deletion**

```bash
curl http://localhost:8000/api/recurring_rules/$RULE_ID | jq '.'
```

**Expected:**
- Status: `404 Not Found`

**Business Rule Verified:** ✅ Full CRUD operations on recurring rules working

---

### Scenario 5: Settings Singleton Pattern

**Purpose:** Verify settings auto-create on first GET and singleton behavior.

**Step 5.1: Clear settings (if any exist)**

```bash
# Note: This requires direct MongoDB access or a test endpoint
# For manual testing, ensure settings collection is empty before starting
```

**Step 5.2: GET settings (auto-create defaults)**

```bash
curl http://localhost:8000/api/settings | jq '.'
```

**Expected:**
- Status: `200 OK`
- Default settings created:
  - `"base_currency": "GBP"`
  - `"default_currency": "GBP"`
  - `"date_format": "DD/MM/YYYY"`
  - `"baseline_display_months": 1`
  - Default rates for USD, CAD, EUR
  - `"version": "1.0.0"`

Save: `SETTINGS_ID="<uuid>"`

**Step 5.3: GET settings again (returns same singleton)**

```bash
curl http://localhost:8000/api/settings | jq '.id'
```

**Expected:**
- Same `id` as Step 5.2 (singleton)

**Step 5.4: Update settings (partial update)**

```bash
curl -X PUT http://localhost:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "rates": {
      "USD": "1.30",
      "EUR": "1.20"
    }
  }' | jq '.'
```

**Expected:**
- Status: `200 OK`
- `rates` updated with new values
- Other fields unchanged
- `updated_at` timestamp changed

**Step 5.5: Update multiple fields**

```bash
curl -X PUT http://localhost:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "base_currency": "USD",
    "default_currency": "USD",
    "baseline_display_months": 3
  }' | jq '.'
```

**Expected:**
- Status: `200 OK`
- All specified fields updated
- `rates` from Step 5.4 preserved

**Business Rule Verified:** ✅ Settings singleton pattern working correctly

---

### Scenario 6: Story Cascade Delete

**Purpose:** Verify that deleting a story removes all associated events.

**Step 6.1: Setup - Create account**

```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Account",
    "currency": "GBP",
    "current_balance": 5000.00,
    "is_default": true
  }' | jq '.id'
```

Save: `ACCOUNT_ID="<uuid>"`

**Step 6.2: Create story**

```bash
curl -X POST http://localhost:8000/api/stories \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-story-delete",
    "start_date": "2025-02-01",
    "end_date": "2025-03-01",
    "default_account_id": "'$ACCOUNT_ID'",
    "funding_mode": "projected",
    "goal_type": "none",
    "display_currency": "GBP"
  }' | jq '.id'
```

Save: `STORY_ID="<uuid>"`

**Step 6.3: Create 3 events for this story**

```bash
# Event 1
curl -X POST http://localhost:8000/api/events?story_id=$STORY_ID \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-02-10",
    "description": "Event 1",
    "amount": -100.00,
    "currency": "GBP",
    "is_baseline": false,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.id'
```

Save: `EVENT1_ID="<uuid>"`

```bash
# Event 2
curl -X POST http://localhost:8000/api/events?story_id=$STORY_ID \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-02-15",
    "description": "Event 2",
    "amount": -200.00,
    "currency": "GBP",
    "is_baseline": false,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.id'
```

Save: `EVENT2_ID="<uuid>"`

```bash
# Event 3
curl -X POST http://localhost:8000/api/events?story_id=$STORY_ID \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-02-20",
    "description": "Event 3",
    "amount": -150.00,
    "currency": "GBP",
    "is_baseline": false,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.id'
```

Save: `EVENT3_ID="<uuid>"`

**Step 6.4: Verify events exist**

```bash
curl "http://localhost:8000/api/events?story_id=$STORY_ID" | jq 'length'
```

**Expected:**
- Returns: `3` (3 events associated with story)

**Step 6.5: Delete the story**

```bash
curl -X DELETE http://localhost:8000/api/stories/$STORY_ID
```

**Expected:**
- Status: `204 No Content`

**Step 6.6: Verify story deleted**

```bash
curl http://localhost:8000/api/stories/$STORY_ID | jq '.'
```

**Expected:**
- Status: `404 Not Found`

**Step 6.7: Verify ALL events deleted (cascade)**

```bash
# Check Event 1
curl http://localhost:8000/api/events/$EVENT1_ID | jq '.'

# Check Event 2
curl http://localhost:8000/api/events/$EVENT2_ID | jq '.'

# Check Event 3
curl http://localhost:8000/api/events/$EVENT3_ID | jq '.'
```

**Expected for ALL:**
- Status: `404 Not Found` (all events deleted via cascade)

**Step 6.8: Create one-off baseline event (verify not affected by story deletion)**

One-off events with `is_baseline=true` are part of the baseline collection but independent of stories:

```bash
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-02-10",
    "description": "One-off Baseline Event",
    "amount": -50.00,
    "currency": "GBP",
    "is_baseline": true,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.id'
```

Save: `BASELINE_ID="<uuid>"`

Verify it still exists after story deletion (one-off baseline events are independent of stories):

```bash
curl http://localhost:8000/api/events/$BASELINE_ID | jq '.'
```

**Expected:**
- Status: `200 OK`
- One-off baseline event unaffected by story deletion

**Business Rule Verified:** ✅ Story deletion cascades to story events only, one-off baseline events (is_baseline=true, story_id=null) are preserved

---

## API Endpoint Reference

### Account Endpoints

#### 1. List All Accounts

**Endpoint:** `GET /api/accounts`

**Purpose:** Retrieve all accounts (active and archived).

**Request:**
```bash
curl http://localhost:8000/api/accounts | jq '.'
```

**Success Response:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Monzo",
    "currency": "GBP",
    "current_balance": "2500.0",
    "balance_updated_at": "2024-12-18T10:30:00",
    "is_default": true,
    "is_archived": false,
    "pending_reconciliation": false,
    "created_at": "2024-12-15T00:00:00",
    "updated_at": "2024-12-18T10:30:00"
  }
]
```

**Status Codes:**
- `200 OK`: Success

**Business Rules:**
- Returns empty array `[]` if no accounts exist
- Exactly one account has `is_default=true`
- Archived accounts included (filter client-side if needed)

---

#### 2. Get Single Account

**Endpoint:** `GET /api/accounts/{id}`

**Purpose:** Retrieve a specific account by ID.

**Request:**
```bash
ACCOUNT_ID="550e8400-e29b-41d4-a716-446655440000"
curl http://localhost:8000/api/accounts/$ACCOUNT_ID | jq '.'
```

**Success Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Monzo",
  "currency": "GBP",
  "current_balance": "2500.0",
  "balance_updated_at": "2024-12-18T10:30:00",
  "is_default": true,
  "is_archived": false,
  "pending_reconciliation": false,
  "created_at": "2024-12-15T00:00:00",
  "updated_at": "2024-12-18T10:30:00"
}
```

**Error Response (404):**
```json
{
  "detail": "Account not found"
}
```

**Status Codes:**
- `200 OK`: Account found
- `404 Not Found`: Account doesn't exist

---

#### 3. Create Account

**Endpoint:** `POST /api/accounts`

**Purpose:** Create a new account.

**Request:**
```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "HSBC",
    "currency": "USD",
    "current_balance": 5000.00,
    "is_default": false
  }' | jq '.'
```

**Required Fields:**
- `name` (string, min 1 char)
- `currency` (string, 3 uppercase letters: GBP, USD, CAD, etc.)
- `current_balance` (number, can be negative for overdrafts)

**Optional Fields:**
- `balance_updated_at` (datetime, defaults to now)
- `is_default` (boolean, defaults to false if other accounts exist)
- `is_archived` (boolean, defaults to false)
- `pending_reconciliation` (boolean, defaults to false)

**Success Response:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "HSBC",
  "currency": "USD",
  "current_balance": "5000.0",
  "balance_updated_at": "2024-12-18T14:00:00",
  "is_default": false,
  "is_archived": false,
  "pending_reconciliation": false,
  "created_at": "2024-12-18T14:00:00",
  "updated_at": "2024-12-18T14:00:00"
}
```

**Error Response (422):**
```json
{
  "detail": [
    {
      "loc": ["body", "currency"],
      "msg": "Currency code must be 3 uppercase letters",
      "type": "value_error"
    }
  ]
}
```

**Status Codes:**
- `201 Created`: Account created successfully
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- First account created automatically gets `is_default=true`
- Currency code must be exactly 3 uppercase letters
- Balance can be negative (overdrafts allowed)

---

#### 4. Update Account

**Endpoint:** `PUT /api/accounts/{id}`

**Purpose:** Update an existing account (partial update supported).

**Request:**
```bash
ACCOUNT_ID="550e8400-e29b-41d4-a716-446655440000"

# Update only balance
curl -X PUT http://localhost:8000/api/accounts/$ACCOUNT_ID \
  -H "Content-Type: application/json" \
  -d '{
    "current_balance": 3200.50,
    "balance_updated_at": "2024-12-19T09:00:00"
  }' | jq '.'
```

**Updatable Fields (all optional):**
- `name`
- `currency`
- `current_balance`
- `balance_updated_at`
- `is_default`
- `is_archived`
- `pending_reconciliation`

**Success Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Monzo",
  "currency": "GBP",
  "current_balance": "3200.5",
  "balance_updated_at": "2024-12-19T09:00:00",
  "is_default": true,
  "is_archived": false,
  "pending_reconciliation": false,
  "created_at": "2024-12-15T00:00:00",
  "updated_at": "2024-12-19T09:15:00"
}
```

**Status Codes:**
- `200 OK`: Account updated
- `404 Not Found`: Account doesn't exist
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- Setting `is_default=true` automatically unsets other accounts' `is_default`
- `updated_at` timestamp automatically updated

---

#### 5. Delete (Archive) Account

**Endpoint:** `DELETE /api/accounts/{id}`

**Purpose:** Archive an account (soft delete - retains history).

**Request:**
```bash
ACCOUNT_ID="660e8400-e29b-41d4-a716-446655440001"
curl -X DELETE http://localhost:8000/api/accounts/$ACCOUNT_ID
```

**Success Response:**
- Status: `204 No Content`
- Empty body

**Error Response (409 - Cannot archive default):**
```json
{
  "detail": "Cannot archive the default account. Set another account as default first."
}
```

**Status Codes:**
- `204 No Content`: Account archived
- `404 Not Found`: Account doesn't exist
- `409 Conflict`: Cannot archive default account

**Business Rules:**
- Cannot archive the default account (must transfer `is_default` to another account first)
- Account is soft-deleted (`is_archived=true`), not removed from database
- Historical events retain reference to archived account

---

### Story Endpoints

#### 6. List All Stories

**Endpoint:** `GET /api/stories`

**Purpose:** Retrieve all stories.

**Request:**
```bash
curl http://localhost:8000/api/stories | jq '.'
```

**Success Response:**
```json
[
  {
    "id": "770e8400-e29b-41d4-a716-446655440000",
    "name": "canada-trip",
    "start_date": "2025-01-15",
    "end_date": "2025-02-15",
    "default_account_id": "550e8400-e29b-41d4-a716-446655440000",
    "funding_mode": "projected",
    "funding_amount": null,
    "goal_type": "spend_up_to",
    "goal_amount": "5000.0",
    "display_currency": "GBP",
    "created_at": "2024-12-18T15:00:00",
    "created_by": null,
    "updated_at": "2024-12-18T15:00:00",
    "updated_by": null
  }
]
```

**Status Codes:**
- `200 OK`: Success

**Business Rules:**
- Returns empty array `[]` if no stories exist
- Stories can have overlapping date ranges

---

#### 7. Get Single Story

**Endpoint:** `GET /api/stories/{id}`

**Purpose:** Retrieve a specific story by ID.

**Request:**
```bash
STORY_ID="770e8400-e29b-41d4-a716-446655440000"
curl http://localhost:8000/api/stories/$STORY_ID | jq '.'
```

**Success Response:**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "name": "canada-trip",
  "start_date": "2025-01-15",
  "end_date": "2025-02-15",
  "default_account_id": "550e8400-e29b-41d4-a716-446655440000",
  "funding_mode": "projected",
  "funding_amount": null,
  "goal_type": "spend_up_to",
  "goal_amount": "5000.0",
  "display_currency": "GBP",
  "created_at": "2024-12-18T15:00:00",
  "created_by": null,
  "updated_at": "2024-12-18T15:00:00",
  "updated_by": null
}
```

**Error Response (404):**
```json
{
  "detail": "Story not found"
}
```

**Status Codes:**
- `200 OK`: Story found
- `404 Not Found`: Story doesn't exist

---

#### 8. Create Story

**Endpoint:** `POST /api/stories`

**Purpose:** Create a new story.

**Request:**
```bash
curl -X POST http://localhost:8000/api/stories \
  -H "Content-Type: application/json" \
  -d '{
    "name": "house-deposit",
    "start_date": "2025-03-01",
    "end_date": "2025-12-31",
    "default_account_id": "550e8400-e29b-41d4-a716-446655440000",
    "funding_mode": "fixed",
    "funding_amount": 15000.00,
    "goal_type": "end_with_at_least",
    "goal_amount": 20000.00,
    "display_currency": "GBP"
  }' | jq '.'
```

**Required Fields:**
- `name` (string, min 1 char)
- `start_date` (date, YYYY-MM-DD)
- `display_currency` (string, 3 uppercase letters)

**Optional Fields:**
- `end_date` (date, must be >= start_date, null = ongoing)
- `default_account_id` (UUID, fallback for events)
- `funding_mode` (enum: "projected", "fixed", "projected_plus", default: "projected")
- `funding_amount` (number, required if funding_mode is "fixed" or "projected_plus")
- `goal_type` (enum: "end_with_at_least", "spend_up_to", "none", default: "none")
- `goal_amount` (number, required if goal_type != "none")

**Success Response:**
```json
{
  "id": "880e8400-e29b-41d4-a716-446655440000",
  "name": "house-deposit",
  "start_date": "2025-03-01",
  "end_date": "2025-12-31",
  "default_account_id": "550e8400-e29b-41d4-a716-446655440000",
  "funding_mode": "fixed",
  "funding_amount": "15000.0",
  "goal_type": "end_with_at_least",
  "goal_amount": "20000.0",
  "display_currency": "GBP",
  "created_at": "2024-12-18T16:00:00",
  "created_by": null,
  "updated_at": "2024-12-18T16:00:00",
  "updated_by": null
}
```

**Error Response (422):**
```json
{
  "detail": "funding_amount required for fixed mode"
}
```

**Status Codes:**
- `201 Created`: Story created
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- `end_date` must be >= `start_date`
- `funding_mode="fixed"` or `"projected_plus"` requires `funding_amount`
- `goal_type != "none"` requires `goal_amount`

---

#### 9. Update Story

**Endpoint:** `PUT /api/stories/{id}`

**Purpose:** Update an existing story (partial update supported).

**Request:**
```bash
STORY_ID="770e8400-e29b-41d4-a716-446655440000"

curl -X PUT http://localhost:8000/api/stories/$STORY_ID \
  -H "Content-Type: application/json" \
  -d '{
    "goal_amount": 6000.00
  }' | jq '.'
```

**Updatable Fields (all optional):**
- `name`
- `start_date`
- `end_date`
- `default_account_id`
- `funding_mode`
- `funding_amount`
- `goal_type`
- `goal_amount`
- `display_currency`

**Success Response:**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "name": "canada-trip",
  "start_date": "2025-01-15",
  "end_date": "2025-02-15",
  "default_account_id": "550e8400-e29b-41d4-a716-446655440000",
  "funding_mode": "projected",
  "funding_amount": null,
  "goal_type": "spend_up_to",
  "goal_amount": "6000.0",
  "display_currency": "GBP",
  "created_at": "2024-12-18T15:00:00",
  "created_by": null,
  "updated_at": "2024-12-18T17:00:00",
  "updated_by": null
}
```

**Status Codes:**
- `200 OK`: Story updated
- `404 Not Found`: Story doesn't exist
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- Changing `default_account_id` only affects future events (existing events unchanged)
- Date range validation applies if both dates provided

---

#### 10. Delete Story

**Endpoint:** `DELETE /api/stories/{id}`

**Purpose:** Delete a story and all associated events (cascade delete).

**Request:**
```bash
STORY_ID="770e8400-e29b-41d4-a716-446655440000"
curl -X DELETE http://localhost:8000/api/stories/$STORY_ID
```

**Success Response:**
- Status: `204 No Content`
- Empty body

**Status Codes:**
- `204 No Content`: Story deleted
- `404 Not Found`: Story doesn't exist

**Business Rules:**
- **Cascade delete:** All events with this `story_id` are also deleted
- Baseline events (story_id=null) are not affected

---

### Event Endpoints

#### 11. List All Events

**Endpoint:** `GET /api/events`

**Query Parameters:**
- `story_id` (UUID, optional): Filter by story
- `account_id` (UUID, optional): Filter by account
- `start_date` (date, optional): Filter events >= this date
- `end_date` (date, optional): Filter events <= this date

**Purpose:** Retrieve events with optional filtering.

**Request (all events):**
```bash
curl http://localhost:8000/api/events | jq '.'
```

**Request (filter by story):**
```bash
STORY_ID="770e8400-e29b-41d4-a716-446655440000"
curl "http://localhost:8000/api/events?story_id=$STORY_ID" | jq '.'
```

**Request (filter by account):**
```bash
ACCOUNT_ID="550e8400-e29b-41d4-a716-446655440000"
curl "http://localhost:8000/api/events?account_id=$ACCOUNT_ID" | jq '.'
```

**Request (filter by date range):**
```bash
curl "http://localhost:8000/api/events?start_date=2025-01-01&end_date=2025-01-31" | jq '.'
```

**Success Response:**
```json
[
  {
    "id": "990e8400-e29b-41d4-a716-446655440000",
    "event_date": "2025-01-20",
    "description": "Flight to Vancouver",
    "amount": "-450.0",
    "currency": "GBP",
    "rate_to_base": "1.0",
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "story_id": "770e8400-e29b-41d4-a716-446655440000",
    "is_baseline": false,
    "is_hypothetical": false,
    "is_auto_adjustment": false,
    "created_at": "2024-12-18T18:00:00",
    "created_by": null,
    "updated_at": "2024-12-18T18:00:00",
    "updated_by": null,
    "recurring_rule_id": null
  }
]
```

**Status Codes:**
- `200 OK`: Success

**Business Rules:**
- Same-day ordering: amount DESC (income first), then created_at ASC
- Returns empty array `[]` if no events match filters

---

#### 12. Get Single Event

**Endpoint:** `GET /api/events/{id}`

**Purpose:** Retrieve a specific event by ID.

**Request:**
```bash
EVENT_ID="990e8400-e29b-41d4-a716-446655440000"
curl http://localhost:8000/api/events/$EVENT_ID | jq '.'
```

**Success Response:**
```json
{
  "id": "990e8400-e29b-41d4-a716-446655440000",
  "event_date": "2025-01-20",
  "description": "Flight to Vancouver",
  "amount": "-450.0",
  "currency": "GBP",
  "rate_to_base": "1.0",
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "story_id": "770e8400-e29b-41d4-a716-446655440000",
  "is_baseline": false,
  "is_hypothetical": false,
  "is_auto_adjustment": false,
  "created_at": "2024-12-18T18:00:00",
  "created_by": null,
  "updated_at": "2024-12-18T18:00:00",
  "updated_by": null,
  "recurring_rule_id": null
}
```

**Error Response (404):**
```json
{
  "detail": "Event not found"
}
```

**Status Codes:**
- `200 OK`: Event found
- `404 Not Found`: Event doesn't exist

---

#### 13. Create Event

**Endpoint:** `POST /api/events`

**Query Parameters:**
- `story_id` (UUID, optional): Associate event with story

**Purpose:** Create a new event.

**Request (baseline event):**
```bash
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-01-10",
    "description": "Groceries",
    "amount": -85.50,
    "currency": "GBP",
    "is_baseline": true,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.'
```

**Request (story event):**
```bash
STORY_ID="770e8400-e29b-41d4-a716-446655440000"
curl -X POST "http://localhost:8000/api/events?story_id=$STORY_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "event_date": "2025-01-20",
    "description": "Hotel booking",
    "amount": -650.00,
    "currency": "GBP",
    "is_baseline": false,
    "is_hypothetical": false,
    "is_auto_adjustment": false
  }' | jq '.'
```

**Required Fields:**
- `event_date` (date, YYYY-MM-DD format)
- `description` (string, min 1 char)
- `amount` (number, positive=income, negative=expense)
- `currency` (string, 3 uppercase letters)
- `is_baseline` (boolean)
- `is_hypothetical` (boolean)
- `is_auto_adjustment` (boolean)

**Optional Fields:**
- `account_id` (UUID, resolved via 3-level hierarchy if not provided)
- `rate_to_base` (number, auto-locked from settings if not provided)

**Success Response:**
```json
{
  "id": "aa0e8400-e29b-41d4-a716-446655440000",
  "event_date": "2025-01-20",
  "description": "Hotel booking",
  "amount": "-650.0",
  "currency": "GBP",
  "rate_to_base": "1.0",
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "story_id": "770e8400-e29b-41d4-a716-446655440000",
  "is_baseline": false,
  "is_hypothetical": false,
  "is_auto_adjustment": false,
  "created_at": "2024-12-18T19:00:00",
  "created_by": null,
  "updated_at": "2024-12-18T19:00:00",
  "updated_by": null,
  "recurring_rule_id": null
}
```

**Error Response (422 - Baseline + Story conflict):**
```json
{
  "detail": "Baseline events cannot belong to a story"
}
```

**Status Codes:**
- `201 Created`: Event created
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- Account resolution: explicit account_id → story default → global default
- `rate_to_base` locked from current settings.rates at creation
- Baseline events cannot have `story_id` (validated)
- `date` field accepts both `date` and `event_date` for compatibility

---

#### 14. Update Event

**Endpoint:** `PUT /api/events/{id}`

**Purpose:** Update an existing event (partial update supported).

**Request:**
```bash
EVENT_ID="990e8400-e29b-41d4-a716-446655440000"

curl -X PUT http://localhost:8000/api/events/$EVENT_ID \
  -H "Content-Type: application/json" \
  -d '{
    "amount": -475.00,
    "description": "Flight to Vancouver (updated)"
  }' | jq '.'
```

**Updatable Fields (all optional):**
- `date` (or `event_date`)
- `description`
- `amount`
- `currency`
- `rate_to_base`
- `account_id`
- `story_id`
- `is_baseline`
- `is_hypothetical`
- `is_auto_adjustment`

**Success Response:**
```json
{
  "id": "990e8400-e29b-41d4-a716-446655440000",
  "event_date": "2025-01-20",
  "description": "Flight to Vancouver (updated)",
  "amount": "-475.0",
  "currency": "GBP",
  "rate_to_base": "1.0",
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "story_id": "770e8400-e29b-41d4-a716-446655440000",
  "is_baseline": false,
  "is_hypothetical": false,
  "is_auto_adjustment": false,
  "created_at": "2024-12-18T18:00:00",
  "created_by": null,
  "updated_at": "2024-12-18T20:00:00",
  "updated_by": null,
  "recurring_rule_id": null
}
```

**Status Codes:**
- `200 OK`: Event updated
- `404 Not Found`: Event doesn't exist
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- Past events CAN be edited (users may correct mistakes)
- Editing triggers recalculation of projections

---

#### 15. Delete Event

**Endpoint:** `DELETE /api/events/{id}`

**Purpose:** Delete an event.

**Request:**
```bash
EVENT_ID="990e8400-e29b-41d4-a716-446655440000"
curl -X DELETE http://localhost:8000/api/events/$EVENT_ID
```

**Success Response:**
- Status: `204 No Content`
- Empty body

**Status Codes:**
- `204 No Content`: Event deleted
- `404 Not Found`: Event doesn't exist

**Business Rules:**
- Hard delete (event permanently removed)
- No cascade effects (only the event is deleted)

---

### Recurring Rule Endpoints

#### 16. List All Recurring Rules

**Endpoint:** `GET /api/recurring_rules`

**Purpose:** Retrieve all recurring rules.

**Request:**
```bash
curl http://localhost:8000/api/recurring_rules | jq '.'
```

**Success Response:**
```json
[
  {
    "id": "bb0e8400-e29b-41d4-a716-446655440000",
    "description": "Monthly Salary",
    "amount": "3500.0",
    "currency": "GBP",
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "frequency": "monthly",
    "day": 28,
    "start_date": "2025-01-01",
    "end_date": null,
    "created_at": "2024-12-18T21:00:00",
    "updated_at": "2024-12-18T21:00:00"
  }
]
```

**Status Codes:**
- `200 OK`: Success

---

#### 17. Get Single Recurring Rule

**Endpoint:** `GET /api/recurring_rules/{id}`

**Purpose:** Retrieve a specific recurring rule by ID.

**Request:**
```bash
RULE_ID="bb0e8400-e29b-41d4-a716-446655440000"
curl http://localhost:8000/api/recurring_rules/$RULE_ID | jq '.'
```

**Success Response:**
```json
{
  "id": "bb0e8400-e29b-41d4-a716-446655440000",
  "description": "Monthly Salary",
  "amount": "3500.0",
  "currency": "GBP",
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "frequency": "monthly",
  "day": 28,
  "start_date": "2025-01-01",
  "end_date": null,
  "created_at": "2024-12-18T21:00:00",
  "updated_at": "2024-12-18T21:00:00"
}
```

**Error Response (404):**
```json
{
  "detail": "Recurring rule not found"
}
```

**Status Codes:**
- `200 OK`: Rule found
- `404 Not Found`: Rule doesn't exist

---

#### 18. Create Recurring Rule

**Endpoint:** `POST /api/recurring_rules`

**Purpose:** Create a new recurring rule.

**Request (monthly):**
```bash
curl -X POST http://localhost:8000/api/recurring_rules \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Rent",
    "amount": -1500.00,
    "currency": "GBP",
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "frequency": "monthly",
    "day": 1,
    "start_date": "2025-01-01",
    "end_date": null
  }' | jq '.'
```

**Request (weekly):**
```bash
curl -X POST http://localhost:8000/api/recurring_rules \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Weekly Groceries",
    "amount": -120.00,
    "currency": "GBP",
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "frequency": "weekly",
    "day": 6,
    "start_date": "2025-01-04",
    "end_date": null
  }' | jq '.'
```

**Required Fields:**
- `description` (string, min 1 char)
- `amount` (number, positive=income, negative=expense)
- `currency` (string, 3 uppercase letters)
- `account_id` (UUID)
- `frequency` (enum: "weekly", "monthly", "annual")
- `day` (integer):
  - Weekly: 1-7 (Monday=1, Sunday=7)
  - Monthly/Annual: 1-31
- `start_date` (date, YYYY-MM-DD)

**Optional Fields:**
- `end_date` (date, must be >= start_date, null = ongoing)

**Success Response:**
```json
{
  "id": "cc0e8400-e29b-41d4-a716-446655440000",
  "description": "Rent",
  "amount": "-1500.0",
  "currency": "GBP",
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "frequency": "monthly",
  "day": 1,
  "start_date": "2025-01-01",
  "end_date": null,
  "created_at": "2024-12-18T22:00:00",
  "updated_at": "2024-12-18T22:00:00"
}
```

**Error Response (422 - Invalid day for frequency):**
```json
{
  "detail": "Weekly frequency requires day 1-7 (Monday=1, Sunday=7)"
}
```

**Status Codes:**
- `201 Created`: Rule created
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- Day validation depends on frequency
- Events are generated within ±1 month generation window
- Modification affects future events only

---

#### 19. Update Recurring Rule

**Endpoint:** `PUT /api/recurring_rules/{id}`

**Purpose:** Update an existing recurring rule (partial update supported).

**Request:**
```bash
RULE_ID="bb0e8400-e29b-41d4-a716-446655440000"

curl -X PUT http://localhost:8000/api/recurring_rules/$RULE_ID \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 3750.00
  }' | jq '.'
```

**Updatable Fields (all optional):**
- `description`
- `amount`
- `currency`
- `account_id`
- `frequency`
- `day`
- `start_date`
- `end_date`

**Success Response:**
```json
{
  "id": "bb0e8400-e29b-41d4-a716-446655440000",
  "description": "Monthly Salary",
  "amount": "3750.0",
  "currency": "GBP",
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "frequency": "monthly",
  "day": 28,
  "start_date": "2025-01-01",
  "end_date": null,
  "created_at": "2024-12-18T21:00:00",
  "updated_at": "2024-12-18T23:00:00"
}
```

**Status Codes:**
- `200 OK`: Rule updated
- `404 Not Found`: Rule doesn't exist
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- Updating affects only future generated events
- Past events remain unchanged

---

#### 20. Delete Recurring Rule

**Endpoint:** `DELETE /api/recurring_rules/{id}`

**Purpose:** Delete a recurring rule.

**Request:**
```bash
RULE_ID="bb0e8400-e29b-41d4-a716-446655440000"
curl -X DELETE http://localhost:8000/api/recurring_rules/$RULE_ID
```

**Success Response:**
- Status: `204 No Content`
- Empty body

**Status Codes:**
- `204 No Content`: Rule deleted
- `404 Not Found`: Rule doesn't exist

**Business Rules:**
- Deletes rule and removes future generated events
- Past generated events are retained (historical record)

---

### Settings Endpoints

#### 21. Get Settings

**Endpoint:** `GET /api/settings`

**Purpose:** Retrieve global settings (singleton).

**Request:**
```bash
curl http://localhost:8000/api/settings | jq '.'
```

**Success Response:**
```json
{
  "id": "dd0e8400-e29b-41d4-a716-446655440000",
  "base_currency": "GBP",
  "default_currency": "GBP",
  "date_format": "DD/MM/YYYY",
  "baseline_display_months": 1,
  "rates": {
    "USD": "1.27",
    "EUR": "1.17",
    "CAD": "1.71"
  },
  "server_url": "",
  "last_backup_date": null,
  "version": "1.0.0",
  "created_at": "2024-12-18T00:00:00",
  "updated_at": "2024-12-18T00:00:00"
}
```

**Status Codes:**
- `200 OK`: Settings returned

**Business Rules:**
- **Singleton pattern:** Only one settings document exists
- **Auto-create:** If no settings exist, default settings are created on first GET
- Subsequent GET requests return the same singleton document

---

#### 22. Update Settings

**Endpoint:** `PUT /api/settings`

**Purpose:** Update global settings (partial update supported).

**Request (update rates):**
```bash
curl -X PUT http://localhost:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "rates": {
      "USD": "1.30",
      "EUR": "1.20",
      "CAD": "1.75"
    }
  }' | jq '.'
```

**Request (update base currency):**
```bash
curl -X PUT http://localhost:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "base_currency": "USD",
    "default_currency": "USD"
  }' | jq '.'
```

**Updatable Fields (all optional):**
- `base_currency` (string, 3 uppercase letters)
- `default_currency` (string, 3 uppercase letters)
- `date_format` (string)
- `baseline_display_months` (integer, 1-12)
- `rates` (dict, currency code → rate as string)
- `server_url` (string)
- `last_backup_date` (datetime)
- `version` (string)

**Success Response:**
```json
{
  "id": "dd0e8400-e29b-41d4-a716-446655440000",
  "base_currency": "USD",
  "default_currency": "USD",
  "date_format": "DD/MM/YYYY",
  "baseline_display_months": 1,
  "rates": {
    "GBP": "0.79",
    "EUR": "0.92",
    "CAD": "1.38"
  },
  "server_url": "",
  "last_backup_date": null,
  "version": "1.0.0",
  "created_at": "2024-12-18T00:00:00",
  "updated_at": "2024-12-19T00:00:00"
}
```

**Error Response (422 - Invalid currency code):**
```json
{
  "detail": [
    {
      "loc": ["body", "base_currency"],
      "msg": "Currency code must be 3 uppercase letters",
      "type": "value_error"
    }
  ]
}
```

**Status Codes:**
- `200 OK`: Settings updated
- `422 Unprocessable Entity`: Validation error

**Business Rules:**
- Partial updates supported (only specified fields changed)
- `updated_at` timestamp automatically updated
- Currency codes validated (must be 3 uppercase letters)
- Rates must be positive decimal values
- If no settings exist, creates default settings first, then applies update

---

## Error Response Reference

### Common HTTP Status Codes

| Code | Meaning | When It Occurs |
|------|---------|----------------|
| `200 OK` | Success | GET, PUT requests successful |
| `201 Created` | Resource created | POST requests successful |
| `204 No Content` | Success with no response body | DELETE requests successful |
| `404 Not Found` | Resource doesn't exist | GET/PUT/DELETE on non-existent ID |
| `409 Conflict` | Business rule violation | Archiving default account, etc. |
| `422 Unprocessable Entity` | Validation error | Invalid data format or business logic |

### Example Error Responses

**422 Validation Error:**
```json
{
  "detail": [
    {
      "loc": ["body", "currency"],
      "msg": "Currency code must be 3 uppercase letters",
      "type": "value_error"
    }
  ]
}
```

**404 Not Found:**
```json
{
  "detail": "Account not found"
}
```

**409 Conflict:**
```json
{
  "detail": "Cannot archive the default account. Set another account as default first."
}
```

---

## Additional Resources

### Testing with jq

**Pretty-print JSON:**
```bash
curl http://localhost:8000/api/accounts | jq '.'
```

**Extract specific fields:**
```bash
curl http://localhost:8000/api/accounts | jq '.[] | {name: .name, balance: .current_balance}'
```

**Filter by condition:**
```bash
curl http://localhost:8000/api/accounts | jq '.[] | select(.is_default==true)'
```

### Useful MongoDB Queries

**Count documents:**
```bash
mongosh mongodb://localhost:63000/chaptr --eval "db.accounts.countDocuments({})"
```

**View all accounts:**
```bash
mongosh mongodb://localhost:63000/chaptr --eval "db.accounts.find().pretty()"
```

**Clear collection:**
```bash
mongosh mongodb://localhost:63000/chaptr --eval "db.accounts.deleteMany({})"
```

---

## Changelog

**Version 1.0 (December 2024)**
- Initial manual testing guide
- All 22 endpoints documented
- 6 comprehensive testing scenarios
- Business rule validation
- Error response reference

---

**End of Manual Testing Guide**
