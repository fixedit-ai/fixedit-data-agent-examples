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

# Process data line by line and output it as pure json.
while IFS= read -r line; do
    # Skip empty lines
    if [ -n "$line" ]; then
        # Process this frame with jq
        echo "$line" | jq -c '
        .frame as $frame |
        if ($frame.observations | length) > 0 then
          $frame.observations[] |
          {
            "frame": $frame.timestamp,
            "timestamp": .timestamp,
            "track_id": .track_id,
            "object_type": (.class.type // "null"),
            "bounding_box": .bounding_box
          }
        else
          empty
        end'
    fi
done < "$HELPER_FILES_DIR/$SAMPLE_FILE"
