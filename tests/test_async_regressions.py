"""
Tests de regresión para ASYNC-019..033.

Cada test mapea a un issue específico documentado en issues_async.md.
Previene que los bugs corregidos se repitan al modificar async_core.py,
dto.jinja o test_handler.jinja.
"""
import pytest
from apigen_copier.async_core import (
    _build_sample_fields,
    _find_schema_def,
    _extract_operation_properties,
    _sample_value_for_field,
    _SAMPLE_VALUE_BY_TYPE,
    _SAMPLE_VALUE_BY_FORMAT,
)


# ── ASYNC-024: sample fields para DTOs con campos required ──────

class TestBuildSampleFieldsBasic:

    def test_returns_empty_for_scalar_dto(self):
        assert _build_sample_fields("str", {}) == ""
        assert _build_sample_fields("int", {}) == ""
        assert _build_sample_fields("dict", {}) == ""
        assert _build_sample_fields("float", {}) == ""
        assert _build_sample_fields("bool", {}) == ""

    def test_returns_empty_for_none(self):
        assert _build_sample_fields(None, {}) == ""
        assert _build_sample_fields("", {}) == ""

    def test_simple_string_fields(self):
        schemas = {
            "MyPayload": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
            }
        }
        result = _build_sample_fields("MyPayload", schemas)
        assert 'name="test"' in result
        assert 'email="test"' in result


# ── ASYNC-025: búsqueda case-insensitive en payload_schemas ──────

class TestFindSchemaDef:

    def test_exact_match(self):
        schemas = {"MyPayload": {"type": "object"}}
        assert _find_schema_def("MyPayload", schemas) == {"type": "object"}

    def test_case_insensitive_fallback(self):
        schemas = {"lightMeasuredPayload": {"type": "object", "properties": {"lumens": {"type": "integer"}}}}
        result = _find_schema_def("LightMeasuredPayload", schemas)
        assert result == schemas["lightMeasuredPayload"]

    def test_returns_empty_when_not_found(self):
        schemas = {"other": {"type": "object"}}
        assert _find_schema_def("Missing", schemas) == {}


class TestBuildSampleFieldsCaseInsensitive:

    def test_camel_case_schema_found_via_pascal_case_dto(self):
        schemas = {
            "lightMeasuredPayload": {
                "type": "object",
                "properties": {
                    "lumens": {"type": "integer"},
                    "sentAt": {"type": "string", "format": "date-time"},
                },
            }
        }
        result = _build_sample_fields("LightMeasuredPayload", schemas)
        assert "lumens=0" in result
        assert 'sent_at="2024-01-01T00:00:00"' in result


# ── ASYNC-026: valores de ejemplo para datetime, date, email, uri, uuid ──

class TestSampleValueByFormat:

    def test_datetime_format(self):
        finfo = {"type": "string", "format": "date-time"}
        assert _sample_value_for_field(finfo) == '"2024-01-01T00:00:00"'

    def test_date_format(self):
        finfo = {"type": "string", "format": "date"}
        assert _sample_value_for_field(finfo) == '"2024-01-01"'

    def test_email_format(self):
        finfo = {"type": "string", "format": "email"}
        assert _sample_value_for_field(finfo) == '"test@test.com"'

    def test_uri_format(self):
        finfo = {"type": "string", "format": "uri"}
        assert _sample_value_for_field(finfo) == '"https://example.com"'

    def test_uuid_format(self):
        finfo = {"type": "string", "format": "uuid"}
        assert _sample_value_for_field(finfo) == '"00000000-0000-0000-0000-000000000000"'

    def test_unknown_format_falls_back_to_type(self):
        finfo = {"type": "integer", "format": "int32"}
        assert _sample_value_for_field(finfo) == "0"

    def test_format_takes_priority_over_type(self):
        finfo = {"type": "string", "format": "date-time"}
        result = _sample_value_for_field(finfo)
        assert result == '"2024-01-01T00:00:00"'
        assert result != '"test"'


# ── ASYNC-027: sample fields para type: object y type: array ──────

class TestSampleValueForObjects:

    def test_object_type_generates_dict(self):
        finfo = {"type": "object", "properties": {"id": {"type": "integer"}}}
        result = _sample_value_for_field(finfo)
        assert result == "{}"

    def test_object_camel_case_field(self):
        finfo = {"type": "object"}
        result = _sample_value_for_field(finfo)
        assert result == "{}"

    def test_object_snake_case_field(self):
        finfo = {"type": "object"}
        result = _sample_value_for_field(finfo)
        assert result == "{}"

    def test_array_type_generates_empty_list(self):
        finfo = {"type": "array", "items": {"type": "string"}}
        result = _sample_value_for_field(finfo)
        assert result == "[]"

    def test_build_sample_fields_with_nested_objects(self):
        schemas = {
            "Payload": {
                "type": "object",
                "properties": {
                    "activity": {"type": "object", "properties": {"clicks": {"type": "integer"}}},
                    "employee_id": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            }
        }
        result = _build_sample_fields("Payload", schemas)
        assert "activity={}" in result
        assert 'employee_id="test"' in result
        assert "tags=[]" in result


# ── ASYNC-028: Optional[type] = None en DTOs (test de integración) ──────

class TestDTOOptionalGeneration:

    def test_generated_dto_uses_optional_for_non_required_fields(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        import os

        template_dir = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "apigen_copier",
            "partials_asyncapi",
        )
        env = Environment(loader=FileSystemLoader(template_dir))

        from apigen_copier.async_core import _to_snake_case

        def python_type_filter(finfo):
            t = finfo.get("type", "string")
            mapping = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
            if t == "object":
                return finfo.get("_class_name", "dict")
            return mapping.get(t, "str")

        def snake_filter(name):
            return _to_snake_case(name)

        env.filters["python_type"] = python_type_filter
        env.filters["snake"] = snake_filter

        template = env.get_template("dto.jinja")
        result = template.render(
            class_name="TestPayload",
            schema_name="testPayload",
            has_literal=False,
            has_datetime=False,
            nested_classes=[],
            properties={
                "name": {"type": "string", "required": False},
                "age": {"type": "integer", "required": True},
                "score": {"type": "number", "required": False},
            },
        )

        assert "name: Optional[str] = None" in result
        assert "age: int" in result
        assert "Optional[int]" not in result or "age: Optional[int]" not in result
        assert "score: Optional[float] = None" in result


# ── ASYNC-019: payloads escalares no deben generar import inválido ──────

class TestScalarPayloadHandling:

    def test_build_sample_fields_ignores_scalars(self):
        assert _build_sample_fields("str", {}) == ""
        assert _build_sample_fields("int", {}) == ""
        assert _build_sample_fields("float", {}) == ""
        assert _build_sample_fields("bool", {}) == ""


# ── ASYNC-023: _extract_operation_properties fallback ──────

class TestExtractOperationProperties:

    def test_extracts_from_messages(self):
        class MockOp:
            messages = [
                {"payload": {"properties": {"name": {"type": "string"}}}}
            ]
        result = _extract_operation_properties(MockOp())
        assert "name" in result
        assert result["name"]["type"] == "string"

    def test_returns_empty_for_none(self):
        assert _extract_operation_properties(None) == {}

    def test_returns_empty_for_no_properties(self):
        class MockOp:
            messages = [{"payload": {}}]
        assert _extract_operation_properties(MockOp()) == {}


# ── Cobertura de _SAMPLE_VALUE_BY_TYPE ──────

class TestSampleValueByType:

    def test_all_basic_types_have_values(self):
        assert "string" in _SAMPLE_VALUE_BY_TYPE
        assert "number" in _SAMPLE_VALUE_BY_TYPE
        assert "integer" in _SAMPLE_VALUE_BY_TYPE
        assert "boolean" in _SAMPLE_VALUE_BY_TYPE

    def test_all_formats_have_values(self):
        assert "date-time" in _SAMPLE_VALUE_BY_FORMAT
        assert "date" in _SAMPLE_VALUE_BY_FORMAT
        assert "email" in _SAMPLE_VALUE_BY_FORMAT
        assert "uri" in _SAMPLE_VALUE_BY_FORMAT
        assert "uuid" in _SAMPLE_VALUE_BY_FORMAT


# ── ASYNC-030: _find_field_path returns field info for type mismatch detection ──

class TestFindFieldPathReturnsInfo:

    def test_returns_path_and_field_info(self):
        from apigen_copier.async_core import _find_field_path
        props = {"sentAt": {"type": "string", "format": "date-time"}}
        path, info = _find_field_path(props, "sent_at")
        assert path == "data.sent_at"
        assert info["format"] == "date-time"

    def test_returns_none_none_when_not_found(self):
        from apigen_copier.async_core import _find_field_path
        path, info = _find_field_path({"name": {"type": "string"}}, "missing")
        assert path is None
        assert info is None

    def test_nested_field_returns_info(self):
        from apigen_copier.async_core import _find_field_path
        props = {
            "activity": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "format": "date-time"},
                },
            },
        }
        path, info = _find_field_path(props, "time")
        assert path == "data.activity.time"
        assert info["format"] == "date-time"


# ── ASYNC-030: _build_field_mapping detects datetime→String mismatch ──

class TestBuildFieldMappingDatetimeCast:

    def test_datetime_to_string_sets_needs_str_cast(self, tmp_path):
        from apigen_copier.async_core import _build_field_mapping
        from apigen_copier.async_schemas import AsyncAPIProjectSchema

        schema = AsyncAPIProjectSchema(**{
            "project": {"name": "test", "version": "1.0.0", "data-driver": "postgresql"},
            "default_content_type": "application/json",
            "output_dir": str(tmp_path),
            "servers": {"dev": {"host": "localhost:9092", "protocol": "kafka"}},
            "channels": {},
            "operations": {
                "onEvent": {
                    "action": "receive",
                    "channel": {"address": "test.topic", "messages": {
                        "Msg": {"payload": {"$ref": "#/components/schemas/TestPayload"}}
                    }},
                    "messages": [{"payload": {"$ref": "#/components/schemas/TestPayload"}}],
                }
            },
            "components": {
                "schemas": {
                    "TestPayload": {
                        "type": "object",
                        "properties": {
                            "sentAt": {"type": "string", "format": "date-time"},
                            "name": {"type": "string"},
                        },
                    }
                }
            },
            "entities": {
                "MyModel": {
                    "table": "my_models",
                    "attributes": [
                        {"name": "id", "type": "String", "relational-persistence": {"primary-key": True}},
                        {"name": "sent_at", "type": "String"},
                        {"name": "name", "type": "String"},
                    ],
                }
            },
            "payload_schemas": {
                "TestPayload": {
                    "type": "object",
                    "properties": {
                        "sentAt": {"type": "string", "format": "date-time"},
                        "name": {"type": "string"},
                    },
                }
            },
        })

        op = list(schema.typed_operations.values())[0]
        field_map = _build_field_mapping("MyModel", schema, op)

        sent_at_entry = next(f for f in field_map if f["attr"] == "sent_at")
        name_entry = next(f for f in field_map if f["attr"] == "name")

        assert sent_at_entry["needs_str_cast"] is True
        assert name_entry["needs_str_cast"] is False


# ── x-apigen-mapping.field: property-level mapping (same as OpenAPI) ──

class TestFindFieldPathWithMapping:
    """Test that _find_field_path prioritizes x-apigen-mapping.field over name matching."""

    def test_explicit_mapping_field_matches(self):
        """Property with x-apigen-mapping.field should match the target attribute."""
        from apigen_copier.async_core import _find_field_path
        props = {
            "sentAt": {
                "type": "string",
                "format": "date-time",
                "x-apigen-mapping": {"field": "sent_at"},
            }
        }
        path, info = _find_field_path(props, "sent_at")
        assert path == "data.sent_at"
        assert info["format"] == "date-time"

    def test_explicit_mapping_different_names(self):
        """Property name completely different from model attr — only mapping bridges them."""
        from apigen_copier.async_core import _find_field_path
        props = {
            "fechaEnvio": {
                "type": "string",
                "x-apigen-mapping": {"field": "sent_at"},
            }
        }
        path, info = _find_field_path(props, "sent_at")
        assert path == "data.fecha_envio"
        assert info["type"] == "string"

    def test_mapping_takes_priority_over_name_match(self):
        """When both mapping and name match exist, mapping wins."""
        from apigen_copier.async_core import _find_field_path
        props = {
            "sent_at": {
                "type": "string",
                "description": "name-matched field",
            },
            "sentDateTime": {
                "type": "string",
                "format": "date-time",
                "x-apigen-mapping": {"field": "sent_at"},
            },
        }
        path, info = _find_field_path(props, "sent_at")
        # Should match via explicit mapping, not name
        assert path == "data.sent_date_time"
        assert info["format"] == "date-time"

    def test_fallback_to_name_matching_without_mapping(self):
        """Without x-apigen-mapping, fall back to snake_case name matching (backward compat)."""
        from apigen_copier.async_core import _find_field_path
        props = {
            "sentAt": {"type": "string", "format": "date-time"},
        }
        path, info = _find_field_path(props, "sent_at")
        assert path == "data.sent_at"
        assert info["format"] == "date-time"

    def test_nested_explicit_mapping(self):
        """x-apigen-mapping.field inside nested object should be found."""
        from apigen_copier.async_core import _find_field_path
        props = {
            "details": {
                "type": "object",
                "properties": {
                    "createdAt": {
                        "type": "string",
                        "format": "date-time",
                        "x-apigen-mapping": {"field": "creation_date"},
                    },
                },
            },
        }
        path, info = _find_field_path(props, "creation_date")
        assert path == "data.details.created_at"
        assert info["format"] == "date-time"


class TestBuildFieldMappingWithExplicitMapping:
    """Test _build_field_mapping uses x-apigen-mapping.field from properties."""

    def test_uses_mapping_field_for_different_names(self, tmp_path):
        from apigen_copier.async_core import _build_field_mapping
        from apigen_copier.async_schemas import AsyncAPIProjectSchema

        schema = AsyncAPIProjectSchema(**{
            "project": {"name": "test", "version": "1.0.0", "data-driver": "postgresql"},
            "default_content_type": "application/json",
            "output_dir": str(tmp_path),
            "servers": {"dev": {"host": "localhost:9092", "protocol": "kafka"}},
            "channels": {},
            "operations": {
                "onEvent": {
                    "action": "receive",
                    "channel": {"address": "test.topic", "messages": {
                        "Msg": {"payload": {"$ref": "#/components/schemas/TestPayload"}}
                    }},
                    "messages": [{"payload": {"$ref": "#/components/schemas/TestPayload"}}],
                }
            },
            "components": {
                "schemas": {
                    "TestPayload": {
                        "type": "object",
                        "properties": {
                            "fechaEnvio": {
                                "type": "string",
                                "format": "date-time",
                                "x-apigen-mapping": {"field": "sent_at"},
                            },
                            "nombre": {
                                "type": "string",
                                "x-apigen-mapping": {"field": "name"},
                            },
                        },
                    }
                }
            },
            "entities": {
                "MyModel": {
                    "table": "my_models",
                    "attributes": [
                        {"name": "id", "type": "String", "relational-persistence": {"primary-key": True}},
                        {"name": "sent_at", "type": "String"},
                        {"name": "name", "type": "String"},
                    ],
                }
            },
            "payload_schemas": {
                "TestPayload": {
                    "type": "object",
                    "properties": {
                        "fechaEnvio": {
                            "type": "string",
                            "format": "date-time",
                            "x-apigen-mapping": {"field": "sent_at"},
                        },
                        "nombre": {
                            "type": "string",
                            "x-apigen-mapping": {"field": "name"},
                        },
                    },
                }
            },
        })

        op = list(schema.typed_operations.values())[0]
        field_map = _build_field_mapping("MyModel", schema, op)

        sent_at_entry = next(f for f in field_map if f["attr"] == "sent_at")
        name_entry = next(f for f in field_map if f["attr"] == "name")

        assert sent_at_entry["path"] == "data.fecha_envio"
        assert name_entry["path"] == "data.nombre"


# ── ASYNC-031: entity template generates UUID default for String PK ──

class TestEntityStringPKUUID:

    def test_string_pk_gets_uuid_default(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        import os

        template_dir = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "apigen_copier",
            "partials",
        )
        env = Environment(loader=FileSystemLoader(template_dir))

        from apigen_copier.type_mapper import to_sa_column
        env.filters["sa_column_type"] = to_sa_column
        env.filters["snake"] = lambda s: s

        template = env.get_template("infra_entity.jinja")

        class MockPersistence:
            primary_key = True
            autogenerated = True
            column = None
            join_table = None
            join_column = None
            inverse_join_column = None
            foreign_column = None

        class MockAttr:
            name = "id"
            type = "String"
            is_array = False
            items_ref_model = None
            ref_model = None
            has_json_conversion = False
            persistence = MockPersistence()

        result = template.render(
            entity_name="Test",
            table_name="tests",
            attributes=[MockAttr()],
            data_driver="postgresql",
            all_entities={},
            entity_pk_type="String",
            related_pk_types={},
        )

        assert "primary_key=True" in result
        assert "default=lambda: str(__import__('uuid').uuid4())" in result
        assert "UUID" not in result  # uses String, not UUID(as_uuid=False)

    def test_integer_pk_no_uuid_default(self, tmp_path):
        from jinja2 import Environment, FileSystemLoader
        import os

        template_dir = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "apigen_copier",
            "partials",
        )
        env = Environment(loader=FileSystemLoader(template_dir))

        from apigen_copier.type_mapper import to_sa_column
        env.filters["sa_column_type"] = to_sa_column
        env.filters["snake"] = lambda s: s

        template = env.get_template("infra_entity.jinja")

        class MockPersistence:
            primary_key = True
            autogenerated = True
            column = None
            join_table = None
            join_column = None
            inverse_join_column = None
            foreign_column = None

        class MockAttr:
            name = "id"
            type = "Integer"
            is_array = False
            items_ref_model = None
            ref_model = None
            has_json_conversion = False
            persistence = MockPersistence()

        result = template.render(
            entity_name="Test",
            table_name="tests",
            attributes=[MockAttr()],
            data_driver="postgresql",
            all_entities={},
            entity_pk_type="Integer",
            related_pk_types={},
        )

        assert "autoincrement=True" in result
        assert "uuid" not in result
