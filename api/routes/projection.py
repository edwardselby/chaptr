"""
Projection endpoints.

Provides balance projection queries across accounts, stories, and date ranges.
Connects to core projection engine for all calculation logic.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from uuid import UUID
from typing import Annotated, Optional
from datetime import date
import re

from api.config import MongoDB
from api.models import ProjectionResponse
from api.utils.auth import get_current_user
from core.projection import (
    calculate_global_projection,
    detect_global_negative_warnings,
    detect_account_negative_warnings,
    detect_story_goal_warnings
)

router = APIRouter()


@router.get("/projection", response_model=dict)
async def get_projection(
    view: Annotated[
        str,
        Query(
            description="Projection view: 'all', 'all_what_if', or story UUID",
            examples=["all", "all_what_if", "550e8400-e29b-41d4-a716-446655440000"]
        )
    ],
    start: Annotated[
        date,
        Query(
            description="Start date for projection (YYYY-MM-DD)",
            examples=["2024-12-18"]
        )
    ],
    end: Annotated[
        date,
        Query(
            description="End date for projection (YYYY-MM-DD)",
            examples=["2025-01-18"]
        )
    ],
    include_warnings: Annotated[
        bool,
        Query(
            description="Include warning analysis in response",
            examples=[False]
        )
    ] = False,
    display_currency: Annotated[
        Optional[str],
        Query(
            description="Currency for display conversion (e.g., GBP, USD)",
            examples=["GBP"]
        )
    ] = None,
    current_user: dict = Depends(get_current_user),
    db = Depends(MongoDB.get_database)
):
    """
    Calculate financial projection with customizable view and date range.

    This endpoint connects to the core projection engine to calculate
    balance projections across accounts, stories, and time periods.

    View Modes:
    - "all": Active and default stories only (reality mode)
    - "all_what_if": Include what-if stories (hypothetical mode)
    - UUID: Single story projection with funding mode

    Returns daily balance projections with optional warnings and gap indicators.

    :param view: Projection view mode
    :type view: str
    :param start: Projection start date
    :type start: date
    :param end: Projection end date
    :type end: date
    :param include_warnings: Include warning detection (default: false)
    :type include_warnings: bool
    :param display_currency: Currency for display amounts (optional)
    :type display_currency: Optional[str]
    :param current_user: Authenticated user
    :type current_user: dict
    :param db: Database connection
    :return: Projection data with events and optional warnings
    :rtype: dict
    :raises HTTPException: 400 for invalid parameters, 404 for story not found

    :Example:

    ```bash
    # Basic projection (all view)
    curl "http://localhost:8000/api/projection?view=all&start=2024-12-18&end=2025-01-18"

    # With warnings
    curl "http://localhost:8000/api/projection?view=all&start=2024-12-18&end=2025-01-18&include_warnings=true"

    # Story projection
    curl "http://localhost:8000/api/projection?view=550e8400-e29b-41d4-a716-446655440000&start=2024-12-18&end=2025-01-18"

    # Currency conversion
    curl "http://localhost:8000/api/projection?view=all&start=2024-12-18&end=2025-01-18&display_currency=USD"
    ```
    """
    # Validate date range
    if end < start:
        raise HTTPException(
            status_code=400,
            detail="End date must be after or equal to start date"
        )

    # Validate view parameter
    story_id = None
    if view not in ["all", "all_what_if"]:
        try:
            story_id = UUID(view)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid view: must be 'all', 'all_what_if', or valid story UUID"
            )

    # Validate currency code format if provided
    if display_currency:
        if not re.match(r"^[A-Z]{3}$", display_currency):
            raise HTTPException(
                status_code=400,
                detail="Currency must be 3 uppercase letters (e.g., GBP, USD)"
            )

    # Call core projection function
    try:
        projection_result = await calculate_global_projection(
            view=view,
            story_id=str(story_id) if story_id else None,
            start_date=start,
            end_date=end,
            display_currency=display_currency,
            db=db
        )
    except Exception as e:
        # Handle projection calculation errors
        raise HTTPException(
            status_code=500,
            detail=f"Projection calculation failed: {str(e)}"
        )

    # Add warnings if requested
    if include_warnings:
        warnings = []

        # Detect global negative balance warnings
        warnings.extend(detect_global_negative_warnings(projection_result))

        # Add warnings to response
        projection_result["warnings"] = warnings

    return projection_result
