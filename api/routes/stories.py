"""
Story management endpoints.

Provides CRUD operations for financial stories (trips, projects, life events).
"""

from fastapi import APIRouter, Depends
from uuid import UUID

from api.config import MongoDB
from api.models import Story, StoryCreate, StoryUpdate
from api.repositories.stories import StoryRepository
from api.utils.auth import get_current_user

router = APIRouter()


def get_story_repo() -> StoryRepository:
    """
    Dependency injection for StoryRepository.

    :return: Initialized StoryRepository
    :rtype: StoryRepository
    """
    db = MongoDB.get_database()
    return StoryRepository(db)


@router.get("/stories", response_model=list[Story])
async def list_stories(
    current_user: dict = Depends(get_current_user),
    repo: StoryRepository = Depends(get_story_repo)
):
    """
    List all stories.

    Returns all stories sorted by start_date descending (most recent first).

    :param repo: Injected StoryRepository
    :type repo: StoryRepository
    :return: List of stories
    :rtype: list[Story]

    :Example:

    ```bash
    curl http://localhost:8000/api/stories
    ```
    """
    return await repo.list(sort=[("start_date", -1)])


@router.get("/stories/{story_id}", response_model=Story)
async def get_story(
    story_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: StoryRepository = Depends(get_story_repo)
):
    """
    Get single story by ID.

    :param story_id: Story UUID
    :type story_id: UUID
    :param repo: Injected StoryRepository
    :type repo: StoryRepository
    :return: Story details
    :rtype: Story
    :raises ResourceNotFoundError: If story not found (404)

    :Example:

    ```bash
    curl http://localhost:8000/api/stories/{story-id}
    ```
    """
    return await repo.get(story_id)


@router.post("/stories", response_model=Story, status_code=201)
async def create_story(
    data: StoryCreate,
    current_user: dict = Depends(get_current_user),
    repo: StoryRepository = Depends(get_story_repo)
):
    """
    Create new story.

    Business Rules:
    - start_date must be before end_date (if both set)
    - default_account_id must reference existing, non-archived account
    - funding_mode: 'projected' (default), 'fixed', 'projected_plus'
    - If funding_mode is 'fixed' or 'projected_plus', funding_amount required
    - goal_type: 'end_with_at_least', 'spend_up_to', 'none'
    - If goal_type is not 'none', goal_amount required

    :param data: Story creation data
    :type data: StoryCreate
    :param repo: Injected StoryRepository
    :type repo: StoryRepository
    :return: Created story
    :rtype: Story
    :raises ValidationError: If business rules violated (422)

    :Example:

    ```bash
    # Create story with projected funding (default)
    curl -X POST http://localhost:8000/api/stories \\
      -H "Content-Type: application/json" \\
      -d '{
        "name": "canada-trip",
        "start_date": "2025-06-01",
        "end_date": "2025-06-30",
        "display_currency": "CAD",
        "funding_mode": "projected"
      }'

    # Create story with fixed funding
    curl -X POST http://localhost:8000/api/stories \\
      -H "Content-Type: application/json" \\
      -d '{
        "name": "volvo",
        "start_date": "2025-03-01",
        "display_currency": "GBP",
        "funding_mode": "fixed",
        "funding_amount": 15000,
        "goal_type": "spend_up_to",
        "goal_amount": 15000
      }'
    ```
    """
    return await repo.create(data, current_user=current_user, client_id=None)


@router.put("/stories/{story_id}", response_model=Story)
async def update_story(
    story_id: UUID,
    data: StoryUpdate,
    current_user: dict = Depends(get_current_user),
    repo: StoryRepository = Depends(get_story_repo)
):
    """
    Update existing story.

    Supports partial updates - only provided fields are updated.
    Cross-field validation (funding_mode + funding_amount, goal_type + goal_amount)
    is performed by merging update with existing data.

    Business Rules:
    - Changing default_account_id only affects future events, not existing ones
    - Cross-field relationships validated after merge

    :param story_id: Story UUID
    :type story_id: UUID
    :param data: Update data (partial)
    :type data: StoryUpdate
    :param repo: Injected StoryRepository
    :type repo: StoryRepository
    :return: Updated story
    :rtype: Story
    :raises ResourceNotFoundError: If story not found (404)
    :raises ValidationError: If cross-field validation fails (422)

    :Example:

    ```bash
    # Update funding mode
    curl -X PUT http://localhost:8000/api/stories/{story-id} \\
      -H "Content-Type: application/json" \\
      -d '{
        "funding_mode": "projected_plus",
        "funding_amount": 5000
      }'

    # Update story dates
    curl -X PUT http://localhost:8000/api/stories/{story-id} \\
      -H "Content-Type: application/json" \\
      -d '{
        "start_date": "2025-07-01",
        "end_date": "2025-07-31"
      }'
    ```
    """
    return await repo.update(story_id, data, current_user=current_user, client_id=None)


@router.delete("/stories/{story_id}", status_code=204)
async def delete_story(
    story_id: UUID,
    current_user: dict = Depends(get_current_user),
    repo: StoryRepository = Depends(get_story_repo)
):
    """
    Delete story and cascade to events.

    **DESTRUCTIVE ACTION**: Deletes the story AND all events belonging to it.
    This is a hard delete (no archive). Deletion is permanent.

    Business Rules:
    - Deletes ALL events with story_id = this story
    - This is irreversible

    :param story_id: Story UUID
    :type story_id: UUID
    :param repo: Injected StoryRepository
    :type repo: StoryRepository
    :return: No content (204)
    :raises ResourceNotFoundError: If story not found (404)

    :Example:

    ```bash
    curl -X DELETE http://localhost:8000/api/stories/{story-id}
    ```
    """
    await repo.delete(story_id, current_user=current_user, client_id=None)
    return None
