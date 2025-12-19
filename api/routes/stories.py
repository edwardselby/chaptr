"""
Story management endpoints.

Provides CRUD operations for financial stories (trips, projects, life events).

TODO Phase 1.4: Implement full CRUD logic
See spec: Core Concepts > Stories
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/stories")
async def list_stories():
    """
    List all stories.

    TODO Phase 1.4:
    - Query MongoDB stories collection
    - Sort by start_date DESC
    - Return array of Story models

    Returns:
        list: Array of story objects
    """
    return []


@router.get("/stories/{id}")
async def get_story(id: str):
    """
    Get single story by ID.

    TODO Phase 1.4:
    - Query MongoDB by id
    - Return 404 if not found
    - Return Story model

    Args:
        id: Story UUID

    Returns:
        dict: Story object
    """
    raise HTTPException(status_code=404, detail="Story not found")


@router.post("/stories")
async def create_story():
    """
    Create new story.

    TODO Phase 1.4:
    - Validate StoryCreate model
    - Validate funding_mode enum
    - Validate goal_type enum
    - Validate start_date <= end_date (if end_date set)
    - Insert into MongoDB
    - Create hypothetical funding event if funding_mode != 'projected'
    - Return created Story

    Business Rules:
    - start_date must be before or equal to end_date (if both set)
    - default_account_id must reference existing, non-archived account
    - funding_mode: 'projected' (default), 'fixed', 'projected_plus'
    - goal_type: 'end_with_at_least', 'spend_up_to', 'none'

    Returns:
        dict: Created story object
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put("/stories/{id}")
async def update_story(id: str):
    """
    Update existing story.

    TODO Phase 1.4:
    - Validate StoryUpdate model
    - Check if story exists
    - Update in MongoDB
    - Handle funding_mode changes
    - Return updated Story

    Args:
        id: Story UUID

    Returns:
        dict: Updated story object
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/stories/{id}")
async def delete_story(id: str):
    """
    Delete story and cascade to events.

    TODO Phase 1.4:
    - Delete all events with story_id = this story
    - Delete story from MongoDB
    - Return success status

    Business Rules:
    - Deleting a story deletes ALL events belonging to that story
    - This is a destructive action (hard delete)

    Args:
        id: Story UUID

    Returns:
        dict: Success message
    """
    raise HTTPException(status_code=501, detail="Not implemented")
