#!/bin/sh

# =============================================================================
# Axis Image Consumer Script
# =============================================================================
#
# PURPOSE:
#   Fetches a JPEG from the camera VAPIX API and prints a JSON object containing
#   the base64-encoded image and the optional resolution.
#
# INPUT VARIABLES:
#   VAPIX_USERNAME  - Username for camera authentication (default: root)
#   VAPIX_PASSWORD  - Password for camera authentication (default: pass)
#   CAMERA_IP       - IP address or hostname of the Axis camera (default: 127.0.0.1)
#   RESOLUTION      - Optional image resolution (e.g. 1920x1080) for the JPEG URL query;
#                     if unset the camera uses its default resolution for the JPEG request.
#   TELEGRAF_DEBUG  - Enable debug logging when set to "true"
#   HELPER_FILES_DIR - Directory for debug log files
#
# OUTPUT:
#   Success: JSON with format {"image_base64":"<base64_data>","resolution":"<resolution>"}
#   The resolution key is always present; when RESOLUTION is unset it is an empty string.
#   Failure: {"error":"<message>","image_base64":null}
#
# =============================================================================

# Configuration
VAPIX_USERNAME="${VAPIX_USERNAME:-root}"
VAPIX_PASSWORD="${VAPIX_PASSWORD:-pass}"
CAMERA_IP="${CAMERA_IP:-127.0.0.1}"

# We use HTTP for the image fetch. Since the request is to localhost, this is quite safe.
# If using this to fetch images from an external camera in a non-private network,
# then it is recommended to use HTTPS instead. That can be used together with --insecure
# to handle self-signed certificates, and --anyauth to handle compatibility with both
# AXIS OS 12 and previous versions.
# Using HTTP will remove the overhead of TLS. All Axis devices accept DIGEST authentication
# when using HTTP.
IMAGE_URL="http://${CAMERA_IP}/axis-cgi/jpg/image.cgi"

# Debug mode - use TELEGRAF_DEBUG environment variable
DEBUG="${TELEGRAF_DEBUG:-false}"

# Function to log debug messages
debug_log() {
    if [ "$DEBUG" = "true" ]; then
        echo "DEBUG: $1" >&2
    fi
}

# Function to log debug messages to a file instead of stderr
debug_log_file() {
    if [ "$DEBUG" = "true" ]; then
        echo "DEBUG: $1" >> "${HELPER_FILES_DIR}/axis_image_consumer.debug" 2>/dev/null || true
    fi
}

# Function to fetch image and convert to base64
fetch_image() {
    # Construct URL with resolution if provided
    url="$IMAGE_URL"
    if [ -n "$RESOLUTION" ]; then
        url="${IMAGE_URL}?resolution=${RESOLUTION}"
        debug_log_file "Using resolution parameter: $RESOLUTION"
    fi

    debug_log_file "Fetching image from: $url"
    debug_log_file "Using credentials: $VAPIX_USERNAME:****"

    # Test connectivity first
    test_response=$(curl -s --digest -u "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" "$url" --head 2>&1)
    test_exit=$?

    if [ $test_exit -ne 0 ]; then
        debug_log_file "Connectivity test failed: $test_response"
        return 1
    fi

    # Fetch image with authentication and pipe directly to base64 encoding
    # This avoids storing binary data in shell variables which can corrupt it
    encoded_data=$(curl -s --digest -u "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" "$url" 2>/dev/null | openssl base64 -A)
    curl_exit=$?

    if [ $curl_exit -ne 0 ]; then
        debug_log_file "Curl or base64 encoding failed with exit code $curl_exit"
        return 1
    fi

    # Check if we got actual encoded data (should be more than 100 characters for a valid image)
    data_size=${#encoded_data}
    debug_log_file "Received $data_size characters of base64 encoded data"

    if [ $data_size -lt 100 ]; then
        debug_log_file "Encoded data too small, likely an error"
        return 1
    fi

    # Check if response looks like HTML error page (case-insensitive matching)
    # We need to decode the base64 to check for HTML content, the reason we do
    # it in this slightly roundabout way is because shell variables are not compatible
    # with binary data.
    if echo "$encoded_data" | openssl base64 -d 2>/dev/null | grep -qi "<html\|<title\|error\|Error"; then
        debug_log_file "Response appears to be HTML error page"
        decoded_response=$(echo "$encoded_data" | openssl base64 -d 2>/dev/null)
        debug_log_file "Error response content: $decoded_response"
        return 1
    fi

    echo "$encoded_data"
    return 0
}

# Check if jq is available
if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required but not available" >&2
    exit 1
fi

# Fetch the image
debug_log_file "Starting image fetch..."
IMAGE_BASE64=$(fetch_image)
FETCH_EXIT=$?

# Check if image fetch was successful
if [ $FETCH_EXIT -ne 0 ] || [ -z "$IMAGE_BASE64" ]; then
    debug_log_file "Image fetch failed or returned empty data"
    jq -n '{"error": "Failed to fetch or encode image", "image_base64": null}'
    exit 1
fi

# Build the JSON line Telegraf will parse....
# A JPEG is hundreds of KB once base64-encoded, so we use a here-document instead of e.g.
# passing the variable as an argument to `jq -n --arg img "$IMAGE_BASE64" '{image_base64:$img,...}'`.
# On many systems each program invocation has a tight limit on total argument size.
# Passing the entire base64 blob as argv to jq can fail with "argument list too long" errors.
JSON_OUTPUT=$(cat <<EOF
{"image_base64":"$IMAGE_BASE64","resolution":"${RESOLUTION:-}"}
EOF
)

# Validate JSON using jq
if echo "$JSON_OUTPUT" | jq . >/dev/null 2>&1; then
    debug_log_file "JSON validation successful"
else
    echo "axis_image_consumer.sh: JSON validation failed: invalid JSON payload (jq parse error)" >&2
    exit 1
fi

# Log the actual JSON size
debug_log_file "Actual JSON output size: ${#JSON_OUTPUT} bytes"

# Output the JSON (compact format, no newlines)
printf "%s" "$JSON_OUTPUT"
