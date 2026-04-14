from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Dict, Any, List, Optional
from .contracts import ApigenProject, ModelContract

class ServerSchema(BaseModel):
    host: str
    protocol: str
    security: list = Field(default_factory=list)
    variables: dict = Field(default_factory=dict)

class ChannelSchema(BaseModel):
    address: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    messages: dict = Field(default_factory=dict)
    bindings: dict = Field(default_factory=dict)

class OperationSchema(BaseModel):
    action: str
    channel: ChannelSchema
    bindings: dict = Field(default_factory=dict)
    reply: Optional[dict] = None
    messages: list = Field(default_factory=list)
    required_count: int = Field(default=0, description="Number of required fields in primary payload (for dispatcher ordering)")

    @staticmethod
    def _resolve_param_value(pdata, fallback: str) -> str:
        """Extract a concrete value from a channel parameter definition."""
        if not isinstance(pdata, dict):
            return str(pdata)
        default = pdata.get("default")
        if default is not None:
            return str(default)
        enum_vals = pdata.get("enum", [])
        return enum_vals[0] if enum_vals else fallback

    @property
    def channel_address(self) -> str:
        addr = self.channel.address or ""
        for pname, pdata in (self.channel.parameters or {}).items():
            placeholder = "{" + pname + "}"
            if placeholder in addr:
                addr = addr.replace(placeholder, self._resolve_param_value(pdata, pname))
        return addr

    @property
    def reply_channel_address(self) -> Optional[str]:
        if not self.reply:
            return None
        rc = self.reply.get("channel", {})
        if isinstance(rc, dict):
            return rc.get("address")
        return getattr(rc, "address", None)

    def _get_first_binding(self) -> dict:
        if not self.messages:
            return {}
        msg = self.messages[0]
        if isinstance(msg, dict):
            return msg.get("x-apigen-binding", {})
        return getattr(msg, "x-apigen-binding", {}) or {}

    @property
    def binding_action(self) -> str:
        return self._get_first_binding().get("action", "")

    @property
    def binding_model(self) -> str:
        return self._get_first_binding().get("model", "")

    def expand_messages(self) -> list["OperationSchema"]:
        if len(self.messages) <= 1:
            return [self]
        bindings = set()
        for msg in self.messages:
            if isinstance(msg, dict):
                b = msg.get("x-apigen-binding", {})
            else:
                b = getattr(msg, "x-apigen-binding", {}) or {}
            key = (b.get("action", ""), b.get("model", ""))
            bindings.add(key)
        if len(bindings) <= 1:
            return [self]
        expanded = []
        for msg in self.messages:
            sub_op = OperationSchema(
                action=self.action,
                channel=self.channel,
                bindings=self.bindings,
                reply=self.reply,
                messages=[msg],
            )
            expanded.append(sub_op)
        return expanded


class AsyncAPIProjectSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='ignore')
    project: ApigenProject
    entities: Dict[str, ModelContract] = Field(default_factory=dict)
    servers: Dict[str, ServerSchema] = Field(default_factory=dict)
    channels: Dict[str, ChannelSchema] = Field(default_factory=dict)
    operations: Dict[str, OperationSchema] = Field(default_factory=dict)
    components: dict = Field(default_factory=dict)
    output_dir: str = Field(..., description="Absolute path where the code will be generated")

    @property
    def primary_server(self):
        if not self.servers:
            return None
        return list(self.servers.values())[0]

    @property
    def primary_protocol(self) -> str:
        if not self.servers:
            return "kafka"
        return self.primary_server.protocol
        
    @property
    def is_kafka(self) -> bool:
        return self.primary_protocol.startswith("kafka")

    @property
    def project_slug(self) -> str:
        if not self.project or not self.project.name:
            return "project"
        return self.project.name.lower().replace(" ", "_").replace("-", "_")

    @property
    def payload_schemas(self) -> dict:
        return self.components.get("schemas", {})

    @property
    def typed_operations(self) -> dict:
        return self.operations

    @property
    def receive_operations(self) -> dict:
        result = {}
        for k, v in self.operations.items():
            if v.action != "receive":
                continue
            expanded = v.expand_messages()
            if len(expanded) == 1:
                result[k] = expanded[0]
            else:
                for i, sub_op in enumerate(expanded):
                    binding = sub_op._get_first_binding()
                    action = binding.get("action", "")
                    suffix = f"_{action}" if action else f"_{i}"
                    sub_name = k + suffix
                    result[sub_name] = sub_op
        return result

    @property
    def publisher_operations(self) -> dict:
        """Operations that send messages AND have no reply."""
        return {k: v for k, v in self.operations.items() if v.action == "send" and not v.reply}

    @property
    def rpc_operations(self) -> dict:
        """Operations that send messages AND expect a reply (RPC/Request-Response)."""
        return {k: v for k, v in self.operations.items() if v.action == "send" and v.reply}

    @property
    def model_contracts(self) -> dict:
        return self.entities

    @model_validator(mode='after')
    def validate_schema(self) -> 'AsyncAPIProjectSchema':
        if not self.operations:
            raise ValueError("AsyncAPI project must define at least one operation in 'operations'.")
        if not self.servers:
            raise ValueError("AsyncAPI project must define at least one broker in 'servers'.")
        return self
