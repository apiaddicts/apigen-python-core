"""
Tests for OPENAPI-002: readOnly/writeOnly → ModelGet/ModelCreate/ModelUpdate
Tests for OPENAPI-001: StandardResponse[T] detection

Issues documented inline as ISSUE comments.
"""
import pytest
import yaml
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def _write_spec(spec, path):
    """Write spec to YAML ensuring 'openapi' key appears first (for auto-detection)."""
    with open(path, 'w') as f:
        # Write openapi version first so generate_project detects it in first 1KB
        f.write(f"openapi: \"{spec.get('openapi', '3.0.3')}\"\n")
        remaining = {k: v for k, v in spec.items() if k != 'openapi'}
        yaml.dump(remaining, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _load_enriched_spec():
    """Load the enriched Petstore spec from the test fixtures."""
    spec_path = os.path.join(
        os.path.dirname(__file__), '..', '..',
        'prueba jeff', 'Petstore with Owners-enriched.yaml'
    )
    if not os.path.exists(spec_path):
        pytest.skip("Enriched Petstore spec not found")
    with open(spec_path) as f:
        return yaml.safe_load(f)


def _find_file(root_dir, filename):
    """Find a file by name in a directory tree."""
    for root, dirs, files in os.walk(root_dir):
        if filename in files:
            return os.path.join(root, filename)
    return None


@pytest.fixture
def enriched_spec_with_readonly():
    """Load enriched Petstore spec with readOnly: true on Pet.id."""
    spec = _load_enriched_spec()
    schemas = spec['components']['schemas']
    if 'Pet' in schemas and 'properties' in schemas['Pet']:
        schemas['Pet']['properties']['id']['readOnly'] = True
    return spec


@pytest.fixture
def enriched_spec_without_readonly():
    """Load enriched Petstore spec WITHOUT readOnly/writeOnly."""
    return _load_enriched_spec()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for generated output."""
    d = tempfile.mkdtemp(prefix='openapi_test_')
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ── OPENAPI-002: readOnly/writeOnly Tests ──

class TestReadOnlyWriteOnlyParsing:
    """Test that the parser correctly captures readOnly/writeOnly.
    
    ISSUE: ModelAttribute (copier contract) initially lacked read_only/write_only fields.
    SOLUTION: Added read_only, write_only to ModelAttribute in model_contract.py.
    
    ISSUE: copier parser._enrich_attr_from_prop() didn't capture readOnly/writeOnly.
    SOLUTION: Added readOnly/writeOnly capture at end of _enrich_attr_from_prop().
    """

    def test_parser_captures_readonly(self, enriched_spec_with_readonly, temp_dir):
        """readOnly: true on Pet.id → attr.read_only=True."""
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(enriched_spec_with_readonly, spec_file)

        from apigen_copier.parser import OpenAPIParser
        parser = OpenAPIParser(spec_file)
        
        pet = parser.models.get('Pet')
        assert pet is not None, "Pet model not found"
        
        id_attr = next((a for a in pet.attributes if a.name == 'id'), None)
        assert id_attr is not None, "Pet.id attribute not found"
        assert id_attr.read_only is True, "Pet.id should be readOnly"

    def test_parser_no_readonly_by_default(self, enriched_spec_without_readonly, temp_dir):
        """Without readOnly in spec → all attrs have read_only=False."""
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(enriched_spec_without_readonly, spec_file)

        from apigen_copier.parser import OpenAPIParser
        parser = OpenAPIParser(spec_file)
        
        pet = parser.models.get('Pet')
        assert pet is not None, "Pet model not found"
        
        for attr in pet.attributes:
            assert attr.read_only is False, f"Pet.{attr.name} should NOT be readOnly"
            assert attr.write_only is False, f"Pet.{attr.name} should NOT be writeOnly"

    def test_writeonly_captured(self, enriched_spec_with_readonly, temp_dir):
        """writeOnly: true on a field → attr.write_only=True."""
        spec = enriched_spec_with_readonly
        spec['components']['schemas']['Pet']['properties']['password'] = {
            'type': 'string',
            'writeOnly': True
        }
        spec['components']['x-apigen-models']['Pet']['attributes'].append({
            'name': 'password',
            'type': 'String',
            'relational-persistence': {'column': 'password'}
        })
        
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(spec, spec_file)

        from apigen_copier.parser import OpenAPIParser
        parser = OpenAPIParser(spec_file)
        
        pet = parser.models.get('Pet')
        pw_attr = next((a for a in pet.attributes if a.name == 'password'), None)
        assert pw_attr is not None, "Pet.password attribute not found"
        assert pw_attr.write_only is True, "Pet.password should be writeOnly"


class TestModelGeneration:
    """Test that generated model files contain correct Get/Create/Update models.
    
    ISSUE: yaml.dump reorders keys, so 'openapi' didn't appear in first 1KB.
    generate_project() checks the first 1KB for auto-detection.
    SOLUTION: Custom _write_spec() helper writes 'openapi' key first.
    """

    def test_readonly_generates_three_models(self, enriched_spec_with_readonly, temp_dir):
        """Spec with readOnly → generates PetGet, PetCreate, PetUpdate."""
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(enriched_spec_with_readonly, spec_file)

        from apigen_copier.core import generate_project
        generate_project(spec_file, temp_dir)

        pet_model = _find_file(temp_dir, 'pet_model.py')
        assert pet_model is not None, "pet_model.py not generated"
        
        with open(pet_model) as f:
            content = f.read()
        
        assert 'class Pet(BaseModel):' in content, "Base Pet model missing"
        assert 'class PetGet(BaseModel):' in content, "PetGet not generated"
        assert 'class PetCreate(BaseModel):' in content, "PetCreate not generated"
        assert 'class PetUpdate(BaseModel):' in content, "PetUpdate not generated"

    def test_readonly_id_excluded_from_create(self, enriched_spec_with_readonly, temp_dir):
        """PetCreate should NOT have 'id' field (readOnly)."""
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(enriched_spec_with_readonly, spec_file)

        from apigen_copier.core import generate_project
        generate_project(spec_file, temp_dir)

        pet_model = _find_file(temp_dir, 'pet_model.py')
        with open(pet_model) as f:
            content = f.read()
        
        # Extract PetCreate class body
        create_start = content.index('class PetCreate')
        next_class = content.find('class Pet', create_start + 1)
        if next_class == -1:
            next_class = content.find('# Deferred', create_start)
        create_body = content[create_start:next_class]
        
        assert 'id:' not in create_body, "PetCreate should NOT contain 'id' (readOnly field)"
        assert 'name:' in create_body, "PetCreate should contain 'name'"

    def test_no_readonly_single_model(self, enriched_spec_without_readonly, temp_dir):
        """Spec without readOnly/writeOnly → only base model, no Get/Create/Update."""
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(enriched_spec_without_readonly, spec_file)

        from apigen_copier.core import generate_project
        generate_project(spec_file, temp_dir)

        pet_model = _find_file(temp_dir, 'pet_model.py')
        with open(pet_model) as f:
            content = f.read()
        
        assert 'class Pet(BaseModel):' in content, "Base Pet model missing"
        assert 'PetGet' not in content, "PetGet should NOT exist (no readOnly)"
        assert 'PetCreate' not in content, "PetCreate should NOT exist (no readOnly)"


# ── OPENAPI-001: StandardResponse Tests ──

class TestStandardResponseDetection:
    """Test StandardResponse[T] detection and generation.
    
    ISSUE: ApigenProject (project contract) had no standard_response_operations field.
    SOLUTION: Added standard_response_operations: Optional[List[Any]] to ApigenProject.
    """

    def test_no_standard_response_by_default(self, enriched_spec_without_readonly, temp_dir):
        """Spec without standard-response-operations → no StandardResponse."""
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(enriched_spec_without_readonly, spec_file)

        from apigen_copier.core import generate_project
        generate_project(spec_file, temp_dir)

        found = _find_file(temp_dir, 'standard_response.py')
        assert found is None, "standard_response.py should NOT be generated without opt-in"

    def test_standard_response_with_optin(self, enriched_spec_without_readonly, temp_dir):
        """Spec with standard-response-operations → generates StandardResponse module."""
        spec = enriched_spec_without_readonly
        spec['x-apigen-project']['standard-response-operations'] = [
            {"op": "move", "from": "/data", "path": "/result/data"}
        ]
        
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(spec, spec_file)

        from apigen_copier.core import generate_project
        generate_project(spec_file, temp_dir)

        found = _find_file(temp_dir, 'standard_response.py')
        assert found is not None, "standard_response.py should be generated with standard-response-operations"

    def test_standard_response_routes_import(self, enriched_spec_without_readonly, temp_dir):
        """With standard-response-operations → routes import StandardResponse."""
        spec = enriched_spec_without_readonly
        spec['x-apigen-project']['standard-response-operations'] = [
            {"op": "move", "from": "/data", "path": "/result/data"}
        ]
        
        spec_file = os.path.join(temp_dir, 'test_spec.yaml')
        _write_spec(spec, spec_file)

        from apigen_copier.core import generate_project
        generate_project(spec_file, temp_dir)

        # Check any routes file contains StandardResponse import
        route_found = False
        for root, dirs, files in os.walk(temp_dir):
            for fn in files:
                if fn.endswith('_routes.py'):
                    with open(os.path.join(root, fn)) as f:
                        content = f.read()
                    if 'from src.application.schemas.standard_response import StandardResponse' in content:
                        route_found = True
                        break
        assert route_found, "Route files should import StandardResponse when standard-response-operations is set"
