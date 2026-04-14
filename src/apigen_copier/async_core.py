"""
AsyncAPI code generation orchestrator.

Follows SOLID principles:
- **Single Responsibility**: Each _generate_* function handles one concern.
- **Open/Closed**: New operation types can be added by extending _GENERATORS without modifying existing code.
- **Dependency Inversion**: Functions depend on AsyncAPIProjectSchema (abstraction), not raw dicts.
- **Interface Segregation**: Each generator receives only the data it needs via schema properties.

Public entry point: generate_from_async_schema(schema)
"""
from __future__ import annotations

import os
import re
import shutil
from typing import Dict, Any, Optional

from copier import run_copy
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .async_schemas import AsyncAPIProjectSchema, OperationSchema
from .custom_code_merger import extract_custom_blocks, inject_custom_blocks, copy_user_code_folder


_INIT_PY = "__init__.py"
_MAPPING_TAG = "x-apigen-mapping"


def _write_init_py(directory: str) -> None:
    """Create an empty __init__.py if it doesn't exist."""
    init = os.path.join(directory, _INIT_PY)
    if not os.path.exists(init):
        with open(init, "w") as f:
            f.write("")


def _to_snake_case(value: str) -> str:
    """Convert CamelCase or kebab-case to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.replace("-", "_").replace("__", "_").lower()


def _dto_file_stem(module_name: str) -> str:
    """Return the file stem for a DTO module, avoiding double _dto suffix.

    'order_dto' → 'order_dto' (not 'order_dto_dto').
    """
    if module_name.endswith("_dto"):
        return module_name
    return f"{module_name}_dto"


def _dto_module_for_template(module_name: str) -> str:
    """Return the module name for use in Jinja templates that append '_dto'.

    Templates do: 'from ...{{ dto_module }}_dto import ...', so we must strip
    trailing '_dto' to avoid 'order_dto_dto'.
    'order_dto' → 'order', 'check_res' → 'check_res'.
    """
    if module_name.endswith("_dto"):
        return module_name[:-4]  # strip '_dto'
    return module_name


def _resolve_enum_literal(field_info: dict) -> str | None:
    """Convert enum values to Literal[...] type string."""
    enum_values = field_info.get("enum")
    if not enum_values:
        return None
    json_type = field_info.get("type", "string")
    if json_type == "string":
        enum_values = [str(v).upper() if isinstance(v, bool) else v for v in enum_values]
    literals = ", ".join(repr(v) for v in enum_values)
    return f"Literal[{literals}]"


_JSON_TO_PYTHON = {
    "string": "str", "integer": "int", "number": "float",
    "boolean": "bool", "object": "dict", "array": "list",
}


def _json_type_to_python(field_info: Any) -> str:
    """Map JSON Schema type → Python type string (for DTO generation)."""
    if not isinstance(field_info, dict):
        return _JSON_TO_PYTHON.get(str(field_info), "str")

    literal = _resolve_enum_literal(field_info)
    if literal:
        return literal

    json_type = field_info.get("type", "string")
    if json_type == "string" and field_info.get("format") == "date-time":
        return "datetime"
    if json_type == "object" and field_info.get("_nested_class"):
        return field_info["_nested_class"]

    return _JSON_TO_PYTHON.get(json_type, "str")


def _is_nullable(field_info: Any) -> bool:
    """Check if a field has nullable: true."""
    if isinstance(field_info, dict):
        return field_info.get("nullable", False) is True
    return False


def _create_env(partials_dir: str) -> Environment:
    """Create a Jinja2 Environment with custom filters."""
    env = Environment(
        loader=FileSystemLoader(partials_dir),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["snake"] = _to_snake_case
    env.filters["python_type"] = _json_type_to_python
    env.filters["is_nullable"] = _is_nullable
    env.filters["regex_replace"] = lambda s, pattern, repl: re.sub(pattern, repl, s)
    return env


def _resolve_server_variables(primary) -> dict:
    """Extract server variables with defaults from primary server."""
    if not primary or not hasattr(primary, "variables") or not primary.variables:
        return {}
    result = {}
    for var_name, var_data in primary.variables.items():
        result[var_name] = var_data.get("default", "") if isinstance(var_data, dict) else str(var_data)
    return result


def _extract_broker_credentials(server_vars: dict) -> tuple[str, str, str]:
    """Extract user/pass/vhost defaults from server variables."""
    broker_user, broker_pass, broker_vhost = "", "", "/"
    for var_name, var_default in server_vars.items():
        vn = var_name.lower()
        if "user" in vn:
            broker_user = var_default
        elif "pass" in vn:
            broker_pass = var_default
        elif "vhost" in vn:
            broker_vhost = var_default
    return broker_user, broker_pass, broker_vhost


def _generate_broker_config(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate broker configuration (Kafka or RabbitMQ)."""
    broker_dir = os.path.join(src_dir, "broker")
    os.makedirs(broker_dir, exist_ok=True)

    primary = schema.primary_server
    server_vars = _resolve_server_variables(primary)

    raw_host = primary.host if primary else "localhost:9092"
    resolved_host = raw_host
    for var_name, var_default in server_vars.items():
        resolved_host = resolved_host.replace("{" + var_name + "}", var_default)

    broker_user, broker_pass, broker_vhost = _extract_broker_credentials(server_vars)

    content = env.get_template("broker_config.jinja").render(
        protocol=schema.primary_protocol,
        server_host=resolved_host,
        is_kafka=schema.is_kafka,
        has_security=bool(primary.security) if primary else False,
        broker_user_default=broker_user,
        broker_pass_default=broker_pass,
        broker_vhost=broker_vhost,
    )
    with open(os.path.join(broker_dir, "config.py"), "w") as f:
        f.write(content)

    _write_init_py(broker_dir)


def _extract_nested_classes(properties: dict) -> list[dict]:
    """Extract nested object properties into typed inline classes.

    For each field with type=object + properties, creates a nested class
    entry and tags the field with "_nested_class" for type resolution.
    Returns a list of {"class_name": str, "properties": dict} dicts.

    Enables 'activity: Activity' instead of 'activity: dict'.
    """
    nested = []
    for field_name, field_info in properties.items():
        if not isinstance(field_info, dict):
            continue
        if field_info.get("type") == "object" and field_info.get("properties"):
            class_name = "".join(w.capitalize() for w in _to_snake_case(field_name).split("_"))
            field_info["_nested_class"] = class_name
            deeper = _extract_nested_classes(field_info["properties"])
            nested.extend(deeper)
            nested.append({
                "class_name": class_name,
                "properties": field_info["properties"],
            })
    return nested


def _resolve_fragment(properties: dict, fragment: dict, all_schemas: dict) -> None:
    """Resolve a single allOf fragment and merge its properties."""
    if "$ref" in fragment:
        ref_name = fragment["$ref"].split("/")[-1]
        ref_schema = all_schemas.get(ref_name, {})
        properties.update(_resolve_schema_properties(ref_schema, all_schemas))
    else:
        properties.update(fragment.get("properties", {}))


def _resolve_schema_properties(schema_def: dict, all_schemas: dict) -> dict:
    """Resolve allOf/$ref/oneOf/anyOf compositions into merged properties.

    Schemas using allOf/oneOf/anyOf with $ref inherit properties
    from referenced schemas. This function resolves all references and merges
    properties into a flat dict suitable for DTO generation.
    Propagates 'required' list from schema level into each field dict.
    """
    properties = dict(schema_def.get("properties", {}))
    required_fields = set(schema_def.get("required", []))

    # Tag each field with its required status
    for field_name in properties:
        if isinstance(properties[field_name], dict):
            properties[field_name] = dict(properties[field_name])  # shallow copy
            if field_name in required_fields:
                properties[field_name]["required"] = True

    for fragment in schema_def.get("allOf", []):
        _resolve_fragment(properties, fragment, all_schemas)

    for key in ("oneOf", "anyOf"):
        for option in schema_def.get(key, []):
            _resolve_fragment(properties, option, all_schemas)

    return properties


def _detect_allof_base_class(schema_def: dict, all_schemas: dict) -> tuple:
    """Detect if a schema uses allOf with a $ref to another schema (inheritance).

    Mirrors apigen.net behavior where allOf.$ref becomes class inheritance.

    Returns:
        (base_class_name, base_module_name, base_properties) if found,
        (None, None, {}) otherwise.
    """
    all_of = schema_def.get("allOf", [])
    for fragment in all_of:
        if "$ref" in fragment:
            ref_name = fragment["$ref"].split("/")[-1]
            if ref_name in all_schemas:
                base_class = _to_pascal_case(ref_name)
                base_module = _to_snake_case(ref_name)
                base_props = _resolve_schema_properties(all_schemas[ref_name], all_schemas)
                return base_class, base_module, base_props
    return None, None, {}


def _extract_oneof_variants(schema_def: dict) -> tuple:
    """Extract oneOf variant info for discriminated union generation.

    OneOf schemas generate Pydantic Union type aliases.

    Supports two resolution modes:
    - Pre-resolution: "$ref" key is still present in each option.
    - Post-resolution: "$ref" was resolved by ``_resolve_deep()`` but
      ``_original_ref`` metadata was preserved, allowing reliable
      variant identification without heuristics.

    Returns:
        (variants, discriminator) where variants is a list of
        {"class_name": str, "module": str} dicts, and discriminator
        is the field name (or None if not present).
        Returns ([], None) if the schema is not a oneOf.
    """
    one_of = schema_def.get("oneOf", [])
    if not one_of:
        return [], None

    variants = []
    for option in one_of:
        # Case 1: $ref still present (unresolved)
        if "$ref" in option:
            ref_name = option["$ref"].split("/")[-1]
            variants.append({
                "class_name": _to_pascal_case(ref_name),
                "module": _to_snake_case(ref_name),
            })
            continue

        # Case 2: $ref resolved by _resolve_deep — use _original_ref metadata
        if isinstance(option, dict) and "_original_ref" in option:
            ref_name = option["_original_ref"].split("/")[-1]
            variants.append({
                "class_name": _to_pascal_case(ref_name),
                "module": _to_snake_case(ref_name),
            })

    if not variants:
        return [], None

    discriminator = schema_def.get("discriminator")
    # discriminator can be a string field name or a dict with propertyName
    if isinstance(discriminator, dict):
        discriminator = discriminator.get("propertyName")
    # Convert to snake_case for Pydantic field names
    if discriminator:
        discriminator = _to_snake_case(discriminator)

    return variants, discriminator


def _should_allow_extra(schema_def: dict) -> bool:
    """Determine if a DTO should accept extra fields based on additionalProperties.

    JSON Schema's additionalProperties controls whether unknown fields are accepted:
    - true or {type: ...} → allow extra fields (Pydantic extra='allow')
    - false or absent → forbid extra fields (Pydantic extra='forbid', our safe default)
    """
    additional = schema_def.get("additionalProperties")
    if additional is None or additional is False:
        return False
    return True


def _count_required_fields(op_name: str, op: OperationSchema, payload_schemas: dict) -> int:
    """Count required fields in the primary payload for dispatcher ordering.

    Operations with more required fields are more specific and should be
    tried first when discriminating multi-message channels (ASYNC-064).
    """
    for msg in op.messages:
        payload = msg.get("payload", {}) if isinstance(msg, dict) else {}
        required = payload.get("required", [])
        if required:
            return len(required)
        ref = payload.get("$ref", "")
        if ref:
            ref_name = ref.split("/")[-1]
            schema_def = payload_schemas.get(ref_name, {})
            return len(schema_def.get("required", []))

    # Fallback: try to match by name in payload_schemas
    for schema_name, schema_def in payload_schemas.items():
        if _to_snake_case(schema_name) == _to_snake_case(op_name):
            return len(schema_def.get("required", []))
    return 0


def _force_optional_properties(properties: dict) -> dict:
    """Force all properties to required=False for anyOf schemas.

    AnyOf means 'any combination', so all fields must be Optional.
    """
    return {
        k: {**(v if isinstance(v, dict) else {}), "required": False}
        for k, v in properties.items()
    }


def _collect_autogen_pk_fields(model_contracts: dict | None) -> set:
    """Collect field names that are autogenerated primary keys."""
    result: set = set()
    if not model_contracts:
        return result
    for model in model_contracts.values():
        for attr in model.attributes:
            if attr.persistence and attr.persistence.primary_key and attr.persistence.autogenerated:
                result.add(attr.name)
    return result


def _mark_autogen_pk_optional(properties: dict, autogen_pk_fields: set) -> None:
    """Mark properties that map to autogenerated PKs as optional."""
    if not autogen_pk_fields:
        return
    for _finfo in properties.values():
        if not isinstance(_finfo, dict):
            continue
        mapping = _finfo.get("x-apigen-mapping", {})
        if mapping.get("field") in autogen_pk_fields:
            _finfo["required"] = False


def _render_enum_dto(enum_template, class_name: str, schema_name: str, schema_def: dict, dto_dir: str, module_name: str) -> bool:
    """Render an enum DTO if applicable. Returns True if rendered."""
    enum_values = schema_def.get("enum")
    if not enum_values or schema_def.get("type") not in ("string", None):
        return False
    content = enum_template.render(class_name=class_name, schema_name=schema_name, enum_values=enum_values)
    with open(os.path.join(dto_dir, f"{_dto_file_stem(module_name)}.py"), "w") as f:
        f.write(content)
    return True


def _render_union_dto(union_template, class_name: str, schema_name: str, schema_def: dict, dto_dir: str, module_name: str) -> bool:
    """Render a Union type alias DTO for oneOf schemas. Returns True if rendered."""
    variants, discriminator = _extract_oneof_variants(schema_def)
    if not variants:
        return False
    content = union_template.render(class_name=class_name, schema_name=schema_name, variants=variants, discriminator=discriminator)
    with open(os.path.join(dto_dir, f"{_dto_file_stem(module_name)}.py"), "w") as f:
        f.write(content)
    return True


def _render_model_dto(
    template, class_name: str, schema_name: str, schema_def: dict,
    all_schemas: dict, autogen_pk_fields: set, dto_dir: str, module_name: str,
) -> None:
    """Render a standard Pydantic model DTO."""
    properties = _resolve_schema_properties(schema_def, all_schemas)

    if schema_def.get("anyOf"):
        properties = _force_optional_properties(properties)

    _mark_autogen_pk_optional(properties, autogen_pk_fields)

    base_class_name, base_module_name, base_props = _detect_allof_base_class(schema_def, all_schemas)
    own_properties = {k: v for k, v in properties.items() if k not in base_props} if base_props else properties
    nested_classes = _extract_nested_classes(own_properties)
    has_literal, has_datetime = _detect_dto_imports(own_properties, nested_classes)
    allow_extra = _should_allow_extra(schema_def)

    content = template.render(
        class_name=class_name, schema_name=schema_name, properties=own_properties,
        nested_classes=nested_classes, has_literal=has_literal, has_datetime=has_datetime,
        base_class_name=base_class_name, base_module_name=base_module_name, allow_extra=allow_extra,
    )
    with open(os.path.join(dto_dir, f"{_dto_file_stem(module_name)}.py"), "w") as f:
        f.write(content)


def _generate_dtos(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate Pydantic DTOs from components.schemas."""
    dto_dir = os.path.join(src_dir, "application", "dtos")
    os.makedirs(dto_dir, exist_ok=True)

    for d in [os.path.join(src_dir, "application"), dto_dir]:
        _write_init_py(d)

    template = env.get_template("dto.jinja")
    union_template = env.get_template("dto_union.jinja")
    enum_template = env.get_template("dto_enum.jinja")
    all_schemas = schema.payload_schemas
    autogen_pk_fields = _collect_autogen_pk_fields(schema.model_contracts)

    for schema_name, schema_def in all_schemas.items():
        class_name = _to_pascal_case(schema_name)
        module_name = _to_snake_case(schema_name)

        if _render_enum_dto(enum_template, class_name, schema_name, schema_def, dto_dir, module_name):
            continue
        if _render_union_dto(union_template, class_name, schema_name, schema_def, dto_dir, module_name):
            continue
        _render_model_dto(template, class_name, schema_name, schema_def, all_schemas, autogen_pk_fields, dto_dir, module_name)

    _generate_inline_dtos(env, schema, dto_dir)


def _detect_dto_imports(properties: dict, nested_classes: list) -> tuple[bool, bool]:
    """Detect whether a DTO needs Literal or datetime imports."""
    all_props = list(properties.values())
    for nc in nested_classes:
        all_props.extend(nc["properties"].values())
    has_literal = any(isinstance(p, dict) and p.get("enum") for p in all_props)
    has_datetime = any(isinstance(p, dict) and p.get("format") == "date-time" for p in all_props)
    return has_literal, has_datetime


def _render_inline_dto(
    template, payload: dict, op_name: str, all_schemas: dict, dto_dir: str,
    suffix: str = "Payload", autogen_pk_fields: set | None = None,
) -> str | None:
    """Render a single inline DTO and return the module_name (or None if skipped)."""
    properties = _resolve_schema_properties(payload, all_schemas)
    if not properties:
        return None

    class_name = _to_pascal_case(op_name) + suffix

    module_name = _to_snake_case(class_name)

    # Detect allOf inheritance for inline payloads
    base_class_name, base_module_name, base_props = _detect_allof_base_class(
        payload, all_schemas
    )

    _mark_autogen_pk_optional(properties, autogen_pk_fields or set())

    # Detect anyOf → all fields become Optional
    if payload.get("anyOf"):
        properties = _force_optional_properties(properties)

    own_properties = (
        {k: v for k, v in properties.items() if k not in base_props}
        if base_props
        else properties
    )

    nested_classes = _extract_nested_classes(own_properties)
    has_literal, has_datetime = _detect_dto_imports(own_properties, nested_classes)
    allow_extra = _should_allow_extra(payload)
    content = template.render(
        class_name=class_name,
        schema_name=op_name,
        properties=own_properties,
        nested_classes=nested_classes,
        has_literal=has_literal,
        has_datetime=has_datetime,
        base_class_name=base_class_name,
        base_module_name=base_module_name,
        allow_extra=allow_extra,
    )
    with open(os.path.join(dto_dir, f"{_dto_file_stem(module_name)}.py"), "w") as f:
        f.write(content)
    return module_name


def _process_request_messages(
    op, op_name: str, template, all_schemas: dict, dto_dir: str, existing: set,
    autogen_pk_fields: set | None = None,
) -> None:
    """Process inline payloads for request messages."""
    for msg in op.messages:
        payload = msg.get("payload", {})
        if "$ref" in payload:
            continue
        module_name = _render_inline_dto(
            template, payload, op_name, all_schemas, dto_dir,
            autogen_pk_fields=autogen_pk_fields,
        )
        if module_name and module_name not in existing:
            existing.add(module_name)


def _process_reply_messages(
    op, template, all_schemas: dict, dto_dir: str, existing: set,
    autogen_pk_fields: set | None = None,
) -> None:
    """Process inline payloads for reply messages (RPC)."""
    if not op.reply or not isinstance(op.reply, dict):
        return

    reply_channel = op.reply.get("channel", {})
    if not isinstance(reply_channel, dict):
        return

    for msg_name, msg_data in reply_channel.get("messages", {}).items():
        payload = msg_data.get("payload", {})
        if "$ref" in payload or "_original_ref" in payload:
            continue

        module_name = _render_inline_dto(
            template, payload, msg_name, all_schemas, dto_dir, suffix="",
            autogen_pk_fields=autogen_pk_fields,
        )
        if module_name and module_name not in existing:
            existing.add(module_name)


def _generate_inline_dtos(env: Environment, schema: AsyncAPIProjectSchema, dto_dir: str) -> None:
    """Generate DTOs for inline message payloads not in components.schemas."""
    template = env.get_template("dto.jinja")
    existing = {name.lower() for name in schema.payload_schemas}
    all_schemas = schema.payload_schemas

    autogen_pk_fields = _collect_autogen_pk_fields(schema.model_contracts)

    for op_name, op in schema.typed_operations.items():
        # 1. Process request messages
        _process_request_messages(op, op_name, template, all_schemas, dto_dir, existing, autogen_pk_fields)

        # 2. Process reply messages (AsyncAPI v3 RPC replies)
        _process_reply_messages(op, template, all_schemas, dto_dir, existing, autogen_pk_fields)


def _to_pascal_case(name: str) -> str:
    """Convert any naming convention to PascalCase.

    Handles: camelCase, snake_case, kebab-case, PascalCase (passthrough).
    Preserves uppercase runs (acronyms like DTO, RPC, ID).
    """
    # Split on underscores and hyphens
    parts = re.sub(r'[-_]', ' ', name)
    # Split on camelCase word boundaries (lowercase followed by uppercase)
    parts = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', parts)
    # Capitalize first letter of each word, preserve rest (keeps acronyms)
    return ''.join(word[0].upper() + word[1:] for word in parts.split() if word)


def _resolve_from_payload(payload: dict, op_name: str) -> tuple:
    if "$ref" in payload:
        schema_name = payload["$ref"].split("/")[-1]
        return _to_pascal_case(schema_name), _dto_module_for_template(_to_snake_case(schema_name))
    if "properties" in payload:
        class_name = _to_pascal_case(op_name) + "Payload"

        return class_name, _dto_module_for_template(_to_snake_case(class_name))
    scalar_type = payload.get("type")
    if scalar_type and scalar_type != "object":
        py_type = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}.get(scalar_type, "str")
        return py_type, None
    return None, None


def _resolve_dto_for_operation(op_name: str, op: OperationSchema, payload_schemas: dict = None) -> tuple:
    for msg in op.messages:
        result = _resolve_from_payload(msg.get("payload", {}), op_name)
        if result[0]:
            return result

    if payload_schemas:
        for schema_name in payload_schemas:
            if _to_snake_case(schema_name) == _to_snake_case(op_name):
                return _to_pascal_case(schema_name), _dto_module_for_template(_to_snake_case(schema_name))
    return None, None


def _search_nested_object(
    prop_info: dict, target_name: str, prefix: str,
) -> tuple[str, dict] | tuple[None, None]:
    """Search inside a nested object property for a matching field."""
    nested_props = prop_info.get("properties", {})
    if nested_props:
        return _find_field_path(nested_props, target_name, prefix)
    return None, None


def _find_explicit_mapping_path(
    properties: dict, target_name: str, prefix: str
) -> tuple[str, dict] | tuple[None, None]:
    for prop_name, prop_info in properties.items():
        if not isinstance(prop_info, dict):
            continue
        mapping = prop_info.get(_MAPPING_TAG)
        if mapping and mapping.get("field") == target_name:
            prop_info = dict(prop_info)
            prop_info["_json_key"] = prop_name
            return f"{prefix}.{_to_snake_case(prop_name)}", prop_info
        if prop_info.get("type") == "object":
            result = _search_nested_object(prop_info, target_name, f"{prefix}.{_to_snake_case(prop_name)}")
            if result[0] is not None:
                return result
    return None, None


def _find_fallback_path(
    properties: dict, target_name: str, prefix: str
) -> tuple[str, dict] | tuple[None, None]:
    target_snake = _to_snake_case(target_name)
    for prop_name, prop_info in properties.items():
        prop_snake = _to_snake_case(prop_name)
        if prop_snake == target_snake:
            info = dict(prop_info) if isinstance(prop_info, dict) else {}
            info["_json_key"] = prop_name
            return f"{prefix}.{prop_snake}", info
        if isinstance(prop_info, dict) and prop_info.get("type") == "object":
            result = _search_nested_object(prop_info, target_name, f"{prefix}.{prop_snake}")
            if result[0] is not None:
                return result
    return None, None


def _find_field_path(properties: dict, target_name: str, prefix: str = "data") -> tuple[str, dict] | tuple[None, None]:
    """Recursively search payload properties for a field matching target_name.

    Uses the same mapping strategy as OpenAPI: each property can declare
    ``x-apigen-mapping: {field: <entity_attr>}`` for a reliable bridge
    between DTO property names and model attribute names.

    Priority:
      1. Explicit ``x-apigen-mapping.field`` on the property.
      2. snake_case name comparison (backward-compat fallback).

    ASYNC-029: uses dot notation for all access since nested objects are now
    typed Pydantic classes (not dicts). Pydantic uses snake_case aliases.
    Returns (path, field_info) tuple so callers can inspect schema metadata.
    """
    path, info = _find_explicit_mapping_path(properties, target_name, prefix)
    if path is not None:
        return path, info
    return _find_fallback_path(properties, target_name, prefix)


def _resolve_operation_payload_props(
    op: "OperationSchema", components: dict
) -> dict:
    """Resolve the payload properties dict from an operation's messages."""
    all_schemas = components.get("schemas", {})
    for msg in op.messages:
        payload = msg.get("payload", {})
        if "$ref" in payload:
            ref_name = payload["$ref"].split("/")[-1]
            messages = components.get("messages", {})
            if ref_name in messages:
                payload = messages[ref_name].get("payload", {})
            elif ref_name in all_schemas:
                payload = all_schemas[ref_name]
                
        props = _resolve_schema_properties(payload, all_schemas)
        if props:
            return props
    return {}


def _is_primary_key(attr) -> bool:
    """Check if attribute is a primary key (persistence flag or name='id')."""
    return (attr.persistence and attr.persistence.primary_key) or attr.name == "id"


def _build_field_mapping(
    model_name: str,
    schema: "AsyncAPIProjectSchema",
    op: "OperationSchema",
) -> list[dict]:
    """Build a list of {attr, path} dicts mapping domain model attributes to DTO paths."""
    model_contracts = schema.model_contracts
    if not model_contracts or model_name not in model_contracts:
        return []

    model = model_contracts[model_name]
    payload_props = _resolve_operation_payload_props(op, schema.components)
    if not payload_props:
        return []

    field_map = []
    for attr in model.attributes:
        # AsyncAPI: include PK fields — events carry their own identity
        path, field_info = _find_field_path(payload_props, attr.name)
        if path:
            # Detect datetime DTO → String model mismatch
            needs_str_cast = (
                field_info is not None
                and field_info.get("format") == "date-time"
                and attr.type in ("String", "str")
            )
            json_key = field_info.get("_json_key", _to_snake_case(attr.name)) if field_info else _to_snake_case(attr.name)
            field_map.append({"attr": attr.name, "path": path, "needs_str_cast": needs_str_cast, "json_key": json_key})
    return field_map


def _resolve_scalar_attr(schema: "AsyncAPIProjectSchema", model_name: str) -> str | None:
    """Return the first non-PK attribute name of a model."""
    model_contracts = schema.model_contracts or {}
    model = model_contracts.get(model_name)
    if not model:
        return None
    for attr in model.attributes:
        if not _is_primary_key(attr):
            return attr.name
    return None


def _generate_handlers(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate handler files for receive operations."""
    handler_dir = os.path.join(src_dir, "handlers")
    os.makedirs(handler_dir, exist_ok=True)

    template = env.get_template("handler.jinja")

    for op_name, op in schema.receive_operations.items():
        dto_class, dto_module = _resolve_dto_for_operation(op_name, op)

        field_map = []
        if op.binding_model:
            field_map = _build_field_mapping(op.binding_model, schema, op)

        scalar_attr_name = None
        if not field_map and not dto_module and op.binding_model:
            scalar_attr_name = _resolve_scalar_attr(schema, op.binding_model)

        content = template.render(
            operation_name=op_name,
            channel_address=op.channel_address,
            binding_action=op.binding_action,
            binding_model=op.binding_model,
            dto_class=dto_class,
            dto_module=dto_module,
            field_map=field_map,
            scalar_attr_name=scalar_attr_name,
        )
        with open(os.path.join(handler_dir, f"{_to_snake_case(op_name)}_handler.py"), "w") as f:
            f.write(content)

    _write_init_py(handler_dir)


def _generate_publishers(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate publisher files for send operations without reply."""
    publisher_dir = os.path.join(src_dir, "publishers")
    os.makedirs(publisher_dir, exist_ok=True)

    template = env.get_template("publisher.jinja")

    for op_name, op in schema.publisher_operations.items():
        dto_class, dto_module = _resolve_dto_for_operation(op_name, op)
        content = template.render(
            operation_name=op_name,
            channel_address=op.channel_address,
            binding_model=op.binding_model,
            dto_class=dto_class,
            dto_module=dto_module,
        )
        with open(os.path.join(publisher_dir, f"{_to_snake_case(op_name)}_publisher.py"), "w") as f:
            f.write(content)

    _write_init_py(publisher_dir)


def _resolve_reply_dto(op: OperationSchema) -> tuple:
    """Extract response DTO class/module from the reply channel messages.

    Supports both pre- and post-resolution payloads by checking
    ``_original_ref`` metadata (set by ``_resolve_deep()``) in addition
    to the standard ``$ref`` key.
    """
    if not op.reply or not isinstance(op.reply, dict):
        return None, None
    reply_channel = op.reply.get("channel", {})
    if not isinstance(reply_channel, dict):
        return None, None
    for msg_name, msg_data in reply_channel.get("messages", {}).items():
        payload = msg_data.get("payload", {})
        # Case 1: $ref still present (unresolved)
        if "$ref" in payload:
            ref_name = payload["$ref"].split("/")[-1]
            return _to_pascal_case(ref_name), _dto_module_for_template(_to_snake_case(ref_name))
        # Case 2: $ref resolved — use _original_ref metadata
        if isinstance(payload, dict) and "_original_ref" in payload:
            ref_name = payload["_original_ref"].split("/")[-1]
            return _to_pascal_case(ref_name), _dto_module_for_template(_to_snake_case(ref_name))
        # Case 3: inline payload with properties
        if "properties" in payload:
            class_name = _to_pascal_case(msg_name)
            return class_name, _dto_module_for_template(_to_snake_case(class_name))
    return None, None


def _generate_rpc_clients(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate RPC client files for send operations with reply."""
    rpc_dir = os.path.join(src_dir, "rpc")
    os.makedirs(rpc_dir, exist_ok=True)

    template = env.get_template("rpc_client.jinja")

    for op_name, op in schema.rpc_operations.items():
        req_dto_class, req_dto_module = _resolve_dto_for_operation(op_name, op)
        res_dto_class, res_dto_module = _resolve_reply_dto(op)

        content = template.render(
            operation_name=op_name,
            request_channel=op.channel_address,
            reply_channel=op.reply_channel_address or "",
            request_dto_class=req_dto_class,
            request_dto_module=req_dto_module,
            response_dto_class=res_dto_class,
            response_dto_module=res_dto_module,
        )
        with open(os.path.join(rpc_dir, f"{_to_snake_case(op_name)}_client.py"), "w") as f:
            f.write(content)

    _write_init_py(rpc_dir)


def _detect_broker_protocol(schema: AsyncAPIProjectSchema) -> str:
    """Detect broker protocol from schema servers (defaults to kafka)."""
    for srv in schema.servers.values():
        if hasattr(srv, "protocol"):
            return srv.protocol
        if isinstance(srv, dict):
            return srv.get("protocol", "kafka")
    return "kafka"


_SAMPLE_VALUE_BY_TYPE = {
    "string": '"test"', "number": "0", "integer": "0", "boolean": "False",
}

_SAMPLE_VALUE_BY_FORMAT = {
    "date-time": '"2024-01-01T00:00:00"',
    "date": '"2024-01-01"',
    "email": '"test@test.com"',
    "uri": '"https://example.com"',
    "uuid": '"00000000-0000-0000-0000-000000000000"',
}


def _find_schema_def(dto_class: str, payload_schemas: dict) -> dict:
    schema_def = payload_schemas.get(dto_class, {})
    if schema_def:
        return schema_def
    lower_dto = dto_class.lower()
    for key, val in payload_schemas.items():
        if key.lower() == lower_dto:
            return val
    return {}


def _extract_operation_properties(operation) -> dict:
    if not operation:
        return {}
    for msg in operation.messages:
        props = msg.get("payload", {}).get("properties", {})
        if props:
            return props
    return {}


def _sample_value_for_field(finfo: dict, all_schemas: dict = None) -> str:
    enum_vals = finfo.get("enum")
    if enum_vals:
        return repr(enum_vals[0])
    ref = finfo.get("$ref", "")
    if ref and all_schemas:
        ref_name = ref.rsplit("/", 1)[-1]
        ref_schema = all_schemas.get(ref_name, {})
        ref_enum = ref_schema.get("enum")
        if ref_enum:
            return repr(ref_enum[0])
    ftype = finfo.get("type", "string")
    if ftype == "object":
        return "{}"
    if ftype == "array":
        return "[]"
    ffmt = finfo.get("format", "")
    if ffmt in _SAMPLE_VALUE_BY_FORMAT:
        return _SAMPLE_VALUE_BY_FORMAT[ffmt]
    return _SAMPLE_VALUE_BY_TYPE.get(ftype, '"test"')


def _build_sample_fields(dto_class: str, payload_schemas: dict, operation=None) -> str:
    if not dto_class or dto_class in ('dict', 'str', 'int', 'float', 'bool'):
        return ""

    schema_def = _find_schema_def(dto_class, payload_schemas)
    properties = _resolve_schema_properties(schema_def, payload_schemas)
    if not properties:
        properties = _extract_operation_properties(operation)

    sample_parts = []
    for fname, finfo in list(properties.items())[:5]:
        if not isinstance(finfo, dict):
            continue
        value = _sample_value_for_field(finfo, all_schemas=payload_schemas)
        sample_parts.append(f"{_to_snake_case(fname)}={value}")
    return ", ".join(sample_parts)


def _generate_tests(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate unit tests for handlers."""
    project_dir = os.path.dirname(src_dir)
    test_dir = os.path.join(project_dir, "tests")
    os.makedirs(test_dir, exist_ok=True)
    _write_init_py(test_dir)

    broker_protocol = _detect_broker_protocol(schema)
    template = env.get_template("test_handler.jinja")

    for op_name, op in schema.receive_operations.items():
        handler_name = _to_snake_case(op_name)
        dto_class, dto_module = _resolve_dto_for_operation(op_name, op, schema.payload_schemas)
        sample_fields = _build_sample_fields(dto_class, schema.payload_schemas, operation=op)

        content = template.render(
            handler_name=handler_name,
            channel_address=op.channel_address,
            broker_protocol=broker_protocol,
            dto_class=dto_class or "dict",
            dto_module=dto_module or "",
            sample_fields=sample_fields,
        )
        test_file = os.path.join(test_dir, f"test_{handler_name}_handler.py")
        with open(test_file, "w") as f:
            f.write(content)


def _generate_health(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate health check endpoint.

    Creates src/health.py with a FastAPI /health endpoint that reports
    broker and optional database connection status.
    """
    template = env.get_template("health.jinja")
    has_database = bool(schema.entities)
    content = template.render(
        project_name=schema.project.name,
        has_database=has_database,
    )
    with open(os.path.join(src_dir, "health.py"), "w") as f:
        f.write(content)


def _generate_error_handler(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate error handling middleware.

    Creates src/middleware/error_handler.py with safe_handle() wrapper
    for structured error logging on handler exceptions.
    """
    middleware_dir = os.path.join(src_dir, "middleware")
    os.makedirs(middleware_dir, exist_ok=True)
    _write_init_py(middleware_dir)

    broker_protocol = "kafka"
    for srv in schema.servers.values():
        if hasattr(srv, "protocol"):
            broker_protocol = srv.protocol
            break
        elif isinstance(srv, dict):
            broker_protocol = srv.get("protocol", "kafka")
            break

    template = env.get_template("error_handler.jinja")
    content = template.render(
        project_name=schema.project.name,
        broker_protocol=broker_protocol,
    )
    with open(os.path.join(middleware_dir, "error_handler.py"), "w") as f:
        f.write(content)


def _generate_main(env: Environment, schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate the FastStream main.py application entrypoint."""
    template = env.get_template("main.jinja")

    receive_ops = schema.receive_operations
    handler_imports = [
        (_to_snake_case(name) + "_handler", _to_snake_case(name))
        for name in receive_ops
    ]

    dto_map = {}
    for name, op in receive_ops.items():
        dto_class, dto_module = _resolve_dto_for_operation(name, op, schema.payload_schemas)
        dto_map[name] = {"dto_class": dto_class, "dto_module": dto_module}

        # Populate required_count for dispatcher ordering (ASYNC-064)
        op.required_count = _count_required_fields(name, op, schema.payload_schemas)

    grouped_receive_ops = {}
    for name, op in receive_ops.items():
        addr = op.channel_address
        grouped_receive_ops.setdefault(addr, []).append((name, op))

    broker_protocol = "kafka"
    for srv in schema.servers.values():
        if hasattr(srv, "protocol"):
            broker_protocol = srv.protocol
            break
        elif isinstance(srv, dict):
            broker_protocol = srv.get("protocol", "kafka")
            break

    # Include publishers and RPC clients in main.py
    publisher_imports = [
        (_to_snake_case(name) + "_publisher", _to_snake_case(name))
        for name in schema.publisher_operations
    ]
    rpc_imports = [
        (_to_snake_case(name) + "_client", _to_snake_case(name))
        for name in schema.rpc_operations
    ]

    content = template.render(
        project_name=schema.project.name,
        receive_ops=receive_ops,
        grouped_receive_ops=grouped_receive_ops,
        handler_imports=handler_imports,
        dto_map=dto_map,
        broker_protocol=broker_protocol,
        publisher_imports=publisher_imports,
        rpc_imports=rpc_imports,
    )
    with open(os.path.join(src_dir, "main.py"), "w") as f:
        f.write(content)


def _copy_base_classes(template_base_dir: str, src_dir: str) -> None:
    """Copy BaseService and BaseRepository from the REST template.

    These are static files (no Jinja) that the REST copier scaffold copies
    automatically, but the AsyncAPI scaffold does not include them.
    Services generated by ``_generate_infra_services`` inherit from BaseService,
    which in turn depends on BaseRepository.
    """
    rest_template_src = os.path.join(
        template_base_dir, "template", "{{project_slug}}", "src"
    )

    copies = [
        (
            os.path.join(rest_template_src, "domain", "services", "base_service.py"),
            os.path.join(src_dir, "domain", "services", "base_service.py"),
        ),
        (
            os.path.join(rest_template_src, "domain", "repository", "base_repository.py"),
            os.path.join(src_dir, "domain", "repository", "base_repository.py"),
        ),
    ]

    for src, dst in copies:
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            pkg_init = os.path.join(os.path.dirname(dst), _INIT_PY)
            if not os.path.exists(pkg_init):
                with open(pkg_init, "w") as f:
                    f.write("")


def _get_fk_column(attr) -> str | None:
    """Return the column name if attr looks like a foreign key, else None."""
    if attr.type == "Relation" or attr.ref_model:
        return None
    col = attr.persistence.column if attr.persistence and attr.persistence.column else None
    if not col or not col.endswith("_id"):
        return None
    if attr.persistence and attr.persistence.primary_key:
        return None
    return col


def _resolve_fk_target(prefix: str, model_name_lower: dict, table_to_model: dict) -> str | None:
    """Find the target model name for a FK column prefix."""
    if prefix in model_name_lower:
        return model_name_lower[prefix]
    for tbl_name, mod_name in table_to_model.items():
        bare = tbl_name.rstrip("0123456789")
        if bare == prefix or bare == prefix + "s" or bare.rstrip("s") == prefix:
            return mod_name
    return None


def _apply_fk_relation(attr, target_model: str, col: str) -> None:
    """Convert an attribute into a Relation pointing at target_model."""
    from .contracts.model_contract import RelationalPersistence
    attr.type = "Relation"
    attr.ref_model = target_model
    if not attr.persistence:
        attr.persistence = RelationalPersistence(column=col)
    if not attr.persistence.foreign_column:
        attr.persistence.foreign_column = "id"


def _ensure_foreign_keys(model_contracts: dict) -> None:
    model_name_lower = {name.lower(): name for name in model_contracts}

    table_to_model = {}
    for name, model in model_contracts.items():
        tbl = model.table_name
        if tbl:
            table_to_model[tbl.lower()] = name

    for _model_name, model in model_contracts.items():
        for attr in model.attributes:
            col = _get_fk_column(attr)
            if not col:
                continue
            prefix = col[:-3]
            target_model = _resolve_fk_target(prefix, model_name_lower, table_to_model)
            if target_model:
                _apply_fk_relation(attr, target_model, col)


def _ensure_primary_keys(model_contracts: dict) -> None:
    """Ensure 'id' attributes have primary_key=True.

    The apigen-python AsyncAPI parser sometimes outputs empty persistence,
    losing the primary-key flag from x-apigen-models.
    """
    from .contracts.model_contract import RelationalPersistence
    for _name, model in model_contracts.items():
        has_pk = any(a.persistence and a.persistence.primary_key for a in model.attributes)
        if has_pk:
            continue
        for attr in model.attributes:
            if attr.name != "id":
                continue
            if not attr.persistence:
                attr.persistence = RelationalPersistence(primary_key=True)
            else:
                attr.persistence.primary_key = True
            break


def _build_rest_env(schema, model_contracts):
    """Build a RESTProjectSchema and Jinja env from an async schema."""
    from .schemas import RESTProjectSchema
    from .contracts import ApigenProject

    driver_kwargs = {"data-driver": schema.project.data_driver} if schema.project.data_driver else {}
    project = ApigenProject(
        name=schema.project.name,
        version=schema.project.version,
        description=schema.project.description,
        **driver_kwargs,
    )
    rest_schema = RESTProjectSchema(
        project=project,
        entities=model_contracts,
        routers={},
        output_dir=schema.output_dir,
    )

    base_dir = os.path.dirname(os.path.abspath(__file__))
    partials_dir = os.path.join(base_dir, "partials")
    env = Environment(
        loader=FileSystemLoader(partials_dir),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["snake"] = _to_snake_case
    from .type_mapper import to_sa_column, to_python_type
    env.filters["sa_column_type"] = to_sa_column
    env.filters["python_type"] = to_python_type

    return rest_schema, env, base_dir


def _generate_async_repos_and_services(env, rest_schema, src_dir):
    """Generate AsyncAPI-aware repositories and services."""
    repo_template = env.get_template("infra_repository.jinja")
    service_template = env.get_template("infra_service.jinja")

    for name, model in rest_schema.entities.items():
        cleaned_name = name.lower()

        if model.has_persistence:
            repo_dir = os.path.join(src_dir, "infrastructure", "repository", cleaned_name)
            os.makedirs(repo_dir, exist_ok=True)
            content = repo_template.render(entity_name=name, is_asyncapi=True)
            with open(os.path.join(repo_dir, f"{cleaned_name}_repository.py"), "w") as f:
                f.write(content)

        svc_dir = os.path.join(src_dir, "infrastructure", "service", cleaned_name)
        os.makedirs(svc_dir, exist_ok=True)
        content = service_template.render(entity_name=name, has_persistence=model.has_persistence, is_asyncapi=True)
        with open(os.path.join(svc_dir, f"{cleaned_name}_service.py"), "w") as f:
            f.write(content)


def _generate_domain_and_infra(schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate domain models, entities, repositories, services, and mappers.

    **Open/Closed**: Reuses existing REST partials via the existing core module.
    Only generates for entities with persistence (x-apigen-models with table).
    """
    from .core import (
        _generate_domain_models,
        _generate_infra_entities,
        _generate_infra_mappers,
    )

    model_contracts = schema.model_contracts
    if not model_contracts:
        return

    _ensure_primary_keys(model_contracts)
    _ensure_foreign_keys(model_contracts)
    rest_schema, env, base_dir = _build_rest_env(schema, model_contracts)

    _generate_domain_models(env, rest_schema, src_dir)
    _generate_infra_entities(env, rest_schema, src_dir)
    _generate_infra_mappers(env, rest_schema, src_dir)
    _generate_async_repos_and_services(env, rest_schema, src_dir)

    _copy_base_classes(base_dir, src_dir)

    # Ensure __init__.py in all subdirectories
    _ensure_init_py_tree(src_dir)


def _ensure_init_py_tree(root_dir: str) -> None:
    """Create __init__.py in every subdirectory under root_dir.

    Includes intermediate directories (e.g. domain/, domain/models/) even if
    they only contain subdirectories and no direct .py files.
    """
    for dirpath, _dirnames, _filenames in os.walk(root_dir):
        _write_init_py(dirpath)


def _generate_database_config(schema: AsyncAPIProjectSchema, src_dir: str) -> None:
    """Generate database.py configuration (reused from REST template)."""
    infra_dir = os.path.join(src_dir, "infrastructure")
    os.makedirs(infra_dir, exist_ok=True)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    rest_db = os.path.join(base_dir, "template", "{{project_slug}}", "src", "infrastructure", "database.py.jinja")
    if os.path.exists(rest_db):
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        env = Environment(
            loader=FileSystemLoader(os.path.dirname(rest_db)),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template("database.py.jinja")
        content = template.render(project=schema.project)
        with open(os.path.join(infra_dir, "database.py"), "w") as f:
            f.write(content)
    else:
        driver = schema.project.data_driver or "postgresql"
        content = f'''"""Database configuration."""
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "dbname")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"{driver}+asyncpg://{{DB_USER}}:{{DB_PASSWORD}}@{{DB_HOST}}:{{DB_PORT}}/{{DB_NAME}}"
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)
'''
        with open(os.path.join(infra_dir, "database.py"), "w") as f:
            f.write(content)

    _write_init_py(infra_dir)


def _build_copier_data(schema: AsyncAPIProjectSchema) -> dict:
    """Build the Copier template data dict from the async schema."""
    broker_extra = "kafka" if schema.is_kafka else "rabbit"
    primary = schema.primary_server
    kafka_fallback = "localhost:9092" if schema.is_kafka else "localhost:5672"
    default_host = primary.host if primary else kafka_fallback

    server_vars = _resolve_server_variables(primary) if primary else {}
    for var_name, var_default in server_vars.items():
        default_host = default_host.replace("{" + var_name + "}", var_default)

    broker_user, broker_pass, _ = _extract_broker_credentials(server_vars)

    return {
        "project_name": schema.project.name,
        "project_slug": schema.project_slug,
        "description": schema.project.description,
        "version": schema.project.version,
        "project": {
            "version": schema.project.version,
            "description": schema.project.description,
            "data_driver": schema.project.data_driver,
        },
        "broker_extra": broker_extra,
        "is_kafka": schema.is_kafka,
        "broker_default_host": default_host,
        "broker_user_default": broker_user,
        "broker_pass_default": broker_pass,
    }


def generate_from_async_schema(
    schema: AsyncAPIProjectSchema,
    template_dir: str = None,
    existing_project_dir: str = None,
) -> str:
    """Generate a complete FastStream project from an AsyncAPIProjectSchema.

    Orchestrates the full generation pipeline:
    1. Scaffold via Copier (pyproject.toml, Dockerfile, docker-compose, .env)
    2. Broker configuration
    3. DTOs from payload schemas
    4. Handlers (receive operations)
    5. Publishers (send without reply)
    6. RPC clients (send with reply)
    7. Domain models + Infrastructure (reusing REST generators)
    8. Main application entrypoint
    9. Database configuration
    10. Custom code injection (if existing project provided)

    Args:
        schema: The validated AsyncAPI project definition.
        template_dir: Custom path to the Copier template directory.
        existing_project_dir: Path to a previous project directory.
            If provided, custom code blocks will be extracted and re-injected.

    Returns:
        Absolute path to the generated project directory.
    """
    if template_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(base_dir, "template_asyncapi")

    output_dir = schema.output_dir

    # Extract custom code blocks from existing project BEFORE destroying it
    saved_blocks = {}
    if existing_project_dir and os.path.isdir(existing_project_dir):
        saved_blocks = extract_custom_blocks(existing_project_dir)

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    copier_data = _build_copier_data(schema)

    run_copy(
        src_path=template_dir,
        dst_path=output_dir,
        data=copier_data,
        unsafe=True,
    )

    project_slug = schema.project_slug
    project_dir = os.path.join(output_dir, project_slug)
    src_dir = os.path.join(project_dir, "src")
    os.makedirs(src_dir, exist_ok=True)

    env_example = os.path.join(project_dir, ".env.example")
    env_target = os.path.join(project_dir, ".env")
    if os.path.exists(env_example) and not os.path.exists(env_target):
        shutil.copy(env_example, env_target)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    partials_dir = os.path.join(base_dir, "partials_asyncapi")
    env = _create_env(partials_dir)

    _generate_broker_config(env, schema, src_dir)
    _generate_dtos(env, schema, src_dir)
    _generate_handlers(env, schema, src_dir)
    _generate_publishers(env, schema, src_dir)
    _generate_rpc_clients(env, schema, src_dir)
    _generate_error_handler(env, schema, src_dir)
    _generate_health(env, schema, src_dir)
    _generate_main(env, schema, src_dir)

    _generate_domain_and_infra(schema, src_dir)
    _generate_database_config(schema, src_dir)

    _generate_tests(env, schema, src_dir)

    # Ensure __init__.py in all subdirectories (must run after ALL generators)
    _ensure_init_py_tree(src_dir)

    # 10. Inject saved custom code blocks into the new project
    if saved_blocks:
        merge_warnings = inject_custom_blocks(os.path.abspath(project_dir), saved_blocks)
        for w in merge_warnings:
            print(f"  ⚠️  {w}")

    # 11. Copy UserCode/ folder from existing project
    if existing_project_dir and os.path.isdir(existing_project_dir):
        copy_user_code_folder(existing_project_dir, os.path.abspath(project_dir))

    print(f"SUCCESS: AsyncAPI project generated at {project_dir}")
    return os.path.abspath(project_dir)


def generate_async_project(
    parsed_data: dict,
    output_dir: str,
    existing_project_dir: str = None,
) -> str:
    schema = AsyncAPIProjectSchema(
        **parsed_data,
        output_dir=output_dir,
    )

    return generate_from_async_schema(schema, existing_project_dir=existing_project_dir)
