import yaml
import os
import shutil
from copier import run_copy
from .schemas import RESTProjectSchema, OpenApiProjectSchema
from .custom_code_merger import extract_custom_blocks, inject_custom_blocks, copy_user_code_folder

def generate_from_schema(schema: RESTProjectSchema, template_dir: str = None, existing_project_dir: str = None) -> str:
    """
    Generates a FastAPI project directly from a RESTProjectSchema object.
    
    Args:
        schema (RESTProjectSchema): The validated project definition.
        template_dir (str, optional): Custom path to the Copier template directory.
        existing_project_dir (str, optional): Path to a previous project directory.
            If provided, custom code blocks will be extracted and re-injected
            into the newly generated project.
        
    Returns:
        str: Absolute path to the generated project directory.
    """
    if template_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(base_dir, "template")

    output_dir = schema.output_dir

    # Extract custom code blocks from existing project BEFORE destroying it
    saved_blocks = {}
    if existing_project_dir and os.path.isdir(existing_project_dir):
        saved_blocks = extract_custom_blocks(existing_project_dir)
    
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    data = schema.model_dump()
    
    if schema.project:
        data["project_name"] = schema.project.name
        data["project_slug"] = schema.project.name.lower().replace(" ", "_").replace("-", "_")
        data["description"] = schema.project.description
        data["version"] = schema.project.version
        
        if schema.project.data_driver:
            data["db_driver"] = schema.project.data_driver
            data["data_driver"] = schema.project.data_driver

    _backfill_legacy_data(data, schema)

    run_copy(
        src_path=template_dir,
        dst_path=output_dir,
        data=data,
        unsafe=True
    )
    
    # 4. Dynamic Generation (Entities, Routes, etc.)
    generate_dynamic_files(schema, output_dir, data)
    
    project_slug = data.get("project_slug", "project")
    env_example = os.path.join(output_dir, project_slug, ".env.example")
    env_target = os.path.join(output_dir, project_slug, ".env")
    if os.path.exists(env_example) and not os.path.exists(env_target):
        shutil.copy(env_example, env_target)
    
    # 5. Inject saved custom code blocks into the new project
    merge_warnings = []
    if saved_blocks:
        merge_warnings = inject_custom_blocks(os.path.abspath(output_dir), saved_blocks)
        for w in merge_warnings:
            print(f"  ⚠️  {w}")

    # 6. Copy UserCode/ folder from existing project
    if existing_project_dir and os.path.isdir(existing_project_dir):
        copy_user_code_folder(existing_project_dir, os.path.abspath(output_dir))
    
    print(f"SUCCESS: Project generated at {output_dir}")
    return os.path.abspath(output_dir)

def generate_dynamic_files(schema: RESTProjectSchema, output_dir: str, data: dict):
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    partials_dir = os.path.join(base_dir, "partials")
    
    if not os.path.exists(partials_dir):
        print(f"WARNING: Partials directory not found at {partials_dir}. Skipping dynamic generation.")
        return

    # Disable autoescape because we are generating Python source, not HTML.
    # SECURITY: Inputs are sanitized via Pydantic models (identifiers) or explicit filters before rendering.
    # Standard HTML autoescaping would corrupt the generated Python code structure (e.g. < > operators).
    env = Environment(loader=FileSystemLoader(partials_dir), autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True)

    def _to_snake_case(value: str) -> str:
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', value)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.replace("__", "_").lower()

    env.filters["snake"] = _to_snake_case

    from .type_mapper import to_sa_column, to_python_type
    env.filters["sa_column_type"] = to_sa_column
    env.filters["python_type"] = to_python_type
    
    project_slug = data.get("project_slug", "project")
    src_dir = os.path.join(output_dir, project_slug, "src")
    
    try:
        _generate_domain_models(env, schema, src_dir)
        _generate_infra_entities(env, schema, src_dir)
        _generate_infra_repositories(env, schema, src_dir)
        _generate_infra_mappers(env, schema, src_dir)
        _generate_infra_services(env, schema, src_dir)
        
        # OPENAPI-001: Detect standard response and copy module
        is_standard_response = _detect_and_copy_standard_response(schema, src_dir)
        _generate_routes(env, schema, src_dir, is_standard_response=is_standard_response)
                
    except Exception as e:
        print(f"ERROR during dynamic generation: {e}")
        raise e

def _generate_domain_models(env, schema: RESTProjectSchema, src_dir: str):
    model_template = env.get_template("domain_model.jinja")
    for name, model in schema.entities.items():
        cleaned_name = name.lower()
        file_dir = os.path.join(src_dir, "domain", "models", cleaned_name)
        os.makedirs(file_dir, exist_ok=True)
        
        has_rw_fields = any(a.read_only or a.write_only for a in model.attributes)
        content = model_template.render(entity_name=name, attributes=model.attributes, has_rw_fields=has_rw_fields)
        with open(os.path.join(file_dir, f"{cleaned_name}_model.py"), "w") as f:
            f.write(content)


def _detect_and_copy_standard_response(schema: RESTProjectSchema, src_dir: str) -> bool:
    """OPENAPI-001: Detect standard-response-operations in project and copy module."""
    project = schema.project
    has_standard = bool(getattr(project, 'standard_response_operations', None))
    if has_standard:
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        src_file = os.path.join(static_dir, "standard_response.py")
        dest_dir = os.path.join(src_dir, "application", "schemas")
        os.makedirs(dest_dir, exist_ok=True)
        if os.path.exists(src_file):
            shutil.copy2(src_file, os.path.join(dest_dir, "standard_response.py"))
    return has_standard

def _generate_infra_entities(env, schema: RESTProjectSchema, src_dir: str):
    infra_template = env.get_template("infra_entity.jinja")
    for name, model in schema.entities.items():
        if not model.has_persistence:
            continue
        cleaned_name = name.lower()
        file_dir = os.path.join(src_dir, "infrastructure", "entities", cleaned_name)
        os.makedirs(file_dir, exist_ok=True)
        
        related_pk_types = {k: v.primary_key_sa_type for k, v in schema.entities.items()}
        for attr in model.attributes:
            if attr.is_array and attr.items_ref_model and not attr.persistence:
                print(f"⚠️  WARNING: {name}.{attr.name} references {attr.items_ref_model} but has no persistence config. "
                      f"This relationship will be skipped. Add persistence to include it.")
        content = infra_template.render(
            entity_name=name,
            attributes=model.attributes,
            table_name=model.table_name,
            all_entities=schema.entities,
            entity_pk_type=model.primary_key_sa_type,
            related_pk_types=related_pk_types,
            data_driver=schema.project.data_driver,
        )
        with open(os.path.join(file_dir, f"{cleaned_name}_entity.py"), "w") as f:
            f.write(content)

def _generate_infra_repositories(env, schema: RESTProjectSchema, src_dir: str):
    repo_template = env.get_template("infra_repository.jinja")
    for name, model in schema.entities.items():
        if not model.has_persistence:
            continue
        cleaned_name = name.lower()
        file_dir = os.path.join(src_dir, "infrastructure", "repository", cleaned_name)
        os.makedirs(file_dir, exist_ok=True)
        
        content = repo_template.render(entity_name=name)
        with open(os.path.join(file_dir, f"{cleaned_name}_repository.py"), "w") as f:
            f.write(content)

def _generate_infra_mappers(env, schema: RESTProjectSchema, src_dir: str):
    mapper_template = env.get_template("mapper.jinja")
    for name, model in schema.entities.items():
        if not model.has_persistence:
            continue
        cleaned_name = name.lower()
        file_dir = os.path.join(src_dir, "infrastructure", "mappers", cleaned_name)
        os.makedirs(file_dir, exist_ok=True)
        
        content = mapper_template.render(entity_name=name, attributes=model.attributes, all_entities=schema.entities, table_name=model.table_name)
        with open(os.path.join(file_dir, f"{cleaned_name}_mapper.py"), "w") as f:
            f.write(content)

def _generate_infra_services(env, schema: RESTProjectSchema, src_dir: str):
    service_template = env.get_template("infra_service.jinja")
    for name, model in schema.entities.items():
        # Service should be generated for all entities to support routes, regardless of persistence
        cleaned_name = name.lower()
        file_dir = os.path.join(src_dir, "infrastructure", "service", cleaned_name)
        os.makedirs(file_dir, exist_ok=True)
        
        content = service_template.render(entity_name=name, has_persistence=model.has_persistence)
        with open(os.path.join(file_dir, f"{cleaned_name}_service.py"), "w") as f:
            f.write(content)

def _generate_routes(env, schema: RESTProjectSchema, src_dir: str, is_standard_response: bool = False):
    route_template = env.get_template("api_route.jinja")
    
    def generate_router_file(router, router_name: str, parent_path: str = ""):
        cleaned_name = router_name.lower().replace("{", "").replace("}", "").replace("-", "_").lstrip("/")
        file_dir = _resolve_route_dir(src_dir, parent_path, cleaned_name)
        os.makedirs(file_dir, exist_ok=True)
        
        sub_router_imports, sub_router_includes = _collect_sub_routers(
            router, cleaned_name, parent_path, generate_router_file
        )
        json_conversion_fields = _collect_json_fields(schema, router)

        pk_python_type = "int"
        entity = schema.entities.get(router.entity)
        if entity:
            pk = entity.primary_key_attr
            if pk and pk.type == "String":
                pk_python_type = "str"

        content = route_template.render(
            entity_name=router.entity, 
            endpoints=router.endpoints,
            sub_router_imports=sub_router_imports,
            sub_router_includes=sub_router_includes,
            json_conversion_fields=json_conversion_fields,
            entities=schema.entities,
            pk_python_type=pk_python_type,
            is_standard_response=is_standard_response
        )
        
        with open(os.path.join(file_dir, f"{cleaned_name}_routes.py"), "w") as f:
            f.write(content)
    
    for name, router in schema.routers.items():
        generate_router_file(router, name)

def _resolve_route_dir(src_dir: str, parent_path: str, cleaned_name: str) -> str:
    if parent_path:
        return os.path.join(src_dir, "api", "routes", parent_path, cleaned_name)
    return os.path.join(src_dir, "api", "routes", cleaned_name)

def _collect_sub_routers(router, cleaned_name: str, parent_path: str, generate_fn):
    imports_literal = []
    imports_param = []
    includes_literal = []
    includes_param = []
    for sub_name, sub_router in router.sub_routers.items():
        sub_cleaned = sub_name.lower().replace("{", "").replace("}", "").replace("-", "_").lstrip("/")
        imp = f"from .{sub_cleaned}.{sub_cleaned}_routes import router as {sub_cleaned}_router"
        inc = f'router.include_router({sub_cleaned}_router, prefix="/{sub_name}")'
        if "{" in sub_name:
            imports_param.append(imp)
            includes_param.append(inc)
        else:
            imports_literal.append(imp)
            includes_literal.append(inc)
        new_parent = f"{parent_path}/{cleaned_name}" if parent_path else cleaned_name
        generate_fn(sub_router, sub_name, new_parent)
    return imports_literal + imports_param, includes_literal + includes_param

def _collect_json_fields(schema: RESTProjectSchema, router) -> set:
    json_conversion_fields = set()
    entity_model = schema.entities.get(router.entity)
    if entity_model:
        for attr in entity_model.attributes:
            if attr.has_json_conversion:
                json_conversion_fields.add(attr.name)
    return json_conversion_fields

def _build_endpoint_path(router, router_path: str, endpoint) -> str:
    ep_map = endpoint.mapping.lstrip("/")
    full_path = getattr(router, 'mapping', router_path)
    if ep_map:
        full_path = f"{full_path.rstrip('/')}/{ep_map}"
    return full_path


def _backfill_paths(data: dict, schema: RESTProjectSchema):
    if data.get("paths"):
        return
    
    paths = {}
    for router_path, router in schema.routers.items():
        for endpoint in router.endpoints:
            full_path = _build_endpoint_path(router, router_path, endpoint)
            if full_path not in paths:
                paths[full_path] = {}
            paths[full_path][endpoint.method.lower()] = {"operationId": endpoint.name}
    data["paths"] = paths


def _backfill_schemas(data: dict, schema: RESTProjectSchema):
    if data.get("schemas"):
        return
    
    schemas = {}
    for name, entity in schema.entities.items():
        props = {attr.name: {"type": attr.type.lower()} for attr in entity.attributes}
        schemas[name] = {"properties": props}
    data["schemas"] = schemas


def _backfill_legacy_data(data: dict, schema: RESTProjectSchema):
    _backfill_paths(data, schema)
    _backfill_schemas(data, schema)


def generate_project(input_path: str, output_dir: str, template_dir: str = None, existing_project_dir: str = None):

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"{input_path} not found")

    # Detect if input is OpenAPI spec or pre-processed schema
    is_openapi = False
    with open(input_path, "r") as f:
        content = f.read(1024) # Read first 1kb to detect
        if 'openapi' in content or 'swagger' in content:
            is_openapi = True
    
    if is_openapi:
        from .parser import OpenAPIParser
        parser = OpenAPIParser(input_path)
        project_schema = parser.parse(output_dir)
    else:
        with open(input_path, "r") as f:
            if input_path.endswith(".json"):
                import json
                raw_data = json.load(f)
            else:
                raw_data = yaml.safe_load(f)

        if "output_dir" not in raw_data or not raw_data["output_dir"]:
            raw_data["output_dir"] = output_dir


        project_schema = RESTProjectSchema(**raw_data)

    generate_from_schema(project_schema, template_dir, existing_project_dir=existing_project_dir)
