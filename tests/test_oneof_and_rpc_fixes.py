"""
Tests for BUG #1 and BUG #2 fixes in async_core.py.

BUG #1: _extract_oneof_variants must detect variants even after _resolve_deep
         strips $ref keys (uses _original_ref instead).
BUG #2: _resolve_reply_dto must resolve the DTO name from _original_ref metadata
         to match the DTO file generated from components.schemas.
"""
import pytest
from apigen_copier.async_core import _extract_oneof_variants, _resolve_reply_dto, _to_snake_case
from apigen_copier.async_schemas import OperationSchema, ChannelSchema


# ═══════════════════════════════════════════════════════════════
# BUG #1 — _extract_oneof_variants
# ═══════════════════════════════════════════════════════════════


class TestExtractOneofVariantsPreResolution:
    """Tests for oneOf when $ref is still present (unresolved)."""

    def test_detects_variants_from_ref(self):
        schema = {
            "oneOf": [
                {"$ref": "#/components/schemas/StatusChangePayload"},
                {"$ref": "#/components/schemas/AmountChangePayload"},
            ],
            "discriminator": "updateType",
        }
        variants, discriminator = _extract_oneof_variants(schema)

        assert len(variants) == 2
        assert variants[0]["class_name"] == "StatusChangePayload"
        assert variants[0]["module"] == "status_change_payload"
        assert variants[1]["class_name"] == "AmountChangePayload"
        assert variants[1]["module"] == "amount_change_payload"
        assert discriminator == "update_type"

    def test_empty_oneof_returns_none(self):
        variants, discriminator = _extract_oneof_variants({"oneOf": []})
        assert variants == []
        assert discriminator is None

    def test_no_oneof_returns_none(self):
        variants, discriminator = _extract_oneof_variants({"type": "object"})
        assert variants == []
        assert discriminator is None


class TestExtractOneofVariantsPostResolution:
    """Tests for oneOf when $ref has been resolved (uses _original_ref)."""

    def test_detects_variants_from_original_ref(self):
        """After _resolve_deep, options have _original_ref instead of $ref."""
        schema = {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "orderId": {"type": "string"},
                        "updateType": {"type": "string", "enum": ["STATUS_CHANGE"]},
                        "newStatus": {"type": "string"},
                    },
                    "_original_ref": "#/components/schemas/StatusChangePayload",
                },
                {
                    "type": "object",
                    "properties": {
                        "orderId": {"type": "string"},
                        "updateType": {"type": "string", "enum": ["AMOUNT_CHANGE"]},
                        "newAmount": {"type": "number"},
                    },
                    "_original_ref": "#/components/schemas/AmountChangePayload",
                },
            ],
            "discriminator": {"propertyName": "updateType"},
        }
        variants, discriminator = _extract_oneof_variants(schema)

        assert len(variants) == 2
        assert variants[0]["class_name"] == "StatusChangePayload"
        assert variants[0]["module"] == "status_change_payload"
        assert variants[1]["class_name"] == "AmountChangePayload"
        assert variants[1]["module"] == "amount_change_payload"
        assert discriminator == "update_type"

    def test_mixed_ref_and_original_ref(self):
        """Schema with one unresolved $ref and one resolved _original_ref."""
        schema = {
            "oneOf": [
                {"$ref": "#/components/schemas/First"},
                {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "_original_ref": "#/components/schemas/Second",
                },
            ],
        }
        variants, _ = _extract_oneof_variants(schema)

        assert len(variants) == 2
        assert variants[0]["class_name"] == "First"
        assert variants[1]["class_name"] == "Second"

    def test_inline_variants_without_original_ref_skipped(self):
        """Inline objects without _original_ref should not be detected as variants."""
        schema = {
            "oneOf": [
                {"type": "object", "properties": {"a": {"type": "string"}}},
                {"type": "object", "properties": {"b": {"type": "string"}}},
            ],
        }
        variants, _ = _extract_oneof_variants(schema)
        assert variants == []


# ═══════════════════════════════════════════════════════════════
# BUG #2 — _resolve_reply_dto
# ═══════════════════════════════════════════════════════════════


class TestResolveReplyDto:
    """Tests for RPC reply DTO resolution."""

    def test_resolves_from_ref(self):
        """When payload has $ref, should extract schema name."""
        op = OperationSchema(
            action="send",
            channel=ChannelSchema(address="request.topic"),
            reply={
                "channel": {
                    "address": "reply.topic",
                    "messages": {
                        "PriceRes": {
                            "payload": {"$ref": "#/components/schemas/PriceCheckResponse"}
                        }
                    },
                }
            },
        )
        dto_class, dto_module = _resolve_reply_dto(op)

        assert dto_class == "PriceCheckResponse"
        assert dto_module == "price_check_response"

    def test_resolves_from_original_ref(self):
        """When payload $ref was resolved, should use _original_ref."""
        op = OperationSchema(
            action="send",
            channel=ChannelSchema(address="request.topic"),
            reply={
                "channel": {
                    "address": "reply.topic",
                    "messages": {
                        "PriceRes": {
                            "payload": {
                                "type": "object",
                                "properties": {
                                    "price": {"type": "number"},
                                    "available": {"type": "boolean"},
                                },
                                "_original_ref": "#/components/schemas/PriceCheckResponse",
                            }
                        }
                    },
                }
            },
        )
        dto_class, dto_module = _resolve_reply_dto(op)

        assert dto_class == "PriceCheckResponse"
        assert dto_module == "price_check_response"

    def test_inline_reply_payload(self):
        """When reply payload is inline (no $ref), use message name."""
        op = OperationSchema(
            action="send",
            channel=ChannelSchema(address="request.topic"),
            reply={
                "channel": {
                    "address": "reply.topic",
                    "messages": {
                        "InlineResponse": {
                            "payload": {
                                "type": "object",
                                "properties": {"result": {"type": "string"}},
                            }
                        }
                    },
                }
            },
        )
        dto_class, dto_module = _resolve_reply_dto(op)

        assert dto_class == "InlineResponse"
        assert dto_module == "inline_response"

    def test_no_reply_returns_none(self):
        """Operations without reply should return (None, None)."""
        op = OperationSchema(
            action="send",
            channel=ChannelSchema(address="request.topic"),
        )
        dto_class, dto_module = _resolve_reply_dto(op)

        assert dto_class is None
        assert dto_module is None

    def test_empty_messages_returns_none(self):
        """Reply channel with no messages should return (None, None)."""
        op = OperationSchema(
            action="send",
            channel=ChannelSchema(address="request.topic"),
            reply={"channel": {"address": "reply.topic", "messages": {}}},
        )
        dto_class, dto_module = _resolve_reply_dto(op)

        assert dto_class is None
        assert dto_module is None


# ═══════════════════════════════════════════════════════════════
# BUG #3 — _generate_inline_dtos for RPC
# ═══════════════════════════════════════════════════════════════

from apigen_copier.async_core import _generate_inline_dtos
from apigen_copier.async_schemas import AsyncAPIProjectSchema
from unittest.mock import MagicMock, patch

class TestGenerateInlineDtosRPC:
    """Tests for generating inline DTOs from RPC replies."""

    @patch("apigen_copier.async_core._render_inline_dto")
    def test_generates_inline_dto_for_reply(self, mock_render):
        mock_render.return_value = "inline_response"
        
        op = OperationSchema(
            action="send",
            channel=ChannelSchema(address="request.topic"),
            reply={
                "channel": {
                    "address": "reply.topic",
                    "messages": {
                        "InlineResponse": {
                            "payload": {
                                "type": "object",
                                "properties": {"result": {"type": "string"}},
                            }
                        }
                    },
                }
            },
        )
        schema = AsyncAPIProjectSchema(
            project={"name": "test", "version": "1.0"},
            output_dir="/tmp/dtos",
            project_name="test",
            description="test",
            version="1.0.0",
            data_driver="postgresql",
            servers={"dev": {"host": "localhost", "protocol": "kafka"}},
            channels={},
            operations={"op1": op},
            components={"schemas": {}},
            models=[]
        )
        
        env = MagicMock()
        _generate_inline_dtos(env, schema, "/tmp/dtos")
        
        # Should call _render_inline_dto with suffix=""
        mock_render.assert_called_once()
        assert mock_render.call_args.kwargs.get("suffix") == ""

    @patch("apigen_copier.async_core._render_inline_dto")
    def test_skips_reply_with_ref(self, mock_render):
        op = OperationSchema(
            action="send",
            channel=ChannelSchema(address="request.topic"),
            reply={
                "channel": {
                    "address": "reply.topic",
                    "messages": {
                        "PriceRes": {
                            "payload": {"$ref": "#/components/schemas/PriceCheckResponse"}
                        }
                    },
                }
            },
        )
        schema = AsyncAPIProjectSchema(
            project={"name": "test", "version": "1.0"},
            output_dir="/tmp/dtos",
            project_name="test",
            description="test",
            version="1.0.0",
            data_driver="postgresql",
            servers={"dev": {"host": "localhost", "protocol": "kafka"}},
            channels={},
            operations={"op1": op},
            components={"schemas": {}},
            models=[]
        )
        
        env = MagicMock()
        _generate_inline_dtos(env, schema, "/tmp/dtos")
        
        # Should not call _render_inline_dto since there is a $ref
        mock_render.assert_not_called()
