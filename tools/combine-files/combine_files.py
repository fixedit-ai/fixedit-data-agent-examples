#!/usr/bin/env python3
"""
Combine multiple Telegraf configuration files into a single file.

This script can inline Starlark (.star) files and shell scripts (.sh) to create
a self-contained configuration file that doesn't require separate helper files.

Usage:
    python combine_files.py --config file1.conf --config file2.conf \\
        --inline-starlark --inline-shell-script --output combined.conf
"""

import base64
import re
import sys
from pathlib import Path

import click
import tomlkit


def find_file(filename, root_path):
    """
    Find a file relative to a root path.

    Args:
        filename: Name of the file to find (may include subdirectory path)
        root_path: Root directory path to search in (Path object or string)

    Returns:
        Path object of the found file, or None if not found

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     test_file = Path(tmpdir) / "test.txt"
        ...     _ = test_file.write_text("test")
        ...     result = find_file("test.txt", tmpdir)
        ...     result is not None
        True

        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     find_file("nonexistent.txt", tmpdir) is None
        True
    """
    file_path = Path(root_path) / filename
    if file_path.exists():
        return file_path
    return None


def expand_default_values(path_str, path_vars):
    r"""
    Expand ${VAR:-default} patterns in a path string.

    Replaces patterns like ${VAR:-default} with the value from path_vars if
    VAR exists, otherwise uses the default value.

    Args:
        path_str: Path string that may contain default value patterns (string)
        path_vars: Dictionary mapping variable names to their values (dict)

    Returns:
        Path string with default value patterns expanded (string)

    Example:
        >>> expand_default_values("${VAR:-default.sh}", {})
        'default.sh'

        >>> expand_default_values("${VAR:-default.sh}", {"VAR": "custom.sh"})
        'custom.sh'

        >>> expand_default_values("${VAR:-default.sh}", {"OTHER": "value"})
        'default.sh'

        >>> expand_default_values("${DIR:-scripts}/${FILE:-test.sh}", {})
        'scripts/test.sh'

        >>> expand_default_values("${DIR:-scripts}/${FILE:-test.sh}", {"DIR": "custom"})
        'custom/test.sh'

        >>> expand_default_values("${DIR:-scripts}/${FILE:-test.sh}", {"FILE": "run.sh"})
        'scripts/run.sh'

        >>> expand_default_values("${DIR:-scripts}/${FILE:-test.sh}", {"DIR": "custom", "FILE": "run.sh"})
        'custom/run.sh'

        >>> expand_default_values("no_variables.sh", {})
        'no_variables.sh'

        >>> expand_default_values("${VAR}/file.sh", {})
        '${VAR}/file.sh'
    """
    var_default_pattern = r"\$\{([^:}]+):-([^}]+)\}"

    def replace_default(match):
        var_name = match.group(1)
        default_value = match.group(2)
        if path_vars and var_name in path_vars:
            return path_vars[var_name]
        return default_value

    return re.sub(var_default_pattern, replace_default, path_str)


def expand_path_variables(path_str, path_vars):
    """
    Expand all variables in a path string using path_vars dictionary.

    Replaces all occurrences of ${VAR_NAME} in the path string with their
    corresponding values from path_vars. Variables that are empty or '.' are
    replaced with empty string.

    Args:
        path_str: Path string that may contain variable references (string)
        path_vars: Dictionary mapping variable names to their values (dict)

    Returns:
        Path string with all variables expanded (string)

    Example:
        >>> expand_path_variables("${VAR}/file.sh", {"VAR": "scripts"})
        'scripts/file.sh'

        >>> expand_path_variables("${VAR}/file.sh", {"VAR": "."})
        './file.sh'

        >>> expand_path_variables("${VAR}/file.sh", {"VAR": ""})
        '/file.sh'

        >>> expand_path_variables("file.sh", {"VAR": "scripts"})
        'file.sh'

        >>> expand_path_variables("${VAR1}/${VAR2}/file.sh", {"VAR1": "dir1", "VAR2": "dir2"})
        'dir1/dir2/file.sh'

        >>> expand_path_variables("${UNKNOWN}/file.sh", {})
        '${UNKNOWN}/file.sh'

        >>> expand_path_variables("${VAR1}/${VAR2:-default.sh}", {"VAR1": "scripts"})
        'scripts/default.sh'

        >>> expand_path_variables("${VAR1}/${VAR2:-default.sh}", {"VAR1": "scripts", "VAR2": "custom.sh"})
        'scripts/custom.sh'
    """
    # First, handle ${VAR:-default} patterns (always process these regardless of path_vars
    # since we should still expand default values even if we don't have any values specified)
    result = expand_default_values(path_str, path_vars)

    # Then, replace remaining ${VAR} patterns with their values
    if path_vars:
        for variable_name, variable_value in path_vars.items():
            result = result.replace(f"${{{variable_name}}}", variable_value)

    return result


def resolve_script_path(path_str, file_path_root, path_vars):
    """
    Resolve the path to a script file using variable substitution.

    Expands all variables in the path string, then finds the file relative to
    file_path_root.

    Args:
        path_str: Path string that may contain variable references (string)
        file_path_root: Root directory path for finding files (Path object or string)
        path_vars: Dictionary of path variables to use for resolving paths (dict)

    Returns:
        Path object of the found file, or None if not found

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     script_file = Path(tmpdir) / "test.sh"
        ...     _ = script_file.write_text("test")
        ...     # No variable - direct filename
        ...     result = resolve_script_path("test.sh", tmpdir, {})
        ...     result is not None
        True

        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     subdir = Path(tmpdir) / "scripts"
        ...     subdir.mkdir()
        ...     script_file = subdir / "test.sh"
        ...     _ = script_file.write_text("test")
        ...     # Variable points to subdirectory
        ...     result = resolve_script_path("${VAR}/test.sh", tmpdir, {"VAR": "scripts"})
        ...     result is not None
        True

        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     # Variable is '.', results in ./test.sh which is found
        ...     script_file = Path(tmpdir) / "test.sh"
        ...     _ = script_file.write_text("test")
        ...     result = resolve_script_path("${VAR}/test.sh", tmpdir, {"VAR": "."})
        ...     result is not None
        True

        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     # Multiple variables
        ...     subdir1 = Path(tmpdir) / "dir1"
        ...     subdir2 = subdir1 / "dir2"
        ...     subdir2.mkdir(parents=True)
        ...     script_file = subdir2 / "test.sh"
        ...     _ = script_file.write_text("test")
        ...     result = resolve_script_path("${VAR1}/${VAR2}/test.sh", tmpdir, {"VAR1": "dir1", "VAR2": "dir2"})
        ...     result is not None
        True
    """
    # Expand all variables in the path string
    expanded_path = expand_path_variables(path_str, path_vars)

    # Find the file using the expanded path
    return find_file(expanded_path, file_path_root)


def find_matching_lines(config_content, pattern):
    r"""
    Find all regex pattern matches in config content and return their line ranges.

    Searches the entire content for pattern matches (which may span multiple lines)
    and returns the line numbers where each match starts and ends.

    Args:
        config_content: The config file content to search (string)
        pattern: Compiled regex pattern to search for (re.Pattern)

    Returns:
        List of tuples: (start_line, end_line)
        - start_line: 0-based line number where match starts (int)
        - end_line: 0-based line number where match ends (int)

    Example:
        >>> import re
        >>> pattern = re.compile(r'name\s*=\s*"[^"]+"')
        >>> config = 'name = "test"'
        >>> find_matching_lines(config, pattern)
        [(0, 0)]

        >>> import re
        >>> pattern = re.compile(r'items\s*=\s*\[[^\]]+\]', re.MULTILINE | re.DOTALL)
        >>> config = 'test = "hello"\nitems = [\n  "a",\n  "b"\n]'
        >>> find_matching_lines(config, pattern)
        [(1, 4)]

        >>> import re
        >>> pattern = re.compile(r'name\s*=\s*"[^"]+"')
        >>> config = '# name = "commented"'
        >>> find_matching_lines(config, pattern)
        [(0, 0)]

        >>> import re
        >>> pattern = re.compile(r'name\s*=\s*"[^"]+"')
        >>> config = 'name = "first"\nother = "value"\nname = "second"'
        >>> result = find_matching_lines(config, pattern)
        >>> len(result)
        2
        >>> result[0]  # first match
        (0, 0)
        >>> result[1]  # second match
        (2, 2)

        >>> import re
        >>> pattern = re.compile(r'count\s*=\s*\d+')
        >>> config = 'test = "hello"\ncount = 42\nname = "end"'
        >>> find_matching_lines(config, pattern)
        [(1, 1)]
    """
    results = []

    # Find all matches in the entire content (may span multiple lines)
    for match in pattern.finditer(config_content):
        match_start = match.start()
        match_end = match.end()

        # Calculate which line numbers this match spans
        # Count newlines before the match to get start line
        start_line = config_content[:match_start].count("\n")
        end_line = config_content[:match_end].count("\n")

        results.append((start_line, end_line))

    return results


def _find_all_keys_in_toml(data, key_name):
    """
    Find all occurrences of a key in TOML structure.

    Searches at:
    1. Top level: key = value
    2. Inside table arrays: [[table.subtable]] with key = value

    Args:
        data: The TOML data structure (dict from tomlkit.parse)
        key_name: The key name to search for (e.g., "script", "command")

    Returns:
        List of values found (may be empty)

    Examples:
        >>> _find_all_keys_in_toml({"name": "value"}, "name")
        ['value']

        >>> data = {"processors": {"starlark": [{"script": "test1.star"}, {"script": "test2.star"}]}}
        >>> _find_all_keys_in_toml(data, "script")
        ['test1.star', 'test2.star']

        >>> data = {"outputs": {"execd": [{"command": ["test.sh"]}]}}
        >>> _find_all_keys_in_toml(data, "command")
        [['test.sh']]

        >>> data = {"processors": {"starlark": [{"script": "a.star"}]}, "outputs": {"execd": [{"command": ["b.sh"]}]}}
        >>> _find_all_keys_in_toml(data, "script")
        ['a.star']
    """
    results = []

    # Check top level
    if key_name in data:
        results.append(data[key_name])

    # Check inside table arrays: [[table.subtable]]
    # Structure: {"table": {"subtable": [{"key": value}, ...]}}
    for table_value in data.values():
        if not isinstance(table_value, dict):
            continue

        # Iterate through subtables (e.g., "starlark", "execd")
        for subtable_value in table_value.values():
            if not isinstance(subtable_value, list):
                continue

            # Iterate through array elements (the [[...]] entries)
            for item in subtable_value:
                if isinstance(item, dict) and key_name in item:
                    results.append(item[key_name])

    return results


def _extract_normalized_value(key_name, parsed_value_raw):
    r"""
    Get the style-preserved TOML value string for use in regex matching.

    Uses tomlkit.dumps() which is STYLE-PRESERVING: multi-line arrays stay
    multi-line, indentation is preserved, etc. This normalized value is used
    to build a regex pattern for finding the exact key=value in the original
    config text.

    For example, if the config has:
        command = [
          "test.sh",
          "arg1"
        ]

    The normalized value will preserve that formatting:
        [\n  "test.sh",\n  "arg1"\n]

    This allows us to match the exact text from the original config.

    Args:
        key_name: The key name
        parsed_value_raw: The value from tomlkit (preserves style info)

    Returns:
        The style-preserved TOML value string (without the key= part)

    Raises:
        RuntimeError: If the normalized snippet format is unexpected

    Examples:
        >>> # Single-line array
        >>> config = 'command = ["test.sh", "arg1"]'
        >>> doc = tomlkit.parse(config)
        >>> _extract_normalized_value("command", doc["command"])
        '["test.sh", "arg1"]'

        >>> # Multi-line array - style is preserved
        >>> config = 'items = [\n  1,\n  2,\n  3\n]'
        >>> doc = tomlkit.parse(config)
        >>> _extract_normalized_value("items", doc["items"])
        '[\n  1,\n  2,\n  3\n]'

        >>> # Another multi-line example with different indentation preserved
        >>> config = 'command = [\n    "test.sh",\n    "arg1"\n  ]'
        >>> doc = tomlkit.parse(config)
        >>> _extract_normalized_value("command", doc["command"])
        '[\n    "test.sh",\n    "arg1"\n  ]'
    """
    normalized_snippet = tomlkit.dumps({key_name: parsed_value_raw}).strip()
    key_equals = f"{key_name} = "
    if not normalized_snippet.startswith(key_equals):
        raise RuntimeError(
            f"Internal error: unexpected normalized snippet format: {repr(normalized_snippet)}"
        )
    return normalized_snippet[len(key_equals) :]


def _is_valid_toml_match(config_content, start_pos, end_pos, key_name):
    """
    Check if a text snippet is a valid TOML key=value by parsing it.

    This uses tomlkit to validate the match, which properly handles:
    - Comments (ignores them)
    - Strings containing # characters
    - All TOML syntax variations

    Args:
        config_content: The full config content
        start_pos: Start position of the snippet
        end_pos: End position of the snippet
        key_name: The key name we're looking for

    Returns:
        True if the snippet is valid TOML containing the key, False otherwise

    Examples:
        >>> config = 'script = "test.star"'
        >>> _is_valid_toml_match(config, 0, len(config), "script")
        True

        >>> config = '# script = "test.star"'
        >>> _is_valid_toml_match(config, 0, len(config), "script")
        False

        >>> config = 'script = "file#with#hash.star"'
        >>> _is_valid_toml_match(config, 0, len(config), "script")
        True

        >>> config = '  script = "test.star"'
        >>> _is_valid_toml_match(config, 2, len(config), "script")
        True
    """
    snippet = config_content[start_pos:end_pos]
    try:
        doc = tomlkit.parse(snippet)
        return key_name in doc
    except Exception:
        # If it doesn't parse, it's not valid (e.g., it's commented out)
        return False


def _unwrap_tomlkit_value(value):
    """
    Unwrap tomlkit wrapper types to regular Python objects.

    Args:
        value: The tomlkit value

    Returns:
        Regular Python object (str, int, list, dict, etc.)

    Examples:
        >>> doc = tomlkit.parse('name = "test"')
        >>> wrapped = doc['name']
        >>> _unwrap_tomlkit_value(wrapped)
        'test'

        >>> doc = tomlkit.parse('items = [1, 2, 3]')
        >>> wrapped = doc['items']
        >>> _unwrap_tomlkit_value(wrapped)
        [1, 2, 3]

        >>> doc = tomlkit.parse('count = 42')
        >>> wrapped = doc['count']
        >>> _unwrap_tomlkit_value(wrapped)
        42
    """
    if hasattr(value, "unwrap"):
        return value.unwrap()
    else:
        # For simple types that don't have unwrap(), convert to appropriate Python type
        return dict(value) if isinstance(value, dict) else value


def _find_key_value_in_text(
    config_content, key_name, normalized_value, already_found_positions
):
    """
    Find key=value occurrences in the config text.

    Uses regex for high-sensitivity detection, then validates with tomlkit
    to filter out false positives (e.g., commented lines, strings with #).

    Args:
        config_content: The config file content
        key_name: The key name to search for
        normalized_value: The normalized value string
        already_found_positions: Set of positions already found (to avoid duplicates)

    Returns:
        List of tuples: (snippet, start_pos, end_pos)
    """
    # High-sensitivity regex: matches key<whitespace>=<whitespace>value
    # We use tomlkit validation below to filter out false positives
    pattern = re.compile(
        rf"^([ \t]*)({re.escape(key_name)})([ \t]*)=([ \t]*)({re.escape(normalized_value)})",
        re.MULTILINE
        | re.DOTALL,  # ^ matches line start, value might span multiple lines
    )

    matches = []
    for match in pattern.finditer(config_content):
        snippet_start = match.start() + len(match.group(1))
        snippet_end = match.end()

        # Check if we already found this position (avoid duplicates)
        if snippet_start in already_found_positions:
            continue

        # Validate with tomlkit: this filters out comments and handles complex cases
        # like # inside strings
        if not _is_valid_toml_match(
            config_content, snippet_start, snippet_end, key_name
        ):
            continue

        key_value_snippet = config_content[snippet_start:snippet_end]
        matches.append((key_value_snippet, snippet_start, snippet_end))

    return matches


def find_valid_toml_matches(config_content, key_name):
    """
    Find a TOML key=value pair in config content using tomlkit for parsing.

    Uses tomlkit to parse the entire config, which properly handles:
    - Complex nested values (arrays, inline tables, etc.)
    - Multi-line values
    - All TOML syntax variations
    - Comments (they are naturally ignored by the parser)

    Uses tomlkit.dumps() to get a normalized representation, then uses regex to
    find the original key=value in the config while preserving any excessive
    whitespace around the `=` sign. This allows simple string replacement while
    maintaining the user's original formatting.

    Args:
        config_content: The config file content to search (string)
        key_name: The TOML key name to search for and extract (string)

    Returns:
        List of tuples: [(original_snippet, parsed_value, start_pos, end_pos), ...]
        Empty list if key not found. Each tuple contains:
        - original_snippet: The exact key=value text from the original config (string)
        - parsed_value: The parsed value for key_name from tomlkit
        - start_pos: Starting position of the snippet in config_content (int)
        - end_pos: Ending position of the snippet in config_content (int)

    Raises:
        ValueError: If the config content is not valid TOML

    Example:
        >>> config = '[[processors.starlark]]\\n  script = "test.star"'
        >>> results = find_valid_toml_matches(config, "script")
        >>> len(results)
        1
        >>> results[0][0]  # original snippet
        'script = "test.star"'
        >>> results[0][1]  # parsed value
        'test.star'

        >>> config = '# [[processors.starlark]]\\n#   script = "commented.star"'
        >>> find_valid_toml_matches(config, "script")
        []

        >>> config = '[[outputs.execd]]\\n  command = [\\n    "helper.sh",\\n    "arg1"\\n  ]'
        >>> results = find_valid_toml_matches(config, "command")
        >>> results[0][0]  # original snippet (style-preserved)
        'command = [\\n    "helper.sh",\\n    "arg1"\\n  ]'
        >>> results[0][1]  # parsed_value
        ['helper.sh', 'arg1']

        >>> config = '# [[processors.starlark]]\\n#   script = "old.star"\\n[[processors.starlark]]\\n  script = "new.star"'
        >>> results = find_valid_toml_matches(config, "script")
        >>> results[0][0]  # only the real one, not commented
        'script = "new.star"'
        >>> results[0][1]
        'new.star'

        >>> config = '[[outputs.execd]]\\n  command       =       ["test.sh"]'
        >>> results = find_valid_toml_matches(config, "command")
        >>> results[0][0]  # preserves excessive whitespace
        'command       =       ["test.sh"]'

        >>> config = '[[processors.starlark]]\\n  script = "a.star"\\n[[processors.starlark]]\\n  script = "b.star"'
        >>> results = find_valid_toml_matches(config, "script")
        >>> len(results)  # finds multiple occurrences
        2
        >>> results[0][1]
        'a.star'
        >>> results[1][1]
        'b.star'

        >>> config = '[[processors.starlark]]\\n  script = "file#with#hashes.star"'
        >>> results = find_valid_toml_matches(config, "script")
        >>> results[0][1]  # handles # inside strings correctly
        'file#with#hashes.star'
    """
    # Parse the config with tomlkit to get the value
    try:
        doc = tomlkit.parse(config_content)
    except tomlkit.exceptions.TOMLKitError as e:
        raise ValueError(f"Invalid TOML syntax in config: {e}") from e

    # Recursively search for all occurrences of the key in the parsed document
    parsed_values_raw = _find_all_keys_in_toml(doc, key_name)
    if not parsed_values_raw:
        return []

    results = []
    already_found_positions = set()

    # For each value found, locate it in the original config
    for parsed_value_raw in parsed_values_raw:
        normalized_value = _extract_normalized_value(key_name, parsed_value_raw)
        matches = _find_key_value_in_text(
            config_content, key_name, normalized_value, already_found_positions
        )

        for key_value_snippet, snippet_start, snippet_end in matches:
            parsed_value = _unwrap_tomlkit_value(parsed_value_raw)
            results.append(
                (key_value_snippet, parsed_value, snippet_start, snippet_end)
            )
            already_found_positions.add(snippet_start)

    return results


def inline_starlark_script(config_content, file_path_root, path_vars):
    r"""
    Replace external Starlark script references with inline source code.

    Replaces patterns like:
        script = "${VAR}/filename.star"
    with:
        source = '''
        ...file content...
        '''

    The function searches for the referenced .star file relative to the file_path_root,
    reads its content, and replaces the script reference with an inline source block.
    Path variables are used only to resolve file locations, not to modify the output.

    Args:
        config_content: The config file content (string)
        file_path_root: Root directory path for finding files (Path object or string)
        path_vars: Dictionary of path variables to use for resolving file paths (dict)

    Returns:
        Config content with Starlark scripts inlined (string)

    Note:
        If a referenced script file cannot be found, the original reference
        is left unchanged and a warning is printed to stderr.

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     script_file = Path(tmpdir) / "test.star"
        ...     _ = script_file.write_text("load('test.star', 'test')")
        ...     config = 'script = "test.star"'
        ...     result = inline_starlark_script(config, tmpdir, {})
        ...     result
        "source = '''\nload('test.star', 'test')'''"

        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     # Create a subdirectory for the variable path
        ...     subdir = Path(tmpdir) / "scripts"
        ...     subdir.mkdir()
        ...     script_file = subdir / "test.star"
        ...     _ = script_file.write_text("test content")
        ...     config = 'script = "${VAR}/test.star"'
        ...     # file_path_root is tmpdir, VAR points to subdirectory within it
        ...     result = inline_starlark_script(config, tmpdir, {"VAR": "scripts"})
        ...     result
        "source = '''\ntest content'''"

        >>> from pathlib import Path
        >>> import tempfile
        >>> import sys
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     script_file = Path(tmpdir) / "test.star"
        ...     _ = script_file.write_text("code with ''' triple quotes")
        ...     config = 'script = "test.star"'
        ...     # This should fail with an error
        ...     try:
        ...         inline_starlark_script(config, tmpdir, {})
        ...     except SystemExit:
        ...         pass  # Expected to exit with error

        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     script_file = Path(tmpdir) / "old.star"
        ...     _ = script_file.write_text("old content")
        ...     config = '# script = "old.star"'
        ...     result = inline_starlark_script(config, tmpdir, {})
        ...     # Should NOT inline the commented reference - it should remain unchanged
        ...     result
        '# script = "old.star"'
    """
    # Find all script references
    matches = find_valid_toml_matches(config_content, "script")

    if not matches:
        return config_content

    # Process matches in reverse order (from end to start) to avoid position shifts
    for _original_snippet, path_str, start_pos, end_pos in reversed(matches):
        script_path = resolve_script_path(path_str, file_path_root, path_vars)

        if not script_path:
            click.echo(
                f"Error: Could not find Starlark script '{path_str}' in root path '{file_path_root}'",
                err=True,
            )
            sys.exit(1)

        # Read the script content as UTF-8 - this should be safe since we do
        # not expect binary data in Starlark files.
        with open(script_path, encoding="utf-8") as f:
            script_content = f.read()

        # Validate that script doesn't contain triple single quotes which would break the inline format
        if "'''" in script_content:
            click.echo(
                f"Error: Starlark script '{path_str}' contains triple single quotes ('''), which would break the inline source format",
                err=True,
            )
            sys.exit(1)

        # Replace using position-based replacement (more reliable than string.replace)
        replacement = f"source = '''\n{script_content}'''"
        config_content = (
            config_content[:start_pos] + replacement + config_content[end_pos:]
        )

    return config_content


def inline_shell_script(config_content, file_path_root, path_vars):
    r"""
    Replace external shell script references with base64-encoded inline commands.

    Replaces patterns like:
        command = ["${HELPER_FILES_DIR}/filename.sh"]
        command = ["${HELPER_FILES_DIR}/${VAR:-default.sh}"]
    with:
        command = ["sh", "-c", "echo 'BASE64_ENCODED_SCRIPT' | openssl base64 -d | sh"]

    The function searches for the referenced .sh file relative to the file_path_root,
    reads its content, encodes it as base64, and creates an inline command that
    decodes and executes it.

    Only files ending with .sh are inlined. Other command references (like binary
    executables) are left unchanged with a warning.

    Args:
        config_content: The config file content (string)
        file_path_root: Root directory path for finding files (Path object or string)
        path_vars: Dictionary of path variables that were expanded (dict)

    Returns:
        Config content with shell scripts inlined (string)

    Note:
        - Uses openssl base64 -d instead of base64 command since base64
          doesn't exist on the target devices.
        - For variable substitution patterns like ${VAR:-default.sh}, it will
          inline the default script if found.
        - Non-.sh files (e.g., binary executables) are skipped with a warning.

    Raises:
        SystemExit: If a referenced .sh script file cannot be found

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     script_file = Path(tmpdir) / "test.sh"
        ...     _ = script_file.write_text("#!/bin/sh\\necho 'test'")
        ...     config = 'command = ["test.sh"]'
        ...     result = inline_shell_script(config, str(Path(tmpdir)), {})
        ...     "openssl base64 -d" in result
        True

        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     # Create a subdirectory for the variable path
        ...     subdir = Path(tmpdir) / "scripts"
        ...     subdir.mkdir()
        ...     script_file = subdir / "test.sh"
        ...     _ = script_file.write_text("echo test")
        ...     config = 'command = ["${VAR}/test.sh"]'
        ...     # file_path_root is tmpdir, VAR points to subdirectory within it
        ...     result = inline_shell_script(config, str(Path(tmpdir)), {"VAR": "scripts"})
        ...     "openssl base64 -d" in result
        True

        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     # Test nested variables: ${HELPER_FILES_DIR}/${VAR:-default.sh}
        ...     subdir = Path(tmpdir) / "scripts"
        ...     subdir.mkdir()
        ...     script_file = subdir / "default.sh"
        ...     _ = script_file.write_text("echo test")
        ...     config = 'command = ["${HELPER_FILES_DIR}/${VAR:-default.sh}"]'
        ...     result = inline_shell_script(config, str(Path(tmpdir)), {"HELPER_FILES_DIR": "scripts"})
        ...     "openssl base64 -d" in result
        True

        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     script_file = Path(tmpdir) / "old.sh"
        ...     _ = script_file.write_text("echo old")
        ...     config = '# command = ["old.sh"]'
        ...     result = inline_shell_script(config, tmpdir, {})
        ...     # Should NOT inline the commented reference - it should remain unchanged
        ...     result
        '# command = ["old.sh"]'
    """

    def replace_with_inline(script_path, script_args):
        """Replace a script reference with inline base64-encoded version.

        Args:
            script_path: Path to the script file
            script_args: List of additional arguments to pass to the script (may be empty)

        Returns:
            The inline command string with base64-encoded script
        """
        # Read the script content as binary (we don't care about the content, we
        # will base64 encode it anyway)
        with open(script_path, "rb") as f:
            script_content = f.read()

        # Encode to base64 (and decode the bytes as ASCII - we know this is safe
        # since base64 only contains ASCII characters)
        script_base64 = base64.b64encode(script_content).decode("ascii")

        # Build the script invocation with arguments
        # Arguments need to be properly quoted for shell safety
        if script_args:
            # Quote each argument for safe shell execution
            # TODO: Write a test for this...
            quoted_args = " ".join(f'"{arg}"' for arg in script_args)
            script_invocation = f'sh "$tmpfile" {quoted_args}'
        else:
            script_invocation = 'sh "$tmpfile"'

        # Create the inline command using a few tricks:
        # 1. We use a temp file approach so that we preserves stdin for the Telegraf data.
        #    If we did pipe the script to sh, it would consume the stdin and the script would
        #    not be able to read the Telegraf data (assuming it is an output plugin).
        # 2. We have to use -A for openssl base64 decoder, otherwise it will break long
        #    lines causing corruption of the script.
        # 3. We use TOML multi-line literal string (''') to avoid escaping issues.
        # 4. We use a trap to ensure the temp file is cleaned up on exit while preserving
        #    the exit code from the script (since the script is the last command, the exit
        #    code of the script will be the exit code of the entire command. Without the
        #    trap, we would need to capture the exit code from the script and then manually
        #    exit with that code after the cleanup.
        inline_command = (
            'command = ["sh", "-c", \'\'\'\n'
            f"tmpfile=$(mktemp)\n"
            f"trap 'rm -f \"$tmpfile\"' EXIT\n"
            f"openssl base64 -d -A <<'FIXEDIT_SCRIPT_EOF' >\"$tmpfile\"\n"
            f"{script_base64}\n"
            f"FIXEDIT_SCRIPT_EOF\n"
            f"{script_invocation}''']\n"
        )

        return inline_command.rstrip("\n")  # Remove trailing newline

    # Find all command references
    matches = find_valid_toml_matches(config_content, "command")

    if not matches:
        return config_content

    # Process matches in reverse order (from end to start) to avoid position shifts
    for _original_snippet, command_array, start_pos, end_pos in reversed(matches):
        # Validate that we have at least one element
        if not command_array or not isinstance(command_array, list):
            click.echo(
                "Error: Invalid command array",
                err=True,
            )
            sys.exit(1)

        # Extract script path and arguments. E.g. the line might look like:
        # command = ["${HELPER_FILES_DIR}/filename.sh", "arg1", "arg2"]
        # or it might look like:
        # command = ["filename.sh"]
        path_str = command_array[0]
        script_args = command_array[1:] if len(command_array) > 1 else []

        # Expand variables to determine the actual file path
        expanded_path = expand_path_variables(path_str, path_vars)

        # Skip if the expanded path doesn't end with .sh (it might be a binary executable)
        if not expanded_path.endswith(".sh"):
            click.secho(
                f"Warning: Skipping '{path_str}' (expanded: '{expanded_path}') - not a shell script (.sh)",
                fg="yellow",
                err=True,
            )
            continue  # Skip this match but continue processing others

        script_path = resolve_script_path(path_str, file_path_root, path_vars)

        if not script_path:
            click.echo(
                f"Error: Could not find shell script '{path_str}' in root path '{file_path_root}'",
                err=True,
            )
            sys.exit(1)

        # Replace using position-based replacement (more reliable than string.replace)
        replacement = replace_with_inline(script_path, script_args)
        config_content = (
            config_content[:start_pos] + replacement + config_content[end_pos:]
        )

    return config_content


def combine_configs(
    config_files, inline_starlark, inline_shell, file_path_root, path_vars
):
    """
    Combine multiple config files into a single content string.

    Reads each config file, optionally expands path variables, optionally inlines
    Starlark and shell scripts, and concatenates them with separator comments.

    Args:
        config_files: List of config file paths to combine (list of strings)
        inline_starlark: Whether to inline Starlark .star files (bool)
        inline_shell: Whether to inline shell .sh scripts (bool)
        file_path_root: Root directory path for finding referenced files (Path object or string, or None)
        path_vars: Dictionary of path variables to expand (dict)

    Returns:
        Combined config content as a single string

    Raises:
        SystemExit: If any config file is not found

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     config1 = Path(tmpdir) / "config1.conf"
        ...     config2 = Path(tmpdir) / "config2.conf"
        ...     _ = config1.write_text("# Config 1")
        ...     _ = config2.write_text("# Config 2")
        ...     result = combine_configs([str(config1), str(config2)], False, False, str(Path(tmpdir)), {})
        ...     # Now uses relative paths when configs are within file_path_root
        ...     expected = "# ========================================\\n# From: config1.conf\\n# ========================================\\n\\n# Config 1\\n# ========================================\\n# From: config2.conf\\n# ========================================\\n\\n# Config 2"
        ...     result == expected
        True
    """
    combined_content = []

    for config_file in config_files:
        config_path = Path(config_file)

        if not config_path.exists():
            click.echo(f"Error: Config file not found: {config_file}", err=True)
            sys.exit(1)

        # Read config file as UTF-8 - this should be safe since we do not expect
        # binary data in config files.
        with open(config_path, encoding="utf-8") as f:
            content = f.read()

        # Inline Starlark scripts if requested
        if inline_starlark:
            content = inline_starlark_script(content, file_path_root, path_vars)

        # Inline shell scripts if requested
        if inline_shell:
            content = inline_shell_script(content, file_path_root, path_vars)

        # Add a header comment for each config file (with relative path if possible)
        if combined_content:
            combined_content.append("\n")
        combined_content.append("# ========================================\n")

        # Try to make path relative to file_path_root
        try:
            root_path = Path(file_path_root).resolve()
            abs_config_path = Path(config_file).resolve()
            relative_path = abs_config_path.relative_to(root_path)
            combined_content.append(f"# From: {relative_path}\n")
        except (ValueError, TypeError):
            # Path is not relative to root_path or root_path is None, use the original path
            combined_content.append(f"# From: {config_file}\n")

        combined_content.append("# ========================================\n\n")
        combined_content.append(content)

    return "".join(combined_content)


@click.command()
@click.option(
    "--config",
    multiple=True,
    required=True,
    help="Configuration file to include (can be specified multiple times)",
)
@click.option(
    "--inline-starlark",
    is_flag=True,
    help="Inline Starlark .star files referenced in configs",
)
@click.option(
    "--inline-shell-script",
    is_flag=True,
    help="Inline shell .sh scripts referenced in configs using base64 encoding",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Output file path for combined configuration",
)
@click.option(
    "--file-path-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=lambda: str(Path.cwd()),
    help="Root directory path for finding .star and .sh files referenced in configs (defaults to current working directory)",
)
@click.option(
    "--expand-path-var",
    multiple=True,
    help="Expand path variables in configs (format: VAR=value, e.g., HELPER_FILES_DIR=.)",
)
def main(
    config,
    inline_starlark,
    inline_shell_script,
    output,
    file_path_root,
    expand_path_var,
):
    r"""
    Combine multiple Telegraf configuration files into a single file.

    This script can inline Starlark (.star) files and shell scripts (.sh) to create
    a self-contained configuration file that doesn't require separate helper files.

    Examples:

    \b
        # Combine configs without inlining
        python combine_files.py --config config1.conf --config config2.conf --output combined.conf

        # Combine with Starlark inlining
        python combine_files.py --config config1.conf --config config2.conf \\
            --inline-starlark --output combined.conf

        # Combine with both Starlark and shell script inlining
        python combine_files.py --config config1.conf --config config2.conf \\
            --inline-starlark --inline-shell-script --output combined.conf

        # Expand path variables before inlining
        python combine_files.py --config config1.conf --config config2.conf \\
            --expand-path-var HELPER_FILES_DIR=. --inline-starlark --inline-shell-script \\
            --output combined.conf
    """
    # Parse path variables from --expand-path-var arguments
    path_vars = {}
    for var_spec in expand_path_var:
        if "=" not in var_spec:
            click.echo(
                f"Error: Invalid path variable format: {var_spec}. Expected VAR=value",
                err=True,
            )
            sys.exit(1)
        var_name, var_value = var_spec.split("=", 1)
        path_vars[var_name] = var_value

    # Resolve file_path_root to absolute path
    file_path_root_resolved = str(Path(file_path_root).resolve())

    # Combine the configs
    combined = combine_configs(
        config, inline_starlark, inline_shell_script, file_path_root_resolved, path_vars
    )

    # Write output
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(combined)

    click.echo(
        f"Successfully combined {len(config)} config file(s) into {output}", err=True
    )
    if inline_starlark:
        click.echo("  - Starlark scripts inlined", err=True)
    if inline_shell_script:
        click.echo("  - Shell scripts inlined (base64 encoded)", err=True)
    if path_vars:
        click.echo(
            f"  - Path variables expanded: {', '.join(path_vars.keys())}", err=True
        )


if __name__ == "__main__":
    main()
