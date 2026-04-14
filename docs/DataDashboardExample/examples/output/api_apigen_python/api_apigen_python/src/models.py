from pydantic import BaseModel
from typing import Optional, List, Any


class GenerateRequest(BaseModel):
    
    
    file: str = None
    
    fileType: str = None
    
    


class StatusResponse(BaseModel):
    
    
    status: str = None
    
    payload: str = None
    
    


class ErrorResponse(BaseModel):
    
    
    status: str = None
    
    payload: str = None
    
    


class StatusObject(BaseModel):
    
    
    code: int = None
    
    description: str = None
    
    internal_code: str = None
    
    errors: List[Any] = None
    
    


class ValidationError(BaseModel):
    
    
    loc: List[Any] = None
    
    msg: str = None
    
    type: str = None
    
    


class ValidationErrorsResponse(BaseModel):
    
    
    message: str = None
    
    errors: List[Any] = None
    
    


