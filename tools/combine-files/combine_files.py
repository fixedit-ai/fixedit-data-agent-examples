#!/usr/bin/env python3
# pylint: disable=too-many-lines
"""
Combine multiple Telegraf configuration files into a single file.

This script can inline Starlark (.star) files and shell scripts (.sh) to create
a self-contained configuration file that doesn't require separate helper files.

Usage:
    python combine_files.py --config file1.conf --config file2.conf \\
        --inline-starlark --inline-shell-script --output combined.conf
"""

import base64
import json
import re
import sys
from pathlib import Path

import click
import git
import tomlkit


class ConfigContent:
    """
    Manages both original and expanded versions of config content.

    The original config files might contain variables that needs to
    be expanded, either to make the the TOML syntax valid or to make the
    path resolution of helper files (which should be inlined) correct.
    Therefore, we need to expand this before processing the file, but
    the output file that we save should still have all the variables
    left as is. We can do this by keeping a mapping from the expanded
    to the original view.

    Works line-by-line: tracks which lines in expanded came from which lines
    in original. When replacing, we replace whole lines only.

    Example:
        >>> content = ConfigContent("key = ${VAR}", {"VAR": "value"})
        >>> content.get_original()
        'key = ${VAR}'
        >>> content.get_expanded()
        'key = value'

        >>> content = ConfigContent("line1\\nline2 ${V}\\nline3", {"V": "X"})
        >>> content.get_expanded()
        'line1\\nline2 X\\nline3'
        >>> content.replace_lines(1, 1, "new line")
        >>> content.get_original()
        'line1\\nnew line\\nline3'
    """

    def __init__(self, original_content, path_vars=None):
        """
        Initialize with original content and optional path variables.

        Args:
            original_content: The original config content (string)
            path_vars: Dictionary of path variables for expansion (dict)
        """
        self.path_vars = path_vars or {}
        self.original_lines = original_content.split("\n")
        self.expanded_lines = []

        # Mapping from expanded lines to original lines (since a variable might
        # theoretically expand to multiple lines, we need to track the original line number
        # for each expanded line.
        self.line_map = []

        self._build_expanded()

    def _build_expanded(self):
        """Build expanded version and line mapping."""
        self.expanded_lines = []
        self.line_map = []

        for orig_line_num, line in enumerate(self.original_lines):
            expanded = expand_path_variables(line, self.path_vars)
            # If variable expanded to multi-line, track all back to same original line
            for sub_line in expanded.split("\n"):
                self.expanded_lines.append(sub_line)
                self.line_map.append(orig_line_num)

    def get_original(self):
        """
        Get the current original content as string.

        Returns:
            The original content with variables unexpanded

        Example:
            >>> content = ConfigContent("key = ${VAR}", {"VAR": "value"})
            >>> content.get_original()
            'key = ${VAR}'
        """
        return "\n".join(self.original_lines)

    def get_expanded(self):
        """
        Get the current expanded content as string.

        Returns:
            The expanded content with variables resolved

        Example:
            >>> content = ConfigContent("key = ${VAR}", {"VAR": "value"})
            >>> content.get_expanded()
            'key = value'
        """
        return "\n".join(self.expanded_lines)

    def replace_lines(self, exp_start, exp_end, replacement_text):
        """
        Replace lines from exp_start to exp_end (inclusive) in expanded view.

        Automatically converts expanded line numbers to original line numbers,
        replaces in original, and rebuilds the expanded view.

        Args:
            exp_start: Starting line number (0-based) in EXPANDED content
            exp_end: Ending line number (0-based, inclusive) in EXPANDED content
            replacement_text: New text to insert (can be multi-line string)

        Raises:
            ValueError: If trying to replace lines that span multiple original lines
                       where some original lines expanded to multiple lines
        """
        # Map expanded line numbers to original line numbers
        orig_start = self.line_map[exp_start]
        orig_end = self.line_map[exp_end]

        # Validate: all expanded lines in this range must map to contiguous original lines
        # with 1:1 mapping (no multi-line variable expansions)
        for orig_line_num in range(orig_start, orig_end + 1):
            expanded_line_count = self.line_map.count(orig_line_num)
            if expanded_line_count > 1:
                raise ValueError(
                    f"Cannot replace: original line {orig_line_num} expanded "
                    f"to {expanded_line_count} lines. Replacing part of a multi-line "
                    f"variable expansion is not supported."
                )

        # Replace in original
        replacement_lines = replacement_text.split("\n")
        self.original_lines[orig_start : orig_end + 1] = replacement_lines

        # Rebuild expanded and line map since structure changed
        self._build_expanded()


def _has_variable_syntax(text):
    """
    Check if text contains variable syntax like ${VAR}.

    Args:
        text: Text to check for variable syntax

    Returns:
        True if text contains ${, False otherwise
    """
    return "${" in text


def _get_unquoted_variable_hint(error_line):
    """
    Generate a helpful hint if a line has an unexpanded variable.

    Args:
        error_line: The line of config that caused an error

    Returns:
        String with hint, or None if no hint applicable
    """
    if _has_variable_syntax(error_line) and "=" in error_line:
        # Extract variable names from the line
        var_names = re.findall(r"\$\{([^}]+)\}", error_line)
        if var_names:
            var_list = ", ".join(var_names)
            return (
                f"\n  Hint: Variable(s) not expanded: {var_list}"
                "\n        Provide value(s) with: "
                "--temporary-expand-var 'VAR=value'"
                "\n        Note: For non-string fields (bool, int), "
                "the expanded value must be valid TOML"
                "\n              (e.g., 'DEBUG=true' for boolean, "
                "'PORT=8080' for integer)"
            )
    return None


def _extract_toml_error_context(error, config_content):
    """
    Extract context information from a TOML parsing error.

    Args:
        error: The TOMLKitError exception
        config_content: The full config content that failed to parse

    Returns:
        String with error message including line context and helpful hints
    """
    error_msg = f"Invalid TOML syntax: {error}"

    # Try to extract line number from error message and show context
    line_match = re.search(r"line (\d+)", str(error))
    if line_match:
        line_num = int(line_match.group(1))
        lines = config_content.split("\n")
        if 0 < line_num <= len(lines):
            error_line = lines[line_num - 1]
            error_msg += f"\n  Line {line_num}: {error_line}"
            hint = _get_unquoted_variable_hint(error_line)
            if hint:
                error_msg += hint

    return error_msg


def _report_file_not_found(script_type, path_str, file_path_root):
    """
    Report a helpful error message when a script file is not found.

    Args:
        script_type: Type of script (e.g., "Starlark script", "shell script")
        path_str: Path string from config
        file_path_root: Root directory where files are searched

    Exits with error code 1 after printing the message.
    """
    click.secho(f"Error: Could not find {script_type}", fg="red", err=True, bold=True)
    click.echo(f"  Script reference: {path_str}", err=True)
    click.echo(f"  Search location: {file_path_root}", err=True)
    sys.exit(1)


def _validate_no_triple_quotes(content, content_type, context_info=None):
    """
    Validate that content doesn't contain triple single quotes.

    Triple quotes would break TOML multi-line literal string format (''').

    Args:
        content: The content to check for triple quotes
        content_type: Description of what's being checked (used for error message)
        context_info: Optional dict with additional context for error message

    Exits with error code 1 if triple quotes are found.
    """
    if "'''" in content:
        click.secho(
            f"Error: {content_type} contains triple single quotes ('''), "
            "which would break the inline format",
            fg="red",
            err=True,
            bold=True,
        )
        if context_info:
            for key, value in context_info.items():
                click.echo(f"  {key.capitalize()}: {value}", err=True)
        sys.exit(1)


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
        ...     subdir = Path(tmpdir) / "scripts"
        ...     subdir.mkdir()
        ...     test_file = subdir / "helper.sh"
        ...     _ = test_file.write_text("test")
        ...     result = find_file("scripts/helper.sh", tmpdir)
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

        >>> expand_default_values(
        ...     "${DIR:-scripts}/${FILE:-test.sh}", {"DIR": "custom"})
        'custom/test.sh'

        >>> expand_default_values(
        ...     "${DIR:-scripts}/${FILE:-test.sh}", {"FILE": "run.sh"})
        'scripts/run.sh'

        >>> expand_default_values(
        ...     "${DIR:-scripts}/${FILE:-test.sh}",
        ...     {"DIR": "custom", "FILE": "run.sh"})
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

    Replaces all occurrences of ${VAR_NAME} and $VAR_NAME in the path string
    with their corresponding values from path_vars.

    Both ${VAR} and $VAR syntaxes are supported to accommodate different
    configuration styles. The $VAR syntax must follow shell variable naming
    rules (letters, digits, underscores; must start with letter or underscore).

    Args:
        path_str: Path string that may contain variable references (string)
        path_vars: Dictionary mapping variable names to their values (dict)

    Returns:
        Path string with all variables expanded (string)

    Example:
        >>> expand_path_variables("${VAR}/file.sh", {"VAR": "scripts"})
        'scripts/file.sh'

        >>> expand_path_variables("$VAR/file.sh", {"VAR": "scripts"})
        'scripts/file.sh'

        >>> expand_path_variables("${VAR}/file.sh", {"VAR": "."})
        './file.sh'

        >>> expand_path_variables("${VAR}/file.sh", {"VAR": ""})
        '/file.sh'

        >>> expand_path_variables("file.sh", {"VAR": "scripts"})
        'file.sh'

        >>> expand_path_variables(
        ...     "${VAR1}/${VAR2}/file.sh", {"VAR1": "dir1", "VAR2": "dir2"})
        'dir1/dir2/file.sh'

        >>> expand_path_variables(
        ...     "$VAR1/$VAR2/file.sh", {"VAR1": "dir1", "VAR2": "dir2"})
        'dir1/dir2/file.sh'

        >>> expand_path_variables("${UNKNOWN}/file.sh", {})
        '${UNKNOWN}/file.sh'

        >>> expand_path_variables("$UNKNOWN/file.sh", {})
        '$UNKNOWN/file.sh'

        >>> expand_path_variables(
        ...     "${VAR1}/${VAR2:-default.sh}", {"VAR1": "scripts"})
        'scripts/default.sh'

        >>> expand_path_variables(
        ...     "${VAR1}/${VAR2:-default.sh}",
        ...     {"VAR1": "scripts", "VAR2": "custom.sh"})
        'scripts/custom.sh'

        >>> expand_path_variables(
        ...     "$PREFIX/sub/file.sh", {"PREFIX": "base", "UNRELATED": "x"})
        'base/sub/file.sh'
    """
    # First, handle ${VAR:-default} patterns (always process these regardless of path_vars
    # since we should still expand default values even if we don't have any values specified)
    result = expand_default_values(path_str, path_vars)

    # Then, replace remaining ${VAR} and $VAR patterns with their values
    if path_vars:
        for variable_name, variable_value in path_vars.items():
            # Replace ${VAR} syntax
            result = result.replace(f"${{{variable_name}}}", variable_value)
            # Replace $VAR syntax (with word boundary to avoid partial matches)
            # Match $VAR followed by non-alphanumeric/underscore or end of string
            result = re.sub(
                rf"\${re.escape(variable_name)}(?=[^A-Za-z0-9_]|$)",
                variable_value,
                result,
            )

    return result


def _search_table_arrays_for_key(table_value, key_name):
    """
    Search for a key within TOML table arrays.

    Args:
        table_value: A table value from TOML structure
        key_name: The key name to search for

    Returns:
        List of values found in the table arrays

    Examples:
        >>> # Non-dict returns empty
        >>> _search_table_arrays_for_key("not a dict", "key")
        []

        >>> # Dict with list containing matching keys
        >>> table = {"starlark": [{"script": "a.star"},
        ...                        {"script": "b.star"}]}
        >>> _search_table_arrays_for_key(table, "script")
        ['a.star', 'b.star']

        >>> # Dict without matching keys
        >>> table = {"starlark": [{"other": "value"}]}
        >>> _search_table_arrays_for_key(table, "script")
        []

        >>> # Mixed: some items have key, some don't
        >>> table = {"items": [{"script": "a.star"},
        ...                     {"name": "x"},
        ...                     {"script": "b.star"}]}
        >>> _search_table_arrays_for_key(table, "script")
        ['a.star', 'b.star']

        >>> # Non-list subtable values ignored
        >>> table = {"config": {"setting": "value"}}
        >>> _search_table_arrays_for_key(table, "setting")
        []

        >>> # Multiple subtables with arrays
        >>> table = {"proc": [{"script": "x"}],
        ...          "out": [{"script": "y"}]}
        >>> _search_table_arrays_for_key(table, "script")
        ['x', 'y']
    """
    results = []
    if not isinstance(table_value, dict):
        return results

    # Iterate through subtables (e.g., "starlark", "execd")
    for subtable_value in table_value.values():
        if not isinstance(subtable_value, list):
            continue

        # Iterate through array elements (the [[...]] entries)
        for item in subtable_value:
            if isinstance(item, dict) and key_name in item:
                results.append(item[key_name])

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

        >>> data = {"processors": {"starlark": [{"script": "test1.star"},
        ...                                       {"script": "test2.star"}]}}
        >>> _find_all_keys_in_toml(data, "script")
        ['test1.star', 'test2.star']

        >>> data = {"outputs": {"execd": [{"command": ["test.sh"]}]}}
        >>> _find_all_keys_in_toml(data, "command")
        [['test.sh']]

        >>> data = {"processors": {"starlark": [{"script": "a.star"}]},
        ...         "outputs": {"execd": [{"command": ["b.sh"]}]}}
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
        results.extend(_search_table_arrays_for_key(table_value, key_name))

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
        start_pos: Start position of the match (where key starts)
        end_pos: End position of the match
        key_name: The key name we're looking for

    Returns:
        True if the snippet is valid TOML containing the key, False otherwise

    Examples:
        >>> config = 'script = "test.star"'
        >>> _is_valid_toml_match(config, 0, len(config), "script")
        True

        >>> config = '# script = "test.star"'
        >>> _is_valid_toml_match(config, 2, len(config), "script")
        False

        >>> config = 'script = "file#with#hash.star"'
        >>> _is_valid_toml_match(config, 0, len(config), "script")
        True

        >>> config = '  script = "test.star"'
        >>> _is_valid_toml_match(config, 2, len(config), "script")
        True
    """
    # Expand to include from the beginning of the line to catch any # comment markers
    line_start = config_content.rfind("\n", 0, start_pos) + 1
    snippet = config_content[line_start:end_pos]

    try:
        doc = tomlkit.parse(snippet)
        return key_name in doc
    except (tomlkit.exceptions.ParseError, KeyError):
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
    # For simple types that don't have unwrap(), convert to appropriate Python type
    return dict(value) if isinstance(value, dict) else value


def find_valid_toml_matches(config_obj, key_name):  # pylint: disable=too-many-locals
    """
    Find a TOML key=value pair in config content using tomlkit for parsing.

    Parses the expanded version (variables replaced) to find matches, then
    returns line numbers in the expanded view. The caller uses these line
    numbers with ConfigContent.replace_lines() to update both versions.

    Uses tomlkit to parse the entire config, which properly handles:
    - Complex nested values (arrays, inline tables, etc.)
    - Multi-line values
    - All TOML syntax variations
    - Comments (they are naturally ignored by the parser)

    Args:
        config_obj: ConfigContent instance
        key_name: The TOML key name to search for and extract (string)

    Returns:
        List of tuples: [(snippet, parsed_value, exp_start, exp_end, indent), ...]
        Empty list if key not found. Each tuple contains:
        - snippet: The exact key=value text from the expanded config (string)
        - parsed_value: The parsed value for key_name from expanded content
        - exp_start: Starting line number in EXPANDED content (int, 0-based)
        - exp_end: Ending line number in EXPANDED content (int, 0-based, inclusive)
        - indent: Number of spaces of indentation for the key (int)

    Raises:
        ValueError: If the config content is not valid TOML (after variable expansion)

    Example:
        >>> config_obj = ConfigContent(
        ...     '[[processors.starlark]]\\n  script = "test.star"', {})
        >>> results = find_valid_toml_matches(config_obj, "script")
        >>> len(results)
        1
        >>> results[0][0]  # snippet
        'script = "test.star"'
        >>> results[0][1]  # parsed value
        'test.star'
        >>> results[0][2], results[0][3]  # exp_start_line, exp_end_line
        (1, 1)
        >>> results[0][4]  # indent
        2

        >>> config_obj = ConfigContent(
        ...     '# [[processors.starlark]]\\n#   script = "commented.star"',
        ...     {})
        >>> find_valid_toml_matches(config_obj, "script")
        []

        >>> config_obj = ConfigContent(
        ...     '[[outputs.execd]]\\n  command = [\\n    '
        ...     '"helper.sh",\\n    "arg1"\\n  ]', {})
        >>> results = find_valid_toml_matches(config_obj, "command")
        >>> results[0][0]  # snippet (style-preserved)
        'command = [\\n    "helper.sh",\\n    "arg1"\\n  ]'
        >>> results[0][1]  # parsed_value
        ['helper.sh', 'arg1']

        >>> config_obj = ConfigContent(
        ...     '[[processors.starlark]]\\n  script = "a.star"\\n'
        ...     '[[processors.starlark]]\\n  script = "b.star"', {})
        >>> results = find_valid_toml_matches(config_obj, "script")
        >>> len(results)  # finds multiple occurrences
        2
        >>> results[0][1]
        'a.star'
        >>> results[1][1]
        'b.star'

        >>> # Comments are ignored, only real entries are found
        >>> config_obj = ConfigContent(
        ...     '# [[processors.starlark]]\\n#   script = "old.star"\\n'
        ...     '[[processors.starlark]]\\n  script = "new.star"', {})
        >>> results = find_valid_toml_matches(config_obj, "script")
        >>> results[0][0]  # only the real one, not commented
        'script = "new.star"'
        >>> results[0][1]
        'new.star'

        >>> # Handles # inside strings correctly
        >>> config_obj = ConfigContent(
        ...     '[[processors.starlark]]\\n  '
        ...     'script = "file#with#hashes.star"', {})
        >>> results = find_valid_toml_matches(config_obj, "script")
        >>> results[0][1]  # handles # inside strings correctly
        'file#with#hashes.star'

        >>> # Variables are expanded for parsing
        >>> config_obj = ConfigContent(
        ...     '[[processors.starlark]]\\n  script = "${VAR}/test.star"',
        ...     {"VAR": "scripts"})
        >>> results = find_valid_toml_matches(config_obj, "script")
        >>> results[0][0]  # snippet from expanded view
        'script = "scripts/test.star"'
        >>> results[0][1]  # parsed value from expanded view
        'scripts/test.star'
    """
    # Parse the expanded content to find all occurrences of the key
    expanded_content = config_obj.get_expanded()

    # Parse the expanded config with tomlkit
    # Variables are already expanded, so this should work for any valid TOML
    try:
        doc = tomlkit.parse(expanded_content)
    except tomlkit.exceptions.TOMLKitError as e:
        error_msg = _extract_toml_error_context(e, expanded_content)
        raise ValueError(error_msg) from e

    # Recursively search for all occurrences of the key in the parsed document
    parsed_values_raw = _find_all_keys_in_toml(doc, key_name)
    if not parsed_values_raw:
        return []

    results = []
    already_found_positions = set()

    # For each value found, extract the normalized value and build a regex
    # that allows flexible whitespace around the = sign.
    #
    # We can't use tomlkit.dumps() output directly to search because it
    # normalizes whitespace around '='. For example:
    #   Original config: script       =       "file.star"
    #   tomlkit.dumps(): script = "file.star"
    # By using _extract_normalized_value() (which gets just the value part)
    # and building a regex with \s*, we can match any amount of whitespace
    # while still preserving the user's original formatting.
    for parsed_value_raw in parsed_values_raw:
        # Extract just the value part (without "key = ")
        # This preserves style (multi-line, indentation, etc.)
        normalized_value = _extract_normalized_value(key_name, parsed_value_raw)

        # Escape the value for use in regex
        escaped_value = re.escape(normalized_value)

        # Build pattern: key\s*=\s*value (allows any whitespace around =)
        pattern = re.compile(
            rf"({re.escape(key_name)})\s*=\s*({escaped_value})",
            re.MULTILINE | re.DOTALL,
        )

        # Search for all matches with flexible whitespace
        for match in pattern.finditer(expanded_content):
            snippet_start = match.start()
            snippet_end = match.end()

            # Check if we already found this position
            if snippet_start in already_found_positions:
                continue

            # Validate with TOML parsing (also filters out commented lines)
            if not _is_valid_toml_match(
                expanded_content, snippet_start, snippet_end, key_name
            ):
                continue

            # Convert character positions to line numbers
            exp_start = expanded_content[:snippet_start].count("\n")
            exp_end = expanded_content[:snippet_end].count("\n")

            # Get the unwrapped value for the caller
            expanded_value = _unwrap_tomlkit_value(parsed_value_raw)

            # Extract the actual snippet from the content (preserves whitespace)
            actual_snippet = expanded_content[snippet_start:snippet_end]

            # Calculate indentation (spaces before the key on the start line)
            line_start = expanded_content.rfind("\n", 0, snippet_start) + 1
            indent = snippet_start - line_start

            # Add the match to the results
            results.append((actual_snippet, expanded_value, exp_start, exp_end, indent))
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

    Raises:
        SystemExit: If a referenced script file cannot be found, an error
            message is printed to stderr and the program exits with status 1.

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
        >>> from contextlib import redirect_stderr
        >>> from io import StringIO
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     script_file = Path(tmpdir) / "test.star"
        ...     _ = script_file.write_text("code with ''' triple quotes")
        ...     config = 'script = "test.star"'
        ...     # This should fail with an error (suppress stderr to avoid doctest output)
        ...     try:
        ...         with redirect_stderr(StringIO()):
        ...             inline_starlark_script(config, tmpdir, {})
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
    # Create ConfigContent object to manage original and expanded versions
    config_obj = ConfigContent(config_content, path_vars)

    # Find all script references once
    matches = find_valid_toml_matches(config_obj, "script")

    if not matches:
        return config_content

    # Process matches in reverse order (highest line numbers first)
    # so that earlier replacements don't affect later line numbers
    for _snippet, path_str, start_line, end_line, indent in reversed(matches):
        script_path = find_file(path_str, file_path_root)

        if not script_path:
            _report_file_not_found("Starlark script", path_str, file_path_root)

        # Read the script content as UTF-8 - this should be safe since we do
        # not expect binary data in Starlark files.
        with open(script_path, encoding="utf-8") as f:
            script_content = f.read()

        # Validate that script doesn't contain triple single quotes
        _validate_no_triple_quotes(
            script_content, "Starlark script", {"script": path_str}
        )

        # Build replacement preserving the original indentation
        indent_str = " " * indent
        replacement = f"{indent_str}source = '''\n{script_content}'''"
        config_obj.replace_lines(start_line, end_line, replacement)

    return config_obj.get_original()


def _replace_shell_script_with_inline(script_path, script_args):
    """Replace a script reference with inline base64-encoded version.

    Args:
        script_path: Path to the script file
        script_args: List of additional arguments to pass to the script (may be empty)

    Returns:
        The inline command string with base64-encoded script
    """
    # Read the script content as UTF-8 - this should be safe since shell scripts
    # are text files.
    with open(script_path, encoding="utf-8") as f:
        script_content = f.read()

    # Normalize line endings: convert CRLF (\r\n) and CR (\r) to LF (\n).
    # This means that we use the Linux standard also when this script is run on Windows.
    # This ensures consistent base64 encoding across platforms.
    script_content = script_content.replace("\r\n", "\n").replace("\r", "\n")

    # Encode to base64 (first encode string to UTF-8 bytes, then base64 encode,
    # and decode the result as ASCII - we know this is safe since base64 only
    # contains ASCII characters)
    script_base64 = base64.b64encode(script_content.encode("utf-8")).decode("ascii")

    # Build the script invocation with arguments
    # We use json.dumps() which:
    # - Properly escapes quotes and special chars for shell double-quote context
    # - Uses double quotes, avoiding conflicts with TOML's ''' quotes
    # - Preserves shell variable expansion ($VAR) and cmd substitution (`cmd`)
    if script_args:
        quoted_args = " ".join(json.dumps(arg) for arg in script_args)
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


def _process_shell_script_match(config_obj, match, file_path_root):
    """Process a single shell script match and replace it with inline version.

    Args:
        config_obj: ConfigContent object to apply replacements to
        match: Tuple of (_snippet, command_array, start_line, end_line, indent)
        file_path_root: Root directory path for finding files

    This function handles validation, path resolution, and replacement for a single
    command reference found in the config file.
    """
    _snippet, command_array, start_line, end_line, indent = match

    # Validate that we have at least one element
    if not command_array or not isinstance(command_array, list):
        click.secho(
            "Error: Invalid command array",
            fg="red",
            err=True,
            bold=True,
        )
        sys.exit(1)

    # Extract script path and arguments. E.g. the line might look like:
    # command = ["scripts/filename.sh", "arg1", "arg2"]
    # or it might look like:
    # command = ["filename.sh"]
    script_path_str = command_array[0]
    script_args = command_array[1:] if len(command_array) > 1 else []

    # Validate that script arguments don't contain triple single quotes
    for arg in script_args:
        _validate_no_triple_quotes(
            arg, "Shell script argument", {"script": script_path_str, "argument": arg}
        )

    # Skip if the path doesn't end with .sh (it might be a binary executable)
    if not script_path_str.endswith(".sh"):
        click.secho(
            f"Warning: Skipping '{script_path_str}' - not a shell script (.sh)",
            fg="yellow",
            err=True,
        )
        return  # Skip this match

    script_path = find_file(script_path_str, file_path_root)

    if not script_path:
        _report_file_not_found("shell script", script_path_str, file_path_root)

    # Build replacement preserving the original indentation
    indent_str = " " * indent
    replacement = _replace_shell_script_with_inline(script_path, script_args)
    indented_replacement = indent_str + replacement
    config_obj.replace_lines(start_line, end_line, indented_replacement)


def inline_shell_script(config_content, file_path_root, path_vars):
    r"""
    Replace external shell script references with base64-encoded inline commands.

    Replaces patterns like:
        command = ["${HELPER_FILES_DIR}/filename.sh", "arg1", "arg2"]
        command = ["${HELPER_FILES_DIR}/${VAR:-default.sh}"]
    with:
        command = ["sh", "-c", '''<inline script wrapper>''']

    The function searches for the referenced .sh file relative to the file_path_root,
    reads its content, encodes it as base64, and wraps it in an inline command that
    decodes the script into a temporary file and executes it. This approach preserves
    stdin for the script (important for Telegraf output plugins that read metrics data).

    Only files ending with .sh are inlined. Other command references (like binary
    executables) are left unchanged with a warning.

    Args:
        config_content: The config file content (string)
        file_path_root: Root directory path for finding files (Path object or string)
        path_vars: Dictionary of path variables that were expanded (dict)

    Returns:
        Config content with shell scripts inlined (string)

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
        ...     # file_path_root is tmpdir, VAR points to subdirectory
        ...     result = inline_shell_script(
        ...         config, str(Path(tmpdir)), {"VAR": "scripts"})
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
        ...     result = inline_shell_script(
        ...         config, str(Path(tmpdir)),
        ...         {"HELPER_FILES_DIR": "scripts"})
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
    # Create ConfigContent object to manage original and expanded versions
    config_obj = ConfigContent(config_content, path_vars)

    # Find all command references once
    matches = find_valid_toml_matches(config_obj, "command")

    if not matches:
        return config_content

    # Process matches in reverse order (highest line numbers first)
    # so that earlier replacements don't affect later line numbers
    for match in reversed(matches):
        _process_shell_script_match(config_obj, match, file_path_root)

    return config_obj.get_original()


def _process_config_file(
    config_file, inline_starlark, inline_shell, file_path_root, path_vars
):
    """
    Process a single config file by reading and optionally inlining scripts.

    Args:
        config_file: Path to config file to process
        inline_starlark: Whether to inline Starlark scripts
        inline_shell: Whether to inline shell scripts
        file_path_root: Root directory for finding referenced files
        path_vars: Dictionary of path variables

    Returns:
        Processed config content as string

    Raises:
        SystemExit: If file not found or processing errors occur

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> # Basic file reading without inlining
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     config = Path(tmpdir) / "test.conf"
        ...     _ = config.write_text("# Test\\n[agent]\\ninterval=10s")
        ...     result = _process_config_file(
        ...         str(config), False, False, tmpdir, {})
        ...     "# Test" in result and "[agent]" in result
        True

        >>> # Content preserved exactly when not inlining
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     config = Path(tmpdir) / "test.conf"
        ...     content = "key = value\\n"
        ...     _ = config.write_text(content)
        ...     result = _process_config_file(
        ...         str(config), False, False, tmpdir, {})
        ...     result == content
        True
    """
    config_path = Path(config_file)

    if not config_path.exists():
        click.secho(
            f"Error: Config file not found: {config_file}",
            fg="red",
            err=True,
            bold=True,
        )
        sys.exit(1)

    # Read config file as UTF-8
    with open(config_path, encoding="utf-8") as f:
        content = f.read()

    # Inline Starlark scripts if requested
    if inline_starlark:
        try:
            content = inline_starlark_script(content, file_path_root, path_vars)
        except ValueError as e:
            click.secho(
                f"Error processing Starlark scripts in: {config_file}",
                fg="red",
                err=True,
                bold=True,
            )
            click.echo(f"  {e}", err=True)
            sys.exit(1)

    # Inline shell scripts if requested
    if inline_shell:
        try:
            content = inline_shell_script(content, file_path_root, path_vars)
        except ValueError as e:
            click.secho(
                f"Error processing shell scripts in: {config_file}",
                fg="red",
                err=True,
                bold=True,
            )
            click.echo(f"  {e}", err=True)
            sys.exit(1)

    return content


def _get_relative_path_or_original(config_file, file_path_root):
    """
    Get relative path to config file if possible, otherwise return original.

    Args:
        config_file: Path to config file
        file_path_root: Root directory path

    Returns:
        Relative path string if possible, otherwise original path

    Examples:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     config = Path(tmpdir) / "test.conf"
        ...     config.touch()
        ...     result = _get_relative_path_or_original(str(config), tmpdir)
        ...     result
        'test.conf'

        >>> # Path outside root returns original
        >>> _get_relative_path_or_original("/other/path/test.conf", "/tmp")
        '/other/path/test.conf'

        >>> # None root returns original
        >>> _get_relative_path_or_original("test.conf", None)
        'test.conf'
    """
    try:
        root_path = Path(file_path_root).resolve()
        abs_config_path = Path(config_file).resolve()
        relative_path = abs_config_path.relative_to(root_path)
        # Normalize to forward slashes for cross-platform compatibility
        return relative_path.as_posix()
    except (ValueError, TypeError):
        # Path is not relative to root_path or root_path is None
        return config_file


def _get_git_status(repo, file_path_in_repo):  # pylint: disable=too-many-return-statements
    """
    Determine the git status of a file in a repository.

    Args:
        repo: GitPython Repo object
        file_path_in_repo: Path object relative to repository root

    Returns:
        Tuple (file_path_normalized, status) where:
        - file_path_normalized: POSIX-normalized path string
        - status: One of 'untracked', 'modified', 'staged', 'clean', 'unknown'

    Examples:
        >>> import tempfile
        >>> import subprocess
        >>> from pathlib import Path
        >>> import git
        >>> # Test clean file
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "test_repo"
        ...     repo_dir.mkdir()
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     test_file = repo_dir / "test.conf"
        ...     _ = test_file.write_text("content")
        ...     _ = subprocess.run(["git", "add", "test.conf"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "commit", "-m", "Initial"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     repo = git.Repo(repo_dir)
        ...     file_path = test_file.relative_to(repo_dir)
        ...     path_norm, status = _get_git_status(repo, file_path)
        ...     repo.close()
        ...     status == 'clean'
        True

        >>> # Test modified file (unstaged changes)
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "test_repo"
        ...     repo_dir.mkdir()
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     test_file = repo_dir / "test.conf"
        ...     _ = test_file.write_text("original")
        ...     _ = subprocess.run(["git", "add", "test.conf"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "commit", "-m", "Initial"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = test_file.write_text("modified")
        ...     repo = git.Repo(repo_dir)
        ...     file_path = test_file.relative_to(repo_dir)
        ...     path_norm, status = _get_git_status(repo, file_path)
        ...     repo.close()
        ...     status == 'modified'
        True

        >>> # Test untracked file
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "test_repo"
        ...     repo_dir.mkdir()
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     dummy = repo_dir / "dummy.txt"
        ...     _ = dummy.write_text("dummy")
        ...     _ = subprocess.run(["git", "add", "dummy.txt"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "commit", "-m", "Initial"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     test_file = repo_dir / "untracked.conf"
        ...     _ = test_file.write_text("untracked")
        ...     repo = git.Repo(repo_dir)
        ...     file_path = test_file.relative_to(repo_dir)
        ...     path_norm, status = _get_git_status(repo, file_path)
        ...     repo.close()
        ...     status == 'untracked'
        True

        >>> # Test staged file (no unstaged changes)
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "test_repo"
        ...     repo_dir.mkdir()
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     test_file = repo_dir / "test.conf"
        ...     _ = test_file.write_text("original")
        ...     _ = subprocess.run(["git", "add", "test.conf"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "commit", "-m", "Initial"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = test_file.write_text("modified")
        ...     _ = subprocess.run(["git", "add", "test.conf"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     repo = git.Repo(repo_dir)
        ...     file_path = test_file.relative_to(repo_dir)
        ...     path_norm, status = _get_git_status(repo, file_path)
        ...     repo.close()
        ...     status == 'staged'
        True

        >>> # Test with empty git repo (no commits yet)
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "test_repo"
        ...     repo_dir.mkdir()
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     test_file = repo_dir / "test.conf"
        ...     _ = test_file.write_text("content")
        ...     repo = git.Repo(repo_dir)
        ...     file_path = test_file.relative_to(repo_dir)
        ...     path_norm, status = _get_git_status(repo, file_path)
        ...     repo.close()
        ...     # File is untracked in empty repo
        ...     status == 'untracked'
        True

        >>> # Test with empty git repo - staged file (no commits yet)
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "test_repo"
        ...     repo_dir.mkdir()
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     test_file = repo_dir / "test.conf"
        ...     _ = test_file.write_text("content")
        ...     _ = subprocess.run(["git", "add", "test.conf"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     repo = git.Repo(repo_dir)
        ...     file_path = test_file.relative_to(repo_dir)
        ...     path_norm, status = _get_git_status(repo, file_path)
        ...     repo.close()
        ...     # File is staged (in index, ready for first commit)
        ...     status == 'staged'
        True
    """
    file_path_normalized = file_path_in_repo.as_posix()

    # Check if file is untracked
    try:
        untracked_normalized = {Path(path).as_posix() for path in repo.untracked_files}
        if file_path_normalized in untracked_normalized:
            return file_path_normalized, "untracked"
    except git.exc.GitCommandError:
        return file_path_normalized, "unknown"

    # Check if file has unstaged changes (working tree differs from index)
    try:
        if repo.index.diff(None, paths=file_path_normalized):
            return file_path_normalized, "modified"
    except (git.exc.GitCommandError, ValueError):
        return file_path_normalized, "unknown"

    # Check if file has staged changes (index differs from HEAD)
    try:
        if repo.index.diff(repo.head.commit, paths=file_path_normalized):
            return file_path_normalized, "staged"
    except (ValueError, AttributeError):
        # No commits yet (ValueError: Reference does not exist) or detached HEAD
        # If we got here, the file is not untracked and has no unstaged changes,
        # so it must be in the index. With no commits, this means it's staged
        # (ready for the first commit).
        return file_path_normalized, "staged"
    except git.exc.GitCommandError:
        # Other git errors - we can't determine the status
        return file_path_normalized, "unknown"

    return file_path_normalized, "clean"


def _get_git_info(file_path):
    """
    Get git repository information for a file using GitPython.

    Args:
        file_path: Path to the file to check

    Returns:
        Dictionary with git info or None if not in a git repo.
        Keys: 'repo_name', 'file_path_in_repo', 'commit', 'status'
        Status values: 'clean', 'modified', 'staged', 'untracked', 'unknown'

    Examples:
        >>> # File not in git repo returns None
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     test_file = Path(tmpdir) / "test.txt"
        ...     test_file.touch()
        ...     _get_git_info(str(test_file)) is None
        True

        >>> # Test with a git repo - clean file
        >>> import tempfile
        >>> import subprocess
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "test_repo"
        ...     repo_dir.mkdir()
        ...     # Initialize git repo
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test User"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     # Create and commit a file
        ...     test_file = repo_dir / "test.conf"
        ...     _ = test_file.write_text("test content")
        ...     _ = subprocess.run(["git", "add", "test.conf"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "commit", "-m", "Initial commit"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     # Get git info
        ...     info = _get_git_info(str(test_file))
        ...     info is not None and info['repo_name'] == 'test_repo'
        True

        >>> # Test with a git repo - verify all properties returned
        >>> import tempfile
        >>> import subprocess
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "my_project"
        ...     repo_dir.mkdir()
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test User"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     test_file = repo_dir / "config.conf"
        ...     _ = test_file.write_text("content")
        ...     _ = subprocess.run(["git", "add", "config.conf"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "commit", "-m", "Add config"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     info = _get_git_info(str(test_file))
        ...     # Check all properties (status tested in _get_git_status)
        ...     (info['file_path_in_repo'] == 'config.conf' and
        ...      info['status'] == 'clean' and
        ...      info['repo_name'] == 'my_project' and
        ...      len(info['commit']) == 12)
        True

        >>> # Test with a git repo - file in subdirectory
        >>> import tempfile
        >>> import subprocess
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     repo_dir = Path(tmpdir) / "test_repo"
        ...     repo_dir.mkdir()
        ...     _ = subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.email", "test@example.com"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "config", "user.name", "Test User"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     # Create subdirectory and file
        ...     subdir = repo_dir / "configs"
        ...     subdir.mkdir()
        ...     test_file = subdir / "test.conf"
        ...     _ = test_file.write_text("content")
        ...     _ = subprocess.run(["git", "add", "configs/test.conf"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     _ = subprocess.run(["git", "commit", "-m", "Add config"],
        ...                        cwd=repo_dir, capture_output=True)
        ...     info = _get_git_info(str(test_file))
        ...     info is not None and info['file_path_in_repo'] == 'configs/test.conf'
        True

    """
    try:
        file_path_obj = Path(file_path).resolve()

        # Find the git repository containing this file
        repo = git.Repo(file_path_obj, search_parent_directories=True)
        try:
            # Get repository name from the root directory
            repo_root = Path(repo.working_dir)
            repo_name = repo_root.name

            # Get file path relative to repo root
            file_path_in_repo = file_path_obj.relative_to(repo_root)

            # Get current commit (short hash)
            try:
                commit = repo.head.commit.hexsha[:12]
            except (ValueError, AttributeError):
                # No commits yet or detached HEAD
                commit = "unknown"

            # Determine the specific status of the file
            file_path_normalized, status = _get_git_status(repo, file_path_in_repo)

            return {
                "repo_name": repo_name,
                "file_path_in_repo": file_path_normalized,
                "commit": commit,
                "status": status,
            }
        finally:
            # Close repo to release file handles (important on Windows)
            repo.close()

    except (git.exc.InvalidGitRepositoryError, git.exc.GitError):
        # Not in a git repository or git error
        return None


def _add_config_header(combined_content, config_file, file_path_root):
    """
    Add header comment for a config file to the combined content.

    Args:
        combined_content: List to append header to
        config_file: Path to config file
        file_path_root: Root directory path for relative path computation

    Examples:
        >>> # First file - blank line before header
        >>> content = []
        >>> _add_config_header(content, "test.conf", "/tmp")
        >>> result = "".join(content)
        >>> "# From file: test.conf" in result
        True
        >>> result.startswith("\\n# ========================================")
        True

        >>> # Git info is included in header
        >>> ("# From file: test.conf" in result and
        ...  ("# Git repo:" in result or "# No version tracking" in result))
        True

        >>> # Second file - separator added before
        >>> first_len = len(content)
        >>> _add_config_header(content, "test2.conf", "/tmp")
        >>> # Check that a newline separator was added between files
        >>> len(content) > first_len and content[first_len] == "\\n"
        True
        >>> "# From file: test2.conf" in "".join(content)
        True

        >>> # Verify relative path handling
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     cfg = Path(tmpdir) / "subdir" / "config.conf"
        ...     cfg.parent.mkdir()
        ...     cfg.touch()
        ...     content = []
        ...     _add_config_header(content, str(cfg), tmpdir)
        ...     "# From file: subdir/config.conf\\n" in "".join(content)
        True
    """
    if combined_content:
        combined_content.append("\n")
    combined_content.append("\n")
    combined_content.append("# ========================================\n")

    display_path = _get_relative_path_or_original(config_file, file_path_root)
    combined_content.append(f"# From file: {display_path}\n")

    # Add git information
    git_info = _get_git_info(config_file)
    if git_info:
        combined_content.append(f"# Git repo: {git_info['repo_name']}\n")
        combined_content.append(
            f"# File path in repo: {git_info['file_path_in_repo']}\n"
        )
        combined_content.append(f"# Commit: {git_info['commit']}\n")
        # Format status for display
        status_display = {
            "clean": "clean",
            "modified": "modified (uncommitted changes)",
            "staged": "staged (changes ready to commit)",
            "untracked": "untracked",
            "unknown": "unknown (could not determine status)",
        }.get(git_info["status"], git_info["status"])
        combined_content.append(f"# Status: {status_display}\n")
    else:
        combined_content.append("# No version tracking info found\n")

    combined_content.append("# ========================================\n\n")


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
        file_path_root: Root directory path for finding referenced files
            (Path object or string, or None)
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
        ...     result = combine_configs(
        ...         [str(config1), str(config2)], False, False,
        ...         str(Path(tmpdir)), {})
        ...     # Check that key elements are present (git info may vary)
        ...     ("# From file: config1.conf" in result and
        ...      "# Config 1" in result and
        ...      "# From file: config2.conf" in result and
        ...      "# Config 2" in result and
        ...      result.count("# ========================================") >= 4)
        True
    """
    combined_content = []

    for config_file in config_files:
        content = _process_config_file(
            config_file, inline_starlark, inline_shell, file_path_root, path_vars
        )
        _add_config_header(combined_content, config_file, file_path_root)
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
    "do_inline_starlark",
    is_flag=True,
    help="Inline Starlark .star files referenced in configs",
)
@click.option(
    "--inline-shell-script",
    "do_inline_shell_script",
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
    help=(
        "Root directory path for finding .star and .sh files referenced "
        "in configs (defaults to current working directory)"
    ),
)
@click.option(
    "--temporary-expand-var",
    multiple=True,
    help=(
        "Temporarily expand variables in configs for TOML parsing and file "
        "resolution (format: VAR=value, e.g., HELPER_FILES_DIR=.)"
    ),
)
def main(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    config,
    do_inline_starlark,
    do_inline_shell_script,
    output,
    file_path_root,
    temporary_expand_var,
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

        # Temporarily expand variables before inlining
        python combine_files.py --config config1.conf --config config2.conf \\
            --temporary-expand-var HELPER_FILES_DIR=. --inline-starlark --inline-shell-script \\
            --output combined.conf
    """
    # Parse variables from --temporary-expand-var arguments
    path_vars = {}
    for var_spec in temporary_expand_var:
        if "=" not in var_spec:
            click.secho(
                f"Error: Invalid variable format: {var_spec}. Expected VAR=value",
                fg="red",
                err=True,
                bold=True,
            )
            sys.exit(1)
        var_name, var_value = var_spec.split("=", 1)
        path_vars[var_name] = var_value

    # Resolve file_path_root to absolute path
    file_path_root_resolved = str(Path(file_path_root).resolve())

    # Combine the configs
    combined = combine_configs(
        config,
        do_inline_starlark,
        do_inline_shell_script,
        file_path_root_resolved,
        path_vars,
    )

    # Write output
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(combined)

    click.echo(
        f"Successfully combined {len(config)} config file(s) into {output}", err=True
    )
    if do_inline_starlark:
        click.echo("  - Starlark scripts inlined", err=True)
    if do_inline_shell_script:
        click.echo("  - Shell scripts inlined (base64 encoded)", err=True)
    if path_vars:
        click.echo(
            f"  - Variables temporarily expanded: {', '.join(path_vars.keys())}",
            err=True,
        )


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
