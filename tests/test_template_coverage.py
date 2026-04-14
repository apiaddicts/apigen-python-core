
import pytest
import sys
import os
import shutil
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy.orm import RelationshipProperty, ColumnProperty

# Import necessary modules from apigen_copier
from apigen_copier.schemas import RESTProjectSchema, OpenApiProjectSchema, RouterSchema, EndpointSchema
from apigen_copier.contracts import ModelContract, ModelAttribute, RelationalPersistence
from apigen_copier.core import generate_from_schema

class TestBaseRepositoryTemplate:
    
    @pytest.fixture(scope="class")
    def generated_repo_class(self):
        """
        Generates a dummy project and imports the BaseRepository class dynamically.
        """
        output_path = os.path.join(os.getcwd(), "temp_repo_test")
        
        # 1. Create a minimal schema to trigger generation
        project_info = OpenApiProjectSchema(
            name="Repo Test Project", 
            version="0.0.1",
            description="Test for BaseRepository",
            **{"data-driver": "postgresql"}
        )
        
        # Needs at least one model to generate repository
        user_model = ModelContract(
            name="User",
            relational_persistence=RelationalPersistence(table="users"),
            attributes=[ModelAttribute(name="id", type="Integer")]
        )

        schema = RESTProjectSchema(
            project=project_info,
            entities={"User": user_model},
            routers={},
            output_dir=output_path
        )
        
        # 2. Generate
        generate_from_schema(schema)
        
        # 3. Import BaseRepository dynamically
        # The generator creates a folder based on project name (slugified)
        project_slug = "repo_test_project" 
        repo_path = os.path.join(output_path, project_slug, "src", "domain", "repository")
        src_path = os.path.join(output_path, project_slug, "src")
        sys.path.append(src_path) # Add src to path for internal imports
        
        try:
            # We need to mock 'src.infrastructure.database' typically used in base_repository
            # But since we are resolving imports, let's see if we can just import the file directly
            import importlib.util
            spec = importlib.util.spec_from_file_location("base_repository", os.path.join(repo_path, "base_repository.py"))
            module = importlib.util.module_from_spec(spec)
            
            # MOCK dependencies that MainRepository imports
            sys.modules["src.infrastructure.database"] = MagicMock()
            
            spec.loader.exec_module(module)
            return module.BaseRepository
        finally:
            # Cleanup at end of session would be better, but for now we leave it for inspection if fails
            pass

    def test_apply_selection_logic(self, generated_repo_class):
        """
        Unit test for _apply_selection logic in the generated BaseRepository.
        """
        # Mock Session and Model
        mock_session = AsyncMock()
        mock_model = MagicMock()
        repo = generated_repo_class(mock_model, mock_session)
        
        # Test 1: Empty selection returns stmt unmodified
        mock_stmt = MagicMock()
        result = repo._apply_selection(mock_stmt, selection=None)
        assert result == mock_stmt
        
        # Test 2: Parse Selection
        selection_str = "id,name,category.name"
        tree = repo._parse_selection(selection_str)
        assert "id" in tree["fields"]
        assert "name" in tree["fields"]
        assert "category" in tree["relations"]
        assert "name" in tree["relations"]["category"]["fields"]

    def test_to_dict_logic(self, generated_repo_class):
        """
        Unit test for _to_dict logic.
        """
        mock_session = AsyncMock()
        mock_model = MagicMock()
        repo = generated_repo_class(mock_model, mock_session)
        
        # Mock an item with attributes
        item = MagicMock()
        item.id = 1
        item.name = "Test"
        item.category = MagicMock()
        item.category.name = "Cat1"
        item.tags = []
        
        # Selection: id, name, category.name
        selection = "id,name,category.name"
        
        result = repo._to_dict(item, selection)
        
        assert result["id"] == 1
        assert result["name"] == "Test"
        assert result["category"]["name"] == "Cat1"
        # Ensure unselected fields are not present (implied by dict construction)
        
    def test_apply_expansion_logic(self, generated_repo_class):
        """
        Unit test for _apply_expansion.
        """
        mock_session = AsyncMock()
        mock_model = MagicMock()
        
        # Setup model introspection for expansion
        # We need `generated_repo_class` to verify if it calls options/selectinload
        # This is harder to mock perfectly without SQLAlchemy structure, 
        # but we can verify it parses string and attempts to set options.
        repo = generated_repo_class(mock_model, mock_session)
        
        mock_stmt = MagicMock()
        repo._apply_expansion(mock_stmt, expand="category")
        
        # Verify it attempted to getattr(model, 'category')
        # Since 'category' doesn't exist on our Mock model, the safe implementation should handle it or fail gracefully.
        # The implementation loops and checks `hasattr`. 
        # So we should expect 0 calls to options if attributes don't exist.
        
        mock_stmt.options.assert_not_called()
