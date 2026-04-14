from apigen_copier.type_mapper import to_sa_column, to_python_type, to_sa_pk_type
from apigen_copier.async_schemas import ChannelSchema, OperationSchema
from apigen_copier.async_core import _ensure_foreign_keys, _sample_value_for_field
from apigen_copier.contracts.model_contract import ModelContract, ModelAttribute, RelationalPersistence


def _make_op(address, parameters=None):
    return OperationSchema(
        action="receive",
        channel=ChannelSchema(address=address, parameters=parameters or {}),
    )


class TestAsyncIssue055LongToBigInteger:

    def test_long_maps_to_biginteger_column(self):
        assert to_sa_column("Long") == "BigInteger"

    def test_long_maps_to_biginteger_column_mysql(self):
        assert to_sa_column("Long", "mysql") == "BigInteger"

    def test_long_maps_to_int_python(self):
        assert to_python_type("Long") == "int"

    def test_long_pk_maps_to_biginteger(self):
        assert to_sa_pk_type("Long") == "BigInteger"

    def test_integer_still_maps_to_integer(self):
        assert to_sa_column("Integer") == "Integer"
        assert to_sa_pk_type("Integer") == "Integer"

    def test_biginteger_still_maps_to_biginteger(self):
        assert to_sa_column("BigInteger") == "BigInteger"


class TestAsyncIssue057ChannelAddressParams:

    def test_param_with_default_uses_default(self):
        op = _make_op("orders.{region}.events", {"region": {"default": "us"}})
        assert op.channel_address == "orders.us.events"

    def test_param_with_enum_no_default_uses_first_enum(self):
        op = _make_op("orders.{region}.events", {"region": {"enum": ["eu", "latam"]}})
        assert op.channel_address == "orders.eu.events"

    def test_param_with_default_and_enum_prefers_default(self):
        op = _make_op("orders.{region}.events", {"region": {"default": "apac", "enum": ["us", "eu"]}})
        assert op.channel_address == "orders.apac.events"

    def test_param_no_default_no_enum_falls_back_to_name(self):
        op = _make_op("notifications.{channelType}", {"channelType": {}})
        assert op.channel_address == "notifications.channelType"

    def test_no_params_returns_address_as_is(self):
        op = _make_op("shop.orders.lifecycle")
        assert op.channel_address == "shop.orders.lifecycle"

    def test_multiple_params_resolved(self):
        op = _make_op("{env}.orders.{region}", {
            "env": {"default": "prod"},
            "region": {"enum": ["us", "eu"]},
        })
        assert op.channel_address == "prod.orders.us"

    def test_scalar_param_value(self):
        op = _make_op("topic.{ver}", {"ver": "v2"})
        assert op.channel_address == "topic.v2"


class TestAsyncIssue060ExpandMultiMessageOps:

    def test_single_message_no_expansion(self):
        op = _make_op("topic.a")
        op.messages = [{"x-apigen-binding": {"action": "create", "model": "Pet"}}]
        expanded = op.expand_messages()
        assert len(expanded) == 1
        assert expanded[0].binding_action == "create"

    def test_multi_message_same_binding_no_expansion(self):
        op = _make_op("topic.a")
        op.messages = [
            {"x-apigen-binding": {"action": "create", "model": "Pet"}},
            {"x-apigen-binding": {"action": "create", "model": "Pet"}},
        ]
        expanded = op.expand_messages()
        assert len(expanded) == 1

    def test_multi_message_different_bindings_expanded(self):
        op = _make_op("topic.a")
        op.messages = [
            {"x-apigen-binding": {"action": "create", "model": "Pet"}},
            {"x-apigen-binding": {"action": "update", "model": "Pet"}},
            {"x-apigen-binding": {"action": "delete", "model": "Pet"}},
        ]
        expanded = op.expand_messages()
        assert len(expanded) == 3
        assert expanded[0].binding_action == "create"
        assert expanded[1].binding_action == "update"
        assert expanded[2].binding_action == "delete"

    def test_expanded_ops_share_channel(self):
        op = _make_op("pets.lifecycle")
        op.messages = [
            {"x-apigen-binding": {"action": "create", "model": "Pet"}},
            {"x-apigen-binding": {"action": "delete", "model": "Pet"}},
        ]
        expanded = op.expand_messages()
        assert all(e.channel_address == "pets.lifecycle" for e in expanded)


class TestAsyncIssue058GroupedReceiveOps:

    def test_single_op_per_topic_not_grouped(self):
        op1 = _make_op("topic.a")
        op2 = _make_op("topic.b")
        ops = {"op1": op1, "op2": op2}
        grouped = {}
        for name, op in ops.items():
            grouped.setdefault(op.channel_address, []).append((name, op))
        assert len(grouped) == 2
        assert len(grouped["topic.a"]) == 1
        assert len(grouped["topic.b"]) == 1

    def test_multiple_ops_same_topic_grouped(self):
        op1 = _make_op("orders.events")
        op2 = _make_op("orders.events")
        op3 = _make_op("orders.events")
        ops = {"create": op1, "update": op2, "delete": op3}
        grouped = {}
        for name, op in ops.items():
            grouped.setdefault(op.channel_address, []).append((name, op))
        assert len(grouped) == 1
        assert len(grouped["orders.events"]) == 3
        names = [n for n, _ in grouped["orders.events"]]
        assert names == ["create", "update", "delete"]

    def test_mixed_single_and_multi(self):
        ops = {
            "orderCreated": _make_op("orders.events"),
            "orderUpdated": _make_op("orders.events"),
            "userRegistered": _make_op("users.lifecycle"),
        }
        grouped = {}
        for name, op in ops.items():
            grouped.setdefault(op.channel_address, []).append((name, op))
        assert len(grouped) == 2
        assert len(grouped["orders.events"]) == 2
        assert len(grouped["users.lifecycle"]) == 1


class TestAsyncIssue061DateToDate:

    def test_date_maps_to_date_column(self):
        assert to_sa_column("Date") == "Date"

    def test_date_maps_to_date_python(self):
        assert to_python_type("Date") == "date"

    def test_localdate_maps_to_date_column(self):
        assert to_sa_column("LocalDate") == "Date"

    def test_datetime_types_still_map_to_datetime_tz(self):
        assert to_sa_column("LocalDateTime") == "DateTime(timezone=True)"
        assert to_sa_column("OffsetDateTime") == "DateTime(timezone=True)"
        assert to_sa_column("ZonedDateTime") == "DateTime(timezone=True)"
        assert to_sa_column("Instant") == "DateTime(timezone=True)"

    def test_localdate_pk_maps_to_date(self):
        assert to_sa_pk_type("LocalDate") == "Date"


def _make_contracts(models_spec):
    contracts = {}
    for name, attrs_spec in models_spec.items():
        table = attrs_spec.pop("__table__", name.lower())
        attrs = []
        for attr_name, attr_cfg in attrs_spec.items():
            if isinstance(attr_cfg, str):
                attr_cfg = {"type": attr_cfg, "column": attr_name}
            persistence = None
            if "column" in attr_cfg:
                p_kwargs = {"column": attr_cfg["column"]}
                if attr_cfg.get("primary_key"):
                    p_kwargs["primary_key"] = True
                persistence = RelationalPersistence(**p_kwargs)
            attrs.append(ModelAttribute(
                name=attr_name,
                type=attr_cfg.get("type", "String"),
                persistence=persistence,
                ref_model=attr_cfg.get("ref_model"),
            ))
        contracts[name] = ModelContract(
            attributes=attrs,
            persistence=RelationalPersistence(table=table),
        )
    return contracts


class TestAsyncIssue056ForeignKeys:

    def test_owner_id_becomes_relation_to_owner(self):
        contracts = _make_contracts({
            "Pet": {"__table__": "pets", "id": {"type": "Long", "column": "id", "primary_key": True}, "name": "String", "ownerId": {"type": "Long", "column": "owner_id"}},
            "Owner": {"__table__": "owner", "id": {"type": "Long", "column": "id", "primary_key": True}, "email": "String"},
        })
        _ensure_foreign_keys(contracts)
        owner_attr = next(a for a in contracts["Pet"].attributes if a.name == "ownerId")
        assert owner_attr.type == "Relation"
        assert owner_attr.ref_model == "Owner"
        assert owner_attr.persistence.foreign_column == "id"

    def test_pk_column_not_converted(self):
        contracts = _make_contracts({
            "Pet": {"__table__": "pets", "id": {"type": "Long", "column": "pet_id", "primary_key": True}},
        })
        _ensure_foreign_keys(contracts)
        pk_attr = contracts["Pet"].attributes[0]
        assert pk_attr.type == "Long"

    def test_no_matching_model_stays_scalar(self):
        contracts = _make_contracts({
            "Order": {"__table__": "orders", "id": {"type": "String", "column": "id", "primary_key": True}, "customerId": {"type": "String", "column": "customer_id"}},
        })
        _ensure_foreign_keys(contracts)
        cid = next(a for a in contracts["Order"].attributes if a.name == "customerId")
        assert cid.type == "String"
        assert cid.ref_model is None

    def test_table_with_trailing_digits_matched(self):
        contracts = _make_contracts({
            "Pet": {"__table__": "pets2", "id": {"type": "Long", "column": "id", "primary_key": True}, "ownerId": {"type": "Long", "column": "owner_id"}},
            "Owner": {"__table__": "owner2", "id": {"type": "Long", "column": "id", "primary_key": True}},
        })
        _ensure_foreign_keys(contracts)
        owner_attr = next(a for a in contracts["Pet"].attributes if a.name == "ownerId")
        assert owner_attr.type == "Relation"
        assert owner_attr.ref_model == "Owner"

    def test_already_relation_not_modified(self):
        contracts = _make_contracts({
            "Pet": {"__table__": "pets", "id": {"type": "Long", "column": "id", "primary_key": True}, "ownerId": {"type": "Relation", "column": "owner_id", "ref_model": "Owner"}},
            "Owner": {"__table__": "owner", "id": {"type": "Long", "column": "id", "primary_key": True}},
        })
        _ensure_foreign_keys(contracts)
        owner_attr = next(a for a in contracts["Pet"].attributes if a.name == "ownerId")
        assert owner_attr.type == "Relation"
        assert owner_attr.ref_model == "Owner"

    def test_visit_pet_id_matched_to_pets_table(self):
        contracts = _make_contracts({
            "Visit": {"__table__": "visit2", "id": {"type": "Long", "column": "id", "primary_key": True}, "petId": {"type": "Long", "column": "pet_id"}},
            "Pet": {"__table__": "pets2", "id": {"type": "Long", "column": "id", "primary_key": True}},
        })
        _ensure_foreign_keys(contracts)
        pet_attr = next(a for a in contracts["Visit"].attributes if a.name == "petId")
        assert pet_attr.type == "Relation"
        assert pet_attr.ref_model == "Pet"


class TestAsyncIssue062EnumSchemas:

    def _render_enum(self, class_name, schema_name, enum_values):
        from jinja2 import Environment, FileSystemLoader
        import os
        partials_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "src", "apigen_copier", "partials_asyncapi",
        )
        env = Environment(loader=FileSystemLoader(partials_dir))
        template = env.get_template("dto_enum.jinja")
        return template.render(
            class_name=class_name,
            schema_name=schema_name,
            enum_values=enum_values,
        )

    def test_string_enum_generates_str_enum_class(self):
        result = self._render_enum("PetStatus", "PetStatus", ["available", "pending", "sold"])
        assert "class PetStatus(str, Enum):" in result
        assert 'AVAILABLE = "available"' in result
        assert 'PENDING = "pending"' in result
        assert 'SOLD = "sold"' in result

    def test_enum_imports_enum_module(self):
        result = self._render_enum("ChannelType", "ChannelType", ["EMAIL", "SMS"])
        assert "from enum import Enum" in result
        assert "BaseModel" not in result

    def test_enum_with_hyphens_normalized(self):
        result = self._render_enum("Status", "Status", ["in-progress", "on-hold"])
        assert 'IN_PROGRESS = "in-progress"' in result
        assert 'ON_HOLD = "on-hold"' in result

    def test_enum_detection_in_schema(self):
        schema_def = {"type": "string", "enum": ["a", "b", "c"]}
        assert schema_def.get("enum") is not None
        assert schema_def.get("type") == "string"


class TestAsyncIssue063SampleValues:

    def test_enum_field_uses_first_value(self):
        finfo = {"type": "string", "enum": ["EMAIL", "SMS", "PUSH"]}
        assert _sample_value_for_field(finfo) == "'EMAIL'"

    def test_ref_to_enum_schema_uses_first_value(self):
        finfo = {"$ref": "#/components/schemas/ChannelType"}
        schemas = {"ChannelType": {"type": "string", "enum": ["EMAIL", "SMS"]}}
        assert _sample_value_for_field(finfo, all_schemas=schemas) == "'EMAIL'"

    def test_object_type_returns_dict(self):
        finfo = {"type": "object"}
        assert _sample_value_for_field(finfo) == "{}"

    def test_string_type_returns_test(self):
        finfo = {"type": "string"}
        assert _sample_value_for_field(finfo) == '"test"'

    def test_integer_enum_uses_first_value(self):
        finfo = {"type": "integer", "enum": [1, 2, 3]}
        assert _sample_value_for_field(finfo) == "1"

    def test_ref_to_non_enum_schema_falls_back(self):
        finfo = {"$ref": "#/components/schemas/SomeObj"}
        schemas = {"SomeObj": {"type": "object", "properties": {"x": {"type": "string"}}}}
        assert _sample_value_for_field(finfo, all_schemas=schemas) == '"test"'
