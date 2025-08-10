#!/bin/sh

# Sample Data Feeder Script
#
# This script simulates the axis_metadata_consumer.sh behavior for testing.
# It reads the sample JSON file and outputs one detection per message,
# thus making it easier for the json parser in the execd input plugin.
#
# Usage: Called by Telegraf execd input, just like axis_metadata_consumer.sh

# Check if sample file is specified
if [ -z "$SAMPLE_FILE" ]; then
    echo "ERROR: SAMPLE_FILE environment variable not set" >&2
    exit 1
fi

# Check if sample file exists
if [ ! -f "$HELPER_FILES_DIR/$SAMPLE_FILE" ]; then
    echo "ERROR: Sample file not found: $HELPER_FILES_DIR/$SAMPLE_FILE" >&2
    exit 1
fi

# Check if jq is available
if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required but not available" >&2
    exit 1
fi

# Process each frame and output one detection per message
while IFS= read -r line; do
    # Extract frame info
    frame=$(echo "$line" | jq -r '.frame')
    timestamp=$(echo "$line" | jq -r '.timestamp')

    # Get number of detections
    detection_count=$(echo "$line" | jq '.detections | length')

    # Only output messages if there are detections
    if [ "$detection_count" -gt 0 ]; then
        # Output each detection as a separate message
        i=0
        while [ $i -lt "$detection_count" ]; do
            detection=$(echo "$line" | jq ".detections[$i]")
            track_id=$(echo "$detection" | jq -r '.track_id')
            object_type=$(echo "$detection" | jq -r '.object_type')
            x=$(echo "$detection" | jq -r '.x')
            y=$(echo "$detection" | jq -r '.y')

            # Output individual detection with frame context
            echo "{\"frame\": $frame, \"timestamp\": \"$timestamp\", \"track_id\": \"$track_id\", \"object_type\": \"$object_type\", \"x\": $x, \"y\": $y}"

            i=$((i + 1))
        done
    fi
done < "$HELPER_FILES_DIR/$SAMPLE_FILE"
