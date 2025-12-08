#!/usr/bin/env python3
"""Test runner for combine_files.py"""

import subprocess
import sys
import tempfile
from difflib import unified_diff
from pathlib import Path


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
            # Prepare command
            # --file-path-root is where to find referenced scripts (test_files_dir)
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

            # Run command
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                print("  ✗ FAILED: Command failed")
                print(f"  Exit code: {result.returncode}")
                if result.stderr:
                    print(f"  Error: {result.stderr[:200]}")
                print()
                return False

            if "Successfully" not in result.stderr:
                print("  ✗ FAILED: No success message")
                print()
                return False

            # Read expected and actual output
            expected_content = expected_file.read_text()
            actual_content = output_file.read_text()

            # Compare
            if expected_content == actual_content:
                print("  ✓ PASSED")
                print()
                return True
            else:
                print("  ✗ FAILED: Output differs from expected")
                print("  Diff (first 20 lines):")
                diff = unified_diff(
                    expected_content.splitlines(keepends=True),
                    actual_content.splitlines(keepends=True),
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
                return False

        except Exception as e:
            print(f"  ✗ FAILED: Exception: {e}")
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
            "--expand-path-var",
            "SCRIPTS_DIR=scripts",
        ),
        (
            "Path variables with default values",
            "test_default_values.conf",
            "test_default_values.conf.expected",
            "--inline-starlark",
            "--inline-shell-script",
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
        print("All tests passed! ✓")
        return 0
    else:
        print("Some tests failed! ✗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
