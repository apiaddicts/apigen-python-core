"""
Tests for custom_code_merger module.

TDD tests — validates extract, inject, and merge logic for user-editable
custom code blocks in generated files.

Matching is by relative file path (no block_id needed).
"""
import os
import pytest


# ── Constants (mirrored from the module) ────────────────────────

START_MARKER = "# ✏️ CUSTOM CODE START"
END_MARKER = "# ✏️ CUSTOM CODE END"

SEPARATOR = "# ════════════════════════════════════════════════════════════════"


def _make_file(directory, relative_path, content):
    """Helper: create a file with given content inside directory."""
    full_path = os.path.join(str(directory), relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(content)
    return full_path


def _read_file(path):
    with open(path, "r") as f:
        return f.read()


# ── Fixtures ────────────────────────────────────────────────────

GENERATED_FILE_EMPTY_BLOCK = """\
from src.infrastructure.service.pet.pet_service import PetService

class PetService:
    pass

{sep}
{start}
# Write your custom code below this line.
{sep}


{sep}
{end}
{sep}
""".format(sep=SEPARATOR, start=START_MARKER, end=END_MARKER)


GENERATED_FILE_WITH_CUSTOM_CODE = """\
from src.infrastructure.service.pet.pet_service import PetService

class PetService:
    pass

{sep}
{start}
# Write your custom code below this line.
{sep}

from datetime import datetime

def custom_validation(pet):
    if not pet.name:
        raise ValueError("Pet name required")
    return True

{sep}
{end}
{sep}
""".format(sep=SEPARATOR, start=START_MARKER, end=END_MARKER)


GENERATED_FILE_NO_MARKERS = """\
from src.infrastructure.service.pet.pet_service import PetService

class PetService:
    pass
"""


# ── Tests: extract_custom_blocks ────────────────────────────────

class TestExtractCustomBlocks:

    def test_extract_from_file_with_custom_code(self, tmp_path):
        """Should extract the custom code content keyed by relative file path."""
        from apigen_copier.custom_code_merger import extract_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_WITH_CUSTOM_CODE)
        blocks = extract_custom_blocks(str(tmp_path))

        key = "src/service/pet/pet_service.py"
        assert key in blocks
        assert "from datetime import datetime" in blocks[key]
        assert "def custom_validation(pet):" in blocks[key]
        assert 'raise ValueError("Pet name required")' in blocks[key]

    def test_extract_from_file_with_empty_block(self, tmp_path):
        """Empty blocks (no user code) should NOT be extracted."""
        from apigen_copier.custom_code_merger import extract_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)
        blocks = extract_custom_blocks(str(tmp_path))

        assert len(blocks) == 0

    def test_extract_from_file_without_markers(self, tmp_path):
        """Files without markers should be silently ignored."""
        from apigen_copier.custom_code_merger import extract_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_NO_MARKERS)
        blocks = extract_custom_blocks(str(tmp_path))

        assert len(blocks) == 0

    def test_extract_multiple_files(self, tmp_path):
        """Should collect blocks from multiple files across directories."""
        from apigen_copier.custom_code_merger import extract_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_WITH_CUSTOM_CODE)

        repo_content = """\
class PetRepository:
    pass

{sep}
{start}
# Write your custom code below this line.
{sep}

async def find_by_name(self, name: str):
    return await self.session.execute(
        select(self.model).where(self.model.name == name)
    )

{sep}
{end}
{sep}
""".format(sep=SEPARATOR, start=START_MARKER, end=END_MARKER)

        _make_file(tmp_path, "src/repository/pet/pet_repository.py", repo_content)

        blocks = extract_custom_blocks(str(tmp_path))

        assert "src/service/pet/pet_service.py" in blocks
        assert "src/repository/pet/pet_repository.py" in blocks
        assert "find_by_name" in blocks["src/repository/pet/pet_repository.py"]

    def test_extract_ignores_binary_and_excluded_files(self, tmp_path):
        """Should skip binary and excluded files (.pyc, .gitkeep, .DS_Store)."""
        from apigen_copier.custom_code_merger import extract_custom_blocks

        _make_file(tmp_path, "module.pyc", GENERATED_FILE_WITH_CUSTOM_CODE)
        _make_file(tmp_path, ".gitkeep", GENERATED_FILE_WITH_CUSTOM_CODE)
        _make_file(tmp_path, ".DS_Store", GENERATED_FILE_WITH_CUSTOM_CODE)
        blocks = extract_custom_blocks(str(tmp_path))
        assert len(blocks) == 0

    def test_extract_scans_non_python_text_files(self, tmp_path):
        """Should extract custom code from non-.py text files (Dockerfile, .env, etc)."""
        from apigen_copier.custom_code_merger import extract_custom_blocks

        _make_file(tmp_path, "Dockerfile", GENERATED_FILE_WITH_CUSTOM_CODE)
        blocks = extract_custom_blocks(str(tmp_path))
        assert "Dockerfile" in blocks

    def test_extract_preserves_indentation(self, tmp_path):
        """Custom code indentation must be preserved exactly."""
        from apigen_copier.custom_code_merger import extract_custom_blocks

        content = """\
class Foo:
    pass

{sep}
{start}
# Write your custom code below this line.
{sep}

    def custom_method(self):
        if True:
            return "indented"

{sep}
{end}
{sep}
""".format(sep=SEPARATOR, start=START_MARKER, end=END_MARKER)

        _make_file(tmp_path, "foo_service.py", content)
        blocks = extract_custom_blocks(str(tmp_path))

        assert "foo_service.py" in blocks
        assert "    def custom_method(self):" in blocks["foo_service.py"]
        assert '            return "indented"' in blocks["foo_service.py"]


# ── Tests: inject_custom_blocks ─────────────────────────────────

class TestInjectCustomBlocks:

    def test_inject_into_empty_block(self, tmp_path):
        """Should replace empty block content with saved custom code."""
        from apigen_copier.custom_code_merger import inject_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)
        saved_blocks = {
            "src/service/pet/pet_service.py": "\nfrom datetime import datetime\n\ndef custom_validation(pet):\n    return True\n"
        }

        warnings = inject_custom_blocks(str(tmp_path), saved_blocks)

        result = _read_file(os.path.join(str(tmp_path), "src/service/pet/pet_service.py"))
        assert "from datetime import datetime" in result
        assert "def custom_validation(pet):" in result
        assert START_MARKER in result
        assert END_MARKER in result
        assert len(warnings) == 0

    def test_inject_preserves_existing_structure(self, tmp_path):
        """Code outside the custom block should remain unchanged."""
        from apigen_copier.custom_code_merger import inject_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)
        saved_blocks = {"src/service/pet/pet_service.py": "\n# my custom\n"}

        inject_custom_blocks(str(tmp_path), saved_blocks)

        result = _read_file(os.path.join(str(tmp_path), "src/service/pet/pet_service.py"))
        assert "class PetService:" in result
        assert "from src.infrastructure.service.pet.pet_service import PetService" in result

    def test_inject_warns_on_missing_file(self, tmp_path):
        """If a saved file path doesn't exist in the new project, return a warning."""
        from apigen_copier.custom_code_merger import inject_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_NO_MARKERS)
        saved_blocks = {"src/service/deleted/deleted_service.py": "\n# my custom code\n"}

        warnings = inject_custom_blocks(str(tmp_path), saved_blocks)

        assert len(warnings) == 1
        assert "deleted_service.py" in warnings[0]

    def test_inject_skips_unrelated_files(self, tmp_path):
        """Saved blocks for other files should not affect unrelated files."""
        from apigen_copier.custom_code_merger import inject_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)
        saved_blocks = {"src/service/owner/owner_service.py": "\n# owner custom\n"}

        inject_custom_blocks(str(tmp_path), saved_blocks)

        result = _read_file(os.path.join(str(tmp_path), "src/service/pet/pet_service.py"))
        assert "owner custom" not in result

    def test_inject_multiple_files(self, tmp_path):
        """Should inject into all matching files across the project."""
        from apigen_copier.custom_code_merger import inject_custom_blocks

        _make_file(tmp_path, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)

        repo_empty = """\
class PetRepository:
    pass

{sep}
{start}
# Write your custom code below this line.
{sep}


{sep}
{end}
{sep}
""".format(sep=SEPARATOR, start=START_MARKER, end=END_MARKER)

        _make_file(tmp_path, "src/repository/pet/pet_repository.py", repo_empty)

        saved_blocks = {
            "src/service/pet/pet_service.py": "\n# service custom\n",
            "src/repository/pet/pet_repository.py": "\n# repo custom\n",
        }

        inject_custom_blocks(str(tmp_path), saved_blocks)

        svc = _read_file(os.path.join(str(tmp_path), "src/service/pet/pet_service.py"))
        repo = _read_file(os.path.join(str(tmp_path), "src/repository/pet/pet_repository.py"))

        assert "# service custom" in svc
        assert "# repo custom" in repo


# ── Tests: merge_projects (orchestrator) ────────────────────────

class TestMergeProjects:

    def test_full_merge_cycle(self, tmp_path):
        """Old project custom code should appear in the new project."""
        from apigen_copier.custom_code_merger import merge_projects

        old_dir = os.path.join(str(tmp_path), "old_project")
        new_dir = os.path.join(str(tmp_path), "new_project")

        _make_file(old_dir, "src/service/pet/pet_service.py", GENERATED_FILE_WITH_CUSTOM_CODE)
        _make_file(new_dir, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)

        warnings = merge_projects(old_dir, new_dir)

        result = _read_file(os.path.join(new_dir, "src/service/pet/pet_service.py"))
        assert "from datetime import datetime" in result
        assert "def custom_validation(pet):" in result
        assert len(warnings) == 0

    def test_merge_with_removed_entity(self, tmp_path):
        """If an entity was removed from spec, its custom code generates a warning."""
        from apigen_copier.custom_code_merger import merge_projects

        old_dir = os.path.join(str(tmp_path), "old_project")
        new_dir = os.path.join(str(tmp_path), "new_project")

        _make_file(old_dir, "src/service/pet/pet_service.py", GENERATED_FILE_WITH_CUSTOM_CODE)

        owner_empty = """\
class OwnerService:
    pass

{sep}
{start}
# Write your custom code below this line.
{sep}


{sep}
{end}
{sep}
""".format(sep=SEPARATOR, start=START_MARKER, end=END_MARKER)

        _make_file(new_dir, "src/service/owner/owner_service.py", owner_empty)

        warnings = merge_projects(old_dir, new_dir)

        assert len(warnings) == 1
        assert "pet_service.py" in warnings[0]

    def test_merge_empty_old_project(self, tmp_path):
        """If old project has no custom code, new project should remain unchanged."""
        from apigen_copier.custom_code_merger import merge_projects

        old_dir = os.path.join(str(tmp_path), "old_project")
        new_dir = os.path.join(str(tmp_path), "new_project")

        _make_file(old_dir, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)
        _make_file(new_dir, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)

        warnings = merge_projects(old_dir, new_dir)

        result = _read_file(os.path.join(new_dir, "src/service/pet/pet_service.py"))
        assert START_MARKER in result
        assert END_MARKER in result
        assert len(warnings) == 0

    def test_merge_no_markers_in_old(self, tmp_path):
        """If old project has no markers (not generated by apigen), just generate clean."""
        from apigen_copier.custom_code_merger import merge_projects

        old_dir = os.path.join(str(tmp_path), "old_project")
        new_dir = os.path.join(str(tmp_path), "new_project")

        _make_file(old_dir, "src/service/pet/pet_service.py", GENERATED_FILE_NO_MARKERS)
        _make_file(new_dir, "src/service/pet/pet_service.py", GENERATED_FILE_EMPTY_BLOCK)

        warnings = merge_projects(old_dir, new_dir)

        result = _read_file(os.path.join(new_dir, "src/service/pet/pet_service.py"))
        assert START_MARKER in result
        assert len(warnings) == 0
