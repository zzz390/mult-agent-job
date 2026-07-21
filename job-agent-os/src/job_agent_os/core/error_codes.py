"""Error codes definition.

Format: XYYZZ
- X = Error level (4=client error, 5=server error)
- YY = Module number
- ZZ = Specific error sequence

Modules:
- 00: General
- 01: Authentication
- 02: User
- 03: Resume
- 04: Job
- 05: Application
- 06: Agent Execution
- 07: Approval
- 08: Memory
- 09: Evaluation
- 10: Prompt
"""

from enum import IntEnum


class ErrorCode(IntEnum):
    """Application error codes."""

    # === General (00) ===
    VALIDATION_FAILED = 40000
    INVALID_REQUEST_BODY = 40001
    MISSING_REQUIRED_PARAM = 40002
    RESOURCE_NOT_FOUND = 40400
    RATE_LIMIT_EXCEEDED = 42900
    INTERNAL_SERVER_ERROR = 50000
    SERVICE_UNAVAILABLE = 50001

    # === Authentication (01) ===
    TOKEN_NOT_PROVIDED = 40100
    TOKEN_EXPIRED = 40101
    TOKEN_INVALID = 40102
    REFRESH_TOKEN_EXPIRED = 40103
    PERMISSION_DENIED = 40104
    INVALID_CREDENTIALS = 40105
    USER_ALREADY_EXISTS = 40106

    # === User (02) ===
    USER_NOT_FOUND = 40200
    INVALID_USER_STATUS = 40201

    # === Resume (03) ===
    INVALID_FILE_FORMAT = 40300
    FILE_SIZE_EXCEEDED = 40301
    RESUME_PARSE_FAILED = 40302
    RESUME_NOT_FOUND = 40303

    # === Job (04) ===
    JOB_NOT_FOUND = 40401
    INVALID_SEARCH_QUERY = 40402
    PLATFORM_SEARCH_FAILED = 40403

    # === Application (05) ===
    DUPLICATE_APPLICATION = 40500
    INVALID_STATUS_TRANSITION = 40501
    APPLICATION_NOT_FOUND = 40502

    # === Agent Execution (06) ===
    SESSION_NOT_FOUND = 40600
    SESSION_ENDED = 40601
    AGENT_EXECUTION_FAILED = 40602
    AGENT_EXECUTION_TIMEOUT = 40603
    SESSION_IN_PROGRESS = 40604

    # === Approval (07) ===
    APPROVAL_NOT_FOUND = 40700
    APPROVAL_ALREADY_PROCESSED = 40701
    APPROVAL_TIMEOUT = 40702
    INVALID_APPROVAL_ACTION = 40703

    # === Memory (08) ===
    MEMORY_NOT_FOUND = 40800
    INVALID_MEMORY_TYPE = 40801

    # === Evaluation (09) ===
    EVALUATION_NOT_FOUND = 40900
    INVALID_EVAL_METRIC = 40901

    # === Prompt (10) ===
    PROMPT_NOT_FOUND = 41000
    PROMPT_VERSION_CONFLICT = 41001
