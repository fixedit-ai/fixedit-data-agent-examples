# Combine Config Files and Scripts for Easier Deployment

Many projects for the [FixedIT Data Agent](https://fixedit.ai/products-data-agent/) end up with multiple `*.conf` files, multiple `.star` Starlark script files and multiple `.sh` shell scripts. Each of these files needs to be uploaded individually to the FixedIT Data Agent which makes the deployment process hard. It is however good to have many smaller files during development since it makes it easier to navigate the code base and write automatic tests for parts of the functionality.

This tool is intended to relieve the pain of having to upload multiple files to the FixedIT Data Agent by combining them into a single file. The tool can combine multiple configuration files into a single file and also inline both Starlark and shell scripts into the same configuration file.

This script is kept generic and should work for any project.

## Table of Contents

<!-- toc -->

- [Installation](#installation)
- [Usage](#usage)
  - [Required Options](#required-options)
  - [Optional Options](#optional-options)
  - [Temporary Variable Expansion](#temporary-variable-expansion)
  - [Simple Example](#simple-example)
  - [Full Example with All Features](#full-example-with-all-features)
- [Example: Combining Multiple Files for the Time-in-Area Project](#example-combining-multiple-files-for-the-time-in-area-project)
  - [Production Configuration](#production-configuration)
  - [Host Testing Configuration](#host-testing-configuration)
- [How it Works](#how-it-works)
  - [Configuration File Combining](#configuration-file-combining)
  - [Starlark Script Inlining](#starlark-script-inlining)
  - [Shell Script Inlining](#shell-script-inlining)
- [Generation of TOML Files](#generation-of-toml-files)
- [Known Limitations](#known-limitations)
  - [Variable Expansion in Script Arguments](#variable-expansion-in-script-arguments)
  - [General Note](#general-note)

<!-- tocstop -->

## Installation

The script requires Python and the dependencies in `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Usage

Basic syntax:

```bash
python combine_files.py [OPTIONS]
```

### Required Options

- `--config <file>` - Configuration file to include (can be specified multiple times, will be combined in the order specified)
- `--output <file>` - Output file path for the combined configuration

### Optional Options

- `--inline-starlark` - Inline Starlark `.star` files referenced in configs. Replaces `script = "file.star"` with `source = '''...content...'''`
- `--inline-shell-script` - Inline shell `.sh` scripts referenced in configs using base64 encoding. Replaces `command = ["file.sh"]` with an inline base64-decoded command
- `--file-path-root <dir>` - Root directory path for finding `.star` and `.sh` files referenced in configs (defaults to current working directory)
- `--temporary-expand-var <VAR=value>` - Temporarily expand variables in configs for TOML parsing and file resolution (can be specified multiple times). Format: `VAR=value`, e.g., `HELPER_FILES_DIR=.`

### Temporary Variable Expansion

The `--temporary-expand-var` option allows you to temporarily substitute variables in your configuration files for TOML parsing and file resolution. The variables are NOT substituted in the final output - they remain as-is so they can be resolved at runtime. This is useful when:

- Your configs reference helper files using variables like `${HELPER_FILES_DIR}/script.sh`
- You want to use different scripts for testing vs production (e.g., `${CONSUMER_SCRIPT:-default.sh}`)
- Your config contains non-string fields (booleans, integers) that use variables and need valid TOML values to parse correctly

The tool supports the following variable patterns:

- `${VAR}` - Simple variable substitution (bash-style with braces)
- `$VAR` - Simple variable substitution (shell-style without braces)
- `${VAR:-default}` - Variable with default value (uses `default` if `VAR` is not defined)

Both `${VAR}` and `$VAR` syntaxes are supported for flexibility. Use the syntax that best fits your configuration style.

Variables are expanded temporarily before the script attempts to parse the TOML and find/inline the referenced files. The original variables are preserved in the output file so they can be resolved at runtime.

### Simple Example

Combine two config files without any inlining:

```bash
python combine_files.py \
  --config config1.conf \
  --config config2.conf \
  --output combined.conf
```

This is essentially the same as appending the second file to the end of the first file and saving it to a new file. The script does, however, also add headers between the content of the files referencing which file the content came from.

### Full Example with All Features

Combine multiple configs with Starlark and shell script inlining:

```bash
python combine_files.py \
  --config config1.conf \
  --config config2.conf \
  --inline-starlark \
  --inline-shell-script \
  --temporary-expand-var HELPER_FILES_DIR=. \
  --file-path-root . \
  --output combined.conf
```

## Example: Combining Multiple Files for the Time-in-Area Project

The following example has been tested on the [Work-in-Progress Time-in-Area project from this open PR](https://github.com/fixedit-ai/fixedit-data-agent-examples/pull/12).

### Production Configuration

To generate a combined configuration file with all scripts inlined for deployment to the FixedIT Data Agent, run:

```bash
export PROJECT_DIR=/path/to/time-in-area-analytics-project
python3 combine_files.py \
  --config $PROJECT_DIR/config_agent.conf \
  --config $PROJECT_DIR/config_input_scene_detections.conf \
  --config $PROJECT_DIR/config_process_class_filter.conf \
  --config $PROJECT_DIR/config_process_zone_filter.conf \
  --config $PROJECT_DIR/config_process_track_duration.conf \
  --config $PROJECT_DIR/config_process_threshold_filter.conf \
  --config $PROJECT_DIR/config_process_rate_limit.conf \
  --config $PROJECT_DIR/config_process_overlay_transform.conf \
  --config $PROJECT_DIR/config_output_overlay.conf \
  --config $PROJECT_DIR/config_process_alarming_state.conf \
  --config $PROJECT_DIR/config_output_events.conf \
  --inline-starlark \
  --inline-shell-script \
  --temporary-expand-var HELPER_FILES_DIR=. \
  --file-path-root $PROJECT_DIR \
  --output combined.conf
```

This will create a `combined.conf` file that:

- Concatenates all configuration files in the correct order
- Inlines Starlark scripts (`.star` files) directly into the configuration
- Inlines shell scripts (`.sh` files) as base64-encoded commands

The resulting single file can be uploaded to the FixedIT Data Agent without needing to upload any separate helper files.

### Host Testing Configuration

You can also generate a combined configuration for host testing. Note the use of `--temporary-expand-var` to override the consumer script with a test version:

```bash
export PROJECT_DIR=/path/to/time-in-area-analytics-project
python3 combine_files.py \
  --config $PROJECT_DIR/config_agent.conf \
  --config $PROJECT_DIR/config_input_scene_detections.conf \
  --config $PROJECT_DIR/config_process_class_filter.conf \
  --config $PROJECT_DIR/config_process_zone_filter.conf \
  --config $PROJECT_DIR/config_process_track_duration.conf \
  --config $PROJECT_DIR/test_files/config_output_stdout.conf \
  --inline-starlark \
  --inline-shell-script \
  --temporary-expand-var HELPER_FILES_DIR=. \
  --temporary-expand-var CONSUMER_SCRIPT=test_files/sample_data_feeder.sh \
  --file-path-root $PROJECT_DIR \
  --output combined_host_test.conf
```

Note that you had to set the `CONSUMER_SCRIPT` variable to the path to the sample data feeder script relative to the `file-path-root`, otherwise the `combine_files.py` script would use the default "real" metadata consumer script which is not available on the host.

This will create a `combined_host_test.conf` file that can be tested on your local machine:

```bash
# Set up test environment with real device data
export SAMPLE_FILE="$PROJECT_DIR/test_files/real_device_data.jsonl"
export TELEGRAF_DEBUG=true

# Set zone to cover entire view (so all detections pass through)
export INCLUDE_ZONE_POLYGON='[[[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]]]'

# Run telegraf
telegraf --config combined_host_test.conf --once
```

## How it Works

### Configuration File Combining

The script reads each configuration file in the order specified and concatenates them with separator comments showing which file each section came from. The path shown in comments is relative to `--file-path-root` when possible.

### Starlark Script Inlining

When `--inline-starlark` is used, the script finds all references like:

```toml
script = "path/to/file.star"
```

and replaces them with:

```toml
source = '''
...content of file.star...
'''
```

The script will fail if the Starlark file contains triple single quotes (`'''`) since that would break the inline format.

### Shell Script Inlining

When `--inline-shell-script` is used, the script finds all references like:

```toml
command = ["path/to/file.sh"]
```

and replaces them with:

```toml
command = ["sh", "-c", '''
tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT
openssl base64 -d -A <<'FIXEDIT_SCRIPT_EOF' >"$tmpfile"
...base64 encoded script...
FIXEDIT_SCRIPT_EOF
sh "$tmpfile"''']
```

The script is base64-encoded to avoid any escaping issues. The temp file approach preserves stdin for the Telegraf data (important for output plugins). The `openssl base64 -d` command is used instead of the `base64` command since `base64` doesn't exist on Axis devices.

**Important**: This works well for `execd` plugins since unpacking only happens once during startup, but might introduce overhead on `exec` plugins since they would be unpacked for every metric passed to them.

## Generation of TOML Files

We are intentionally not using any library to dump the modified TOML files. Instead we do string manipulation to build the final TOML file. The reasoning for this is that we want to introduce as little change as possible when translating the original TOML files to the combined TOML file (with scripts inlined). Using a TOML library to write the file would rewrite every single line, and a bug in that logic could be introduced anywhere in the generated files. By doing manual string manipulation, we can guarantee that the only lines that are changed are the ones inlining scripts. We use the `tomlkit` library for parsing TOML files since that is a style-preserving parser which makes it easier to modify selected lines in the toml without rewriting the entire file.

## Known Limitations

### Variable Expansion in Script Arguments

If you use `--temporary-expand-var` to define a variable (e.g., `--temporary-expand-var MY_VAR=value`), and that same variable appears in a script's command arguments, it will be expanded to the provided value before being passed to the script. This happens because the tool parses the expanded version of the configuration to locate scripts for inlining.

For example:

```bash
# Config has: command = ["script.sh", "$TELEGRAF_DEBUG"]
# Running with: --temporary-expand-var TELEGRAF_DEBUG=false
# Result: The argument becomes `false` instead of "$TELEGRAF_DEBUG"
```

**Workaround:** Read the environment variables in your script arguments using the `env` command or use a different variable name in your script arguments than those you define with `--temporary-expand-var`. Variables not defined in `--temporary-expand-var` are preserved as-is and will be expanded by the shell at runtime.

### General Note

This script is relatively early in its development, so we recommend validating the generated files before using them in production.
