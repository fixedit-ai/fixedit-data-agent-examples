#!/bin/sh

# Axis Overlay Manager Script
#
# This script manages text overlays on Axis cameras based on time-in-area analytics.
# It receives detection metrics from Telegraf and displays overlay text showing
# object information when objects exceed the configured threshold.
#
# Key Features:
# - Receives detection metrics via JSON from Telegraf exec output plugin
# - Manages overlays for objects that exceed time-in-area threshold
# - Shows only one object at a time (most recent detection)
# - Displays object ID, time in area and object type
# - Positions overlay at the center of the detected object
# - Provides comprehensive error handling and validation
#
# Environment Variables:
# - VAPIX_USERNAME: Device username (required)
# - VAPIX_PASSWORD: Device password (required)
# - HELPER_FILES_DIR: Directory for debug log files (required)
# - VAPIX_IP: IP address of the Axis device (defaults to 127.0.0.1 for localhost)
# - TELEGRAF_DEBUG: Enable debug logging when set to "true" (defaults to false)
# - FONT_SIZE: Font size for the overlay text (defaults to 32)
#
# Error Codes:
# - 10: Missing required environment variables
# - 11: Empty input received from stdin
# - 12: Invalid JSON input or missing required fields
# - 13: Overlay API call failed

# Set default VAPIX_IP to localhost if not specified
VAPIX_IP="${VAPIX_IP:-127.0.0.1}"

# Set a font size
FONT_SIZE="${FONT_SIZE:-45}"

# Fixed context name for all overlays to ensure only one is active
OVERLAY_CONTEXT="time_in_area_overlay"

# File to store the overlay identity for this context
# Uses HELPER_FILES_DIR which is set by the FixedIt Data Agent
IDENTITY_FILE="${HELPER_FILES_DIR}/.overlay_identity_${OVERLAY_CONTEXT}"

# Strings that we will match from API responses. These should never
# be changed!
API_ERROR_STRING="error"

# Validate required environment variables for VAPIX API access
if [ -z "$VAPIX_USERNAME" ] || [ -z "$VAPIX_PASSWORD" ]; then
    printf "VAPIX_USERNAME and VAPIX_PASSWORD must be set" >&2
    exit 10
fi

# Debug mode - use TELEGRAF_DEBUG environment variable
DEBUG="${TELEGRAF_DEBUG:-false}"

# Function to log debug messages to a file
debug_log_file() {
    _debug_message=$1
    if [ "$DEBUG" = "true" ]; then
        echo "DEBUG: $_debug_message" >> "${HELPER_FILES_DIR}/overlay_manager.debug" 2>/dev/null || true
    fi
    return 0
}

# Function to get stored overlay identity, or return empty if not found
get_stored_identity() {
    if [ -f "$IDENTITY_FILE" ]; then
        cat "$IDENTITY_FILE" 2>/dev/null | tr -d '\n'
    else
        echo ""
    fi
}

# Function to store overlay identity
store_identity() {
    _identity=$1
    echo "$_identity" > "$IDENTITY_FILE" 2>/dev/null || true
    debug_log_file "Stored overlay identity: $_identity"
}

# Helper function to add a new overlay
add_overlay() {
    text=$1      # Text content
    x=$2         # X coordinate
    y=$3         # Y coordinate

    debug_log_file "Adding new overlay - Text: $text, Pos: ($x, $y)"
    json_payload=$(jq -n \
        --arg text "$text" \
        --arg context "$OVERLAY_CONTEXT" \
        --arg font_size "$FONT_SIZE" \
        --arg x "$x" \
        --arg y "$y" \
        '{
            apiVersion: "1.8",
            method: "addText",
            context: $context,
            params: {
                camera: 1,
                text: $text,
                textColor: "red",
                textBGColor: "white",
                textOLColor: "black",
                fontSize: ($font_size|tonumber),
                position: [($x|tonumber),($y|tonumber)]
            }
        }')

    debug_log_file "Sending JSON payload: $json_payload"
    api_response=$(curl --silent --fail --digest --user "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" \
        "http://${VAPIX_IP}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$json_payload" 2>&1)

    api_exit=$?
    debug_log_file "API call exit code: $api_exit"
    debug_log_file "API response: $api_response"

    if [ $api_exit -ne 0 ] || echo "$api_response" | grep -q "\"$API_ERROR_STRING\""; then
        debug_log_file "ERROR: Failed to create overlay"
        return 1
    fi

    # Extract and store the overlay identity from the response
    overlay_identity=$(echo "$api_response" | jq -r '.data.identity // empty' 2>/dev/null)
    if [ -n "$overlay_identity" ] && [ "$overlay_identity" != "null" ]; then
        debug_log_file "Overlay added successfully with identity: $overlay_identity"
        store_identity "$overlay_identity"
    else
        debug_log_file "Overlay added but could not extract identity - will use identity 1 as fallback"
        store_identity "1"
    fi

    return 0
}

# Helper function to update an existing overlay
update_overlay() {
    text=$1      # Text content
    x=$2         # X coordinate
    y=$3         # Y coordinate

    # Get stored identity, or default to 1 if not found
    overlay_identity=$(get_stored_identity)
    if [ -z "$overlay_identity" ]; then
        overlay_identity="1"
        debug_log_file "No stored identity found, using default: 1"
    else
        debug_log_file "Using stored identity: $overlay_identity"
    fi

    debug_log_file "Updating overlay - Text: $text, Pos: ($x, $y), Identity: $overlay_identity"
    json_payload=$(jq -n \
        --arg text "$text" \
        --arg context "$OVERLAY_CONTEXT" \
        --arg identity "$overlay_identity" \
        --arg x "$x" \
        --arg y "$y" \
        '{
            apiVersion: "1.8",
            method: "setText",
            context: $context,
            params: {
                identity: ($identity|tonumber),
                text: $text,
                position: [($x|tonumber),($y|tonumber)]
            }
        }')

    debug_log_file "Sending JSON payload: $json_payload"
    api_response=$(curl --silent --fail --digest --user "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" \
        "http://${VAPIX_IP}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$json_payload" 2>&1)

    api_exit=$?
    debug_log_file "API call exit code: $api_exit"
    debug_log_file "API response: $api_response"

    # Only check for explicit errors - setText doesn't reliably indicate success/failure
    # but if there's an explicit error in the response, we know it failed
    if [ $api_exit -ne 0 ] || echo "$api_response" | grep -q "\"$API_ERROR_STRING\""; then
        debug_log_file "ERROR: Failed to update overlay (curl exit: $api_exit or error in response)"
        return 1
    fi

    # If we get here, assume it worked (setText doesn't reliably indicate success)
    debug_log_file "Updated overlay with identity: $overlay_identity (assuming success)"
    return 0
}

# Helper function to delete an overlay
delete_overlay() {
    # Get stored identity, or default to 1 if not found
    overlay_identity=$(get_stored_identity)
    if [ -z "$overlay_identity" ]; then
        overlay_identity="1"
        debug_log_file "No stored identity found, using default: 1"
    else
        debug_log_file "Using stored identity: $overlay_identity"
    fi

    debug_log_file "Deleting overlay with identity: $overlay_identity"

    json_payload=$(jq -n \
        --arg context "$OVERLAY_CONTEXT" \
        --arg identity "$overlay_identity" \
        '{
            apiVersion: "1.8",
            method: "remove",
            context: $context,
            params: {
                identity: ($identity|tonumber)
            }
        }')

    debug_log_file "Sending JSON payload: $json_payload"
    api_response=$(curl --silent --fail --digest --user "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" \
        "http://${VAPIX_IP}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$json_payload" 2>&1)

    api_exit=$?
    debug_log_file "API call exit code: $api_exit"
    debug_log_file "API response: $api_response"

    if [ $api_exit -ne 0 ] || echo "$api_response" | grep -q "\"$API_ERROR_STRING\""; then
        debug_log_file "ERROR: Failed to delete overlay"
        return 1
    fi

    # Remove stored identity file since overlay is deleted
    rm -f "$IDENTITY_FILE" 2>/dev/null || true
    debug_log_file "Successfully deleted overlay and cleared stored identity"
    return 0
}

# Helper function to update or create overlay
# If identity file exists, update the existing overlay. Otherwise, create a new one.
update_or_create_overlay() {
    text=$1      # Text content
    x=$2         # X coordinate
    y=$3         # Y coordinate

    debug_log_file "Attempting to update or create overlay - Text: $text, Pos: ($x, $y)"
    
    # Check if identity file exists - if it does, we have an existing overlay to update
    if [ -f "$IDENTITY_FILE" ]; then
        debug_log_file "Identity file exists, updating existing overlay"
        update_overlay "$text" "$x" "$y"
        return $?
    else
        debug_log_file "Identity file does not exist, creating new overlay"
        add_overlay "$text" "$x" "$y"
        return $?
    fi
}

# Function to control overlays via VAPIX API
control_overlay() {
    action=$1    # Action to perform (add, update, update_or_add, delete)
    text=$2      # Text content (for add and update)
    x=$3         # X coordinate
    y=$4         # Y coordinate

    debug_log_file "Making VAPIX API call - Action: $action, Text: $text, Pos: ($x, $y)"
    case $action in
        "add")
            add_overlay "$text" "$x" "$y"
            return $?
            ;;
        "update")
            update_overlay "$text" "$x" "$y"
            return $?
            ;;
        "update_or_add")
            update_or_create_overlay "$text" "$x" "$y"
            return $?
            ;;
        "delete")
            delete_overlay
            return $?
            ;;
        *)
            debug_log_file "ERROR: Unknown action: $action"
            return 1
            ;;
    esac

    api_exit=$?
    debug_log_file "API call exit code: $api_exit"
    debug_log_file "API response: $api_response"

    if [ $api_exit -ne 0 ]; then
        debug_log_file "ERROR: VAPIX API call failed - Action: $action (exit code: $api_exit)"
        printf "Failed to %s overlay" "$action" >&2
        return 1
    fi

    # Check if response contains an error
    if echo "$api_response" | grep -q "\"$API_ERROR_STRING\""; then
        debug_log_file "ERROR: VAPIX API returned error - Action: $action"
        debug_log_file "ERROR: Response: $api_response"
        printf "Failed to %s overlay" "$action" >&2
        return 1
    else
        debug_log_file "VAPIX API call successful - Action: $action"
        return 0
    fi
}

debug_log_file "Starting overlay_manager.sh script"
debug_log_file "Environment variables - VAPIX_USERNAME: $VAPIX_USERNAME, VAPIX_IP: $VAPIX_IP, DEBUG: $DEBUG"

# Read JSON input from Telegraf via stdin
# Expected format:
# {
#   "fields":{
#     "center_x":0.22100000000000009,
#     "center_y":0.5509999999999999,
#     "object_type":"Face",
#     "size":0.04262232000000001,
#     "time_in_area_seconds":211.09837293624878,
#     "timestamp":"2025-10-13T14:47:13.252519Z",
#     "track_id":"2923e6a2-920f-40a7-a7a8-f856b1a136cc"
#   },
#   "name":"overlay_frame",
#   "tags":{},
#   "timestamp":1760366877
# }
json_input=$(cat)

debug_log_file "Received JSON input: $json_input"

# Validate that we received input data
if [ -z "$json_input" ]; then
    debug_log_file "ERROR: Empty input received from Telegraf"
    printf "Empty input received from Telegraf" >&2
    exit 11
fi

# Extract required fields from JSON using jq
track_id=$(echo "$json_input" | jq -r '.fields.track_id // empty')
time_in_area=$(echo "$json_input" | jq -r '.fields.time_in_area_seconds // empty')
object_type=$(echo "$json_input" | jq -r '.fields.object_type // empty')
timestamp=$(echo "$json_input" | jq -r '.timestamp // empty')

# Extract pre-calculated coordinates from Starlark processor
center_x=$(echo "$json_input" | jq -r '.fields.center_x // empty')
center_y=$(echo "$json_input" | jq -r '.fields.center_y // empty')

debug_log_file "Extracted fields - track_id: $track_id, time_in_area_seconds: $time_in_area, object_type: $object_type"

# Validate required fields. We allow object_type to be empty (null) since
# this happens before the video object detection has been able to classify
# the object.
if [ -z "$track_id" ] || [ "$track_id" = "null" ] || \
   [ -z "$time_in_area" ] || [ "$time_in_area" = "null" ] || \
   [ -z "$timestamp" ] || [ "$timestamp" = "null" ]; then
    debug_log_file "ERROR: Missing required track info fields in JSON input"
    printf "Missing required track info fields in JSON input. "\
           "Required: track_id, time_in_area_seconds, timestamp. "\
           "Received: track_id='%s', time_in_area_seconds='%s', timestamp='%s'" \
           "$track_id" "$time_in_area" "$timestamp" >&2
    exit 12
fi

# Use pre-calculated coordinates
if [ -z "$center_x" ] || [ "$center_x" = "null" ] || \
   [ -z "$center_y" ] || [ "$center_y" = "null" ]; then
    debug_log_file "ERROR: Missing required coordinate fields in JSON input"
    printf "Missing required coordinate fields in JSON input. "\
           "Required: center_x, center_y. "\
           "Received: center_x='%s', center_y='%s'" \
           "$center_x" "$center_y" >&2
    exit 12
fi

# Get first 10 chars of track_id and add dots if it's longer than 13 chars.
# This makes the overlay text look better if the IDs are very long.
if [ ${#track_id} -gt 13 ]; then
    short_track_id="$(echo "$track_id" | cut -c1-10)..."
else
    short_track_id=$track_id
fi

# Convert the time in fractions of seconds to more readable format
time_in_area_whole_seconds=$(printf "%.0f" "$time_in_area")
time_in_area_readable=$(date -u -d "@$time_in_area_whole_seconds" +%H:%M:%S)

# Convert the detection timestamp (epoch time with no fractions) to
# a more readable format
timestamp_readable=$(date -u -d "@$timestamp" "+%Y-%m-%d %H:%M:%S")

# Create overlay text with arrow pointing to the object
# Each piece of information on its own line for better readability
overlay_text="← ID: $short_track_id
     Type: $object_type
     Time in area: $time_in_area_readable
     Last seen at: $timestamp_readable UTC"

debug_log_file "Overlay text: $overlay_text"

# Update or create overlay for current detection
debug_log_file "Updating/creating overlay for track: $track_id"
if control_overlay "update_or_add" "$overlay_text" "$center_x" "$center_y"; then
    debug_log_file "Overlay updated/created successfully for track: $track_id"
else
    debug_log_file "ERROR: Failed to update/create overlay for track: $track_id"
    printf "Failed to update/create overlay for track %s" "$track_id" >&2
    exit 13
fi

debug_log_file "Script completed successfully for track: $track_id"

