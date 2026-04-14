import yaml
import json
import os
from typing import Dict, Any, List, Optional
from .schemas import RESTProjectSchema, RouterSchema, EndpointSchema, ResponseSchema, ResponseAttribute
from .contracts import ApigenProject, ModelContract, BindingContract, ModelAttribute

class OpenAPIParser:
    def __init__(self, spec_path: str):
        self.spec_path = spec_path
        self.raw_spec = self._load_spec()
        self.project_info = self._extract_project()
        self.models = self._extract_models()
        self._enrich_models_with_schemas()
        self.routers = self._extract_routers()


    def _load_spec(self) -> Dict[str, Any]:
        with open(self.spec_path, 'r') as f:
            if self.spec_path.endswith('.json'):
                return json.load(f)
            return yaml.safe_load(f)

    def _extract_project(self) -> ApigenProject:
        project_data = self.raw_spec.get('x-apigen-project', {})
        
        if not project_data and 'project' in self.raw_spec:
             project_data = self.raw_spec['project']

        # If not present, try to fallback to standard info (partial)
        if not project_data:
            info = self.raw_spec.get('info', {})
            project_data = {
                'name': info.get('title', 'Project'),
                'description': info.get('description', ''),
                'version': info.get('version', '1.0.0'),
                'data-driver': 'postgresql' # Fixed key to match alias
            }
        if not project_data.get('data-driver') and not project_data.get('data_driver'):
            print("WARNING: No data-driver specified in x-apigen-project. Defaulting to 'postgresql' for compatibility.")
            project_data['data-driver'] = 'postgresql'

        # Extract prefix from servers[0].url if not already set
        if not project_data.get('prefix'):
            servers = self.raw_spec.get('servers', [])
            if servers and isinstance(servers[0], dict):
                server_url = servers[0].get('url', '')
                # Only use path-only URLs as prefix (not full http:// URLs)
                if server_url and not server_url.startswith('http'):
                    project_data['prefix'] = server_url.rstrip('/')

        return ApigenProject(**project_data)

    def _extract_models(self) -> Dict[str, ModelContract]:
        components = self.raw_spec.get('components', {})
        models_data = components.get('x-apigen-models', {})
        models = {}
        
        for name, data in models_data.items():
            data['attributes'] = self._normalize_attributes(data.get('attributes', []))
            models[name] = ModelContract(**data)
        
        self._validate_models_pk(models)
        return models

    def _normalize_attributes(self, attributes: Any) -> List[Dict[str, Any]]:
        normalized_attrs = []
        
        if isinstance(attributes, dict):
            normalized_attrs = self._normalize_dict_attributes(attributes)
        elif isinstance(attributes, list):
            normalized_attrs = attributes
            
        return self._post_process_attributes(normalized_attrs)

    def _normalize_dict_attributes(self, attributes: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = []
        for key, value in attributes.items():
            if not isinstance(value, dict):
                continue
            
            defined_name = value.get('name')
            if defined_name and defined_name != key:
                value['warning'] = f"WARN: Ambiguity detected. Defined name '{defined_name}' ignored in favor of key '{key}'."
                value['name'] = key
            elif not defined_name:
                value['name'] = key
            
            result.append(value)
        return result

    def _post_process_attributes(self, attributes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        new_attributes = []
        for attr in attributes:
            if 'type' in attr:
                if 'format' in attr:
                    from .type_mapper import from_openapi
                    attr['type'] = from_openapi(attr['type'], attr.get('format'))
                else:
                    attr['type'] = self._normalize_type(attr['type'])

            if attr.get('type') == 'ComposedID':
                new_attributes.extend(self._flatten_composed_id(attr))
            else:
                new_attributes.append(attr)
        return new_attributes

    def _flatten_composed_id(self, attr: Dict[str, Any]) -> List[Dict[str, Any]]:
        sub_attrs = attr.get('attributes', [])
        flattened = []
        for sub in sub_attrs:
            if 'relational-persistence' not in sub:
                 sub['relational-persistence'] = {}
            sub['relational-persistence']['primary-key'] = True
            if 'type' in sub:
                sub['type'] = self._normalize_type(sub['type'])
            flattened.append(sub)
        return flattened

    def _normalize_type(self, type_name: str) -> str:
        """Normalize type names to internal format (TitleCase)."""
        mapping = {
            "string": "String",
            "integer": "Integer",
            "int": "Integer",
            "boolean": "Boolean",
            "long": "Long",
            "date": "LocalDate",
            "datetime": "LocalDateTime",
            "uuid": "String",  # UUIDs are strings in python models usually, or we can add UUID type support later
        }
        return mapping.get(type_name.lower(), type_name)

    def _validate_models_pk(self, models: Dict[str, ModelContract]):
        for name, model in models.items():
            has_pk = False
            for attr in model.attributes:
                if attr.persistence and attr.persistence.primary_key:
                    has_pk = True
                    break
            
            if not has_pk:
                raise ValueError(
                    f"Model '{name}' has no Primary Key defined. "
                    f"Please add 'relational-persistence: {{ column: ..., primary-key: true }}' "
                    f"to one of its attributes in the OpenAPI specification."
                )

    def _enrich_models_with_schemas(self):
        """Enrich models with array metadata from components.schemas."""
        components = self.raw_spec.get("components", {})
        schemas = components.get("schemas", {})

        self._schema_to_model = self._build_schema_model_mapping(schemas)

        for schema_name, schema in schemas.items():
            self._process_single_schema(schema, schema_name)

        self._resolve_ref_models()

    def _build_schema_model_mapping(self, schemas: Dict[str, Any]) -> Dict[str, str]:
        """Build schema_name → model_name mapping for ref resolution."""
        mapping = {}
        model_keys_lower = {k.lower(): k for k in self.models}
        for schema_name, schema in schemas.items():
            schema_mapping = schema.get("x-apigen-mapping", {})
            model_name = schema_mapping.get("model", schema_name)
            if model_name in self.models:
                mapping[schema_name] = model_name
            elif schema_name not in self.models:
                matched = self._fuzzy_match_model_name(schema_name.lower(), model_keys_lower)
                if matched:
                    mapping[schema_name] = matched
        return mapping

    def _resolve_ref_models(self):
        """Resolve ref_model/items_ref_model to entity names using schema mapping."""
        for model in self.models.values():
            for attr in model.attributes:
                if attr.ref_model and attr.ref_model in self._schema_to_model:
                    attr.ref_model = self._schema_to_model[attr.ref_model]
                if attr.items_ref_model and attr.items_ref_model in self._schema_to_model:
                    attr.items_ref_model = self._schema_to_model[attr.items_ref_model]

    def _fuzzy_match_model_name(self, schema_lower: str, model_keys_lower: Dict[str, str]) -> Optional[str]:
        """Try to match a schema name to a model name using case-insensitive and plural heuristics."""
        # Exact case-insensitive
        if schema_lower in model_keys_lower:
            return model_keys_lower[schema_lower]
        # Try adding common plural suffixes
        for suffix in ['s', 'es']:
            candidate = schema_lower + suffix
            if candidate in model_keys_lower:
                return model_keys_lower[candidate]
        # Try y→ies (e.g., "category" → "categories")
        if schema_lower.endswith('y'):
            candidate = schema_lower[:-1] + 'ies'
            if candidate in model_keys_lower:
                return model_keys_lower[candidate]
        # Reverse: try to singularize each model key
        for mk_lower, mk_original in model_keys_lower.items():
            if self._is_singular_of(schema_lower, mk_lower):
                return mk_original
        return None

    @staticmethod
    def _is_singular_of(singular: str, plural: str) -> bool:
        """Check if 'singular' is the singular form of 'plural'."""
        if plural.endswith('ies'):
            return singular.endswith('y') and plural.startswith(singular[:-1])
        if plural.endswith('es'):
            return plural.startswith(singular) and len(plural) - len(singular) == 2
        if plural.endswith('s') and not plural.endswith('ss'):
            return plural.startswith(singular) and len(plural) - len(singular) == 1
        return False

    def _process_single_schema(self, schema: Dict[str, Any], schema_name: str):
        mapping = schema.get("x-apigen-mapping", {})
        model_name = mapping.get("model", schema_name)
        
        if model_name not in self.models:
            return

        props = schema.get("properties", {})
        target_model = self.models[model_name]
        attr_index = {a.name: a for a in target_model.attributes}

        for prop_name, prop_data in props.items():
            attr = attr_index.get(prop_name)
            if not attr:
                attr = ModelAttribute(name=prop_name, type=self._schema_type_to_internal(prop_data))
                target_model.attributes.append(attr)
                attr_index[prop_name] = attr
            attr.is_exposed_in_schema = True
            self._enrich_attr_from_prop(attr, prop_data)

    def _enrich_attr_from_prop(self, attr: 'ModelAttribute', prop_data: Dict[str, Any]):
        """Detect arrays and relations from schema property data."""
        if prop_data.get("type") == "array":
            attr.is_array = True
            if attr.type == "String":
                attr.has_json_conversion = True
            items = prop_data.get("items", {})
            if "$ref" in items:
                if not attr.items_ref_model:
                    attr.items_ref_model = self._ref_name(items["$ref"])
            else:
                attr.items_type = self._schema_type_to_internal(items)
        elif "$ref" in prop_data:
            attr.type = "Relation"
            if not attr.ref_model:
                attr.ref_model = self._ref_name(prop_data["$ref"])

        # OPENAPI-002: Capture readOnly/writeOnly from standard OpenAPI properties
        if prop_data.get("readOnly", False):
            attr.read_only = True
        if prop_data.get("writeOnly", False):
            attr.write_only = True

    def _schema_type_to_internal(self, prop: Dict[str, Any]) -> str:
        """Map OpenAPI primitive types to internal names, using format for precision."""
        from .type_mapper import from_openapi
        if not prop:
            return "String"
        return from_openapi(prop.get("type", ""), prop.get("format"))

    def _ref_name(self, ref: str) -> Optional[str]:
        """Extract the model name from a JSON reference."""
        return ref.split("/")[-1] if ref else None

    def _resolve_ref(self, ref: str) -> Dict[str, Any]:
        if not ref or not ref.startswith('#/'):
            return {}
        parts = ref.split('/')
        current = self.raw_spec
        for part in parts[1:]:
             if isinstance(current, dict):
                 current = current.get(part, {})
             else:
                 return {}
        return current

    def _extract_routers(self) -> Dict[str, RouterSchema]:
        routers = {}
        paths = self.raw_spec.get('paths', {})

        for path, path_item in paths.items():
            path_binding_data = path_item.get('x-apigen-binding')
            
            for method, op_data in path_item.items():
                if method.startswith('x-') or not isinstance(op_data, dict):
                    continue
                
                binding_data = op_data.get('x-apigen-binding', path_binding_data)
                if not binding_data:
                    print(f"INFO: Partial generation — skipping {method.upper()} {path} (no x-apigen-binding)")
                    continue

                self._process_operation(path, method, op_data, binding_data, routers)
        
        return routers

    def _process_operation(self, path: str, method: str, op_data: Dict[str, Any], binding_data: Dict[str, Any], routers: Dict[str, RouterSchema]):
        binding = BindingContract(**binding_data)
        model_name = binding.model

        # Derive base path from the YAML path (e.g. "/pet" from "/pet/{petId}")
        # Take first segment(s) before any path parameter
        path_parts = path.strip('/').split('/')
        base_parts = []
        for part in path_parts:
            if part.startswith('{'):
                break
            base_parts.append(part)
        base_path = '/' + '/'.join(base_parts) if base_parts else f"/{model_name.lower()}s"

        if model_name not in routers:
            routers[model_name] = RouterSchema(
                entity=model_name,
                mapping=base_path
            )
        
        # Compute endpoint-relative mapping (portion after the router base)
        if path.startswith(base_path):
            relative_path = path[len(base_path):]
        else:
            relative_path = path
        # Ensure relative path starts with / if non-empty, or is empty string
        if relative_path and not relative_path.startswith('/'):
            relative_path = '/' + relative_path

        endpoint = EndpointSchema(
            method=method.upper(),
            name=op_data.get('operationId', f"{method}{path}"),
            mapping=relative_path,  # Relative to router base
            binding=binding,
            parameters=self._resolve_parameters(op_data.get('parameters', [])),
            responses={
                int(k): v for k, v in op_data.get('responses', {}).items() 
                if str(k).isdigit()
            }
        )

        # Extraer response schema del primer 2xx (filtro de salida)
        response, schema_name = self._extract_response_schema(
            op_data.get('responses', {})
        )
        endpoint.response = response
        endpoint.response_schema_name = schema_name

        # Extraer error response schemas (4xx/5xx con properties)
        endpoint.error_responses = self._extract_error_responses(
            op_data.get('responses', {})
        )

        if model_name in self.models:
            self._handle_composite_pk(endpoint, model_name)

        routers[model_name].endpoints.append(endpoint)

    def _extract_response_schema(self, responses: dict) -> tuple:
        """Extract response fields from the first 2xx response with a schema.
        Returns (ResponseSchema | None, schema_name | None)."""
        for code in sorted(responses.keys()):
            code_int = int(code) if str(code).isdigit() else 0
            if not (200 <= code_int < 300):
                continue
            schema, is_collection, schema_name = self._resolve_response_schema(responses, code)
            if not schema:
                continue
            props = schema.get('properties', {})
            if not props:
                return None, schema_name
            attrs = [self._prop_to_response_attr(name, prop) for name, prop in props.items()]
            return ResponseSchema(is_collection=is_collection, attributes=attrs), schema_name
        return None, None

    def _resolve_response_schema(self, responses: dict, code) -> tuple:
        """Resolve a response entry to its (schema dict, collection flag, schema_name)."""
        resp = responses[str(code)] if str(code) in responses else responses.get(code, {})
        content = resp.get('content', {})
        json_ct = content.get('application/json', {})
        schema = json_ct.get('schema', {})
        schema_name = None
        if '$ref' in schema:
            schema_name = schema['$ref'].rsplit('/', 1)[-1]
            schema = self._resolve_ref(schema['$ref'])
        is_collection = schema.get('type') == 'array'
        if is_collection:
            items = schema.get('items', {})
            if '$ref' in items:
                schema_name = items['$ref'].rsplit('/', 1)[-1]
                schema = self._resolve_ref(items['$ref'])
            else:
                schema = items
        return schema, is_collection, schema_name

    @staticmethod
    def _prop_to_response_attr(name: str, prop: dict) -> ResponseAttribute:
        """Convert a single schema property to a ResponseAttribute."""
        if '$ref' in prop:
            ref_model = prop['$ref'].split('/')[-1]
            return ResponseAttribute(name=name, type='Relation', ref_model=ref_model, entity_field_name=ref_model)
        if prop.get('type') == 'array':
            items = prop.get('items', {})
            ref = items.get('$ref')
            ref_name = ref.split('/')[-1] if ref else None
            return ResponseAttribute(
                name=name, type='Array',
                ref_model=ref_name,
                entity_field_name=ref_name
            )
        from .type_mapper import from_openapi
        return ResponseAttribute(
            name=name,
            type=from_openapi(prop.get('type', ''), prop.get('format'))
        )

    def _extract_error_responses(self, responses: dict) -> Dict[int, ResponseSchema]:
        """Extract error response schemas (4xx/5xx) that have properties with default/example values."""
        error_schemas = {}
        for code in sorted(responses.keys()):
            code_int = int(code) if str(code).isdigit() else 0
            if code_int < 400:
                continue
            resp = responses[str(code)] if str(code) in responses else responses.get(code, {})
            content = resp.get('content', {})
            json_ct = content.get('application/json', {})
            schema = json_ct.get('schema', {})

            if '$ref' in schema:
                schema = self._resolve_ref(schema['$ref'])

            props = schema.get('properties', {})
            if not props:
                continue  # Solo description → skip, usará HTTPException

            attrs = []
            for name, prop in props.items():
                default_val = prop.get('default', prop.get('example'))
                attrs.append(ResponseAttribute(
                    name=name,
                    type=self._schema_type_to_internal(prop),
                    default_value=default_val
                ))
            error_schemas[code_int] = ResponseSchema(
                is_collection=False, attributes=attrs
            )
        return error_schemas

    def _resolve_parameters(self, raw_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        resolved_params = []
        for p in raw_params:
            if '$ref' in p:
                resolved = self._resolve_ref(p['$ref'])
            else:
                resolved = p
            # Flatten schema.type into param.type for template compatibility
            if 'type' not in resolved and 'schema' in resolved and isinstance(resolved['schema'], dict):
                resolved['type'] = resolved['schema'].get('type', 'string')
            resolved_params.append(resolved)
        return resolved_params

    def _handle_composite_pk(self, endpoint: EndpointSchema, model_name: str):
        target_model = self.models[model_name]
        pks = [attr for attr in target_model.attributes if attr.persistence and attr.persistence.primary_key]
        
        if len(pks) > 1 and '/{id}' in endpoint.mapping:
            new_suffix = "/" + "/".join([f"{{{pk.name}}}" for pk in pks])
            endpoint.mapping = endpoint.mapping.replace('/{id}', new_suffix)
            
            endpoint.parameters = [p for p in endpoint.parameters if p['name'] != 'id']
            
            for pk in pks:
                schema_type = {"type": "string"}
                if pk.type == "Integer": schema_type = {"type": "integer", "format": "int32"}
                elif pk.type == "Long": schema_type = {"type": "integer", "format": "int64"}
                elif pk.type == "Boolean": schema_type = {"type": "boolean"}
                
                endpoint.parameters.append({
                    'name': pk.name,
                    'in': 'path',
                    'required': True,
                    'schema': schema_type,
                    'type': schema_type['type'] # Flatten for Jinja template
                })

    def parse(self, output_dir: str) -> RESTProjectSchema:
        return RESTProjectSchema(
            project=self.project_info,
            entities=self.models,
            routers=self.routers,
            output_dir=output_dir
        )
