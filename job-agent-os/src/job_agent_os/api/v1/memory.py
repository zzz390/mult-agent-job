"""Memory endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from job_agent_os.api.deps import CurrentUser, DBSession
from job_agent_os.api.response import paginated_response, success_response
from job_agent_os.core.error_codes import ErrorCode
from job_agent_os.core.exceptions import NotFoundException
from job_agent_os.models.memory import Memory
from job_agent_os.schemas.memory import (
    MemoryCreate,
    MemoryResponse,
    MemorySearchRequest,
)

router = APIRouter()


@router.get("")
async def list_memories(
    db: DBSession,
    user: CurrentUser,
    category: str | None = Query(default=None),
    memory_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List memories for the current user."""
    query = select(Memory).where(
        Memory.user_id == user.id,
        Memory.is_active == True,  # noqa: E712
    )
    count_query = select(func.count(Memory.id)).where(
        Memory.user_id == user.id,
        Memory.is_active == True,  # noqa: E712
    )

    if category:
        query = query.where(Memory.category == category)
        count_query = count_query.where(Memory.category == category)
    if memory_type:
        query = query.where(Memory.memory_type == memory_type)
        count_query = count_query.where(Memory.memory_type == memory_type)

    # Count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Memory.created_at.desc())
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    memories = list(result.scalars().all())

    items = [
        MemoryResponse.model_validate(m).model_dump(mode="json") for m in memories
    ]
    return paginated_response(items=items, total=total, page=page, page_size=page_size)


@router.put("/{key}", status_code=status.HTTP_200_OK)
async def create_or_update_memory(
    key: str,
    request: MemoryCreate,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Create or update a memory by key."""
    # Check if memory with this key exists
    result = await db.execute(
        select(Memory).where(
            Memory.user_id == user.id,
            Memory.key == key,
            Memory.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update
        existing.content = request.content
        existing.category = request.category
        existing.importance_score = request.importance_score
        await db.flush()
        await db.refresh(existing)
        memory = existing
    else:
        # Create
        memory = Memory(
            user_id=user.id,
            memory_type="user_defined",
            category=request.category,
            key=key,
            content=request.content,
            importance_score=request.importance_score,
            is_active=True,
        )
        db.add(memory)
        await db.flush()
        await db.refresh(memory)

    return success_response(
        data=MemoryResponse.model_validate(memory).model_dump(mode="json")
    )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: UUID,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Delete a memory (soft delete)."""
    result = await db.execute(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user.id,
        )
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise NotFoundException(
            message="Memory not found",
            code=ErrorCode.MEMORY_NOT_FOUND,
        )

    memory.is_active = False
    await db.flush()

    return success_response(message="Memory deleted")


@router.post("/search")
async def search_memories(
    request: MemorySearchRequest,
    db: DBSession,
    user: CurrentUser,
) -> dict:
    """Semantic search over memories.

    In full implementation (Phase 5), this would use vector similarity search.
    For now, performs keyword-based search on content_text.
    """
    query = select(Memory).where(
        Memory.user_id == user.id,
        Memory.is_active == True,  # noqa: E712
    )

    if request.category:
        query = query.where(Memory.category == request.category)

    # Simple text search (will be replaced by vector search in Phase 5)
    query = query.where(
        Memory.content_text.ilike(f"%{request.query}%")
        | Memory.key.ilike(f"%{request.query}%")
    )

    query = query.order_by(Memory.importance_score.desc()).limit(request.top_k)

    result = await db.execute(query)
    memories = list(result.scalars().all())

    items = [
        MemoryResponse.model_validate(m).model_dump(mode="json") for m in memories
    ]
    return success_response(data=items)

