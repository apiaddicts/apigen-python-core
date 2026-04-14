"""
Centraliza el mapeo de tipos internos a SQLAlchemy y Python.

Single source of truth para todos los mapeos de tipos del generador.
Usado por: parser.py, model_contract.py, templates Jinja (via filtros).
"""

# ──────────────────────────────────────────────────────────
#  Tipo interno → (SA Column Type, Python Type Hint)
# ──────────────────────────────────────────────────────────
_DATETIME_TZ = "DateTime(timezone=True)"

_INTERNAL_TO_SA_PYTHON = {
    "String":         ("String",      "str"),
    "Integer":        ("Integer",     "int"),
    "Long":           ("BigInteger",  "int"),
    "Boolean":        ("Boolean",     "bool"),
    "Float":          ("Float",       "float"),
    "Double":         ("Float",       "float"),
    "BigDecimal":     ("Numeric",     "Decimal"),
    "BigInteger":     ("BigInteger",  "int"),
    "LocalDate":      ("Date",        "date"),
    "LocalDateTime":  (_DATETIME_TZ,  "datetime"),
    "Date":           ("Date",        "date"),
    "OffsetDateTime": (_DATETIME_TZ,  "datetime"),
    "ZonedDateTime":  (_DATETIME_TZ,  "datetime"),
    "Instant":        (_DATETIME_TZ,  "datetime"),
}

# ──────────────────────────────────────────────────────────
#  OpenAPI (type, format) → tipo interno
# ──────────────────────────────────────────────────────────
_OPENAPI_TO_INTERNAL = {
    ("string",  None):        "String",
    ("string",  "date"):      "LocalDate",
    ("string",  "date-time"): "LocalDateTime",
    ("integer", None):        "Integer",
    ("integer", "int32"):     "Integer",
    ("integer", "int64"):     "Long",
    ("number",  None):        "Float",
    ("number",  "float"):     "Float",
    ("number",  "double"):    "Double",
    ("boolean", None):        "Boolean",
    ("array",   None):        "Array",
    ("object",  None):        "Relation",
}

_MYSQL_DEFAULT = "String(255)"
_PG_DEFAULT = "String"


# ──────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────

def to_sa_column(internal_type: str, data_driver: str = "postgresql") -> str:
    """Convierte tipo interno a tipo de columna SQLAlchemy."""
    entry = _INTERNAL_TO_SA_PYTHON.get(internal_type)
    if entry:
        return entry[0]
    return _MYSQL_DEFAULT if data_driver == "mysql" else _PG_DEFAULT


def to_python_type(internal_type: str) -> str:
    """Convierte tipo interno a type hint de Python."""
    entry = _INTERNAL_TO_SA_PYTHON.get(internal_type)
    return entry[1] if entry else "Any"


def to_sa_pk_type(internal_type: str) -> str:
    """Convierte tipo interno a tipo SA para primary keys (sin timezone)."""
    pk_map = {
        "String": "String",
        "Integer": "Integer",
        "Long": "BigInteger",
        "Boolean": "Boolean",
        "LocalDate": "Date",
        "LocalDateTime": "DateTime",
    }
    return pk_map.get(internal_type, "Integer")


def from_openapi(openapi_type: str, fmt: str = None) -> str:
    """Convierte tipo OpenAPI + format a tipo interno."""
    exact = _OPENAPI_TO_INTERNAL.get((openapi_type, fmt))
    if exact:
        return exact
    # Fallback: buscar sin format
    return _OPENAPI_TO_INTERNAL.get((openapi_type, None), "String")
