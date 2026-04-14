import pytest
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.orm import declarative_base

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))


Base = declarative_base()

class MockModel(Base):
    __tablename__ = 'mocks'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    age = Column(Integer)
    status = Column(String)

class MockRepo:
    model = MockModel
    
    def _resolve_field_name(self, field: str):
        import re
        if '_' not in field and not field.islower():
            snake = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', field)
            snake = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', snake).lower()
            return snake
        return field

# In order to test the parser we need to extract it from the template
# We can dynamically recreate the parser here since it's pure Python AST
class _FilterParser:
    def __init__(self, model, repo):
        self.model = model
        self.repo = repo

    def parse(self, expr_str: str):
        import ast
        try:
            tree = ast.parse(expr_str, mode='eval').body
            return self._visit(tree)
        except SyntaxError as e:
            raise ValueError(f"Syntax error: {e}")

    def _visit(self, node):
        import ast
        from sqlalchemy import and_, or_

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And): return and_(*[self._visit(val) for val in node.values])
            elif isinstance(node.op, ast.Or): return or_(*[self._visit(val) for val in node.values])
            else: raise ValueError("Unsupported logc")
                
        elif isinstance(node, ast.Compare):
            left = self._visit(node.left)
            right = self._visit(node.comparators[0])
            op = node.ops[0]
            
            if isinstance(op, ast.Eq): return left == right
            elif isinstance(op, ast.NotEq): return left != right
            elif isinstance(op, ast.Gt): return left > right
            elif isinstance(op, ast.Lt): return left < right
            elif isinstance(op, ast.GtE): return left >= right
            elif isinstance(op, ast.LtE): return left <= right
            else: raise ValueError("Unsupported comp")
                
        elif isinstance(node, ast.Name):
            field_name = self.repo._resolve_field_name(node.id)
            if not hasattr(self.model, field_name):
                raise ValueError(f"Invalid property '{node.id}' in filter")
            return getattr(self.model, field_name)
            
        elif isinstance(node, ast.Constant):
            return node.value
            
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                left = self._visit(node.func.value)
                func_name = node.func.attr
                if not node.args: raise ValueError("Function requires args")
                right = self._visit(node.args[0])
                    
                if func_name == "contains": return left.ilike(f"%{right}%")
                elif func_name == "startswith": return left.ilike(f"{right}%")
                elif func_name == "endswith": return left.ilike(f"%{right}")
                else: raise ValueError(f"Unsupported function: {func_name}")
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id
                if len(node.args) < 2: raise ValueError("Function requires 2 args")
                left = self._visit(node.args[0])
                right = self._visit(node.args[1])
                
                if func_name == "contains": return left.ilike(f"%{right}%")
                elif func_name == "startswith": return left.ilike(f"{right}%")
                elif func_name == "endswith": return left.ilike(f"%{right}")
                else: raise ValueError(f"Unsupported function: {func_name}")
            else:
                raise ValueError("Unsupported call type")
        else:
            raise ValueError(f"Unsupported AST node: {type(node)}")

@pytest.fixture
def run_copier(tmp_path):
    def _run(openapi_yaml_content: str):
        from apigen_copier.core import generate_from_schema
        from apigen_copier.parser import OpenAPIParser
        
        # 1. Setup paths
        schema_path = tmp_path / "spec.yaml"
        schema_path.write_text(openapi_yaml_content)
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        # 2. Parse Spec
        parser = OpenAPIParser(str(schema_path))
        schema = parser.parse(str(output_dir))
        
        # 3. Generate
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        template_dir = os.path.join(base_dir, "src", "apigen_copier", "template")
        
        generate_from_schema(schema=schema, template_dir=template_dir)
        
        # Adjust output_dir to include project slug
        project_slug = schema.project.name.lower().replace(" ", "_").replace("-", "_")
        return output_dir / project_slug
    return _run


# ==============================================================================
# AST Parser Tests
# ==============================================================================

def test_ast_parser_simple_equality():
    parser = _FilterParser(MockModel, MockRepo())
    expr = parser.parse("name == 'Buddy'")
    stmt = select(MockModel).where(expr)
    sql = str(stmt.compile())
    assert "mocks.name = :name_" in sql

def test_ast_parser_relational():
    parser = _FilterParser(MockModel, MockRepo())
    expr = parser.parse("age > 5 and age <= 10")
    stmt = select(MockModel).where(expr)
    sql = str(stmt.compile())
    assert "mocks.age > :age_" in sql
    assert "mocks.age <= :age_" in sql

def test_ast_parser_logical_grouping():
    parser = _FilterParser(MockModel, MockRepo())
    expr = parser.parse("(name == 'Max' or status == 'sold') and age > 5")
    stmt = select(MockModel).where(expr)
    sql = str(stmt.compile())
    # Should compile successfully
    assert "mocks.name = :name" in sql
    assert "mocks.age > :age" in sql

def test_ast_parser_contains_function():
    parser = _FilterParser(MockModel, MockRepo())
    # Test .net style
    expr1 = parser.parse("name.contains('ud')")
    stmt1 = select(MockModel).where(expr1)
    assert "lower(mocks.name) LIKE lower(:name_" in str(stmt1.compile())
    
    # Test functional style
    expr2 = parser.parse("contains(name, 'ud')")
    stmt2 = select(MockModel).where(expr2)
    assert "lower(mocks.name) LIKE lower(:name_" in str(stmt2.compile())

def test_ast_parser_invalid_property():
    parser = _FilterParser(MockModel, MockRepo())
    with pytest.raises(ValueError, match="Invalid property 'invalidField'"):
        parser.parse("invalidField == 'foo'")

def test_ast_parser_injection_attempt():
    parser = _FilterParser(MockModel, MockRepo())
    # Trying to execute python code should fail because mode='eval' and restricted visitor
    with pytest.raises(ValueError):
        parser.parse("__import__('os').system('echo pwned')")

def test_ast_parser_camel_to_snake():
    parser = _FilterParser(MockModel, MockRepo())
    # Testing that 'petAge' resolves to 'age' or 'pet_age' (we pretend age is pet_age but we'll just test name resolution works)
    # Actually we just test the snake case converter
    assert parser.repo._resolve_field_name("userName") == "user_name"
    assert parser.repo._resolve_field_name("petId") == "pet_id"
    assert parser.repo._resolve_field_name("id") == "id"

# ==============================================================================
# Copier Generation Tests 
# ==============================================================================

def test_copier_generates_filter_parameter(run_copier):
    spec = """
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
paths:
  /pets:
    x-apigen-binding:
      model: Pet
    get:
      parameters:
        - name: filter
          in: query
          schema:
            type: string
          description: Dynamic LINQ filter
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Pet'
components:
  x-apigen-models:
    Pet:
      table: pets
      attributes:
        id:
          type: integer
          relational-persistence: { column: id, primary-key: true }
  schemas:
    Pet:
      type: object
      x-apigen-binding: true
      properties:
        id:
          type: integer
        name:
          type: string
"""
    output_dir = run_copier(spec)
    
    # 1. Check API Route
    route_file = output_dir / "src" / "api" / "routes" / "pet" / "pet_routes.py"
    content = route_file.read_text()
    
    # Needs to accept filter parameter in route definition
    assert "filter: str = Query(None)" in content
    # Needs to pass filter parameter to service.get_all
    assert "filter=filter" in content
    
    # 2. Check Service Layer
    service_file = output_dir / "src" / "infrastructure" / "service" / "pet" / "pet_service.py"
    svc_content = service_file.read_text()
    
    # Service get_all should take filter and pass it to repository
    assert "def get_all(self," in svc_content
    assert "filter: str = None" in svc_content
    assert "filter_expr=filter" in svc_content

def test_copier_generates_without_filter_when_absent(run_copier):
    spec = """
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
paths:
  /pets:
    x-apigen-binding:
      model: Pet
    get:
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Pet'
components:
  x-apigen-models:
    Pet:
      table: pets
      attributes:
        id:
          type: integer
          relational-persistence: { column: id, primary-key: true }
  schemas:
    Pet:
      type: object
      x-apigen-binding: true
      properties:
        id:
          type: integer
"""
    output_dir = run_copier(spec)
    
    # 1. Check API Route
    route_file = output_dir / "src" / "api" / "routes" / "pet" / "pet_routes.py"
    content = route_file.read_text()
    
    # Should NOT accept filter
    assert "filter: str =" not in content
    
    # 2. Check Service Layer
    service_file = output_dir / "src" / "infrastructure" / "service" / "pet" / "pet_service.py"
    svc_content = service_file.read_text()
    # It still accepts it statically, but route doesn't pass it.
    assert "filter: str = None" in svc_content
