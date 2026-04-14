from pydantic import BaseModel, Field
from typing import Dict, Optional

class BindingContract(BaseModel):
    """
    Contrato para x-apigen-binding en operazioni paths.
    """
    model: str = Field(..., description="Nombre del modelo de dominio asociado")
    # Los parámetros dinámicos (path params mapping) se capturarán con extra='allow' o accediendo al dict
    
    model_config = {"extra": "allow"}
