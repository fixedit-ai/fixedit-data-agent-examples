#!/usr/bin/env python3
"""Test runner for combine_files.py"""

import re
import subprocess
import sys
import tempfile
from difflib import unified_diff
from pathlib import Path


def compare_with_regex(expected_lines, actual_lines):
    """
    Compare expected and actual lines, supporting regex patterns in expected.

    Expected lines can contain {{REGEX:pattern}} which will be matched
    against the corresponding actual line using regex.

    Args:
        expected_lines: List of expected lines (may contain {{REGEX:pattern}})
        actual_lines: List of actual lines

    Returns:
        Tuple (bool, list): (True if match, list of mismatch details)
    """
    if len(expected_lines) != len(actual_lines):
        return False, [
            f"Line count mismatch: expected {len(expected_lines)}, got {len(actual_lines)}"
        ]

    mismatches = []
    for i, (expected, actual) in enumerate(zip(expected_lines, actual_lines)):
        # Check if this line uses regex pattern
        regex_match = re.search(r"\{\{REGEX:(.+?)\}\}", expected)
        if regex_match:
            pattern = regex_match.group(1)
            # Replace the {{REGEX:...}} with the pattern for matching
            expected_pattern = expected.replace(f"{{{{REGEX:{pattern}}}}}", pattern)
            # Ensure pattern matches the full line (strip newlines for comparison)
            expected_stripped = expected_pattern.rstrip("\n\r")
            actual_stripped = actual.rstrip("\n\r")
            # Use fullmatch to ensure the entire line matches the pattern
            if not re.fullmatch(expected_stripped, actual_stripped):
                mismatches.append(
                    f"Line {i+1}: regex pattern '{pattern}' did not match '{actual_stripped}'"
                )
        else:
            # Exact match required
            if expected != actual:
                mismatches.append(f"Line {i+1}: expected '{expected}', got '{actual}'")

    return len(mismatches) == 0, mismatches


def _run_combine_command(script_path, config_file, test_files_dir, output_file, *args):
    """
    Run the combine_files.py command and validate the result.

    Args:
        script_path: Path to combine_files.py
        config_file: Path to config file
        test_files_dir: Path to test_files directory
        output_file: Path to output file
        *args: Additional arguments for combine_files.py

    Returns:
        Tuple (bool, str): (True if command succeeded, error message if failed)
    """
    cmd = [
        sys.executable,
        str(script_path),
        "--config",
        str(config_file),
        "--file-path-root",
        str(test_files_dir),
        "--output",
        str(output_file),
        *args,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        error_msg = f"Command failed with exit code {result.returncode}"
        if result.stderr:
            error_msg += f": {result.stderr[:200]}"
        return False, error_msg

    if "Successfully" not in result.stderr:
        return False, "No success message in output"

    return True, ""


def _report_test_failure(mismatches, expected_lines, actual_lines, expected_file):
    """
    Report test failure with mismatch details or unified diff.

    Args:
        mismatches: List of mismatch messages
        expected_lines: Expected output lines
        actual_lines: Actual output lines
        expected_file: Path to expected file
    """
    print("  X FAILED: Output differs from expected")
    if mismatches:
        print("  Mismatches:")
        for mismatch in mismatches[:10]:  # Show first 10 mismatches
            print(f"    {mismatch}")
        if len(mismatches) > 10:
            print(f"    ... and {len(mismatches) - 10} more")
    else:
        # Fallback to unified diff if regex comparison didn't provide details
        print("  Diff (first 20 lines):")
        diff = unified_diff(
            expected_lines,
            actual_lines,
            fromfile=str(expected_file),
            tofile="actual output",
            lineterm="",
        )
        for i, line in enumerate(diff):
            if i >= 20:
                print("  ...")
                break
            print(f"  {line.rstrip()}")
    print()


def run_test(
    test_name, script_path, test_files_dir, config_filename, expected_filename, *args
):
    """
    Run a single test case.

    Args:
        test_name: Name of the test
        script_path: Path to combine_files.py
        test_files_dir: Path to test_files directory (contains configs and scripts)
        config_filename: Config filename (relative to test_files_dir)
        expected_filename: Expected output filename (relative to test_files_dir)
        *args: Additional arguments for combine_files.py

    Returns:
        True if test passed, False otherwise
    """
    print(f"Test: {test_name}")

    # Build paths
    config_file = test_files_dir / config_filename
    expected_file = test_files_dir / expected_filename

    # Use a temporary directory that auto-cleans up
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_file = Path(tmp_dir) / "output.txt"

        try:
            # Run command and validate
            success, error_msg = _run_combine_command(
                script_path, config_file, test_files_dir, output_file, *args
            )
            if not success:
                print(f"  X FAILED: {error_msg}")
                print()
                return False

            # Read expected and actual output
            expected_content = expected_file.read_text()
            actual_content = output_file.read_text()

            # Compare with regex support
            expected_lines = expected_content.splitlines(keepends=True)
            actual_lines = actual_content.splitlines(keepends=True)

            matches, mismatches = compare_with_regex(expected_lines, actual_lines)

            if matches:
                print("  [OK]")
                print()
                return True

            _report_test_failure(
                mismatches, expected_lines, actual_lines, expected_file
            )
            return False

        except Exception as e:
            print(f"  X FAILED: Exception: {e}")
            print()
            return False


def main():
    """Run all integration tests."""
    # Locate paths using pathlib
    test_files_dir = Path(__file__).parent
    script_path = test_files_dir.parent / "combine_files.py"

    print("Running combine_files.py integration tests...")
    print()

    tests_passed = 0
    tests_failed = 0

    # Define all tests - filenames are relative to test_files_dir
    tests = [
        (
            "Starlark inline",
            "test_starlark_inline.conf",
            "test_starlark_inline.conf.expected",
            "--inline-starlark",
        ),
        (
            "Shell inline",
            "test_shell_inline.conf",
            "test_shell_inline.conf.expected",
            "--inline-shell-script",
        ),
        (
            "Both inline",
            "test_both_inline.conf",
            "test_both_inline.conf.expected",
            "--inline-starlark",
            "--inline-shell-script",
        ),
        (
            "Comments preserved",
            "test_comments.conf",
            "test_comments.conf.expected",
            "--inline-starlark",
        ),
        (
            "Multi-line arrays",
            "test_multiline.conf",
            "test_multiline.conf.expected",
            "--inline-shell-script",
        ),
        (
            "Whitespace preserved",
            "test_whitespace.conf",
            "test_whitespace.conf.expected",
            "--inline-starlark",
            "--inline-shell-script",
        ),
        (
            "Multiple starlark scripts",
            "test_multiple_scripts.conf",
            "test_multiple_scripts.conf.expected",
            "--inline-starlark",
        ),
        (
            "Multiple shell commands",
            "test_multiple_commands.conf",
            "test_multiple_commands.conf.expected",
            "--inline-shell-script",
        ),
        (
            "Shell script with arguments",
            "test_script_with_args.conf",
            "test_script_with_args.conf.expected",
            "--inline-shell-script",
        ),
        (
            "Multiple mixed scripts and commands",
            "test_multiple_mixed.conf",
            "test_multiple_mixed.conf.expected",
            "--inline-starlark",
            "--inline-shell-script",
        ),
        (
            "Path variables",
            "test_path_variables.conf",
            "test_path_variables.conf.expected",
            "--inline-starlark",
            "--inline-shell-script",
            "--temporary-expand-var",
            "SCRIPTS_DIR=scripts",
        ),
        (
            "Path variables with default values",
            "test_default_values.conf",
            "test_default_values.conf.expected",
            "--inline-starlark",
            "--inline-shell-script",
        ),
        (
            "Non-string variables (e.g. boolean)",
            "test_nonstring_variables.conf",
            "test_nonstring_variables.conf.expected",
            "--inline-starlark",
            "--temporary-expand-var",
            "TELEGRAF_DEBUG=true",
        ),
        (
            "Multi-line variable expansion",
            "test_multiline_variable.conf",
            "test_multiline_variable.conf.expected",
            "--inline-starlark",
            "--temporary-expand-var",
            'MULTILINE_DESC="""\nLine 1\nLine 2\nLine 3\n"""',
        ),
    ]

    # Run all tests
    for test_name, config_filename, expected_filename, *test_args in tests:
        if run_test(
            test_name,
            script_path,
            test_files_dir,
            config_filename,
            expected_filename,
            *test_args,
        ):
            tests_passed += 1
        else:
            tests_failed += 1

    # Summary
    print("=" * 60)
    print("Test Summary:")
    print(f"  Passed: {tests_passed}")
    print(f"  Failed: {tests_failed}")
    print("=" * 60)

    if tests_failed == 0:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed! X")
        return 1


if __name__ == "__main__":
    sys.exit(main())
