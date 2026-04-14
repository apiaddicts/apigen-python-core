
import pytest
from apigen_copier.parser import OpenAPIParser, ModelAttribute

class TestParserAttributes:
    
    @pytest.fixture
    def mock_parser(self):
        # Create a parser but bypass __init__ logic that reads files
        parser = OpenAPIParser.__new__(OpenAPIParser)
        parser.raw_spec = {"openapi": "3.0.0", "paths": {}}
        parser.models = {} 
        return parser

    def test_normalize_attributes_list(self, mock_parser):
        """Verify standard list format is preserved."""
        raw = [
            {"name": "id", "type": "string"},
            {"name": "age", "type": "int"}
        ]
        result = mock_parser._normalize_attributes(raw)
        
        assert len(result) == 2
        assert result[0]['name'] == 'id'
        assert result[0]['type'] == 'String' # Normalized
        assert result[1]['type'] == 'Integer' # Normalized

    def test_normalize_attributes_dict_simple(self, mock_parser):
        """Verify dictionary format uses keys as names."""
        raw = {
            "uuid": {"type": "string"},
            "age": {"type": "integer"}
        }
        result = mock_parser._normalize_attributes(raw)
        
        assert len(result) == 2
        # Order is preserved in recent python versions, but we find by name
        uuid = next(r for r in result if r['name'] == 'uuid')
        assert uuid['type'] == 'String'
        
        age = next(r for r in result if r['name'] == 'age')
        assert age['type'] == 'Integer'

    def test_normalize_attributes_dict_ambiguity(self, mock_parser):
        """Verify dictionary key overrides conflicted internal name and adds warning."""
        raw = {
            "myKey": {"name": "conflictName", "type": "string"}
        }
        result = mock_parser._normalize_attributes(raw)
        
        attr = result[0]
        assert attr['name'] == 'myKey' # Key wins
        assert "warning" in attr
        assert "conflictName" in attr['warning']
        assert "myKey" in attr['warning']

    def test_flatten_composed_id(self, mock_parser):
        """Verify ComposedID is flattened into sub-attributes."""
        raw = [
            {
                "type": "ComposedID", 
                "attributes": [
                    {"name": "part1", "type": "string"},
                    {"name": "part2", "type": "int"}
                ]
            }
        ]
        result = mock_parser._normalize_attributes(raw)
        
        assert len(result) == 2
        p1 = next(r for r in result if r['name'] == 'part1')
        p2 = next(r for r in result if r['name'] == 'part2')
        
        assert p1['relational-persistence']['primary-key'] is True
        assert p2['relational-persistence']['primary-key'] is True
        assert p2['type'] == 'Integer' # Recursive normalization

    def test_type_normalization(self, mock_parser):
        """Verify various type strings map correctly."""
        assert mock_parser._normalize_type("uuid") == "String"
        assert mock_parser._normalize_type("long") == "Long"
        assert mock_parser._normalize_type("date") == "LocalDate"
        assert mock_parser._normalize_type("unknown") == "unknown"
