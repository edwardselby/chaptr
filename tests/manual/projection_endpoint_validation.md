# Projection Endpoint Manual Validation
## Task 4 - Test projection endpoint with curl for all view types

**Date**: 2025-12-22
**Task**: 4ab09b87-69b4-4450-b62f-bd464625bd77
**Endpoint**: `GET /api/projection`

---

## Test Plan

### 1. Test view="all" (baseline + all stories)
### 2. Test view="baseline" (baseline events only)
### 3. Test view with specific story_id
### 4. Test date range parameters
### 5. Test error handling (invalid dates, missing story)
### 6. Test warnings parameter

---

## Test Execution

### Test 1: View="all" - All Events
**Request**:
```bash
curl -s "http://localhost:8000/api/projection?view=all&start_date=2024-12-18&end_date=2025-01-18" | jq
```

**Expected**:
- Baseline events visible
- All story events visible (canada-trip, volvo, home)
- No hypothetical events
- Running balance calculated
- Warnings included

**Result**:
