#!/bin/sh

# Axis Strobe Light Controller Script
#
# This script controls an Axis strobe light device by activating specific
# color profiles based on GitHub workflow status received via Telegraf.
#
# Key Features:
# - Receives color commands via JSON from Telegraf exec output plugin
# - Controls Axis strobe device using VAPIX HTTP API
# - Manages exclusive color profiles (only one active at a time)
# - Provides comprehensive error handling and validation
# - Supports green (success), yellow (running), and red (failure) colors
#
# Environment Variables Required:
# - VAPIX_USERNAME: Device username
# - VAPIX_PASSWORD: Device password
# - TELEGRAF_DEBUG: Enable debug logging when set to "true"
# - HELPER_FILES_DIR: Directory for debug log files
#
# Optional Environment Variables:
# - VAPIX_IP: IP address of the Axis strobe device (defaults to 127.0.0.1)
#
# Error Codes:
# - 10: Missing required environment variables
# - 11: Empty input received from stdin
# - 12: No color field found in JSON input
# - 13: Invalid color value (not green/yellow/red)
# - 14: VAPIX API call failed

# Set stricter error handling
set -eu

# Color profile constants
readonly COLOR_GREEN="green"
readonly COLOR_YELLOW="yellow"
readonly COLOR_RED="red"

# Validate required environment variables for VAPIX API access
# These credentials are needed to authenticate with the Axis device
# and control the strobe light profiles via HTTP API calls
if [ -z "$VAPIX_USERNAME" ] || [ -z "$VAPIX_PASSWORD" ]; then
    printf "Error: VAPIX_USERNAME and VAPIX_PASSWORD must be set" >&2
    exit 10
fi

# Set default IP to localhost if not provided. This is what is needed when
# running directly on the Axis strobe.
VAPIX_IP="${VAPIX_IP:-127.0.0.1}"

# Debug mode - use TELEGRAF_DEBUG environment variable
DEBUG="${TELEGRAF_DEBUG:-false}"

# Function to log debug messages to a file
debug_log_file() {
    _dbg_log_message="$1"
    if [ "$DEBUG" = "true" ]; then
        echo "DEBUG: $_dbg_log_message" >> "${HELPER_FILES_DIR}/trigger_strobe.debug" 2>/dev/null || true
    fi
    return 0
}

debug_log_file "Starting trigger_strobe.sh script"
debug_log_file "Environment variables - VAPIX_USERNAME: $VAPIX_USERNAME, VAPIX_IP: $VAPIX_IP, DEBUG: $DEBUG"

# Read JSON input from Telegraf via stdin
# Expected format: {"fields":{"color":"green"},"name":"workflow_color",...}
# This is the metric data sent by the Telegraf exec output plugin
json_input=$(cat)

debug_log_file "Received JSON input: $json_input"

# Validate that we received input data
# Empty input indicates a problem with the Telegraf pipeline
if [ -z "$json_input" ]; then
    debug_log_file "ERROR: Empty input received from Telegraf"
    printf "Error: Empty input received from Telegraf. Expected JSON format: {\"fields\":{\"color\":\"value\"}}" >&2
    exit 11
fi

# Extract color value from JSON using jq
# Telegraf sends individual metric objects when use_batch_format=false
# JSON structure: {"fields":{"color":"value"},"name":"workflow_color",...}
# The .fields.color path extracts the color command from the metric
# Note: If use_batch_format=true was used, we'd need '.metrics[0].fields.color'
if ! color="$(printf '%s\n' "$json_input" | jq -re '.fields.color? // empty')"; then
  debug_log_file "ERROR: jq failed to extract .fields.color from input:$json_input"
  printf "Error: No color field found in JSON input:$json_input" >&2
  exit 12
fi

debug_log_file "Extracted color value: $color"

# Validate color value against supported strobe profiles
# Only these three colors have corresponding profiles configured on the device
# Each color represents a different workflow state for visual monitoring
debug_log_file "Validating color value: $color"
case $color in
    "$COLOR_GREEN")   # Workflow success - all tests passed, deployment successful
        debug_log_file "Color validation successful: green (success)"
        ;;
    "$COLOR_YELLOW")  # Workflow running - in progress, queued, or unknown state
        debug_log_file "Color validation successful: yellow (running)"
        ;;
    "$COLOR_RED")     # Workflow failure - tests failed, build errors, deployment issues
        debug_log_file "Color validation successful: red (failure)"
        ;;
    *)
        debug_log_file "ERROR: Invalid color value: $color"
        printf "Error: Invalid color '%s'. Supported colors: green ($COLOR_GREEN), yellow ($COLOR_YELLOW), red ($COLOR_RED)." "$color" >&2
        exit 13
        ;;
esac

# Function to control strobe light profiles via VAPIX API
# This function handles both starting and stopping of color profiles
# Uses HTTP Digest authentication since the Axis devices requires that for HTTP
control_profile() {
    _ctrl_profile="$1"    # Profile name (green, yellow, red)
    _ctrl_action="$2"     # Action to perform (start, stop)

    debug_log_file "Making VAPIX API call - Profile: $_ctrl_profile, Action: $_ctrl_action"
    debug_log_file "API endpoint: http://${VAPIX_IP}/axis-cgi/siren_and_light.cgi"
    debug_log_file "Using credentials: $VAPIX_USERNAME:$(printf '%*s' ${#VAPIX_PASSWORD} '' | tr ' ' '*')"

    # Make VAPIX API call to control the strobe profile
    # Endpoint: siren_and_light.cgi for controlling light patterns
    # Method: POST with JSON payload specifying action and profile
    # Auth: HTTP Digest authentication
    _ctrl_api_response=$(curl --fail --digest --user "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" "http://${VAPIX_IP}/axis-cgi/siren_and_light.cgi" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "{\"apiVersion\":\"1.0\",\"method\":\"$_ctrl_action\",\"params\":{\"profile\":\"$_ctrl_profile\"}}" 2>&1)
    _ctrl_api_exit=$?

    debug_log_file "API call exit code: $_ctrl_api_exit"
    debug_log_file "API response: $_ctrl_api_response"

    # Check if the API call was successful
    # Non-zero exit code indicates network error, authentication failure,
    # or invalid profile/action parameters
    if [ $_ctrl_api_exit -ne 0 ]; then
        debug_log_file "ERROR: VAPIX API call failed - Profile: $_ctrl_profile, Action: $_ctrl_action"
        debug_log_file "ERROR: Response: $_ctrl_api_response"
        printf "Failed to %s profile '%s'" "$_ctrl_action" "$_ctrl_profile" >&2
        exit 14
    else
        debug_log_file "VAPIX API call successful - Profile: $_ctrl_profile, Action: $_ctrl_action"
    fi
    return 0
}

# Activate the requested color profile
# This starts the strobe pattern corresponding to the workflow status
debug_log_file "Starting color profile: $color"
control_profile "$color" "start"

# Deactivate all other color profiles to ensure exclusive operation,
# this way we do not need to care about the priorities of the profiles
# when creating them.
debug_log_file "Deactivating other color profiles to ensure exclusive operation"
case $color in
    "$COLOR_GREEN")   # Success state - stop running and failure indicators
        debug_log_file "Stopping yellow and red profiles"
        control_profile "$COLOR_YELLOW" "stop"
        control_profile "$COLOR_RED" "stop"
        ;;
    "$COLOR_YELLOW")  # Running state - stop success and failure indicators
        debug_log_file "Stopping green and red profiles"
        control_profile "$COLOR_GREEN" "stop"
        control_profile "$COLOR_RED" "stop"
        ;;
    "$COLOR_RED")     # Failure state - stop success and running indicators
        debug_log_file "Stopping green and yellow profiles"
        control_profile "$COLOR_GREEN" "stop"
        control_profile "$COLOR_YELLOW" "stop"
        ;;
    *)
        debug_log_file "ERROR: Invalid color value: $color"
        printf "Error: Invalid color '%s'. Supported colors: green ($COLOR_GREEN), yellow ($COLOR_YELLOW), red ($COLOR_RED)." "$color" >&2
        exit 13
        ;;
esac

debug_log_file "Script completed successfully - Color: $color"