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


def read_file_content(file_path):
    """
    Read file content, handling encoding issues.

    Attempts to read the file as UTF-8 text. If that fails due to encoding
    issues, falls back to binary mode and decodes with error replacement.

    Args:
        file_path: Path to the file to read (Path object or string)

    Returns:
        String content of the file

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     test_file = Path(tmpdir) / "test.txt"
        ...     _ = test_file.write_text("Hello, world!")
        ...     content = read_file_content(test_file)
        ...     content == "Hello, world!"
        True

        >>> # Test binary fallback with invalid UTF-8
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     test_file = Path(tmpdir) / "test.bin"
        ...     _ = test_file.write_bytes(bytes([0xff, 0xfe, 0x00, 0x01]))
        ...     content = read_file_content(test_file)
        ...     len(content) > 0  # Should decode with replacement characters
        True
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        # Fallback to binary mode if UTF-8 fails
        with open(file_path, "rb") as f:
            return f.read().decode("utf-8", errors="replace")


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
    if not path_vars:
        return path_str

    result = path_str

    # First, handle ${VAR:-default} patterns - use default value if VAR not in path_vars
    var_default_pattern = r"\$\{([^:}]+):-([^}]+)\}"

    def replace_default(match):
        var_name = match.group(1)
        default_value = match.group(2)
        if var_name in path_vars:
            return path_vars[var_name]
        return default_value

    result = re.sub(var_default_pattern, replace_default, result)

    # Then, replace remaining ${VAR} patterns with their values
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


def inline_starlark_script(config_content, file_path_root, path_vars):
    """
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
        "source = '''\\nload('test.star', 'test')'''"

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
        "source = '''\\ntest content'''"

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
    """
    # Pattern to match: script = "any/path/with/variables"
    # Matches the entire quoted path string, which may contain any number of variables
    pattern = r'script\s*=\s*"([^"]+)"'

    def replace_script(match):
        path_str = match.group(1)  # The entire path string (may contain variables)

        script_path = resolve_script_path(path_str, file_path_root, path_vars)

        if not script_path:
            click.echo(
                f"Error: Could not find Starlark script '{path_str}' in root path '{file_path_root}'",
                err=True,
            )
            sys.exit(1)

        # Read the script content
        script_content = read_file_content(script_path)

        # Validate that script doesn't contain triple single quotes which would break the inline format
        if "'''" in script_content:
            click.echo(
                f"Error: Starlark script '{path_str}' contains triple single quotes ('''), which would break the inline source format",
                err=True,
            )
            sys.exit(1)

        # Replace with inline source
        return f"source = '''\n{script_content}'''"

    return re.sub(pattern, replace_script, config_content)


def inline_shell_script(config_content, file_path_root, path_vars):
    """
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
    """

    def replace_with_inline(script_path, original):
        """Replace a script reference with inline base64-encoded version."""
        if not script_path:
            return original

        # Read the script content
        script_content = read_file_content(script_path)

        # Encode to base64
        script_base64 = base64.b64encode(script_content.encode("utf-8")).decode("ascii")

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
            f"sh \"$tmpfile\"''']\n"
        )

        return inline_command.rstrip("\n")  # Remove trailing newline

    # Pattern to match: command = ["any/path/with/variables"]
    # Matches the entire quoted path string, which may contain any number of variables
    # expand_path_variables handles both ${VAR} and ${VAR:-default} patterns
    # Handles both single-line and multi-line command arrays
    pattern = r'command\s*=\s*\[([^\]]*?)"([^"]+)"([^\]]*?)\]'

    def replace_command(match):
        """Handle script references with variable expansion."""
        path_str = match.group(2)  # The entire path string (may contain variables)

        # Expand variables to determine the actual file path
        expanded_path = expand_path_variables(path_str, path_vars)

        # Skip if the expanded path doesn't end with .sh (it might be a binary executable)
        if not expanded_path.endswith(".sh"):
            click.secho(
                f"Warning: Skipping '{path_str}' (expanded: '{expanded_path}') - not a shell script (.sh)",
                fg="yellow",
                err=True,
            )
            return match.group(0)  # Return unchanged

        script_path = resolve_script_path(path_str, file_path_root, path_vars)

        if script_path:
            return replace_with_inline(script_path, match.group(0))
        click.echo(
            f"Error: Could not find shell script '{path_str}' in root path '{file_path_root}'",
            err=True,
        )
        sys.exit(1)

    content = re.sub(pattern, replace_command, config_content)

    return content


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

        content = read_file_content(config_path)

        # Inline Starlark scripts if requested
        if inline_starlark:
            content = inline_starlark_script(content, file_path_root, path_vars)

        # Inline shell scripts if requested
        if inline_shell:
            content = inline_shell_script(content, file_path_root, path_vars)

        # Add a header comment for each config file (with relative path if possible)
        if combined_content:
            combined_content.append("\n")
        combined_content.append(f"# ========================================\n")

        # Try to make path relative to file_path_root
        try:
            root_path = Path(file_path_root).resolve()
            abs_config_path = Path(config_file).resolve()
            relative_path = abs_config_path.relative_to(root_path)
            combined_content.append(f"# From: {relative_path}\n")
        except (ValueError, TypeError):
            # Path is not relative to root_path or root_path is None, use the original path
            combined_content.append(f"# From: {config_file}\n")

        combined_content.append(f"# ========================================\n\n")
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
    """
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
