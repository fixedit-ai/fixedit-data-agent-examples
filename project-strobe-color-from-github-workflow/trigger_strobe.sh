#!/bin/sh

# Script to trigger the strobe light with a specific color
# This script is called by telegraf's exec plugin to control the strobe light
# based on the workflow status color from GitHub metrics.
# It reads the color from stdin in JSON format.

# Validate that the environment variables are set
if [ -z "$VAPIX_USERNAME" ] || [ -z "$VAPIX_PASSWORD" ] || [ -z "$VAPIX_IP" ]; then
    printf "Error: VAPIX_USERNAME, VAPIX_PASSWORD, and VAPIX_IP must be set\n" >&2
    exit 10
fi

# Read the JSON input from stdin
json_input=$(cat)

# Check if we got any input
if [ -z "$json_input" ]; then
    printf "Error: Empty input received\n" >&2
    exit 11
fi

# Extract the color value using jq
# The JSON structure is: {"fields":{"color":"value"},"name":"workflow_color",...}
# This works since we are using the new use_batch_format=false option, otherwise
# we would need to use jq -r '.metrics[0].fields.color'.
color=$(echo "$json_input" | jq -r '.fields.color')

# Validate that we got a color
if [ -z "$color" ] || [ "$color" = "null" ]; then
    printf "Error: No color found in input: %s\n" "$json_input" >&2
    exit 12
fi

# Validate that the color is one of the allowed values
case $color in
    "green"|"yellow"|"red")
        ;;
    *)
        printf "Error: Invalid color '%s'. Must be one of: green, yellow, red\n" "$color" >&2
        exit 13
        ;;
esac

# Function to control a profile (start or stop)
control_profile() {
    local profile=$1
    local action=$2
    curl --digest -u ${VAPIX_USERNAME}:${VAPIX_PASSWORD} "http://${VAPIX_IP}/axis-cgi/siren_and_light.cgi" \
        -X POST \
        -d "{\"apiVersion\":\"1.0\",\"method\":\"$action\",\"params\":{\"profile\":\"$profile\"}}"

    if [ $? -ne 0 ]; then
        printf "Failed to %s profile '%s'\n" "$action" "$profile" >&2
        exit 14
    fi
}

# Start the requested profile
control_profile "$color" "start"

# Stop all profiles except the one we want to start
case $color in
    "green")
        control_profile "yellow" "stop"
        control_profile "red" "stop"
        ;;
    "yellow")
        control_profile "green" "stop"
        control_profile "red" "stop"
        ;;
    "red")
        control_profile "green" "stop"
        control_profile "yellow" "stop"
        ;;
esac