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
# - VAPIX_IP: IP address of the Axis strobe device (should be 127.0.0.1 when
#   the FixedIT Data Agent runs on the Axis strobe).
#
# Error Codes:
# - 10: Missing required environment variables
# - 11: Empty input received from stdin
# - 12: No color field found in JSON input
# - 13: Invalid color value (not green/yellow/red)
# - 14: VAPIX API call failed

# Validate required environment variables for VAPIX API access
# These credentials are needed to authenticate with the Axis device
# and control the strobe light profiles via HTTP API calls
if [ -z "$VAPIX_USERNAME" ] || [ -z "$VAPIX_PASSWORD" ] || [ -z "$VAPIX_IP" ]; then
    printf "Error: VAPIX_USERNAME, VAPIX_PASSWORD, and VAPIX_IP must be set\n" >&2
    exit 10
fi

# Read JSON input from Telegraf via stdin
# Expected format: {"fields":{"color":"green"},"name":"workflow_color",...}
# This is the metric data sent by the Telegraf exec output plugin
json_input=$(cat)

# Validate that we received input data
# Empty input indicates a problem with the Telegraf pipeline
if [ -z "$json_input" ]; then
    printf "Error: Empty input received from Telegraf\n" >&2
    printf "Expected JSON format: {\"fields\":{\"color\":\"value\"}}\n" >&2
    exit 11
fi

# Extract color value from JSON using jq
# Telegraf sends individual metric objects when use_batch_format=false
# JSON structure: {"fields":{"color":"value"},"name":"workflow_color",...}
# The .fields.color path extracts the color command from the metric
# Note: If use_batch_format=true was used, we'd need '.metrics[0].fields.color'
color=$(echo "$json_input" | jq -r '.fields.color')

# Validate that color extraction was successful
# jq returns 'null' as a string if the field doesn't exist
# Empty result indicates JSON parsing failure or missing field
if [ -z "$color" ] || [ "$color" = "null" ]; then
    printf "Error: No color field found in JSON input\n" >&2
    printf "Input received: %s\n" "$json_input" >&2
    printf "Expected JSON with .fields.color field\n" >&2
    exit 12
fi

# Validate color value against supported strobe profiles
# Only these three colors have corresponding profiles configured on the device
# Each color represents a different workflow state for visual monitoring
case $color in
    "green")   # Workflow success - all tests passed, deployment successful
        ;;
    "yellow")  # Workflow running - in progress, queued, or unknown state
        ;;
    "red")     # Workflow failure - tests failed, build errors, deployment issues
        ;;
    *)
        printf "Error: Invalid color '%s'\n" "$color" >&2
        printf "Supported colors: green (success), yellow (running), red (failure)\n" >&2
        printf "Ensure corresponding profiles are configured on the Axis device\n" >&2
        exit 13
        ;;
esac

# Function to control strobe light profiles via VAPIX API
# This function handles both starting and stopping of color profiles
# Uses HTTP Digest authentication since the Axis devices requires that for HTTP
control_profile() {
    local profile=$1    # Profile name (green, yellow, red)
    local action=$2     # Action to perform (start, stop)

    # Make VAPIX API call to control the strobe profile
    # Endpoint: siren_and_light.cgi for controlling light patterns
    # Method: POST with JSON payload specifying action and profile
    # Auth: HTTP Digest authentication
    curl --digest -u ${VAPIX_USERNAME}:${VAPIX_PASSWORD} "http://${VAPIX_IP}/axis-cgi/siren_and_light.cgi" \
        -X POST \
        -d "{\"apiVersion\":\"1.0\",\"method\":\"$action\",\"params\":{\"profile\":\"$profile\"}}"

    # Check if the API call was successful
    # Non-zero exit code indicates network error, authentication failure,
    # or invalid profile/action parameters
    if [ $? -ne 0 ]; then
        printf "Failed to %s profile '%s'\n" "$action" "$profile" >&2
        printf "Check network connectivity, credentials, and profile configuration\n" >&2
        exit 14
    fi
}

# Activate the requested color profile
# This starts the strobe pattern corresponding to the workflow status
control_profile "$color" "start"

# Deactivate all other color profiles to ensure exclusive operation,
# this way we do not need to care about the priorities of the profiles
# when creating them.
case $color in
    "green")   # Success state - stop running and failure indicators
        control_profile "yellow" "stop"
        control_profile "red" "stop"
        ;;
    "yellow")  # Running state - stop success and failure indicators
        control_profile "green" "stop"
        control_profile "red" "stop"
        ;;
    "red")     # Failure state - stop success and running indicators
        control_profile "green" "stop"
        control_profile "yellow" "stop"
        ;;
esac