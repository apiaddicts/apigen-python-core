"""
Custom code merger — preserves user code across regenerations.

When a project is regenerated, this module:
1. Extracts user-written code from delimited blocks in the OLD project
2. Injects that saved code into the freshly-generated NEW project

Each generated file has a block at the end:

    # ════════════════════════════════════════════════════════════════
    # ✏️ CUSTOM CODE START
    # Write your custom code below this line.
    # ════════════════════════════════════════════════════════════════
    
    <user code here>
    
    # ════════════════════════════════════════════════════════════════
    # ✏️ CUSTOM CODE END
    # ════════════════════════════════════════════════════════════════

Matching is done by **relative file path** — same file in the old and new
project maps to the same custom block. This is deterministic because the
generator always produces the same file structure from the same spec.
"""
import os
import shutil
from typing import Optional


# ── Marker constants ────────────────────────────────────────────

START_MARKER = "# ✏️ CUSTOM CODE START"
END_MARKER = "# ✏️ CUSTOM CODE END"

SEPARATOR = "# ════════════════════════════════════════════════════════════════"


# ── Internal helpers ────────────────────────────────────────────

def _is_content_empty(content: str) -> bool:
    """Check if custom block content is effectively empty.
    
    A block is empty if it contains only whitespace, empty comments,
    or the generated hint lines from templates.
    """
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "#":
            continue
        if "Write your custom code" in stripped:
            continue
        if "You can add imports" in stripped:
            continue
        return False
    return True


# Extensions / names that should NEVER be scanned (binary or auto-generated)
_SKIP_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".zip", ".gz", ".tar", ".whl",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".db", ".sqlite", ".sqlite3",
})
_SKIP_NAMES = frozenset({".gitkeep", ".DS_Store"})


def _iter_project_files(directory: str):
    """Yield (relative_path, absolute_path) for all text files under directory."""
    for root, _dirs, files in os.walk(directory):
        for fname in sorted(files):
            if fname in _SKIP_NAMES:
                continue
            _, ext = os.path.splitext(fname)
            if ext.lower() in _SKIP_EXTENSIONS:
                continue
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, directory)
            yield rel_path, abs_path


def _extract_block_from_file(filepath: str) -> Optional[str]:
    """Extract custom code content from a single file, or None if empty/missing."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return None

    inside_block = False
    block_lines = []

    for line in lines:
        if START_MARKER in line:
            inside_block = True
            block_lines = []
        elif END_MARKER in line and inside_block:
            content = "".join(block_lines)
            return content if not _is_content_empty(content) else None
        elif inside_block:
            # Skip separator lines that are part of the marker header
            if SEPARATOR in line:
                continue
            block_lines.append(line)

    return None


def _inject_block_into_file(filepath: str, custom_content: str) -> bool:
    """Replace the empty block content in a file with saved custom content.
    
    Returns True if the file was modified.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return False

    result = []
    skip_until_end = False
    modified = False

    for line in lines:
        if START_MARKER in line:
            result.append(line)
            skip_until_end = True
        elif END_MARKER in line and skip_until_end:
            # Inject the saved custom content before the END marker
            result.append(custom_content)
            if not custom_content.endswith("\n"):
                result.append("\n")
            result.append(line)
            skip_until_end = False
            modified = True
        elif skip_until_end:
            continue  # Skip default empty content
        else:
            result.append(line)

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(result)

    return modified


# ── Public API ──────────────────────────────────────────────────

def extract_custom_blocks(project_dir: str) -> dict[str, str]:
    """Scan all files in project_dir and extract custom code blocks.
    
    Returns:
        Dict mapping relative_file_path → custom code content (only non-empty).
    """
    blocks: dict[str, str] = {}

    for rel_path, abs_path in _iter_project_files(project_dir):
        content = _extract_block_from_file(abs_path)
        if content is not None:
            blocks[rel_path] = content

    return blocks


def inject_custom_blocks(
    project_dir: str,
    blocks: dict[str, str],
) -> list[str]:
    """Inject saved custom code blocks into freshly generated files.
    
    Matches by relative file path — if the same file exists in the new
    project, the custom code is injected into its CUSTOM CODE block.
    
    Args:
        project_dir: Path to the freshly generated project.
        blocks: Dict of relative_path → saved custom code.
    
    Returns:
        List of warning messages for blocks that had no matching file.
    """
    if not blocks:
        return []

    injected: set[str] = set()

    for rel_path, content in blocks.items():
        target = os.path.join(project_dir, rel_path)
        if os.path.isfile(target) and _inject_block_into_file(target, content):
            injected.add(rel_path)

    warnings = []
    for rel_path in blocks:
        if rel_path not in injected:
            warnings.append(
                f"WARNING: Custom code from '{rel_path}' could not be injected — "
                f"file does not exist in the new project."
            )

    return warnings


def merge_projects(
    old_project_dir: str,
    new_project_dir: str,
) -> list[str]:
    """Orchestrate full custom code preservation across regeneration.
    
    1. Copy UserCode/ folder from the old project (if it exists)
    2. Extract custom code blocks from the old project
    3. Inject them into the new project (matched by file path)
    4. Return any warnings about lost blocks
    
    Args:
        old_project_dir: Path to the user's previous project.
        new_project_dir: Path to the freshly generated project.
    
    Returns:
        List of warning messages (empty if everything merged successfully).
    """
    warnings = []

    # 1. Copy UserCode/ folder
    copy_user_code_folder(old_project_dir, new_project_dir)

    # 2. Extract and inject custom code blocks
    blocks = extract_custom_blocks(old_project_dir)
    if blocks:
        warnings = inject_custom_blocks(new_project_dir, blocks)

    return warnings


def copy_user_code_folder(
    old_project_dir: str,
    new_project_dir: str,
) -> bool:
    """Copy UserCode/ from the old project into the new project.
    
    Searches recursively for a 'UserCode' directory in the old project.
    If found, copies it to the matching location in the new project,
    replacing the empty generated UserCode/ folder.
    
    Returns True if a UserCode/ folder was copied.
    """
    old_user_code = _find_user_code_dir(old_project_dir)
    if not old_user_code:
        return False

    # Compute the relative path of UserCode within the old project
    rel_path = os.path.relpath(old_user_code, old_project_dir)

    # Target in the new project
    new_user_code = os.path.join(new_project_dir, rel_path)

    # Remove the empty generated UserCode/ if it exists
    if os.path.isdir(new_user_code):
        shutil.rmtree(new_user_code)

    shutil.copytree(old_user_code, new_user_code)
    print(f"  [UserCode] Copied from existing project → {rel_path}")
    return True


def _find_user_code_dir(project_dir: str) -> Optional[str]:
    """Find the UserCode/ directory within a project."""
    for root, dirs, _files in os.walk(project_dir):
        if "UserCode" in dirs:
            return os.path.join(root, "UserCode")
    return None
