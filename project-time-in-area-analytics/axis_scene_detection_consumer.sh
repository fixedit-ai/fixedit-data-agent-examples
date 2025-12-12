#!/bin/sh

# Axis Camera Metadata Consumer Script
#
# This script consumes analytics scene description data from an Axis camera's
# internal message broker and outputs JSON for Telegraf processing.
#
# IMPORTANT: This script only works when deployed to the camera itself.
# It cannot be tested on a host system because it depends on camera-specific
# commands and internal message broker infrastructure.
#
# Key Features:
# - Consumes analytics scene description data from camera's message broker
# - Unpacks frame events to individual detection messages
# - Filters output to extract only JSON data with detections
# - Outputs structured data for MQTT transmission
# - Camera-specific implementation (requires deployment)
#
# Technical Details:
# - Uses message-broker-cli (camera-specific command)
# - Consumes topic: com.axis.analytics_scene_description.v0.beta
# - Transforms frame-based format to individual detection messages
# - Uses jq to parse and restructure JSON data
# - Outputs one detection per line for Telegraf processing

# Analytics scene description topic (camera-specific)
TOPIC="com.axis.analytics_scene_description.v0.beta"
SOURCE="1"

# Check if jq is available on the camera
if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required but not available on this camera" >&2
    exit 1
fi

# Run the metadata broker, filter JSON, and transform to individual detections
# Example transformations:
# 1. sed removes prefix: "INFO: {json}" -> "{json}"
# 2. jq unpacks:
#    stdin: {"frame":{"observations":[{"track_id":"123"},{"track_id":"456"}]}}
#    stdout: {"frame":"2024-01-15T10:00:01Z","track_id":"123"}
#    stdout: {"frame":"2024-01-15T10:00:01Z","track_id":"456"}
message-broker-cli consume "$TOPIC" "$SOURCE" | \
sed -n 's/^[^{]*//p' | \
jq -c '
.frame as $frame |
if ($frame.observations | length) > 0 then
  $frame.observations[] |
  {
    "frame": $frame.timestamp,
    "timestamp": .timestamp,
    "track_id": .track_id,
    "object_type": .class.type,
    "bounding_box": .bounding_box
  }
else
  empty
end'