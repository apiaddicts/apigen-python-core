import os

def verify_file_content(path, expected_strings):
    if not os.path.exists(path):
        print(f"FAIL: {path} does not exist")
        return False
    
    with open(path, 'r') as f:
        content = f.read()
        
    all_found = True
    for s in expected_strings:
        if s not in content:
            print(f"FAIL: '{s}' not found in {path}")
            all_found = False
            
    if all_found:
        print(f"PASS: {path}")
    return all_found

def verify_project(base_dir, project_slug, is_pyscaffold=False):
    print(f"\nVerifying {base_dir}...")
    if is_pyscaffold:
        # PyScaffold uses src/package_name structure
        models_path = os.path.join(base_dir, project_slug, "src", project_slug, "models.py")
        schemas_path = os.path.join(base_dir, project_slug, "src", project_slug, "schemas.py")
        routers_path = os.path.join(base_dir, project_slug, "src", project_slug, "routers.py")
    else:
        models_path = os.path.join(base_dir, project_slug, "src", "models.py")
        schemas_path = os.path.join(base_dir, project_slug, "src", "schemas.py")
        routers_path = os.path.join(base_dir, project_slug, "src", "routers.py")
    
    expected_models = ["class Patient(Base):", "class Room(Base):", "class Stay(Base):"]
    expected_schemas = ["class PatientBase(BaseModel):", "class RoomBase(BaseModel):", "class StayBase(BaseModel):"]
    expected_routers = ["@router.get(\"/patients/\"", "@router.get(\"/rooms/\"", "@router.get(\"/stays/\""]
    
    v1 = verify_file_content(models_path, expected_models)
    v2 = verify_file_content(schemas_path, expected_schemas)
    v3 = verify_file_content(routers_path, expected_routers)
    
    readme_path = os.path.join(os.path.dirname(base_dir), "README.md")
    if is_pyscaffold:
         readme_path = os.path.join(os.path.dirname(base_dir), "README.md") 
         
    v4 = False
    if os.path.exists(readme_path):
        print(f"PASS: {readme_path} exists")
        v4 = True
    else:
        print(f"FAIL: {readme_path} does not exist")
    
    return v1 and v2 and v3 and v4

if __name__ == "__main__":
    base_path = os.path.dirname(os.path.abspath(__file__))
    # Go up one level from resources/ to root
    root_path = os.path.dirname(base_path)
    
    results = []
    results.append(verify_project(os.path.join(root_path, "technologies/cookiecutter/output"), "hospital_api_cookiecutter"))
    results.append(verify_project(os.path.join(root_path, "technologies/cruft/output"), "hospital_api_cruft"))
    results.append(verify_project(os.path.join(root_path, "technologies/copier/output"), "hospital_api_copier"))
    results.append(verify_project(os.path.join(root_path, "technologies/pyscaffold/output"), "hospital_api_pyscaffold", is_pyscaffold=True))
    
    if all(results):
        print("\nALL CHECKS PASSED!")
        exit(0)
    else:
        print("\nSOME CHECKS FAILED.")
        exit(1)
