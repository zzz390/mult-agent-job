"""Schemas package - Pydantic request/response models."""

from job_agent_os.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatistics,
    ApplicationStatusUpdate,
    KanbanView,
)
from job_agent_os.schemas.approval import (
    ApprovalRespondRequest,
    ApprovalResponse,
    BatchApprovalRequest,
)
from job_agent_os.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from job_agent_os.schemas.common import (
    ApiResponse,
    ErrorResponse,
    PaginatedData,
    PaginationMeta,
    PaginationParams,
)
from job_agent_os.schemas.evaluation import EvalReport, TokenUsageStats
from job_agent_os.schemas.interview import (
    InterviewQuestion,
    InterviewQuestionSet,
    QuestionGenerateRequest,
)
from job_agent_os.schemas.job import (
    JobListItem,
    JobQuery,
    JobResponse,
    JobSearchRequest,
    ParsedJD,
)
from job_agent_os.schemas.match import MatchScore, RecommendationFeedback, RecommendationItem
from job_agent_os.schemas.memory import MemoryCreate, MemoryResponse, MemorySearchRequest
from job_agent_os.schemas.resume import ResumeCreate, ResumeResponse, ResumeUpdate, StructuredResumeData
from job_agent_os.schemas.session import (
    SessionCreate,
    SessionMessage,
    SessionMessageResponse,
    SessionResponse,
)
from job_agent_os.schemas.user import (
    JobIntentionCreate,
    JobIntentionResponse,
    UserResponse,
    UserUpdateRequest,
)

__all__ = [
    "ApiResponse",
    "ApplicationCreate",
    "ApplicationResponse",
    "ApplicationStatistics",
    "ApplicationStatusUpdate",
    "ApprovalRespondRequest",
    "ApprovalResponse",
    "BatchApprovalRequest",
    "ErrorResponse",
    "EvalReport",
    "InterviewQuestion",
    "InterviewQuestionSet",
    "JobIntentionCreate",
    "JobIntentionResponse",
    "JobListItem",
    "JobQuery",
    "JobResponse",
    "JobSearchRequest",
    "KanbanView",
    "LoginRequest",
    "MatchScore",
    "MemoryCreate",
    "MemoryResponse",
    "MemorySearchRequest",
    "PaginatedData",
    "PaginationMeta",
    "PaginationParams",
    "ParsedJD",
    "QuestionGenerateRequest",
    "RecommendationFeedback",
    "RecommendationItem",
    "RefreshTokenRequest",
    "RegisterRequest",
    "ResumeCreate",
    "ResumeResponse",
    "ResumeUpdate",
    "SessionCreate",
    "SessionMessage",
    "SessionMessageResponse",
    "SessionResponse",
    "StructuredResumeData",
    "TokenResponse",
    "TokenUsageStats",
    "UserResponse",
    "UserUpdateRequest",
]
