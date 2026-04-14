from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal, Dict, Any, List

class ApigenProject(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    """
    Contrato para la extensión x-apigen-project.
    Define la configuración global del proyecto.
    """
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Nombre del proyecto/aplicación")
    description: str = Field(default="", description="Breve descripción del propósito del proyecto")
    version: str = Field(..., description="Versión del proyecto (ej. '1.0.0')")
    data_driver: Optional[Literal["mysql", "postgresql", "oracle", "s3", "sqlite", "mssql"]] = Field(
        default=None, 
        alias="data-driver", 
        description="Especifica el motor de base de datos a utilizar"
    )
    python_properties: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Configuraciones específicas para proyectos Python"
    )
    artifact_id: Optional[str] = Field(
        default=None, 
        alias="artifact-id", 
        description="Identificador del artefacto/paquete"
    )
    prefix: Optional[str] = Field(
        default="",
        description="Prefijo global para las rutas de la API (ej. /api/v1)"
    )
    standard_response_operations: Optional[List[Any]] = Field(
        default=None,
        alias="standard-response-operations",
        description="JSON Patch operations for standard response transformation (opt-in)"
    )
