# CHAPTR Testing Guide

**Version:** 1.0
**Last Updated:** January 2025

> Comprehensive testing guide covering backend API validation, sync protocol testing, offline capabilities, and queue-as-state architecture validation.

---

# PART I: Backend API Testing


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

---
---

# PART II: Sync Protocol Testing

This guide provides step-by-step curl commands to manually test sync functionality with simulated multi-client scenarios and conflict detection.

---

## Prerequisites

### 1. Start API Server

```bash
# In project root directory
uvicorn api.main:app --reload
```

Server will be available at: `http://localhost:8000`

### 2. Get Authentication Token

**Login as admin user:**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "Edward",
    "password": "your_password_here"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"
```

**Note**: Replace `your_password_here` with actual admin password.

### 3. Create Test Account

```bash
ACCOUNT_ID=$(curl -s -X POST http://localhost:8000/api/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Account",
    "currency": "GBP",
    "current_balance": 1000.00,
    "balance_updated_at": "2025-12-23T00:00:00Z",
    "is_default": true,
    "is_archived": false,
    "pending_reconciliation": false
  }' | jq -r '.id')

echo "Account ID: $ACCOUNT_ID"
```

### 4. Create Test Story (Optional)

```bash
STORY_ID=$(curl -s -X POST http://localhost:8000/api/stories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Story",
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
    "default_account_id": "'"$ACCOUNT_ID"'",
    "funding_mode": "projected",
    "funding_amount": null,
    "goal_type": "none",
    "goal_amount": null,
    "display_currency": "GBP"
  }' | jq -r '.id')

echo "Story ID: $STORY_ID"
```

---

## Test 1: Two-Device Sync (Task 26)

### Scenario Overview

Simulate two devices syncing with the same user account:
- **Device A**: Creates Event E1 and syncs
- **Device B**: Syncs and receives E1
- **Device B**: Creates Event E2 and syncs
- **Device A**: Syncs again and receives E2

---

### Step 1: Device A - Create Event E1

```bash
EVENT_E1_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-a",
    "last_sync_at": null,
    "changes": [
      {
        "entity_type": "event",
        "entity_id": "'"$EVENT_E1_ID"'",
        "action": "create",
        "data": {
          "event_date": "2025-01-15",
          "description": "Event from Device A",
          "amount": -50.00,
          "currency": "GBP",
          "account_id": "'"$ACCOUNT_ID"'",
          "story_id": null,
          "is_baseline": true,
          "is_hypothetical": false,
          "is_auto_adjustment": false
        },
        "base_updated_at": null
      }
    ]
  }' | jq '.'
```

**Expected Output:**
```json
{
  "applied": ["<EVENT_E1_ID>"],
  "conflicts": [],
  "server_changes": [],
  "sync_timestamp": "2025-12-23T...",
  "full_sync_required": false
}
```

**Save sync timestamp for Device A:**
```bash
SYNC_TS_A=$(curl -s -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-a",
    "last_sync_at": null,
    "changes": []
  }' | jq -r '.sync_timestamp')

echo "Device A Sync Timestamp: $SYNC_TS_A"
```

---

### Step 2: Device B - First Sync (Receive E1)

```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-b",
    "last_sync_at": null,
    "changes": []
  }' | jq '.'
```

**Expected Output:**
```json
{
  "applied": [],
  "conflicts": [],
  "server_changes": [
    {
      "entity_type": "event",
      "entity_id": "<EVENT_E1_ID>",
      "action": "create",
      "data": {
        "event_date": "2025-01-15",
        "description": "Event from Device A",
        ...
      }
    }
  ],
  "sync_timestamp": "2025-12-23T...",
  "full_sync_required": false
}
```

**Verify**: `server_changes` should include Event E1 created by Device A.

**Save sync timestamp for Device B:**
```bash
SYNC_TS_B=$(curl -s -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-b",
    "last_sync_at": null,
    "changes": []
  }' | jq -r '.sync_timestamp')

echo "Device B Sync Timestamp: $SYNC_TS_B"
```

---

### Step 3: Device B - Create Event E2

```bash
EVENT_E2_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-b",
    "last_sync_at": "'"$SYNC_TS_B"'",
    "changes": [
      {
        "entity_type": "event",
        "entity_id": "'"$EVENT_E2_ID"'",
        "action": "create",
        "data": {
          "event_date": "2025-01-16",
          "description": "Event from Device B",
          "amount": -75.00,
          "currency": "GBP",
          "account_id": "'"$ACCOUNT_ID"'",
          "story_id": null,
          "is_baseline": true,
          "is_hypothetical": false,
          "is_auto_adjustment": false
        },
        "base_updated_at": null
      }
    ]
  }' | jq '.'
```

**Expected Output:**
```json
{
  "applied": ["<EVENT_E2_ID>"],
  "conflicts": [],
  "server_changes": [],
  "sync_timestamp": "2025-12-23T...",
  "full_sync_required": false
}
```

---

### Step 4: Device A - Second Sync (Receive E2, NOT E1)

```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-a",
    "last_sync_at": "'"$SYNC_TS_A"'",
    "changes": []
  }' | jq '.'
```

**Expected Output:**
```json
{
  "applied": [],
  "conflicts": [],
  "server_changes": [
    {
      "entity_type": "event",
      "entity_id": "<EVENT_E2_ID>",
      "action": "create",
      "data": {
        "description": "Event from Device B",
        ...
      }
    }
  ],
  "sync_timestamp": "2025-12-23T...",
  "full_sync_required": false
}
```

**Verify**:
- ✅ `server_changes` includes Event E2 (from Device B)
- ✅ `server_changes` does NOT include Event E1 (Device A's own event)

---

## Test 2: Edit/Edit Conflict Detection (Task 27)

### Scenario Overview

Two devices edit the same event simultaneously:
- **Device A**: Fetches Event E1 (timestamp T1)
- **Device B**: Fetches Event E1 (timestamp T1)
- **Device A**: Edits E1, syncs successfully (server now T2)
- **Device B**: Edits E1 with old timestamp T1 → **CONFLICT**

---

### Step 1: Create Event E1

```bash
EVENT_E1_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-setup",
    "last_sync_at": null,
    "changes": [
      {
        "entity_type": "event",
        "entity_id": "'"$EVENT_E1_ID"'",
        "action": "create",
        "data": {
          "event_date": "2025-01-20",
          "description": "Original Event",
          "amount": -100.00,
          "currency": "GBP",
          "account_id": "'"$ACCOUNT_ID"'",
          "story_id": null,
          "is_baseline": true,
          "is_hypothetical": false,
          "is_auto_adjustment": false
        },
        "base_updated_at": null
      }
    ]
  }' | jq '.'
```

---

### Step 2: Fetch Event E1 (Get Base Timestamp)

```bash
BASE_TS=$(curl -s -X GET "http://localhost:8000/api/events/$EVENT_E1_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.updated_at')

echo "Base Timestamp: $BASE_TS"
```

---

### Step 3: Device A - Edit Event E1 (Succeeds)

```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-a",
    "last_sync_at": null,
    "changes": [
      {
        "entity_type": "event",
        "entity_id": "'"$EVENT_E1_ID"'",
        "action": "update",
        "data": {
          "description": "Updated by Device A",
          "amount": -150.00
        },
        "base_updated_at": "'"$BASE_TS"'"
      }
    ]
  }' | jq '.'
```

**Expected Output:**
```json
{
  "applied": ["<EVENT_E1_ID>"],
  "conflicts": [],
  ...
}
```

**Verify**: Edit applied successfully.

---

### Step 4: Device B - Edit Event E1 with Old Timestamp (CONFLICT)

```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-b",
    "last_sync_at": null,
    "changes": [
      {
        "entity_type": "event",
        "entity_id": "'"$EVENT_E1_ID"'",
        "action": "update",
        "data": {
          "description": "Updated by Device B",
          "amount": -200.00
        },
        "base_updated_at": "'"$BASE_TS"'"
      }
    ]
  }' | jq '.'
```

**Expected Output:**
```json
{
  "applied": [],
  "conflicts": [
    {
      "entity_type": "event",
      "entity_id": "<EVENT_E1_ID>",
      "conflict_type": "edit_edit",
      "client_version": {
        "description": "Updated by Device B",
        "amount": -200.00
      },
      "server_version": {
        "description": "Updated by Device A",
        "amount": -150.00,
        ...
      }
    }
  ],
  ...
}
```

**Verify**:
- ✅ `applied` is empty (no changes applied)
- ✅ `conflicts` array has 1 conflict
- ✅ Conflict type is `"edit_edit"`
- ✅ `client_version` shows Device B's attempted change
- ✅ `server_version` shows Device A's applied change

---

## Test 3: Delete/Edit Conflict Detection (Task 27)

### Scenario Overview

One device edits, another deletes:
- **Device A**: Fetches Event E1 (timestamp T1)
- **Device B**: Fetches Event E1 (timestamp T1)
- **Device A**: Edits E1, syncs successfully (server now T2)
- **Device B**: Deletes E1 with old timestamp T1 → **CONFLICT**

---

### Step 1: Create Event E1 (Same as Edit/Edit Test)

```bash
EVENT_E1_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-setup",
    "last_sync_at": null,
    "changes": [
      {
        "entity_type": "event",
        "entity_id": "'"$EVENT_E1_ID"'",
        "action": "create",
        "data": {
          "event_date": "2025-01-25",
          "description": "Event to Delete",
          "amount": -50.00,
          "currency": "GBP",
          "account_id": "'"$ACCOUNT_ID"'",
          "story_id": null,
          "is_baseline": true,
          "is_hypothetical": false,
          "is_auto_adjustment": false
        },
        "base_updated_at": null
      }
    ]
  }' | jq '.'
```

---

### Step 2: Get Base Timestamp

```bash
BASE_TS=$(curl -s -X GET "http://localhost:8000/api/events/$EVENT_E1_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.updated_at')

echo "Base Timestamp: $BASE_TS"
```

---

### Step 3: Device A - Edit Event E1 (Succeeds)

```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-a",
    "last_sync_at": null,
    "changes": [
      {
        "entity_type": "event",
        "entity_id": "'"$EVENT_E1_ID"'",
        "action": "update",
        "data": {
          "description": "Modified before delete attempt"
        },
        "base_updated_at": "'"$BASE_TS"'"
      }
    ]
  }' | jq '.'
```

---

### Step 4: Device B - Delete Event E1 with Old Timestamp (CONFLICT)

```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "device-b",
    "last_sync_at": null,
    "changes": [
      {
        "entity_type": "event",
        "entity_id": "'"$EVENT_E1_ID"'",
        "action": "delete",
        "data": null,
        "base_updated_at": "'"$BASE_TS"'"
      }
    ]
  }' | jq '.'
```

**Expected Output:**
```json
{
  "applied": [],
  "conflicts": [
    {
      "entity_type": "event",
      "entity_id": "<EVENT_E1_ID>",
      "conflict_type": "delete_edit",
      "client_version": null,
      "server_version": {
        "description": "Modified before delete attempt",
        ...
      }
    }
  ],
  ...
}
```

**Verify**:
- ✅ `applied` is empty (delete NOT applied)
- ✅ `conflicts` has 1 conflict
- ✅ Conflict type is `"delete_edit"`
- ✅ `client_version` is `null` (client wanted to delete)
- ✅ `server_version` shows current entity state

---

### Step 5: Verify Entity Still Exists

```bash
curl -X GET "http://localhost:8000/api/events/$EVENT_E1_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.description'
```

**Expected Output:**
```json
"Modified before delete attempt"
```

**Verify**: Entity was NOT deleted due to conflict.

---

## Test 4: Stale Client Recovery

### Scenario Overview

Client with very old `last_sync_at` (before oldest change_log entry) should receive `full_sync_required=true`.

---

### Step 1: Create Old Sync Timestamp (60 Days Ago)

```bash
OLD_SYNC=$(date -u -v-60d +"%Y-%m-%dT%H:%M:%SZ")

echo "Old Sync Timestamp: $OLD_SYNC"
```

---

### Step 2: Attempt Sync with Stale Timestamp

```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "stale-client",
    "last_sync_at": "'"$OLD_SYNC"'",
    "changes": []
  }' | jq '.'
```

**Expected Output:**
```json
{
  "applied": [],
  "conflicts": [],
  "server_changes": [],
  "sync_timestamp": "2025-12-23T...",
  "full_sync_required": true
}
```

**Verify**:
- ✅ `full_sync_required` is `true`
- ✅ `server_changes` is empty array

---

### Step 3: Perform Full Sync

```bash
curl -X GET http://localhost:8000/api/sync/full \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.'
```

**Expected Output:**
```json
{
  "accounts": [...],
  "stories": [...],
  "events": [...],
  "recurring_rules": [...],
  "settings": {...},
  "sync_timestamp": "2025-12-23T..."
}
```

**Verify**:
- ✅ All entity types included
- ✅ `sync_timestamp` provided
- ✅ Data filtered by current user

---

## Validation Checklist

### Task 26: Multi-Client Sync
- [ ] Device A creates event, Device B receives it
- [ ] Device B creates event, Device A receives it
- [ ] Devices don't receive their own changes back
- [ ] `sync_timestamp` updates with each sync

### Task 27: Conflict Detection
- [ ] Edit/Edit conflict returns both versions
- [ ] Delete/Edit conflict prevents deletion
- [ ] Conflict types correct (`"edit_edit"`, `"delete_edit"`)
- [ ] `client_version` and `server_version` populated correctly
- [ ] Conflicted changes NOT applied

### General
- [ ] All sync responses have required fields
- [ ] Timestamps in ISO 8601 format
- [ ] UUIDs properly formatted
- [ ] Authentication working correctly
- [ ] No server errors (500 responses)

---

## Cleanup

### Delete Test Data

```bash
# Delete events
curl -X DELETE "http://localhost:8000/api/events/$EVENT_E1_ID" \
  -H "Authorization: Bearer $TOKEN"

curl -X DELETE "http://localhost:8000/api/events/$EVENT_E2_ID" \
  -H "Authorization: Bearer $TOKEN"

# Delete story (if created)
curl -X DELETE "http://localhost:8000/api/stories/$STORY_ID" \
  -H "Authorization: Bearer $TOKEN"

# Delete account
curl -X DELETE "http://localhost:8000/api/accounts/$ACCOUNT_ID" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Troubleshooting

### 401 Unauthorized
- Token expired or invalid
- Run login command again to get fresh token

### 422 Validation Error
- Check JSON payload format
- Verify all required fields present
- Ensure UUIDs are valid format

### 500 Internal Server Error
- Check server logs: `docker logs <container-id>` or terminal output
- Verify MongoDB connection
- Check for data consistency issues

### Conflicts Not Detected
- Ensure `base_updated_at` matches entity's current `updated_at`
- Verify second edit happens AFTER first edit completes
- Check change log entries created correctly

---

## Notes

- Replace `<EVENT_E1_ID>`, `<ACCOUNT_ID>`, etc., with actual UUIDs from responses
- Use `jq` for JSON formatting (install via `brew install jq` on macOS)
- Save sync timestamps for subsequent requests
- Test with real MongoDB, not mongomock, for accurate behavior

---
---

# PART III: Offline & Progressive Enhancement Testing

**Date:** December 23, 2024

---

## Testing Overview

This guide covers manual testing for Phase 5's three-tier progressive enhancement architecture. All implementation is complete - these tests validate the system works correctly across all modes and network conditions.

**7 Remaining Tasks:**
- Task 106: Test app functionality in airplane mode
- Task 107: Make changes offline and verify queuing
- Task 108: Restore connection and verify sync completes
- Task 109: Verify offline/online indicators work correctly
- Task 220: Test Mode 1 Full with offline/online switching
- Task 221: Test Mode 2 Sync-Only in private browsing
- Task 222: Test Mode 3 Basic in HTTP environment

---

## Prerequisites

### Environment Setup

**Mode 1 (Full) Testing:**
- HTTPS environment (required for service worker)
- Modern browser with IndexedDB support
- Network toggle capability (Chrome DevTools or Firefox DevTools)

**Mode 2 (Sync-Only) Testing:**
- Private browsing mode OR
- Browser with IndexedDB disabled

**Mode 3 (Basic) Testing:**
- HTTP environment (not HTTPS) OR
- Force mode with `?mode=basic` query parameter

### Starting the Application

```bash
# Start backend API
cd /Users/edward/PycharmProjects/Chaptr
python api/main.py

# Access frontend
# Mode 1: https://localhost:8000/static/index.html
# Mode 3: http://localhost:8000/static/index.html (HTTP, not HTTPS)
```

### Checking Current Mode

**In Browser Console:**
```javascript
// Check current mode
console.log('Current Mode:', window.storage?.mode);

// Check capabilities
console.log('Capabilities:', {
    offline: window.storage?.mode === 'full',
    sync: window.storage?.mode !== 'basic',
    storage: window.storage?.mode === 'full' ? 'IndexedDB' : 'Memory'
});
```

**In Settings Screen:**
- Navigate to Settings (⚙ icon)
- Check "Runtime Info" section:
  - **Mode**: Should show "Full (Offline-capable)", "Sync-Only (Online required)", or "Basic (Limited)"
  - **Capabilities**: Checkmarks for offline sync and conflict detection
  - **Storage**: IndexedDB or Memory

---

## Test Suite

### Task 106 & 220: Mode 1 Full - Offline Functionality

**Objective:** Verify app works completely offline with queue and sync on reconnect.

#### Test 1.1: Initial Setup (Online)

**Steps:**
1. Open app in HTTPS environment: `https://localhost:8000/static/index.html`
2. Open browser console (F12)
3. Verify service worker registration:
   ```
   [CHAPTR] Service Worker registered: https://localhost:8000/static/
   ```
4. Navigate to Settings screen
5. Verify **Runtime Info**:
   - Mode: "Full (Offline-capable)"
   - Capabilities: ✓ Offline sync, ✓ Conflict detection
   - Storage: "IndexedDB (Dexie 3.2.4)"
6. Create 2 test accounts:
   - Name: "Test Account 1", Currency: GBP, Balance: 1000
   - Name: "Test Account 2", Currency: USD, Balance: 500
7. Verify sync queue count shows **0**

**Expected Result:** ✅
- Mode detected as "Full"
- Service worker registered successfully
- Accounts created and visible
- Sync queue empty (0)

---

#### Test 1.2: Go Offline (Airplane Mode)

**Steps:**
1. **Chrome:** DevTools → Network tab → Throttling dropdown → "Offline"
2. **Firefox:** DevTools → Network tab → Throttling → "Offline"
3. **Alternative:** Turn on actual airplane mode
4. Verify offline indicator appears in UI (connection status badge)
5. Reload the page (Ctrl+R or Cmd+R)

**Expected Result:** ✅
- App loads from service worker cache
- All previously created accounts still visible
- Offline indicator shows "Offline" or similar status
- No errors in console

---

#### Test 1.3: Create Changes Offline (Task 107)

**Steps:**
1. **Still offline** - Create new account:
   - Name: "Offline Account", Currency: EUR, Balance: 750
2. **Still offline** - Update existing account:
   - Edit "Test Account 1" → Change balance to 1200
3. **Still offline** - Delete account:
   - Delete "Test Account 2"
4. Check sync queue count in UI (should increment)
5. Open browser console and verify queued changes:
   ```javascript
   db.sync_queue.toArray().then(q => console.table(q));
   ```

**Expected Result:** ✅
- All changes succeed immediately (optimistic update)
- UI updates instantly
- Sync queue count shows **3** (create + update + delete)
- Console shows 3 items in sync_queue table
- No network errors (changes queued locally)

---

#### Test 1.4: Verify Queuing Details

**Steps:**
1. In console, inspect queued changes:
   ```javascript
   db.sync_queue.toArray().then(changes => {
       changes.forEach(c => {
           console.log(`Action: ${c.action}, Entity: ${c.entity_type}, ID: ${c.entity_id}`);
       });
   });
   ```

**Expected Result:** ✅
- 3 changes in queue:
  1. `action: "create", entity_type: "account"` (Offline Account)
  2. `action: "update", entity_type: "account"` (Test Account 1)
  3. `action: "delete", entity_type: "account"` (Test Account 2)
- Each change has `entity_id`, `data`, `base_updated_at`

---

#### Test 1.5: Restore Connection and Auto-Sync (Task 108)

**Steps:**
1. Re-enable network connection:
   - **Chrome/Firefox:** DevTools → Network → "Online" or "No throttling"
   - **Airplane mode:** Turn off airplane mode
2. Wait 2-3 seconds for auto-sync to trigger
3. Check browser console for sync logs:
   ```
   [CHAPTR] Network restored - auto-syncing...
   [CHAPTR] Starting manual sync...
   [CHAPTR] Syncing 3 pending changes...
   [CHAPTR] Sync complete: 3 applied, 0 conflicts
   ```
4. Verify sync queue count returns to **0**
5. Verify all changes persisted:
   - "Offline Account" exists
   - "Test Account 1" balance is 1200
   - "Test Account 2" is deleted

**Expected Result:** ✅
- Auto-sync triggers automatically on reconnect
- Sync completes successfully (3 applied, 0 conflicts)
- Sync queue count returns to 0
- All offline changes persisted to server
- Toast notification: "Synced 3 changes"

---

#### Test 1.6: Manual Sync Button

**Steps:**
1. **While online**, create another account:
   - Name: "Manual Sync Test", Currency: GBP, Balance: 300
2. Verify sync queue count shows **1**
3. Click the **Sync** button in UI (manual sync)
4. Verify sync queue count returns to **0**
5. Check console for sync logs

**Expected Result:** ✅
- Manual sync button triggers sync
- Sync completes successfully
- Sync queue cleared
- Toast notification confirms sync

---

#### Test 1.7: Offline/Online Indicator (Task 109)

**Steps:**
1. **Online:** Verify connection status badge shows "Online" or green indicator
2. **Go offline:** Change to offline mode
3. Verify connection status badge shows "Offline" or red indicator
4. **Go online:** Restore connection
5. Verify connection status badge shows "Online" again

**Expected Result:** ✅
- Indicator accurately reflects network status
- Visual change on offline → online transition
- No lag in indicator update

---

### Task 221: Mode 2 Sync-Only - Private Browsing

**Objective:** Verify Mode 2 works in private browsing (no IndexedDB, immediate sync required).

#### Test 2.1: Open in Private Browsing

**Steps:**
1. Open **private/incognito window**:
   - Chrome: Ctrl+Shift+N (Windows) or Cmd+Shift+N (Mac)
   - Firefox: Ctrl+Shift+P (Windows) or Cmd+Shift+P (Mac)
2. Navigate to: `https://localhost:8000/static/index.html`
3. Open browser console
4. Check mode detection:
   ```javascript
   console.log('Mode:', window.storage?.mode);
   ```
5. Navigate to Settings → Runtime Info

**Expected Result:** ✅
- Mode detected as "Sync-Only (Online required)"
- Capabilities: ✗ Offline sync, ✓ Conflict detection
- Storage: "Memory (cleared on refresh)"
- Console shows: `[CHAPTR] Dexie unavailable, using Mode 2 (Sync-Only)`

---

#### Test 2.2: Create Account (Immediate Sync)

**Steps:**
1. **While online**, create account:
   - Name: "Sync Only Account", Currency: GBP, Balance: 500
2. Check browser console for immediate sync:
   ```
   [CHAPTR] Mode 2 - Creating account with immediate sync
   [CHAPTR] POST /api/accounts
   ```
3. Verify account appears in UI
4. Check sync queue count (should be **0** - no queue in Mode 2)

**Expected Result:** ✅
- Account created immediately via API call
- No queuing (sync queue count always 0)
- Account visible in UI
- No Dexie storage used

---

#### Test 2.3: Update and Delete (Immediate Sync)

**Steps:**
1. **While online**, update the account:
   - Change balance to 600
2. Check console for immediate PATCH request
3. **While online**, delete the account
4. Check console for immediate DELETE request

**Expected Result:** ✅
- All operations trigger immediate API calls
- No queuing behavior
- Changes reflected immediately in UI

---

#### Test 2.4: Offline Behavior (Should Fail)

**Steps:**
1. **Go offline** (DevTools → Network → Offline)
2. Try to create account:
   - Name: "Offline Test", Currency: USD, Balance: 100
3. Check for error message

**Expected Result:** ✅
- Operation **fails** with error
- Toast notification: "Network error - cannot create account offline"
- No optimistic update (account not visible in UI)
- Mode 2 requires network connection for all operations

---

#### Test 2.5: Refresh Clears Data

**Steps:**
1. **Go back online**
2. Create 2 accounts
3. Verify accounts visible
4. **Refresh page** (Ctrl+R or Cmd+R)
5. Check if accounts still visible

**Expected Result:** ✅
- After refresh, accounts are **re-fetched from server**
- Data not stored locally (memory cleared on refresh)
- Accounts re-appear after fetch completes

---

### Task 222: Mode 3 Basic - HTTP Environment

**Objective:** Verify Mode 3 works in HTTP (no service worker, no sync protocol, direct REST).

#### Test 3.1: Open in HTTP Environment

**Steps:**
1. Access app via **HTTP** (not HTTPS):
   - `http://localhost:8000/static/index.html`
2. Open browser console
3. Check mode detection:
   ```javascript
   console.log('Mode:', window.storage?.mode);
   ```
4. Navigate to Settings → Runtime Info
5. Check for **warning banner** at top of page

**Expected Result:** ✅
- Mode detected as "Basic (Limited)"
- Capabilities: ✗ Offline sync, ✗ Conflict detection
- Storage: "Memory (cleared on refresh)"
- **Warning banner visible**: "⚠ Limited mode - offline sync unavailable. Use HTTPS for full functionality."
- Console shows: `[CHAPTR] Service Worker not supported - using Mode 3 (Basic)`

---

#### Test 3.2: Create Account (Direct REST)

**Steps:**
1. **While online**, create account:
   - Name: "Basic Account", Currency: EUR, Balance: 250
2. Check browser console for direct API call:
   ```
   [CHAPTR] Mode 3 - Creating account via direct REST
   [CHAPTR] POST /api/accounts
   ```
3. Verify account appears in UI
4. Check sync queue count (should be **N/A** or hidden in Mode 3)

**Expected Result:** ✅
- Account created via direct REST call
- No queuing, no sync protocol
- Account visible immediately
- No service worker, no Dexie

---

#### Test 3.3: Update and Delete (Direct REST)

**Steps:**
1. Update the account → Change balance to 300
2. Check console for `PATCH /api/accounts/:id`
3. Delete the account
4. Check console for `DELETE /api/accounts/:id`

**Expected Result:** ✅
- All operations use direct REST endpoints
- No sync protocol involved
- Changes reflected immediately

---

#### Test 3.4: Offline Behavior (Should Fail)

**Steps:**
1. **Go offline**
2. Try to create account
3. Check for error

**Expected Result:** ✅
- Operation **fails** immediately
- Error toast: "Network error - operation failed"
- No offline capability
- No queuing

---

#### Test 3.5: Conflict Handling (Last Write Wins)

**Steps:**
1. **Go back online**
2. Open app in **two different browser tabs** (both HTTP)
3. In **Tab 1**: Create account "Conflict Test", balance 100
4. In **Tab 2**: Refresh page, then edit "Conflict Test" → balance 200
5. In **Tab 1**: Edit "Conflict Test" → balance 300
6. Refresh both tabs

**Expected Result:** ✅
- **Last write wins** (no conflict detection)
- Final balance is whichever tab saved last (likely 300)
- No conflict notification
- Mode 3 does not track conflicts

---

## Edge Cases and Advanced Tests

### Edge Case 1: Queue Limit Warning (400 changes)

**Mode:** Mode 1 Full
**Objective:** Verify warning toast at 400 pending changes.

**Steps:**
1. Go offline
2. Create a script to queue 400 changes:
   ```javascript
   async function create400Accounts() {
       for (let i = 1; i <= 400; i++) {
           await db.queueChange('account', `test-${i}`, 'create', {
               name: `Test ${i}`,
               currency: 'GBP',
               current_balance: 100
           });
       }
       console.log('Queued 400 changes');
   }
   create400Accounts();
   ```
3. Check for warning toast
4. Verify sync queue count shows **400**

**Expected Result:** ✅
- Warning toast appears: "⚠ 400+ pending changes. Sync recommended."
- Sync queue count shows 400
- Operations still allowed

---

### Edge Case 2: Queue Limit Block (500 changes)

**Mode:** Mode 1 Full
**Objective:** Verify hard block at 500 pending changes.

**Steps:**
1. Continue from Edge Case 1 (400 changes queued)
2. Go offline
3. Try to create 100 more accounts (should hit 500 limit)
4. Check for block modal

**Expected Result:** ✅
- At 500th change, **modal appears**: "Queue limit reached. Please sync before making more changes."
- Modal shows **Sync Now** button
- Further operations blocked until sync
- User must sync or go online to continue

---

### Edge Case 3: Full Sync Requirement (Stale Client)

**Mode:** Mode 1 Full
**Objective:** Test server-triggered full sync for stale clients.

**Steps:**
1. This requires **backend modification** to simulate stale client
2. Modify `/api/sync` endpoint to return:
   ```json
   {
       "applied": [],
       "conflicts": [],
       "server_changes": [],
       "full_sync_required": true,
       "sync_timestamp": "2024-12-23T20:00:00Z"
   }
   ```
3. Trigger manual sync
4. Verify full sync behavior

**Expected Result:** ✅
- Toast: "Updating to latest data..."
- Dexie cleared
- All data re-downloaded from server via `GET /api/sync/full`
- Toast: "Data updated successfully"
- No data loss

---

## Test Matrix Summary

| Test Scenario | Mode 1 (Full) | Mode 2 (Sync) | Mode 3 (Basic) |
|--------------|---------------|---------------|----------------|
| **Offline Create** | ✅ Queued | ❌ Fails | ❌ Fails |
| **Offline Update** | ✅ Queued | ❌ Fails | ❌ Fails |
| **Offline Delete** | ✅ Queued | ❌ Fails | ❌ Fails |
| **Auto-sync on Reconnect** | ✅ Yes | N/A | N/A |
| **Manual Sync** | ✅ Yes | N/A | N/A |
| **Conflict Detection** | ✅ Yes | ✅ Yes | ❌ No |
| **Refresh Persistence** | ✅ Yes (Dexie) | ❌ No (memory) | ❌ No (memory) |
| **Service Worker** | ✅ Yes | ✅ Yes | ❌ No |
| **Queue Limits** | ✅ 400/500 | N/A | N/A |
| **Full Sync** | ✅ Yes | N/A | N/A |

---

## Completion Checklist

### Task 106: Airplane Mode Testing
- [ ] App loads offline from service worker cache
- [ ] Previously loaded data visible
- [ ] Offline indicator shows correct status
- [ ] No console errors

### Task 107: Offline Changes and Queuing
- [ ] Create account offline → queued
- [ ] Update account offline → queued
- [ ] Delete account offline → queued
- [ ] Sync queue count increments correctly
- [ ] Optimistic UI updates work

### Task 108: Connection Restore and Sync
- [ ] Auto-sync triggers on reconnect
- [ ] All queued changes synced successfully
- [ ] Sync queue count returns to 0
- [ ] Toast notification confirms sync

### Task 109: Offline/Online Indicators
- [ ] Indicator shows "Online" when connected
- [ ] Indicator shows "Offline" when disconnected
- [ ] Indicator updates immediately on status change

### Task 220: Mode 1 Full Testing
- [ ] Mode detected correctly in HTTPS
- [ ] Service worker registers successfully
- [ ] Offline CRUD operations work
- [ ] Queue and sync work correctly
- [ ] Mode display in Settings accurate

### Task 221: Mode 2 Sync-Only Testing
- [ ] Mode detected in private browsing
- [ ] Immediate sync on all operations
- [ ] No queuing behavior
- [ ] Offline operations fail gracefully
- [ ] Refresh re-fetches data

### Task 222: Mode 3 Basic Testing
- [ ] Mode detected in HTTP environment
- [ ] Warning banner visible
- [ ] Direct REST calls for all operations
- [ ] No conflict detection
- [ ] Last write wins on conflicts

---

## Known Issues and Limitations

### Mode 1 (Full)
- Requires HTTPS for service worker
- Browser must support IndexedDB
- Queue limited to 500 changes

### Mode 2 (Sync-Only)
- No offline capability
- Data cleared on refresh
- Requires constant network connection

### Mode 3 (Basic)
- No service worker (no asset caching)
- No conflict detection
- Last write wins on simultaneous edits
- Data cleared on refresh

---

## Troubleshooting

### Service Worker Not Registering

**Symptom:** Console error: "Service Worker registration failed"

**Solutions:**
1. Ensure using HTTPS (not HTTP)
2. Check for browser support: `'serviceWorker' in navigator`
3. Clear browser cache and reload
4. Check for existing service workers: Chrome DevTools → Application → Service Workers

---

### Mode Detection Incorrect

**Symptom:** Wrong mode detected (e.g., expecting Full but got Sync-Only)

**Solutions:**
1. Check browser environment (HTTPS vs HTTP)
2. Check IndexedDB availability: Open DevTools → Application → IndexedDB
3. Force mode with query parameter: `?mode=full` or `?mode=basic`
4. Clear IndexedDB and reload
5. Check localStorage: `localStorage.getItem('FORCE_MODE')`

---

### Sync Not Triggering

**Symptom:** Queued changes not syncing on reconnect

**Solutions:**
1. Check network connection (DevTools → Network tab)
2. Verify backend API is running: `curl http://localhost:8000/api/health`
3. Check console for sync errors
4. Try manual sync button
5. Verify sync endpoint: `POST http://localhost:8000/api/sync`

---

### Queue Limit Not Enforcing

**Symptom:** Can create more than 500 changes

**Solutions:**
1. Check `queueChange()` implementation in storage-adapter.js
2. Verify `db.sync_queue.count()` working correctly
3. Check console for queue limit logs
4. Clear sync queue and retry: `db.sync_queue.clear()`

---

## Test Completion Report Template

```markdown
# Phase 5 Testing Report

**Date:** YYYY-MM-DD
**Tester:** [Name]
**Environment:** [Browser, OS]

## Mode 1 (Full) - HTTPS
- [ ] Task 106: Airplane mode - ✅ PASS / ❌ FAIL
- [ ] Task 107: Offline queuing - ✅ PASS / ❌ FAIL
- [ ] Task 108: Sync on reconnect - ✅ PASS / ❌ FAIL
- [ ] Task 109: Indicators - ✅ PASS / ❌ FAIL
- [ ] Task 220: Full mode testing - ✅ PASS / ❌ FAIL

## Mode 2 (Sync-Only) - Private Browsing
- [ ] Task 221: Sync-Only testing - ✅ PASS / ❌ FAIL

## Mode 3 (Basic) - HTTP
- [ ] Task 222: Basic mode testing - ✅ PASS / ❌ FAIL

## Edge Cases
- [ ] Queue warning (400) - ✅ PASS / ❌ FAIL
- [ ] Queue block (500) - ✅ PASS / ❌ FAIL
- [ ] Full sync requirement - ✅ PASS / ❌ FAIL

## Issues Found
[List any bugs or unexpected behavior]

## Notes
[Additional observations]

**Overall Status:** ✅ ALL PASS / ⚠️ SOME FAILURES / ❌ BLOCKED
```

---

## Next Steps After Testing

Once all tests pass:

1. **Mark tasks complete:**
   ```bash
   task 106 done
   task 107 done
   task 108 done
   task 109 done
   task 220 done
   task 221 done
   task 222 done
   ```

2. **Update CHANGELOG.md** with Phase 5 tasks

3. **Create feature branch and PR:**
   ```bash
   git checkout dev
   git checkout -b feature/phase5-offline-capability
   git add -A
   git commit -m "CPTR-[uuids]: Complete Phase 5 - Offline capability with three-tier progressive enhancement"
   git push -u origin feature/phase5-offline-capability
   gh pr create --base dev --title "Phase 5: Offline Capability" --body "Complete implementation of three-tier offline system"
   ```

4. **Proceed to Phase 6: Reconciliation** (33 tasks)

---

**Testing Guide Complete**

---
---

# PART IV: Queue-as-State Architecture Testing

**Refactor Branch**: `refactor/queue-as-state`

---

## Overview

This document outlines comprehensive testing scenarios for the queue-as-state refactor. The refactor eliminates fragmented patterns (shadow events, phantom events, mode checks) in favor of a unified queue-as-state architecture.

**Core Principle**: `IndexedDB State = Last Server State + Applied Sync Queue`

---

## Architecture Changes Summary

### What Changed:

1. **Queue Schema Enhanced** - db.js schema v3 with metadata tracking
2. **Pure Helper Functions** - event-helpers.js, queue-helpers.js created
3. **Account Creation** - Uses queue-first pattern with derived events
4. **Recurring Rules** - Generate real instances (no more phantoms)
5. **Adjustment Events** - Frontend sets flag, server creates event
6. **Mode Checks Removed** - Business logic works uniformly across modes
7. **Storage Adapter Complete** - Recurring rule methods added

### What to Test:

- ✅ Derived events created with proper metadata
- ✅ Server corrections applied silently
- ✅ Recurring instances are real events
- ✅ Projection simplified (no phantom generation)
- ✅ Reconciliation triggered by flag
- ✅ Queue metadata preserved through sync

---

## Test Scenario 1: Account Creation Offline

**Objective**: Verify account creation generates opening balance event with proper queue metadata.

### Prerequisites:
- CHAPTR running in full offline mode
- Clean IndexedDB (or known state)

### Steps:

1. **Create Account**:
   - Navigate to Accounts screen
   - Click "Add Account"
   - Name: "Test Account"
   - Currency: GBP
   - Current Balance: £1000
   - Is Default: Yes
   - Click "Create"

2. **Verify Local State**:
   - Open browser DevTools → Application → IndexedDB → CHAPTR
   - Check `accounts` table:
     - ✅ Account exists with id, £1000 balance
     - ✅ Has `_queued_op: 'create'` flag
   - Check `events` table:
     - ✅ Opening balance event exists
     - ✅ Description: "opening balance" (lowercase)
     - ✅ Amount: 1000
     - ✅ `is_opening_balance: true`
     - ✅ `is_baseline: true`
     - ✅ Has `_queued_op: 'create'` flag
   - Check `sync_queue` table:
     - ✅ 2 entries (account + event)
     - ✅ Event entry has `_derived_from: 'account_creation'`
     - ✅ Event entry has `dependencies: [account_id]`

3. **Sync to Server**:
   - Click sync button
   - Wait for sync to complete

4. **Verify Server Acceptance**:
   - Check `sync_queue` table:
     - ✅ Empty (both changes applied)
   - Check `accounts` table:
     - ✅ Account still exists
     - ✅ NO `_queued_op` flag
     - ✅ Has `updated_at` from server
   - Check `events` table:
     - ✅ Opening balance event still exists
     - ✅ NO `_queued_op` flag
     - ✅ May have server-corrected fields (server version wins)

### Expected Outcome:
- ✅ Single opening balance event (no duplicates)
- ✅ Projection shows £1000 balance
- ✅ No conflicts generated

---

## Test Scenario 2: Recurring Rule Creation

**Objective**: Verify recurring rules generate real instances (no phantoms).

### Prerequisites:
- CHAPTR running in full offline mode
- At least one account exists

### Steps:

1. **Create Recurring Rule**:
   - Navigate to Events/Projection screen
   - Click "Add Event"
   - Check "Recurring" checkbox
   - Description: "Weekly Coffee"
   - Amount: -£15
   - Account: (select existing)
   - Frequency: Weekly
   - Day: Monday (1)
   - Start Date: (today's date)
   - End Date: (leave empty for ongoing)
   - Click "Create"

2. **Verify Instances Generated**:
   - Open DevTools → IndexedDB → events table
   - ✅ Multiple event entries exist (±30 days from today)
   - ✅ Each has `recurring_rule_id` = rule UUID
   - ✅ Each has `_queued_op: 'create'` flag
   - Check `sync_queue` table:
     - ✅ 1 entry for rule + N entries for instances
     - ✅ Each instance has `_derived_from: 'recurring_rule_creation'`
     - ✅ Each instance has `dependencies: [rule_id]`

3. **Verify Projection**:
   - View projection
   - ✅ Instances appear on correct dates
   - ✅ No duplicate events
   - ✅ NO phantom generation logic running (check console logs)

4. **Edit Instance**:
   - Click on one recurring instance
   - Change amount to -£20
   - Save
   - ✅ Instance updated (it's a real event, not phantom)
   - ✅ Future instances unaffected

5. **Sync to Server**:
   - Click sync
   - ✅ All instances synced
   - ✅ Server may override with authoritative versions

### Expected Outcome:
- ✅ Real instances in Dexie (not ephemeral phantoms)
- ✅ Instances can be edited directly
- ✅ Projection is fast (no generation loop)

---

## Test Scenario 3: Recurring Rule Update

**Objective**: Verify rule updates regenerate future instances.

### Prerequisites:
- Recurring rule exists with instances
- Some instances are in the future

### Steps:

1. **Update Recurring Rule**:
   - Navigate to recurring rule
   - Click edit
   - Change amount from -£15 to -£20
   - Save

2. **Verify Instance Regeneration**:
   - Check `events` table:
     - ✅ Future unedited instances deleted
     - ✅ New instances created with -£20
   - Check `sync_queue`:
     - ✅ Delete entries for old instances
     - ✅ Create entries for new instances

3. **Verify Edited Instances Preserved**:
   - Edited instances (created_at ≠ updated_at) should remain unchanged

### Expected Outcome:
- ✅ Future instances reflect new amount
- ✅ Edited instances preserved
- ✅ Past instances unchanged

---

## Test Scenario 4: Recurring Rule Deletion

**Objective**: Verify rule deletion preserves past instances.

### Prerequisites:
- Recurring rule with past and future instances

### Steps:

1. **Delete Recurring Rule**:
   - Click delete on recurring rule
   - Confirm deletion

2. **Verify Instance Handling**:
   - Check `events` table:
     - ✅ Past instances preserved
     - ✅ Future unedited instances deleted
     - ✅ Manually edited instances preserved
   - Check `recurring_rules` table:
     - ✅ Rule deleted

### Expected Outcome:
- ✅ Past events remain (historical record)
- ✅ Future auto-generated events removed
- ✅ Manually edited future events preserved

---

## Test Scenario 5: Balance Reconciliation

**Objective**: Verify balance updates set flag, server creates adjustment.

### Prerequisites:
- Account with known balance
- Projection visible

### Steps:

1. **Trigger Drift**:
   - Note current projected balance (e.g., £500)
   - Click "Update Balance" on account
   - Enter actual balance: £550 (£50 drift)
   - Save

2. **Verify Local State**:
   - Check `accounts` table:
     - ✅ `current_balance: 550`
     - ✅ `pending_reconciliation: true`
     - ✅ `balance_updated_at` updated
   - Check `events` table:
     - ✅ NO frontend adjustment event created
   - Check projection:
     - ✅ Virtual drift row displayed (£50 difference)

3. **Sync to Server**:
   - Click sync
   - Server triggers reconciliation

4. **Verify Server Adjustment**:
   - Check `events` table after sync:
     - ✅ NEW adjustment event from server
     - ✅ Description: "balance adjustment" (lowercase)
     - ✅ Amount: 50 (drift amount)
     - ✅ `is_auto_adjustment: true`
     - ✅ `is_baseline: true`
   - Check `accounts` table:
     - ✅ `pending_reconciliation: false` (cleared by server)

### Expected Outcome:
- ✅ Frontend sets flag only
- ✅ Server creates authoritative adjustment
- ✅ Single adjustment event (no duplicates)
- ✅ Projection now accurate

---

## Test Scenario 6: Derived Event Conflict Resolution

**Objective**: Verify server corrections silently override client-generated derived events.

### Prerequisites:
- Offline mode with queued changes

### Steps:

1. **Create Conflict Scenario**:
   - Create account offline (£1000 balance)
   - Opening balance event queued
   - Simulate server correction (server decides balance was actually £950)

2. **Sync and Verify**:
   - Click sync
   - Check `conflicts` table:
     - ✅ Conflict entry with `conflict_type: 'derived_event_overridden'`
     - ✅ `resolved_at` is set (auto-resolved)
   - Check `events` table:
     - ✅ Server's opening balance (£950) exists
     - ✅ Client's opening balance (£1000) deleted
   - ✅ NO user notification (silent resolution)

### Expected Outcome:
- ✅ Server version wins automatically
- ✅ No user intervention required
- ✅ Conflict logged but resolved

---

## Test Scenario 7: Queue Metadata Preservation

**Objective**: Verify queue metadata (_derived_from, dependencies) preserved through sync.

### Prerequisites:
- Offline mode

### Steps:

1. **Create Queued Changes**:
   - Create account → opening balance queued
   - Create recurring rule → instances queued

2. **Verify Queue Metadata**:
   - Check `sync_queue` entries:
     - Opening balance: `_derived_from: 'account_creation'`, `dependencies: [account_id]`
     - Instances: `_derived_from: 'recurring_rule_creation'`, `dependencies: [rule_id]`

3. **Sync and Verify**:
   - Sync completes successfully
   - ✅ Metadata used by server for intelligent processing

### Expected Outcome:
- ✅ Queue carries rich metadata
- ✅ Server can make smart decisions

---

## Test Scenario 8: Edge Cases

### 8.1: £0 Balance Account

1. Create account with £0 balance
2. ✅ NO opening balance event created
3. ✅ Account created successfully

### 8.2: Queue Limit (500 changes)

1. Queue 500+ changes (create many events)
2. ✅ Hard block modal shown at 500
3. ✅ User forced to sync before continuing

### 8.3: Sync Conflicts (Non-Derived)

1. Edit same event offline and online
2. ✅ Conflict detected
3. ✅ Conflict UI shown (user resolves manually)

### 8.4: Network Interruption During Sync

1. Start sync
2. Disconnect network mid-sync
3. ✅ Partial changes handled gracefully
4. ✅ Queue items remain for retry

---

## Test Scenario 9: Mode Independence

**Objective**: Verify business logic works in all 3 modes.

### Test in Each Mode:

**Mode 1 (Full Offline)**:
- ✅ Account creation → opening balance queued
- ✅ Recurring rule → instances generated
- ✅ Balance update → pending_reconciliation set

**Mode 2 (Sync-Only)**:
- ✅ Account creation → direct API + Dexie update
- ✅ Recurring rule → direct API + instances in Dexie
- ✅ Balance update → pending_reconciliation set + API call

**Mode 3 (Basic)**:
- ✅ Account creation → direct API (no Dexie)
- ✅ Recurring rule → direct API
- ✅ Balance update → direct API

### Expected Outcome:
- ✅ NO mode checks in app.js business logic
- ✅ Storage adapter handles mode routing internally

---

## Test Scenario 10: Projection Performance

**Objective**: Verify projection is faster without phantom generation.

### Steps:

1. **Create Recurring Rules**:
   - Create 5 weekly recurring rules
   - Create 3 monthly recurring rules

2. **Measure Projection Time**:
   - Open DevTools → Performance tab
   - Record projection calculation
   - ✅ No `generateRecurringEventsClientSide` calls in profile
   - ✅ Simple Dexie query for events

3. **Compare Before/After**:
   - Old: Regenerates phantoms on every projection
   - New: Single Dexie query

### Expected Outcome:
- ✅ Projection 2-5x faster
- ✅ Fewer Dexie queries
- ✅ Simpler call stack

---

## Regression Testing

### Critical Flows to Verify:

1. **Account Management**:
   - ✅ Create, update, delete accounts
   - ✅ Opening balance created/deleted with account
   - ✅ Default account toggle works

2. **Event Management**:
   - ✅ Create, update, delete one-time events
   - ✅ Recurring instances editable as normal events
   - ✅ Story assignment works

3. **Projection Calculation**:
   - ✅ Baseline view correct
   - ✅ Story views correct
   - ✅ All view correct
   - ✅ Gap indicators still work

4. **Sync Protocol**:
   - ✅ Full sync works
   - ✅ Incremental sync works
   - ✅ Conflict detection works
   - ✅ Stale client handled (full sync required)

---

## Success Criteria

### Functional:
- ✅ All 10 test scenarios pass
- ✅ No duplicate events
- ✅ No phantom generation
- ✅ Reconciliation works correctly
- ✅ Sync completes without errors

### Code Quality:
- ✅ 0 mode checks in business logic
- ✅ 1 special flag (_queued_op) instead of 4
- ✅ ~400 lines removed
- ✅ No business logic duplication

### Performance:
- ✅ Projection faster (no phantom loop)
- ✅ Fewer Dexie queries
- ✅ Simpler sync handling

---

## Known Issues / Limitations

*None identified as of 2025-12-29*

---

## Next Steps After Testing

1. Merge `refactor/queue-as-state` branch to `dev`
2. Deploy to staging environment
3. Monitor for edge cases in production
4. Update user documentation (if applicable)

---

## Appendix: Quick Checklist

Use this checklist for rapid manual testing:

- [ ] Create account offline → opening balance exists
- [ ] Sync account → single event, no duplicates
- [ ] Create weekly recurring rule → instances exist
- [ ] View projection → instances visible (no phantom generation)
- [ ] Edit recurring instance → edits work
- [ ] Update balance → pending_reconciliation flag set
- [ ] Sync balance update → server adjustment created
- [ ] Delete recurring rule → past instances preserved
- [ ] Check queue metadata → _derived_from fields present
- [ ] Test all 3 modes → consistent behavior

---

**End of Testing Guide**
