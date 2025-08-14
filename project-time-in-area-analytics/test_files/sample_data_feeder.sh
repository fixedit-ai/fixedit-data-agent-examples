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

# Process each frame and output one observation per message
while IFS= read -r line; do
    # Extract frame timestamp
    frame_timestamp=$(echo "$line" | jq -r '.frame.timestamp')

    # Get number of observations (handle null/empty cases)
    observation_count=$(echo "$line" | jq '.frame.observations | length // 0')

    # Only output messages if there are observations
    if [ "$observation_count" -gt 0 ] 2>/dev/null; then
        # Output each observation as a separate message
        i=0
        while [ $i -lt "$observation_count" ]; do
            observation=$(echo "$line" | jq ".frame.observations[$i]")
            track_id=$(echo "$observation" | jq -r '.track_id')
            object_type=$(echo "$observation" | jq -r '.class.type')
            timestamp=$(echo "$observation" | jq -r '.timestamp')

            # Extract bounding box data
            bounding_box=$(echo "$observation" | jq -c '.bounding_box')

            # Output individual detection with frame context
            echo "{\"frame\": \"$frame_timestamp\", \"timestamp\": \"$timestamp\", \"track_id\": \"$track_id\", \"object_type\": \"$object_type\", \"bounding_box\": $bounding_box}"

            i=$((i + 1))
        done
    fi
done < "$HELPER_FILES_DIR/$SAMPLE_FILE"
