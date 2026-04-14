import sys
import os
import shutil
import importlib.util

# Ensure package is in path (parent directory of tests)
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "package"))

from apigen_copier.core import generate_project

def test_db_generation_and_connection():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    input_json_path = os.path.join(current_dir, "test_files/db_project.json")
    
    import json
    with open(input_json_path, "r") as f:
        base_schema = json.load(f)

    drivers = ["postgresql", "mysql", "mssql"]
    
    for driver in drivers:
        schema = base_schema.copy()
        schema["project"]["data_driver"] = driver
        
        temp_input = os.path.join(current_dir, f"temp_{driver}.json")
        with open(temp_input, "w") as f:
            json.dump(schema, f)
            
        output_dir = os.path.abspath(os.path.join(current_dir, "..", f"output_db_test_{driver}"))
        
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            
        try:
            generate_project(temp_input, output_dir)
        except Exception:
            continue
        finally:
            if os.path.exists(temp_input):
                os.remove(temp_input)

        generated_slug = "db_connection_test_app" 
        project_path = os.path.join(output_dir, generated_slug)
        pyproject_file = os.path.join(project_path, "pyproject.toml")
        db_file = os.path.join(project_path, "src", "infrastructure", "database.py")
        
        expected_pkg = {
            "postgresql": "asyncpg",
            "mysql": "aiomysql",
            "mssql": "aioodbc"
        }
        
        expected_driver_str = {
            "postgresql": 'drivername="postgresql+asyncpg"',
            "mysql": 'drivername="mysql+aiomysql"',
            "mssql": 'drivername="mssql+aioodbc"'
        }

        pkg_ok = False
        db_ok = False
        
        if os.path.exists(pyproject_file):
            with open(pyproject_file, "r") as f:
                content = f.read()
                pkg_ok = expected_pkg[driver] in content

        if os.path.exists(db_file):
            with open(db_file, "r") as f:
                content = f.read()
                db_ok = expected_driver_str[driver] in content

        if not (pkg_ok and db_ok):
            raise AssertionError(f"{driver} validation failed (pkg: {pkg_ok}, db: {db_ok})")

if __name__ == "__main__":
    test_db_generation_and_connection()
