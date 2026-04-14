"""
Base Repository - Generic CRUD operations for persistence.
"""
import re
from typing import TypeVar, Generic, List, Optional, Type, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc, desc, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import load_only, selectinload, noload, RelationshipProperty, ColumnProperty, Load
from src.infrastructure.database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""
    
    def __init__(self, model: Type[T], session: AsyncSession):
        self.model = model
        self.session = session
    
    async def get_by_id(self, *ids: Any, expand: str = None, selection: str = None) -> Optional[Any]:
        """Get entity by ID (supports composite keys) with optional expansion and selection."""
        stmt = select(self.model)
        pk_keys = [key.name for key in inspect(self.model).primary_key]
        
        if len(ids) == 1 and len(pk_keys) == 1:
            stmt = stmt.where(getattr(self.model, pk_keys[0]) == ids[0])
        elif len(ids) == len(pk_keys):
            for i, key in enumerate(pk_keys):
                stmt = stmt.where(getattr(self.model, key) == ids[i])
        else:
            raise ValueError(f"Expected {len(pk_keys)} IDs, got {len(ids)}")
            
        stmt = self._apply_expansion(stmt, expand)
        stmt = self._load_collections(stmt, expand)
        stmt = self._apply_selection(stmt, selection, expand=expand)
        
        result = await self.session.execute(stmt)
        item = result.scalars().first()
        
        if not item:
            return None
        if selection:
            return self._to_dict(item, selection, expand)
        return self._to_default_dict(item, expand)
    
    async def get_all(self, limit: int = 20, offset: int = 0, expand: str = None, orderby: str = None, selection: str = None, filter_expr: str = None, **kwargs) -> List[Any]:
        """Get all entities with optional expansion, sorting, selection, filtering, and pagination."""
        stmt = select(self.model)
        stmt = self._apply_expansion(stmt, expand)
        stmt = self._load_collections(stmt, expand)
        stmt = self._apply_filter(stmt, filter_expr)
        stmt = self._apply_sorting(stmt, orderby)
        stmt = self._apply_selection(stmt, selection, expand=expand)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        items = result.scalars().all()
        
        if selection:
            return [self._to_dict(item, selection, expand) for item in items]
        
        return [self._to_default_dict(item, expand) for item in items]

    def _to_dict(self, item, selection: str, expand: str = None):
        """Helper to safely convert ORM object to dict with selected fields."""
        if not item:
            return None
        
        selection_tree = self._parse_selection(selection) if isinstance(selection, str) else (selection or {'fields': [], 'relations': {}})
        data = self._build_selection_data(item, selection_tree)
        self._merge_expanded_relations(data, item, selection_tree, expand)
        return data

    def _build_selection_data(self, item, selection_tree: Dict) -> Dict:
        """Build dict from selected fields and relations."""
        data = {}
        for field in selection_tree.get('fields', []):
            resolved = self._resolve_field_name(field, type(item))
            if hasattr(item, resolved):
                data[field] = getattr(item, resolved)  # Keep original camelCase key
        for rel_name, sub_tree in selection_tree.get('relations', {}).items():
            if hasattr(item, rel_name):
                val = getattr(item, rel_name)
                data[rel_name] = self._process_relation_value(val, sub_tree) if val is not None else None
        return data

    def _merge_expanded_relations(self, data: Dict, item, selection_tree: Dict, expand: str):
        """Add expanded relations not already present in the selection tree."""
        if not expand or not isinstance(expand, str):
            return
        expanded_roots = {p.strip().split('.')[0] for p in expand.split(',')}
        selected_roots = set(selection_tree.get('relations', {}).keys())
        for rel_name in expanded_roots - selected_roots:
            if hasattr(item, rel_name):
                val = getattr(item, rel_name)
                data[rel_name] = self._relation_to_dict(val) if val is not None else None

    def _relation_to_dict(self, val):
        """Convert a loaded relation value to a dict (all columns + loaded relations)."""
        if isinstance(val, list):
            return [self._relation_to_dict(v) for v in val]
        return self._entity_to_full_dict(val)

    def _entity_to_full_dict(self, entity) -> Dict:
        """Convert a single entity to dict with columns and loaded relations as full objects."""
        fk_col_keys = self._get_fk_col_keys(type(entity))
        unloaded = inspect(entity).unloaded
        result = self._collect_columns(entity, fk_col_keys)
        for prop in inspect(type(entity)).attrs:
            if not isinstance(prop, RelationshipProperty):
                continue
            if prop.key not in unloaded:
                rel_val = getattr(entity, prop.key)
                if rel_val is not None:
                    result[prop.key] = self._relation_to_dict(rel_val)
                    continue
            fk_val = self._get_fk_for_relation(entity, prop)
            if fk_val is not None:
                result[prop.key] = fk_val
        return result

    def _process_relation_value(self, val, sub_tree):
        """Helper to process a relationship value (list or single item)."""
        if isinstance(val, list):
            return [self._to_dict(v, sub_tree) for v in val]
        return self._to_dict(val, sub_tree)

    def _apply_sorting(self, stmt, orderby: str):
        """Apply sorting to the query."""
        if not orderby:
            return stmt

        for order in orderby.split(','):
            parts = order.strip().split()
            field_name = self._resolve_field_name(parts[0])
            direction = parts[1].lower() if len(parts) > 1 else 'asc'

            if hasattr(self.model, field_name):
                attr = getattr(self.model, field_name)
                stmt = stmt.order_by(desc(attr) if direction == 'desc' else asc(attr))
        return stmt

    def _apply_selection(self, stmt, selection: str, expand: str = None):
        """Apply field selection to the query."""
        if not selection and not expand:
            return stmt

        selection_tree = self._parse_selection(selection)
        
        stmt = self._apply_root_load_only(stmt, selection_tree, expand)
        stmt = self._apply_relationship_loaders(stmt, selection_tree)
        stmt = self._apply_noload(stmt, selection_tree, expand)
        
        return stmt

    def _apply_root_load_only(self, stmt, selection_tree: Dict, expand: str = None):
        """Helper to apply load_only for root fields, including FK columns for expanded relations."""
        root_fields = selection_tree.get('fields', [])
        if not root_fields:
            return stmt

        load_only_columns = self._collect_load_only_columns(root_fields, selection_tree)
        if expand:
            self._add_fk_columns_for_expand(load_only_columns)
        if load_only_columns:
            stmt = stmt.options(load_only(*load_only_columns))
        return stmt

    def _collect_load_only_columns(self, fields: List[str], selection_tree: Dict) -> List:
        """Classify fields into column loads and relation tree entries."""
        columns = []
        for f in fields:
            resolved = self._resolve_field_name(f)
            if not hasattr(self.model, resolved):
                continue
            attr = getattr(self.model, resolved)
            if not hasattr(attr, 'property'):
                continue
            if isinstance(attr.property, ColumnProperty):
                columns.append(attr)
            elif isinstance(attr.property, RelationshipProperty):
                self._ensure_relation_in_tree(selection_tree, resolved)
        return columns

    def _add_fk_columns_for_expand(self, load_only_columns: List):
        """Add FK columns from the table to ensure selectinload can resolve relations."""
        for col in self.model.__table__.columns:
            if col.foreign_keys and hasattr(self.model, col.name):
                fk_attr = getattr(self.model, col.name)
                if fk_attr not in load_only_columns:
                    load_only_columns.append(fk_attr)

    def _ensure_relation_in_tree(self, tree: Dict, rel_name: str):
        """Ensure a relationship exists in the selection tree."""
        if 'relations' not in tree:
            tree['relations'] = {}
        if rel_name not in tree['relations']:
            tree['relations'][rel_name] = {'fields': [], 'relations': {}}

    def _apply_relationship_loaders(self, stmt, selection_tree: Dict):
        """Helper to apply relationship loaders recursively."""
        loaders = self._build_loaders_recursive(self.model, selection_tree)
        for loader in loaders:
            stmt = stmt.options(loader)
        return stmt

    def _build_loaders_recursive(self, model, tree):
        """Recursive helper to build loaders."""
        loaders = []
        for rel_name, sub_tree in tree.get('relations', {}).items():
            loader = self._create_loader_for_relation(model, rel_name, sub_tree)
            if loader:
                loaders.append(loader)
        return loaders

    def _create_loader_for_relation(self, model, rel_name, sub_tree):
        """Create a loader for a single relationship."""
        if not hasattr(model, rel_name):
            return None
            
        attr = getattr(model, rel_name)
        if not hasattr(attr, 'property') or not isinstance(attr.property, RelationshipProperty):
            return None

        sub_loader = selectinload(attr)
        target_class = attr.property.mapper.class_
        
        # Apply load_only for fields
        sub_fields = sub_tree.get('fields', [])
        if sub_fields:
            valid_fields = [f for f in sub_fields if hasattr(target_class, f)]
            if valid_fields:
                sub_loader = sub_loader.options(load_only(*[getattr(target_class, f) for f in valid_fields]))
        
        # Recurse
        nested_loaders = self._build_loaders_recursive(target_class, sub_tree)
        for nl in nested_loaders:
            sub_loader = sub_loader.options(nl)
            
        return sub_loader

    def _apply_noload(self, stmt, selection_tree: Dict, expand: str):
        """Helper to apply noload for unselected relationships."""
        selected_roots = set(selection_tree.get('relations', {}).keys())
        expanded_paths = set(expand.split(',')) if expand else set()
        expanded_roots = {p.split('.')[0] for p in expanded_paths}
        
        mapper = inspect(self.model)
        for prop in mapper.attrs:
            if isinstance(prop, RelationshipProperty):
                rel_name = prop.key
                if rel_name not in selected_roots and rel_name not in expanded_roots:
                    if prop.lazy in ['selectin', 'joined', False]:
                        stmt = stmt.options(noload(getattr(self.model, rel_name)))
        return stmt

    def _parse_selection(self, selection: str) -> Dict:
        """Parses selection string into a tree structure."""
        tree = {'fields': [], 'relations': {}}
        if not selection:
            return tree
            
        for path in selection.split(','):
            parts = path.strip().split('.')
            self._add_path_to_tree(tree, parts)
        return tree

    def _add_path_to_tree(self, tree: Dict, parts: List[str]):
        """Recursive helper to add a path to the selection tree."""
        current_level = tree
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            
            if is_last:
                if 'fields' not in current_level:
                    current_level['fields'] = []
                current_level['fields'].append(part)
            else:
                if 'relations' not in current_level:
                    current_level['relations'] = {}
                if part not in current_level['relations']:
                    current_level['relations'][part] = {'fields': [], 'relations': {}}
                current_level = current_level['relations'][part]

    def _load_collections(self, stmt, expand: str = None):
        """Auto-load collection relationships (1:N) not covered by expand.
        
        When expand is active, _apply_expansion handles expanded relations.
        This method loads non-expanded collections so they appear as ID lists.
        When no expand, loads all collections.
        """
        expanded_roots = set()
        if expand:
            expanded_roots = {p.strip().split('.')[0] for p in expand.split(',')}

        mapper = inspect(self.model)
        for prop in mapper.relationships:
            if prop.uselist and prop.key not in expanded_roots:
                stmt = stmt.options(selectinload(getattr(self.model, prop.key)))
        return stmt

    def _apply_expansion(self, stmt, expand: str):
        """Apply SQLAlchemy options for relationship expansion.
        
        Handles async-safe loading by applying noload() to all unexpanded
        relationships (preventing MissingGreenlet errors) and building
        correct selectinload chains for multi-level expansion paths.
        """
        if not expand:
            return stmt

        expand_paths = [p.strip() for p in expand.split(',')]
        expand_tree = self._build_expand_tree(expand_paths)
        
        stmt = self._noload_unexpanded_roots(stmt, expand_tree)
        
        for path in expand_paths:
            loader = self._build_loader_for_path(path, expand_tree)
            if loader:
                stmt = stmt.options(loader)
        
        return stmt

    @staticmethod
    def _build_expand_tree(expand_paths: list) -> dict:
        """Build a tree of expanded paths: {root: {child: {grandchild: {}}}}."""
        tree = {}
        for path in expand_paths:
            current = tree
            for part in path.split('.'):
                if part not in current:
                    current[part] = {}
                current = current[part]
        return tree

    def _noload_unexpanded_roots(self, stmt, expand_tree: dict):
        """Noload root-level relationships NOT in the expand tree.
        
        Skips uselist=True (collection) relationships since _load_collections
        handles those with selectinload to show IDs.
        """
        expanded_roots = set(expand_tree.keys())
        for prop in inspect(self.model).attrs:
            if isinstance(prop, RelationshipProperty) and prop.key not in expanded_roots:
                if not prop.uselist:
                    stmt = stmt.options(noload(getattr(self.model, prop.key)))
        return stmt

    def _build_loader_for_path(self, path: str, expand_tree: dict):
        """Build a selectinload chain with noloads for a single expand path."""
        parts = path.split('.')
        current_model = self.model
        loader = None
        
        for i, part in enumerate(parts):
            attr = self._get_relationship_attr(current_model, part)
            if attr is None:
                return None
            
            loader = selectinload(attr) if loader is None else loader.selectinload(attr)
            target_class = attr.property.mapper.class_
            
            sub_tree = self._get_subtree(expand_tree, parts[:i+1])
            loader = self._noload_nested_relationships(loader, target_class, sub_tree)
            current_model = target_class
        
        return loader

    @staticmethod
    def _get_relationship_attr(model, attr_name):
        """Get a relationship attribute from a model, or None if not valid."""
        if not hasattr(model, attr_name):
            return None
        attr = getattr(model, attr_name)
        if not hasattr(attr, 'property') or not isinstance(attr.property, RelationshipProperty):
            return None
        return attr

    @staticmethod
    def _noload_nested_relationships(loader, target_class, sub_tree: dict):
        """Noload nested relationships on target_class NOT present in sub_tree."""
        nested_expanded = set(sub_tree.keys()) if sub_tree else set()
        for prop in inspect(target_class).attrs:
            if isinstance(prop, RelationshipProperty) and prop.key not in nested_expanded:
                loader = loader.options(noload(getattr(target_class, prop.key)))
        return loader

    @staticmethod
    def _get_subtree(tree: dict, parts: list) -> dict:
        """Navigate the expand tree to get the subtree at the given path."""
        current = tree
        for part in parts:
            if part not in current:
                return {}
            current = current[part]
        return current

    async def create(self, entity: T) -> T:
        """Create new entity."""
        try:
            entity = await self.session.merge(entity)
            await self.session.commit()
            await self.session.refresh(entity)
            return self._to_safe_dict(entity)
        except Exception:
            await self.session.rollback()
            raise

    async def create_or_ignore(self, entity: T) -> T:
        """Idempotent create: inserts if not exists, returns existing if found.

        Safe for at-least-once delivery — duplicate messages are silently skipped.
        """
        try:
            entity = await self.session.merge(entity)
            await self.session.commit()
            await self.session.refresh(entity)
            return self._to_safe_dict(entity)
        except IntegrityError:
            await self.session.rollback()
            pk_keys = [col.key for col in inspect(self.model).primary_key]
            pk_values = [getattr(entity, k, None) for k in pk_keys]
            return await self.get_by_id(*pk_values)
        except Exception:
            await self.session.rollback()
            raise

    async def update(self, entity: T) -> T:
        """Update existing entity."""
        try:
            entity = await self.session.merge(entity)
            await self.session.commit()
            await self.session.refresh(entity)
            return self._to_safe_dict(entity)
        except Exception:
            await self.session.rollback()
            raise

    async def delete(self, entity: T) -> None:
        """Delete entity."""
        try:
            await self.session.delete(entity)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def delete_by_id(self, *ids) -> Optional[bool]:
        """Delete entity by primary key(s). Fetches the ORM entity first."""
        try:
            pk_keys = [col.key for col in inspect(self.model).primary_key]
            stmt = select(self.model)
            if len(pk_keys) == 1:
                stmt = stmt.where(getattr(self.model, pk_keys[0]) == ids[0])
            else:
                for i, key in enumerate(pk_keys):
                    stmt = stmt.where(getattr(self.model, key) == ids[i])
            result = await self.session.execute(stmt)
            entity = result.scalars().first()
            if not entity:
                return None
            await self.session.delete(entity)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            raise

    def _to_safe_dict(self, entity) -> Dict:
        """Convert entity to dict with only column values (no lazy-load of relations).
        
        After session.refresh(), relationship attributes are lazy-loadable.
        Accessing them from Pydantic's from_attributes triggers a sync lazy load
        inside an async context, causing 'greenlet_spawn' crash.
        Returning a dict with only column values avoids this entirely.
        Also injects FK values for relations using the relationship key name.
        """
        result = {}
        entity_mapper = inspect(type(entity))
        fk_col_keys = self._get_fk_col_keys(type(entity))
        
        for prop in entity_mapper.attrs:
            if isinstance(prop, ColumnProperty):
                if prop.key in fk_col_keys:
                    continue
                result[prop.key] = getattr(entity, prop.key)
            elif isinstance(prop, RelationshipProperty):
                fk_val = self._get_fk_for_relation(entity, prop)
                if fk_val is not None:
                    result[prop.key] = fk_val
        return result

    def _to_default_dict(self, item, expand: str = None) -> Dict:
        """Convert entity to dict with columns + FK values for unloaded relations."""
        fk_col_keys = self._get_fk_col_keys(type(item))
        unloaded = inspect(item).unloaded
        result = self._collect_columns(item, fk_col_keys)
        self._collect_relations(item, unloaded, result, expand)
        return result

    @staticmethod
    def _collect_columns(entity, fk_col_keys: set) -> Dict:
        """Extract non-FK column values from an entity."""
        result = {}
        for prop in inspect(type(entity)).attrs:
            if isinstance(prop, ColumnProperty) and prop.key not in fk_col_keys:
                result[prop.key] = getattr(entity, prop.key)
        return result

    def _collect_relations(self, entity, unloaded: set, result: Dict, expand: str = None):
        """Resolve relation values: loaded → full dict or IDs, unloaded → FK id."""
        expanded_roots = self._parse_expand_roots(expand)

        for prop in inspect(type(entity)).attrs:
            if not isinstance(prop, RelationshipProperty):
                continue
            if prop.key not in unloaded:
                val = self._resolve_loaded_relation(entity, prop, expanded_roots)
                if val is not None:
                    result[prop.key] = val
                    continue
            fk_val = self._get_fk_for_relation(entity, prop)
            if fk_val is not None:
                result[prop.key] = fk_val

    def _resolve_loaded_relation(self, entity, prop, expanded_roots: set):
        """Resolve a loaded relationship to its serializable form.
        
        Expanded relations return full objects. Non-expanded return {pk: value}.
        """
        rel_val = getattr(entity, prop.key)
        if rel_val is None:
            return None
        if prop.key in expanded_roots:
            return self._relation_to_dict(rel_val)
        if isinstance(rel_val, list):
            return [self._extract_pk(item) for item in rel_val]
        return self._extract_pk(rel_val)

    @staticmethod
    def _parse_expand_roots(expand: str = None) -> set:
        """Parse expand parameter into a set of root relation names."""
        if not expand:
            return set()
        return {p.strip().split('.')[0] for p in expand.split(',')}

    @staticmethod
    def _extract_pk(entity):
        """Extract PK as dict {pk_col_name: value} from an entity.
        
        Returns a dict so the consumer knows the PK column name.
        If entity is already a dict, return as-is.
        """
        if isinstance(entity, dict):
            return entity
        if isinstance(entity, (int, str, float)):
            return entity
        try:
            mapper = inspect(type(entity))
            pk_cols = mapper.primary_key
            return {col.key: getattr(entity, col.key) for col in pk_cols}
        except Exception:
            return entity

    @staticmethod
    def _get_fk_col_keys(model_class) -> set:
        """Get the set of FK column attribute keys for a model.
        
        Only returns columns that have foreign key constraints (e.g. pet_id),
        NOT primary key columns that happen to be referenced by other tables.
        """
        fk_keys = set()
        table = model_class.__table__
        for col in table.columns:
            if col.foreign_keys:
                fk_keys.add(col.key)
        return fk_keys

    @staticmethod
    def _get_fk_for_relation(entity, prop: RelationshipProperty):
        """Get FK as dict {pk_col_name: value} for a relationship.
        
        Returns the FK value wrapped in a dict with the related entity's
        PK column name, so the consumer knows what the value represents.
        """
        for col in prop.local_columns:
            if col.foreign_keys and hasattr(entity, col.key):
                fk_val = getattr(entity, col.key)
                if fk_val is None:
                    return None
                # Get the related entity's PK column name
                try:
                    related_pk_cols = prop.mapper.primary_key
                    if len(related_pk_cols) == 1:
                        return {related_pk_cols[0].key: fk_val}
                    return {related_pk_cols[0].key: fk_val}
                except Exception:
                    return {col.key: fk_val}
        return None

    def _resolve_field_name(self, field: str, model=None) -> str:
        """Resolve camelCase field name to snake_case ORM attribute.
        
        Tries the field as-is first; if not found, converts camelCase to snake_case.
        """
        target = model if model else self.model
        if hasattr(target, field):
            return field
        snake = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', field).lower()
        if hasattr(target, snake):
            return snake
        return field


    def _apply_filter(self, stmt, filter_expr: str):
        """Apply dynamic filter expression to the query.
        
        Supported operations:
            Comparison: ==, !=, >, <, >=, <=
            Functions:  field.contains('val'), field.startswith('val'), field.endswith('val')
            Logical:    and, or  (with parentheses support)
            
        Examples:
            name == 'John'
            age > 25 and status == 'active'
            (name.contains('test') or description.contains('sample')) and id >= 10
        """
        if not filter_expr:
            return stmt

        try:
            parser = self._FilterParser(self.model, self)
            condition = parser.parse(filter_expr)
            if condition is not None:
                stmt = stmt.where(condition)
            return stmt
        except Exception as e:
            # Re-raise as ValueError to map to 400 Bad Request
            raise ValueError(f"Invalid filter expression '{filter_expr}': {str(e)}")

    class _FilterParser:
        """Securely parse Python-like filter expressions into SQLAlchemy conditions using AST."""

        _TEXT_FUNCTIONS = {"contains", "startswith", "endswith"}

        def __init__(self, model, repo):
            self.model = model
            self.repo = repo

        def parse(self, expr_str: str):
            import ast

            try:
                # mode='eval' ensures it's a single expression
                tree = ast.parse(expr_str, mode='eval').body
                return self._visit(tree)
            except SyntaxError as e:
                raise ValueError(f"Syntax error: {e}")

        def _visit(self, node):
            import ast

            handlers = (
                (ast.BoolOp, self._visit_bool_op),
                (ast.Compare, self._visit_compare),
                (ast.Name, self._visit_name),
                (ast.Constant, self._visit_constant),
                (ast.Call, self._visit_call),
            )
            for node_type, handler in handlers:
                if isinstance(node, node_type):
                    return handler(node)

            raise ValueError(f"Unsupported AST node type: {type(node)}")

        def _visit_bool_op(self, node):
            import ast
            from sqlalchemy import and_, or_

            values = [self._visit(val) for val in node.values]
            if isinstance(node.op, ast.And):
                return and_(*values)
            if isinstance(node.op, ast.Or):
                return or_(*values)
            raise ValueError(f"Unsupported logical operator: {type(node.op)}")

        def _visit_compare(self, node):
            import ast

            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise ValueError("Only simple binary comparisons are supported")

            left = self._visit(node.left)
            right = self._visit(node.comparators[0])
            op = node.ops[0]

            if isinstance(op, ast.Eq):
                return left == right
            if isinstance(op, ast.NotEq):
                return left != right
            if isinstance(op, ast.Gt):
                return left > right
            if isinstance(op, ast.Lt):
                return left < right
            if isinstance(op, ast.GtE):
                return left >= right
            if isinstance(op, ast.LtE):
                return left <= right
            raise ValueError(f"Unsupported comparison operator: {type(op)}")

        def _visit_name(self, node):
            field_name = self.repo._resolve_field_name(node.id)
            if not hasattr(self.model, field_name):
                raise ValueError(f"Invalid property '{node.id}' in filter")
            return getattr(self.model, field_name)

        def _visit_constant(self, node):
            # Handles strings, numbers, booleans natively
            return node.value

        def _visit_call(self, node):
            import ast

            if isinstance(node.func, ast.Attribute):
                return self._visit_attribute_call(node)
            if isinstance(node.func, ast.Name):
                return self._visit_named_call(node)
            raise ValueError("Invalid function call format")

        def _visit_attribute_call(self, node):
            left = self._visit(node.func.value)
            func_name = node.func.attr

            self._validate_arg_count(func_name, node.args, expected=1)
            right = self._visit(node.args[0])
            return self._apply_text_function(func_name, left, right)

        def _visit_named_call(self, node):
            func_name = node.func.id

            self._validate_arg_count(func_name, node.args, expected=2, details=" (field, value)")
            left = self._visit(node.args[0])
            right = self._visit(node.args[1])
            return self._apply_text_function(func_name, left, right)

        @staticmethod
        def _validate_arg_count(func_name: str, args, expected: int, details: str = ""):
            suffix = "s" if expected > 1 else ""
            if len(args) != expected:
                raise ValueError(f"Function {func_name} requires {expected} argument{suffix}{details}")

        def _apply_text_function(self, func_name: str, left, right):
            if func_name not in self._TEXT_FUNCTIONS:
                raise ValueError(f"Unsupported function: {func_name}")

            if func_name == "contains":
                return left.ilike(f"%{right}%")
            if func_name == "startswith":
                return left.ilike(f"{right}%")
            return left.ilike(f"%{right}")

# ════════════════════════════════════════════════════════════════
# ✏️ CUSTOM CODE START
# Write your custom code below this line.
# You can add imports, override functions, add new methods, etc.
# ════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════
# ✏️ CUSTOM CODE END
# ════════════════════════════════════════════════════════════════
