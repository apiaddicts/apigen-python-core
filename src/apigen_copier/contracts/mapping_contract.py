from typing import Optional
from pydantic import BaseModel, Field

class MappingContract(BaseModel):
    """
    Contrato para x-apigen-mapping en schemas.
    Permite mapear un esquema de entrada/salida a un modelo de dominio.
    """
    model: str = Field(..., description="Nombre del modelo de dominio asociado")
    field: Optional[str] = Field(default=None, description="Mapeo a campo específico (ej. 'user.email')")
