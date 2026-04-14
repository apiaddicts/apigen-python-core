"""
Standard Response envelope for apigen REST APIs.

Generated when the OpenAPI spec defines standard_response_result in schemas.
Provides a generic wrapper matching the apigen-springboot standard response format.
"""
from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel

T = TypeVar("T")


class StandardError(BaseModel):
    code: int = 0
    message: str = ""


class ResponseResult(BaseModel):
    status: bool = True
    http_code: int = 200
    errors: List[StandardError] = []
    info: Optional[str] = None
    trace_id: Optional[str] = None
    num_elements: Optional[int] = None


class StandardResponse(BaseModel, Generic[T]):
    result: ResponseResult = ResponseResult()
    data: T

# ════════════════════════════════════════════════════════════════
# ✏️ CUSTOM CODE START
# Write your custom code below this line.
# You can add imports, override functions, add new methods, etc.
# ════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════
# ✏️ CUSTOM CODE END
# ════════════════════════════════════════════════════════════════
