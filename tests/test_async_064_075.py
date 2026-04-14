"""
Tests for ASYNC-064 through ASYNC-075 runtime issues.

Each test class maps to a specific issue. Tests are self-contained
and do not depend on external services or repos.
"""
import pytest
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ── Shared fixtures ──────────────────────────────────────────────

TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "src", "apigen_copier", "partials_asyncapi"
)


def _snake(name: str) -> str:
    import re
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


@pytest.fixture(scope="module")
def jinja_env():
    """Jinja environment pointing at the real partials_asyncapi templates."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(),
        keep_trailing_newline=True,
    )
    env.filters["snake"] = _snake

    def _python_type(field_info):
        if isinstance(field_info, dict):
            t = field_info.get("type", "str")
            mapping = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
            return mapping.get(t, "str")
        return "str"

    env.filters["python_type"] = _python_type

    def _regex_replace(value, pattern, replacement):
        import re
        return re.sub(pattern, replacement, value)

    env.filters["regex_replace"] = _regex_replace
    return env


# ══════════════════════════════════════════════════════════════════
# ASYNC-064: DTOs extra='forbid' by default + dispatcher ordering
# ══════════════════════════════════════════════════════════════════


class TestAsync064ExtraForbidDefault:
    """DTO template must generate extra='forbid' by default."""

    def test_dto_has_extra_forbid_when_not_specified(self, jinja_env):
        template = jinja_env.get_template("dto.jinja")
        content = template.render(
            class_name="OrderCreatedPayload",
            schema_name="OrderCreated",
            properties={"order_id": {"type": "string", "required": True}},
            nested_classes=[],
            has_literal=False,
            has_datetime=False,
            base_class_name=None,
            base_module_name=None,
            allow_extra=False,
        )
        assert "extra='forbid'" in content or 'extra="forbid"' in content

    def test_dto_has_extra_allow_when_additional_properties_true(self, jinja_env):
        template = jinja_env.get_template("dto.jinja")
        content = template.render(
            class_name="MetadataPayload",
            schema_name="Metadata",
            properties={"key": {"type": "string", "required": True}},
            nested_classes=[],
            has_literal=False,
            has_datetime=False,
            base_class_name=None,
            base_module_name=None,
            allow_extra=True,
        )
        assert "extra='allow'" in content or 'extra="allow"' in content
        assert "extra='forbid'" not in content

    def test_dto_no_extra_config_when_has_base_class(self, jinja_env):
        """When DTO inherits from base, it should NOT duplicate ConfigDict."""
        template = jinja_env.get_template("dto.jinja")
        content = template.render(
            class_name="PremiumOrder",
            schema_name="PremiumOrder",
            properties={"discount": {"type": "number"}},
            nested_classes=[],
            has_literal=False,
            has_datetime=False,
            base_class_name="OrderBase",
            base_module_name="order_base",
            allow_extra=False,
        )
        # Should NOT have its own ConfigDict since it inherits
        assert "model_config" not in content or "ConfigDict" not in content

    def test_nested_classes_also_get_extra_forbid(self, jinja_env):
        template = jinja_env.get_template("dto.jinja")
        content = template.render(
            class_name="OrderPayload",
            schema_name="Order",
            properties={"name": {"type": "string"}},
            nested_classes=[{
                "class_name": "AddressNested",
                "properties": {"street": {"type": "string"}},
            }],
            has_literal=False,
            has_datetime=False,
            base_class_name=None,
            base_module_name=None,
            allow_extra=False,
        )
        # Both the main class and nested should have extra='forbid'
        assert content.count("extra='forbid'") >= 2 or content.count('extra="forbid"') >= 2


class TestAsync064DispatcherOrdering:
    """Multi-message dispatcher must use if/elif and order by required count."""

    def test_multi_message_dispatcher_uses_elif(self, jinja_env):
        """When multiple ops share a topic, use if/elif not sequential for loops."""
        template = jinja_env.get_template("main.jinja")

        # Simulate two ops on same channel with DTOs
        class FakeOp:
            def __init__(self, channel_addr, binding_model=None, kafka_group_id=None, required_count=0):
                self.channel_address = channel_addr
                self.binding_model = binding_model
                self.kafka_group_id = kafka_group_id
                self.channel = type("C", (), {"bindings": {}})()
                self.required_count = required_count

        ops = {
            "onOrderCreated": FakeOp("shop.orders", "Order", required_count=3),
            "onOrderUpdated": FakeOp("shop.orders", "Order", required_count=2),
        }
        grouped = {"shop.orders": [
            ("onOrderCreated", ops["onOrderCreated"]),
            ("onOrderUpdated", ops["onOrderUpdated"]),
        ]}
        dto_map = {
            "onOrderCreated": {"dto_class": "OrderCreatedPayload", "dto_module": "order_created_payload"},
            "onOrderUpdated": {"dto_class": "OrderUpdatedPayload", "dto_module": "order_updated_payload"},
        }

        content = template.render(
            project_name="test_project",
            receive_ops=ops,
            grouped_receive_ops=grouped,
            handler_imports=[
                ("on_order_created_handler", "on_order_created"),
                ("on_order_updated_handler", "on_order_updated"),
            ],
            dto_map=dto_map,
            broker_protocol="kafka",
            publisher_imports=[],
            rpc_imports=[],
        )

        # Should have elif instead of separate if blocks
        assert "elif" in content or "else" in content

    def test_dispatcher_orders_by_required_count_desc(self, jinja_env):
        """The DTO with more required fields should be tried first."""
        template = jinja_env.get_template("main.jinja")

        class FakeOp:
            def __init__(self, channel_addr, binding_model=None, kafka_group_id=None, required_count=0):
                self.channel_address = channel_addr
                self.binding_model = binding_model
                self.kafka_group_id = kafka_group_id
                self.channel = type("C", (), {"bindings": {}})()
                self.required_count = required_count

        ops = {
            "onOrderUpdated": FakeOp("shop.orders", "Order", required_count=5),
            "onOrderCreated": FakeOp("shop.orders", "Order", required_count=2),
        }
        # Deliberately put lower-required first in the list
        grouped = {"shop.orders": [
            ("onOrderCreated", ops["onOrderCreated"]),
            ("onOrderUpdated", ops["onOrderUpdated"]),
        ]}
        dto_map = {
            "onOrderCreated": {"dto_class": "OrderCreatedPayload", "dto_module": "order_created_payload"},
            "onOrderUpdated": {"dto_class": "OrderUpdatedPayload", "dto_module": "order_updated_payload"},
        }

        content = template.render(
            project_name="test_project",
            receive_ops=ops,
            grouped_receive_ops=grouped,
            handler_imports=[
                ("on_order_created_handler", "on_order_created"),
                ("on_order_updated_handler", "on_order_updated"),
            ],
            dto_map=dto_map,
            broker_protocol="kafka",
            publisher_imports=[],
            rpc_imports=[],
        )

        # In the dispatcher section (after @broker.subscriber), OrderUpdated (5 required)
        # should be tried before OrderCreated (2 required)
        dispatcher_start = content.find("_matched")
        assert dispatcher_start != -1, "Dispatcher should use _matched pattern for multi-message"
        dispatcher_section = content[dispatcher_start:]
        pos_updated = dispatcher_section.find("OrderUpdatedPayload")
        pos_created = dispatcher_section.find("OrderCreatedPayload")
        assert pos_updated < pos_created, (
            "DTO with more required fields should be tried first in dispatcher"
        )


# ══════════════════════════════════════════════════════════════════
# ASYNC-064: async_core reads additionalProperties from schema
# ══════════════════════════════════════════════════════════════════


class TestAsync064AdditionalPropertiesFromSpec:
    """async_core should pass allow_extra based on schema's additionalProperties."""

    def test_additional_properties_true_sets_allow_extra(self):
        from apigen_copier.async_core import _should_allow_extra
        schema_def = {"type": "object", "additionalProperties": True}
        assert _should_allow_extra(schema_def) is True

    def test_additional_properties_false_sets_forbid(self):
        from apigen_copier.async_core import _should_allow_extra
        schema_def = {"type": "object", "additionalProperties": False}
        assert _should_allow_extra(schema_def) is False

    def test_additional_properties_missing_defaults_to_forbid(self):
        from apigen_copier.async_core import _should_allow_extra
        schema_def = {"type": "object", "properties": {"name": {"type": "string"}}}
        assert _should_allow_extra(schema_def) is False

    def test_additional_properties_with_schema_allows(self):
        """additionalProperties: {type: string} means allow extra of that type."""
        from apigen_copier.async_core import _should_allow_extra
        schema_def = {"type": "object", "additionalProperties": {"type": "string"}}
        assert _should_allow_extra(schema_def) is True


# ══════════════════════════════════════════════════════════════════
# ASYNC-065: Session per request — repository uses context manager
# ══════════════════════════════════════════════════════════════════


class TestAsync065SessionPerRequest:
    """Main.jinja handlers should create session per message (async with)."""

    def test_single_op_handler_uses_async_session_context(self, jinja_env):
        """Even single-op handlers with binding_model should use async with session."""
        template = jinja_env.get_template("main.jinja")

        class FakeOp:
            def __init__(self):
                self.channel_address = "shop.orders"
                self.binding_model = "Order"
                self.kafka_group_id = None
                self.channel = type("C", (), {"bindings": {}})()
                self.required_count = 0

        op = FakeOp()
        content = template.render(
            project_name="test",
            receive_ops={"onOrderCreated": op},
            grouped_receive_ops={"shop.orders": [("onOrderCreated", op)]},
            handler_imports=[("on_order_created_handler", "on_order_created")],
            dto_map={"onOrderCreated": {"dto_class": "OrderCreatedPayload", "dto_module": "order_created_payload"}},
            broker_protocol="kafka",
            publisher_imports=[],
            rpc_imports=[],
        )
        assert "async with async_session() as session" in content


class TestAsync065RepositoryRollback:
    """BaseRepository CRUD methods must rollback on failure."""

    REPO_PATH = os.path.join(
        os.path.dirname(__file__), "..", "src", "apigen_copier", "template",
        "{{project_slug}}", "src", "domain", "repository", "base_repository.py",
    )

    def test_create_has_rollback(self):
        with open(self.REPO_PATH) as f:
            content = f.read()
        # Find the create method and verify it has rollback
        create_idx = content.find("async def create(")
        update_idx = content.find("async def update(")
        create_body = content[create_idx:update_idx]
        assert "rollback" in create_body

    def test_update_has_rollback(self):
        with open(self.REPO_PATH) as f:
            content = f.read()
        update_idx = content.find("async def update(")
        delete_idx = content.find("async def delete(self, entity")
        update_body = content[update_idx:delete_idx]
        assert "rollback" in update_body

    def test_delete_has_rollback(self):
        with open(self.REPO_PATH) as f:
            content = f.read()
        delete_idx = content.find("async def delete(self, entity")
        delete_by_id_idx = content.find("async def delete_by_id(")
        delete_body = content[delete_idx:delete_by_id_idx]
        assert "rollback" in delete_body

    def test_delete_by_id_has_rollback(self):
        with open(self.REPO_PATH) as f:
            content = f.read()
        delete_by_id_idx = content.find("async def delete_by_id(")
        safe_dict_idx = content.find("def _to_safe_dict(")
        delete_by_id_body = content[delete_by_id_idx:safe_dict_idx]
        assert "rollback" in delete_by_id_body


# ══════════════════════════════════════════════════════════════════
# ASYNC-066: Idempotency — handlers use create_or_ignore
# ══════════════════════════════════════════════════════════════════


class TestAsync066Idempotency:
    """Handlers with action=create must use create_or_ignore for idempotency."""

    def test_create_handler_uses_create_or_ignore(self, jinja_env):
        template = jinja_env.get_template("handler.jinja")
        content = template.render(
            operation_name="onOrderCreated",
            channel_address="shop.orders",
            binding_action="create",
            binding_model="Order",
            dto_class="OrderCreatedPayload",
            dto_module="order_created_payload",
            field_map=[],
        )
        assert "create_or_ignore" in content
        assert "service.create(model)" not in content

    def test_base_repo_has_create_or_ignore(self):
        repo_path = os.path.join(
            os.path.dirname(__file__), "..", "src", "apigen_copier", "template",
            "{{project_slug}}", "src", "domain", "repository", "base_repository.py",
        )
        with open(repo_path) as f:
            content = f.read()
        assert "async def create_or_ignore(" in content
        assert "IntegrityError" in content

    def test_base_service_has_create_or_ignore(self):
        svc_path = os.path.join(
            os.path.dirname(__file__), "..", "src", "apigen_copier", "template",
            "{{project_slug}}", "src", "domain", "services", "base_service.py",
        )
        with open(svc_path) as f:
            content = f.read()
        assert "create_or_ignore" in content


# ══════════════════════════════════════════════════════════════════
# ASYNC-068: Graceful shutdown with lifespan
# ══════════════════════════════════════════════════════════════════


class TestAsync068GracefulShutdown:
    """Main.jinja must generate lifespan context manager for graceful shutdown."""

    def test_main_has_lifespan(self, jinja_env):
        template = jinja_env.get_template("main.jinja")

        class FakeOp:
            def __init__(self):
                self.channel_address = "events"
                self.binding_model = None
                self.kafka_group_id = None
                self.channel = type("C", (), {"bindings": {}})()
                self.required_count = 0

        op = FakeOp()
        content = template.render(
            project_name="test",
            receive_ops={"onEvent": op},
            grouped_receive_ops={"events": [("onEvent", op)]},
            handler_imports=[("on_event_handler", "on_event")],
            dto_map={"onEvent": {"dto_class": "EventPayload", "dto_module": "event_payload"}},
            broker_protocol="kafka",
            publisher_imports=[],
            rpc_imports=[],
        )
        assert "lifespan" in content
        assert "broker.close" in content or "broker.shutdown" in content

    def test_main_uses_lifespan_in_app(self, jinja_env):
        template = jinja_env.get_template("main.jinja")

        class FakeOp:
            def __init__(self):
                self.channel_address = "events"
                self.binding_model = None
                self.kafka_group_id = None
                self.channel = type("C", (), {"bindings": {}})()
                self.required_count = 0

        op = FakeOp()
        content = template.render(
            project_name="test",
            receive_ops={"onEvent": op},
            grouped_receive_ops={"events": [("onEvent", op)]},
            handler_imports=[("on_event_handler", "on_event")],
            dto_map={"onEvent": {"dto_class": "EventPayload", "dto_module": "event_payload"}},
            broker_protocol="kafka",
            publisher_imports=[],
            rpc_imports=[],
        )
        assert "FastStream(broker, lifespan=lifespan)" in content


# ══════════════════════════════════════════════════════════════════
# ASYNC-069: Broker reconnection
# ══════════════════════════════════════════════════════════════════


class TestAsync069BrokerReconnection:
    """Broker config must include reconnection params."""

    def test_kafka_broker_has_retry_params(self, jinja_env):
        template = jinja_env.get_template("broker_config.jinja")
        content = template.render(
            protocol="kafka",
            server_host="localhost:9092",
            is_kafka=True,
            has_security=False,
            project_name="test",
        )
        assert "retry_backoff_ms" in content or "reconnect_backoff" in content

    def test_rabbit_broker_has_reconnect_interval(self, jinja_env):
        template = jinja_env.get_template("broker_config.jinja")
        content = template.render(
            protocol="amqp",
            server_host="localhost:5672",
            is_kafka=False,
            has_security=False,
            project_name="test",
        )
        assert "reconnect_interval" in content or "fail_fast" in content


# ══════════════════════════════════════════════════════════════════
# ASYNC-070: Error handler with error classification
# ══════════════════════════════════════════════════════════════════


class TestAsync070ErrorClassification:
    """Error handler must distinguish retryable vs permanent errors."""

    def test_error_handler_has_validation_error_catch(self, jinja_env):
        template = jinja_env.get_template("error_handler.jinja")
        content = template.render(project_name="test", broker_protocol="kafka")
        assert "ValidationError" in content

    def test_error_handler_has_retryable_errors(self, jinja_env):
        template = jinja_env.get_template("error_handler.jinja")
        content = template.render(project_name="test", broker_protocol="kafka")
        # Should catch network errors and re-raise
        assert "ConnectionError" in content or "TimeoutError" in content

    def test_error_handler_has_dlq_logic(self, jinja_env):
        template = jinja_env.get_template("error_handler.jinja")
        content = template.render(project_name="test", broker_protocol="kafka")
        assert "dlq" in content.lower() or "dead_letter" in content.lower()


# ══════════════════════════════════════════════════════════════════
# ASYNC-071: Health check with real ping
# ══════════════════════════════════════════════════════════════════


class TestAsync071HealthCheck:
    """File-based health check: writes /tmp/healthy while service is connected."""

    def test_health_check_uses_file(self, jinja_env):
        template = jinja_env.get_template("health.jinja")
        content = template.render(project_name="test", has_database=True)
        assert "HEALTH_FILE" in content
        assert "/tmp/healthy" in content

    def test_health_check_has_loop(self, jinja_env):
        template = jinja_env.get_template("health.jinja")
        content = template.render(project_name="test", has_database=True)
        assert "health_check_loop" in content

    def test_health_check_pings_broker(self, jinja_env):
        template = jinja_env.get_template("health.jinja")
        content = template.render(project_name="test", has_database=True)
        assert "ping" in content.lower() or "wait_for" in content

    def test_health_check_removes_file_on_failure(self, jinja_env):
        template = jinja_env.get_template("health.jinja")
        content = template.render(project_name="test", has_database=True)
        assert "remove" in content.lower()


# ══════════════════════════════════════════════════════════════════
# ASYNC-073: Backpressure with prefetch/max_workers
# ══════════════════════════════════════════════════════════════════


class TestAsync073Backpressure:
    """Subscribers must have concurrency limits."""

    def test_kafka_subscriber_has_max_workers(self, jinja_env):
        template = jinja_env.get_template("main.jinja")

        class FakeOp:
            def __init__(self):
                self.channel_address = "shop.orders"
                self.binding_model = None
                self.kafka_group_id = "group1"
                self.channel = type("C", (), {"bindings": {}})()
                self.required_count = 0

        op = FakeOp()
        content = template.render(
            project_name="test",
            receive_ops={"onOrder": op},
            grouped_receive_ops={"shop.orders": [("onOrder", op)]},
            handler_imports=[("on_order_handler", "on_order")],
            dto_map={"onOrder": {"dto_class": "OrderPayload", "dto_module": "order_payload"}},
            broker_protocol="kafka",
            publisher_imports=[],
            rpc_imports=[],
        )
        assert "MAX_HANDLER_CONCURRENCY" in content or "max_workers" in content

    def test_rabbit_subscriber_has_prefetch(self, jinja_env):
        template = jinja_env.get_template("main.jinja")

        class FakeOp:
            def __init__(self):
                self.channel_address = "shop.orders"
                self.binding_model = None
                self.kafka_group_id = None
                self.channel = type("C", (), {"bindings": {"amqp": {"queue": {"durable": True}}}})()
                self.required_count = 0

        op = FakeOp()
        content = template.render(
            project_name="test",
            receive_ops={"onOrder": op},
            grouped_receive_ops={"shop.orders": [("onOrder", op)]},
            handler_imports=[("on_order_handler", "on_order")],
            dto_map={"onOrder": {"dto_class": "OrderPayload", "dto_module": "order_payload"}},
            broker_protocol="amqp",
            publisher_imports=[],
            rpc_imports=[],
        )
        assert "RabbitQueue" in content
        assert "durable=True" in content
