
import pytest
from apigen_copier.parser import OpenAPIParser, ModelAttribute
from apigen_copier.contracts import ModelContract

class TestSmartMapping:
    
    @pytest.fixture
    def mock_parser(self):
        # Create a parser but bypass __init__ logic that reads files
        parser = OpenAPIParser.__new__(OpenAPIParser)
        parser.raw_spec = {"openapi": "3.0.0", "components": {"schemas": {}}}
        parser.models = {} 
        return parser

    def test_smart_mapping_array_conversion(self, mock_parser):
        """
        Verify that an array field in OpenAPI is marked for JSON conversion 
        if the persistence model expects a String (Smart Mapping).
        """
        # 1. Setup a model with a 'String' attribute that maps to an 'array' in OpenAPI
        # This simulates the state where 'photoUrls' is a String in the Entity (DB) but Array in API.
        
        model_name = "Pet"
        attr_name = "photoUrls"
        
        # Pre-existing model attribute (from x-apigen-models)
        # Note: In the parser logic, if the attribute exists as 'String', 
        # and schema says 'array', it should trigger conversion.
        
        attr = ModelAttribute(name=attr_name, type="String")
        mock_parser.models[model_name] = ModelContract(
            name=model_name,
            attributes=[attr]
        )
        
        # 2. Define the schema with 'array' type for this property
        schema = {
            "type": "object",
            "properties": {
                attr_name: {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
        
        # 3. Process the schema
        # We simulate _process_single_schema logic
        mock_parser._process_single_schema(schema, model_name)
        
        # 4. Assertions
        updated_attr = mock_parser.models[model_name].attributes[0]
        
        assert updated_attr.name == attr_name
        assert updated_attr.is_array is True # Schema said array
        assert updated_attr.has_json_conversion is True # Smart Mapping should trigger
