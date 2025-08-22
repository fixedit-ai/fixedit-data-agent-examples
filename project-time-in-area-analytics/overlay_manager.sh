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
# - Displays time in area, object class, and size information
# - Positions overlay at the center of the detected object
# - Provides comprehensive error handling and validation
#
# Environment Variables Required:
# - VAPIX_USERNAME: Device username
# - VAPIX_PASSWORD: Device password
# - VAPIX_IP: IP address of the Axis device (defaults to 127.0.0.1 for localhost)
# - TELEGRAF_DEBUG: Enable debug logging when set to "true"
# - HELPER_FILES_DIR: Directory for debug log files
#
# Error Codes:
# - 10: Missing required environment variables
# - 11: Empty input received from stdin
# - 12: Invalid JSON input or missing required fields
# - 13: VAPIX API call failed
# - 14: Overlay management error

# Set default VAPIX_IP to localhost if not specified
VAPIX_IP="${VAPIX_IP:-127.0.0.1}"

# Validate required environment variables for VAPIX API access
if [ -z "$VAPIX_USERNAME" ] || [ -z "$VAPIX_PASSWORD" ]; then
    printf "Error: VAPIX_USERNAME and VAPIX_PASSWORD must be set\n" >&2
    exit 10
fi

# Debug mode - use TELEGRAF_DEBUG environment variable
DEBUG="${TELEGRAF_DEBUG:-false}"

# Function to log debug messages to a file
debug_log_file() {
    if [ "$DEBUG" = "true" ]; then
        echo "DEBUG: $1" >> "${HELPER_FILES_DIR}/overlay_manager.debug" 2>/dev/null || true
    fi
}

debug_log_file "Starting overlay_manager.sh script"
debug_log_file "Environment variables - VAPIX_USERNAME: $VAPIX_USERNAME, VAPIX_IP: $VAPIX_IP, DEBUG: $DEBUG"

# Read JSON input from Telegraf via stdin
# Expected format: {"fields":{"track_id":"123","time_in_area_seconds":45.2,"class":"Human",...},"name":"detection_frame",...}
json_input=$(cat)

debug_log_file "Received JSON input: $json_input"

# Validate that we received input data
if [ -z "$json_input" ]; then
    debug_log_file "ERROR: Empty input received from Telegraf"
    printf "Error: Empty input received from Telegraf\n" >&2
    exit 11
fi

# Extract required fields from JSON using jq
track_id=$(echo "$json_input" | jq -r '.fields.track_id // empty')
time_in_area=$(echo "$json_input" | jq -r '.fields.time_in_area_seconds // empty')
object_class=$(echo "$json_input" | jq -r '.fields.object_type // empty')

# Extract pre-calculated coordinates from Starlark processor
center_x=$(echo "$json_input" | jq -r '.fields.center_x // empty')
center_y=$(echo "$json_input" | jq -r '.fields.center_y // empty')
size=$(echo "$json_input" | jq -r '.fields.size // empty')

debug_log_file "Extracted fields - track_id: $track_id, time_in_area: $time_in_area, class: $object_class"

# Validate required fields
if [ -z "$track_id" ] || [ "$track_id" = "null" ] || \
   [ -z "$time_in_area" ] || [ "$time_in_area" = "null" ] || \
   [ -z "$object_class" ] || [ "$object_class" = "null" ]; then
    debug_log_file "ERROR: Missing required fields in JSON input"
    printf "Error: Missing required fields in JSON input\n" >&2
    printf "Required: track_id, time_in_area_seconds, class\n" >&2
    printf "Received: track_id='%s', time_in_area='%s', class='%s'\n" "$track_id" "$time_in_area" "$object_class" >&2
    exit 12
fi

# Use pre-calculated coordinates from Starlark processor
if [ -n "$center_x" ] && [ "$center_x" != "null" ] && \
   [ -n "$center_y" ] && [ "$center_y" != "null" ] && \
   [ -n "$size" ] && [ "$size" != "null" ]; then
    
    debug_log_file "Using pre-calculated coordinates - center: ($center_x, $center_y), size: $size"
else
    # Fallback to center of screen if no coordinates provided
    # Center of screen in VAPIX coordinates is (0.0, 0.0)
    center_x="0.0"
    center_y="0.0"
    size="0.01"
    debug_log_file "No coordinates provided, using center coordinates - center_x: $center_x, center_y: $center_y"
fi

# Format time in area for display
# Use bc for floating point comparison
if [ "$(echo "$time_in_area > 60" | bc -l 2>/dev/null || echo "0")" -eq 1 ]; then
    time_display=$(echo "scale=1; $time_in_area / 60" | bc -l 2>/dev/null || echo "$time_in_area")
    time_unit="min"
else
    time_display=$(echo "scale=0; $time_in_area" | bc -l 2>/dev/null || echo "$time_in_area")
    time_unit="sec"
fi

# Format size for display (convert to percentage)
size_percent=$(echo "scale=1; $size * 100" | bc -l 2>/dev/null || echo "1.0")

# Create overlay text with arrow pointing to the object
# Each piece of information on its own line for better readability
overlay_text="← ID: $track_id
Class: $object_class
Time: ${time_display}${time_unit}
Size: ${size_percent}%"

debug_log_file "Overlay text: $overlay_text"

# Function to control overlays via VAPIX API
control_overlay() {
    action=$1    # Action to perform (addText, setText, remove)
    overlay_id=$2  # Overlay ID (for setText and remove)
    text=$3      # Text content (for addText and setText)
    x=$4         # X coordinate
    y=$5         # Y coordinate
    
    debug_log_file "Making VAPIX API call - Action: $action, ID: $overlay_id, Text: $text, Pos: ($x, $y)"
    
    case $action in
        "addText")
                    # Add new text overlay
        # Escape the text properly for JSON and preserve newlines
        escaped_text=$(echo "$text" | sed 's/"/\\"/g' | sed 's/$/\\n/' | tr -d '\n')
        
        # Create the JSON payload
        json_payload="{\"apiVersion\":\"1.8\",\"method\":\"addText\",\"context\":\"overlay_${track_id}\",\"params\":{\"camera\":1,\"text\":\"$escaped_text\",\"textColor\":\"red\",\"fontSize\":32,\"position\":[$x,$y]}}"
        
        debug_log_file "Sending JSON payload: $json_payload"
        
        api_response=$(curl --silent --fail --digest --user "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" \
            "http://${VAPIX_IP}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi" \
            -X POST \
            -H "Content-Type: application/json" \
            -d "$json_payload" 2>&1)
            ;;
        "setText")
            # Update existing text overlay
            api_response=$(curl --silent --fail --digest --user "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" \
                "http://${VAPIX_IP}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi" \
                -X POST \
                -H "Content-Type: application/json" \
                -d "{
                    \"apiVersion\": \"1.8\",
                    \"method\": \"setText\",
                    \"context\": \"overlay_update_${track_id}\",
                    \"params\": {
                        \"identity\": $overlay_id,
                        \"text\": \"$text\",
                        \"customPosition\": {
                            \"x\": $x,
                            \"y\": $y
                        }
                    }
                }" 2>&1)
            ;;
        "remove")
            # Remove overlay
            api_response=$(curl --silent --fail --digest --user "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" \
                "http://${VAPIX_IP}/axis-cgi/dynamicoverlay/dynamicoverlay.cgi" \
                -X POST \
                -H "Content-Type: application/json" \
                -d "{
                    \"apiVersion\": \"1.8\",
                    \"method\": \"remove\",
                    \"context\": \"overlay_remove_${track_id}\",
                    \"params\": {
                        \"identity\": $overlay_id
                    }
                }" 2>&1)
            ;;
    esac
    
    api_exit=$?
    debug_log_file "API call exit code: $api_exit"
    debug_log_file "API response: $api_response"
    
    if [ $api_exit -ne 0 ]; then
        debug_log_file "ERROR: VAPIX API call failed - Action: $action (exit code: $api_exit)"
        printf "Failed to %s overlay\n" "$action" >&2
        return 1
    fi
    
    # Check if response contains an error
    if echo "$api_response" | grep -q '"error"'; then
        debug_log_file "ERROR: VAPIX API returned error - Action: $action"
        debug_log_file "ERROR: Response: $api_response"
        printf "Failed to %s overlay\n" "$action" >&2
        return 1
    else
        debug_log_file "VAPIX API call successful - Action: $action"
        return 0
    fi
}

# Add new overlay for current detection
debug_log_file "Adding new overlay for track: $track_id"
if control_overlay "addText" "" "$overlay_text" "$center_x" "$center_y"; then
    # Extract the overlay identity from the response
    overlay_identity=$(echo "$api_response" | jq -r '.data.identity // empty' 2>/dev/null)
    
    if [ -n "$overlay_identity" ] && [ "$overlay_identity" != "null" ]; then
        debug_log_file "Overlay added successfully for track: $track_id with identity: $overlay_identity"
        printf "Overlay added for track %s at position (%.3f, %.3f)\n" "$track_id" "$center_x" "$center_y"
        
        # Schedule automatic removal after 1 second
        (
            sleep 1
            debug_log_file "Auto-removing overlay for track: $track_id (ID: $overlay_identity)"
            control_overlay "remove" "$overlay_identity" "" 0 0
            if [ $? -eq 0 ]; then
                debug_log_file "Auto-removal successful for track: $track_id (ID: $overlay_identity)"
            else
                debug_log_file "Auto-removal failed for track: $track_id (ID: $overlay_identity)"
            fi
        ) &
    else
        debug_log_file "Overlay added but could not extract identity from response"
        printf "Overlay added for track %s at position (%.3f, %.3f)\n" "$track_id" "$center_x" "$center_y"
    fi
else
    debug_log_file "ERROR: Failed to add overlay for track: $track_id"
    printf "Failed to add overlay for track %s\n" "$track_id" >&2
    exit 14
fi

debug_log_file "Script completed successfully for track: $track_id"
