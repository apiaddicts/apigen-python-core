from pydantic import BaseModel, Field, model_validator
from typing import Dict, Any, List, Optional
from .contracts import ApigenProject, ModelContract
from .contracts.binding_contract import BindingContract

class ResponseAttribute(BaseModel):
    name: str
    type: str # internal type
    entity_field_name: Optional[str] = None # DB field name
    ref_model: Optional[str] = None
    default_value: Optional[Any] = None # default or example value from schema

class RequestSchema(BaseModel):
    is_collection: bool = False
    attributes: List[ResponseAttribute] = Field(default_factory=list, description="List of attributes for input")
    mime_type: str = "application/json"

class ResponseSchema(BaseModel):
    is_collection: bool = False
    attributes: List[ResponseAttribute] = Field(default_factory=list, description="List of attributes for output")
    mime_type: str = "application/json"

class EndpointSchema(BaseModel):
    method: str
    name: str  # operationId
    mapping: str
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    request: Optional[RequestSchema] = None
    response: Optional[ResponseSchema] = None
    responses: Dict[int, Dict[str, Any]] = Field(default_factory=dict, description="Full response definitions including errors")
    error_responses: Dict[int, ResponseSchema] = Field(default_factory=dict, description="Error response schemas (4xx/5xx) with properties")
    binding: Optional[BindingContract] = None
    response_schema_name: Optional[str] = None  # OpenAPI schema name (e.g. PetPost, PetGet)

    @model_validator(mode='before')
    @classmethod
    def coerce_none_collections(cls, data):
        if isinstance(data, dict):
            if data.get('parameters') is None:
                data['parameters'] = []
            if data.get('responses') is None:
                data['responses'] = {}
            if data.get('error_responses') is None:
                data['error_responses'] = {}
        return data

    @property
    def response_class_name(self) -> Optional[str]:
        """Class name for response model. Uses OpenAPI schema name if available."""
        if not self.response or not self.response.attributes:
            return None
        if self.response_schema_name:
            return self.response_schema_name
        parts = self.name.replace('_', ' ').title().replace(' ', '')
        return f"{parts}Response"

    def error_class_name(self, code: int) -> str:
        """Class name for error response model, e.g. CreateuserError409."""
        parts = self.name.replace('_', ' ').title().replace(' ', '')
        return f"{parts}Error{code}"

class RouterSchema(BaseModel):
    entity: str
    mapping: str
    endpoints: List[EndpointSchema] = Field(default_factory=list)
    sub_routers: Dict[str, "RouterSchema"] = Field(default_factory=dict)

    @model_validator(mode='before')
    @classmethod
    def coerce_none_collections(cls, data):
        if isinstance(data, dict):
            if data.get('sub_routers') is None:
                data['sub_routers'] = {}
            if data.get('endpoints') is None:
                data['endpoints'] = []
        return data

# Needed for self-referencing model
RouterSchema.model_rebuild()

# Alias for backward compatibility if needed, else we use ApigenProject directly
OpenApiProjectSchema = ApigenProject

class RESTProjectSchema(BaseModel):

    project: ApigenProject
    # entities is a Dict mapping Model Name -> ModelContract
    entities: Dict[str, ModelContract] = Field(default_factory=dict)
    routers: Dict[str, RouterSchema] = Field(default_factory=dict)
    output_dir: str = Field(..., description="Absolute path where the code will be generated")
