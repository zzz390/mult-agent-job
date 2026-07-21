"""User endpoints."""

from fastapi import APIRouter, status

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import success_response
from job_agent_os.schemas.user import UserResponse, UserUpdateRequest

router = APIRouter()


@router.get("/me")
async def get_current_user_info(user: CurrentUser) -> dict:
    """Get current user information."""
    return success_response(data=UserResponse.model_validate(user).model_dump())


@router.patch("/me")
async def update_user_info(
    request: UserUpdateRequest,
    user: CurrentUser,
    db: DBSession,
) -> dict:
    """Update current user information."""
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    await db.flush()
    await db.refresh(user)
    return success_response(data=UserResponse.model_validate(user).model_dump())
from fastapi import APIRouter

router = APIRouter()

