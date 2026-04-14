import os
import shutil
import pytest
from apigen_copier.parser import OpenAPIParser, RouterSchema

def test_ensure_strict_endpoint_generation():
    """
    Verifies that the parser does NOT backfill missing CRUD operations.
    It should only create endpoints explicitly defined in the OpenAPI spec.
    """
    # 1. Create a minimal OpenAPI spec with ONLY ONE endpoint (GET /users)
    spec_content = """
openapi: 3.0.0
info:
  title: Strict Test
  version: 1.0.0
x-apigen-project:
  name: Strict Test
  version: 1.0.0
  description: Test description
  data-driver: postgresql
paths:
  /users:
    x-apigen-binding:
      model: User
      persistence:
        table: users
    get:
      summary: List users
      operationId: listUsers
      responses:
        '200':
          description: OK
"""
    
    test_dir = os.path.dirname(os.path.abspath(__file__))
    spec_path = os.path.join(test_dir, "temp_strict_test.yaml")
    
    with open(spec_path, "w") as f:
        f.write(spec_content)
        
    try:
        # 2. Parse the spec
        parser = OpenAPIParser(spec_path)
        
        # 3. Assertions
        assert "User" in parser.routers, "Router for User should be created"
        user_router: RouterSchema = parser.routers["User"]
        
        print(f"Generated endpoints: {[ep.method for ep in user_router.endpoints]}")
        
        # Should have exactly 1 endpoint
        assert len(user_router.endpoints) == 1, \
            f"Expected 1 endpoint, found {len(user_router.endpoints)}"
            
        endpoint = user_router.endpoints[0]
        assert endpoint.method == "GET"
        assert endpoint.name == "listUsers"
        
        # Explicit check for missing ops
        methods = [ep.method for ep in user_router.endpoints]
        assert "POST" not in methods, "POST should not be backfilled"
        assert "DELETE" not in methods, "DELETE should not be backfilled"
        assert "PUT" not in methods, "PUT should not be backfilled"

    finally:
        if os.path.exists(spec_path):
            os.remove(spec_path)

if __name__ == "__main__":
    test_ensure_strict_endpoint_generation()
