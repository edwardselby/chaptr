# Sync Manual Testing Guide

**Purpose**: Manual validation of sync protocol with curl commands (Tasks 26-27)

This guide provides step-by-step curl commands to manually test sync functionality with simulated multi-client scenarios and conflict detection.

---

## Prerequisites

### 1. Start API Server

```bash
cd /Users/edward/PycharmProjects/Chaptr2
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
