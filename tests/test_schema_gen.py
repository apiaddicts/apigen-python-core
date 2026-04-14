import sys
import os
import shutil

# Add package to path to import it directly
sys.path.append(os.path.join(os.getcwd(), "package"))

from apigen_copier.schemas import RESTProjectSchema, OpenApiProjectSchema, RouterSchema, EndpointSchema
from apigen_copier.contracts import ModelContract, ModelAttribute, RelationalPersistence, BindingContract
from apigen_copier.core import generate_from_schema

def test_generation():
    output_path = os.path.join(os.getcwd(), "temp_test_output")
    
    # 1. Create the simplified components
    project_info = OpenApiProjectSchema(
        name="Test Project", 
        version="0.0.1",
        description="A test project",
        **{"data-driver": "postgresql"}  # <-- Testing parameter passing with alias
    )
    
    # Dummy entity
    user_entity = ModelContract(
        relational_persistence=RelationalPersistence(table="users"),
        attributes=[
            ModelAttribute(name="id", type="Integer"),
            ModelAttribute(name="name", type="String")
        ]
    )
    
    # Dummy router
    user_router = RouterSchema(
        entity="User",
        mapping="/users",
        endpoints=[
            EndpointSchema(method="get", name="getUsers", mapping="/")
        ]
    )
    
    # 2. Assemble the full schema
    schema = RESTProjectSchema(
        project=project_info,
        entities={"User": user_entity},
        routers={"users": user_router},
        output_dir=output_path
    )
    
    print(f"Testing generation with enriched schema...")
    print(f"Data Driver: {schema.project.data_driver}")
    
    result_path = generate_from_schema(schema)
    
    print(f"Result path: {result_path}")
    
    if result_path == os.path.abspath(output_path):
        print("VERIFICATION SUCCESS: Path matches")
    else:
        print(f"VERIFICATION FAILED: {result_path} != {os.path.abspath(output_path)}")

    # Cleanup
    if os.path.exists(output_path):
        shutil.rmtree(output_path)

if __name__ == "__main__":
    test_generation()
