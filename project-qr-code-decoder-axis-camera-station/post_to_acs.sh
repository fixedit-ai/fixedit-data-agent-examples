#!/bin/sh

# ACS External Data POST Script for QR Code Detections
#
# This script receives QR code detection data from the FixedIT Data Agent via
# Telegraf exec output plugin and posts it to an ACS (Axis Camera Station)
# server using the ExternalDataFacade API endpoint.
#
# Environment Variables:
# - ACS_SERVER_IP: IP address or hostname of the ACS server (required)
# - ACS_SOURCE: Source identifier for the data (required)
# - ACS_USERNAME: Username for basic authentication (required)
# - ACS_PASSWORD: Password for basic authentication (required)
# - HELPER_FILES_DIR: Directory where to write the debug log file
#   (required, set automatically by the FixedIT Data Agent)
# - ACS_EXTERNAL_DATA_TYPE: Type identifier for the external data (defaults to "QRCodeDetection")
# - ACS_PORT: Port number for the ACS server API (defaults to "55756")
# - CURL_INSECURE: Set to "true" to skip SSL certificate verification (defaults to "false")
# - TELEGRAF_DEBUG: Enable debug logging (defaults to "false")
#
# Error Codes:
# - 10: Missing required environment variables
# - 11: Empty input received from stdin
# - 12: Failed to extract required fields from JSON input
# - 13: Failed to format timestamp
# - 14: ACS API call failed
# - 15: A tool/command is required but not available

# Set stricter error handling
set -eu

# Validate required environment variables
if [ -z "$ACS_SERVER_IP" ]; then
    printf "Error: ACS_SERVER_IP must be set" >&2
    exit 10
fi

if [ -z "$ACS_SOURCE" ]; then
    printf "Error: ACS_SOURCE must be set" >&2
    exit 10
fi

if [ -z "$ACS_USERNAME" ] || [ -z "$ACS_PASSWORD" ]; then
    printf "Error: ACS_USERNAME and ACS_PASSWORD must be set" >&2
    exit 10
fi

# Set default values for optional parameters
ACS_EXTERNAL_DATA_TYPE="${ACS_EXTERNAL_DATA_TYPE:-QRCodeDetection}"
ACS_PORT="${ACS_PORT:-55756}"
DEBUG="${TELEGRAF_DEBUG:-false}"

# Determine if we should skip SSL verification
# This is useful for testing with self-signed certificates but should be avoided in production
_curl_insecure_flag=""
if [ "${CURL_INSECURE:-false}" = "true" ]; then
    _curl_insecure_flag="--insecure"
fi

# Temp file for capturing curl stderr, cleaned up on exit
_api_stderr_file=""
cleanup() {
    [ -n "$_api_stderr_file" ] && rm -f "$_api_stderr_file"
    return 0
}
trap cleanup EXIT INT TERM

# Function to log debug messages to a file
debug_log_file() {
    _dbg_log_message="$1"
    if [ "$DEBUG" = "true" ]; then
        echo "DEBUG: $_dbg_log_message" >> "${HELPER_FILES_DIR}/post_to_acs.debug" 2>/dev/null || true
    fi
    return 0
}

# Function to check if API call has errors
# Returns 0 if error detected, 1 if successful
has_api_error() {
    _check_exit_code="$1"
    _check_http_code="$2"

    # Check if the API call was successful
    # Non-zero exit code indicates network error, authentication failure,
    # or invalid request parameters
    # HTTP status codes >= 400 also indicate errors
    if [ $_check_exit_code -ne 0 ]; then
        return 0  # Error detected
    elif [ -n "$_check_http_code" ] && [ "$_check_http_code" -ge 400 ] 2>/dev/null; then
        return 0  # Error detected
    else
        return 1  # No error
    fi
}

# Function to log and report ACS API call errors, then exit
log_api_error() {
    _err_stderr_file="$1"
    _err_exit_code="$2"
    _err_http_code="$3"
    _err_response_body="$4"
    _err_api_url="$5"

    # Read any curl errors from stderr
    _err_curl_error=""
    if [ -f "$_err_stderr_file" ]; then
        _err_curl_error=$(cat "$_err_stderr_file" 2>/dev/null)
    fi

    debug_log_file "ERROR: ACS API call failed - exit code: $_err_exit_code, HTTP status: $_err_http_code"
    debug_log_file "ERROR: Response body: $_err_response_body"
    if [ -n "$_err_curl_error" ]; then
        debug_log_file "ERROR: Curl error: $_err_curl_error"
    fi

    # Provide specific error message based on error type
    if [ -n "$_err_http_code" ] && [ "$_err_http_code" -ge 400 ] 2>/dev/null; then
        printf "Error: HTTP error response from server (status code: %s)" "$_err_http_code" >&2
    else
        # Handle curl exit codes
        case $_err_exit_code in
            60)
                printf "Error: SSL certificate verification failed. If using a self-signed certificate, set CURL_INSECURE=true" >&2
                ;;
            7)
                printf "Error: Failed to connect to ACS server at %s" "$_err_api_url" >&2
                ;;
            *)
                printf "Error: Failed to post external data to ACS server (curl exit code: %d)" "$_err_exit_code" >&2
                ;;
        esac
    fi

    if [ -n "$_err_curl_error" ]; then
        printf "\nCurl error: %s" "$_err_curl_error" >&2
    fi

    if [ -n "$_err_response_body" ]; then
        printf "\nResponse: %s" "$_err_response_body" >&2
    fi
    exit 14
}

debug_log_file "Starting post_to_acs.sh script"
debug_log_file "Environment variables - ACS_SERVER_IP: $ACS_SERVER_IP, ACS_USERNAME: $ACS_USERNAME, DEBUG: $DEBUG"

# Check if jq is available
if ! command -v jq >/dev/null 2>&1; then
    printf "Error: jq is required but not available" >&2
    exit 15
fi

# Read JSON input from Telegraf via stdin
# This is the metric data sent by the Telegraf exec output plugin
_json_input=$(cat)

debug_log_file "Received JSON input: $_json_input"

# Validate that we received input data
# Empty input indicates a problem with the Telegraf pipeline
if [ -z "$_json_input" ]; then
    debug_log_file "ERROR: Empty input received from Telegraf"
    printf "Error: Empty input received from Telegraf. Expected JSON format with QR code detection fields" >&2
    exit 11
fi

# Extract required fields from JSON using jq
if ! _decoded_value="$(printf '%s\n' "$_json_input" | jq -re '.fields.decoded_data? // empty')"; then
    debug_log_file "ERROR: jq failed to extract .fields.decoded_data from input"
    printf "Error: Failed to extract decoded_data from JSON input" >&2
    exit 12
fi

if ! _decoded_time="$(printf '%s\n' "$_json_input" | jq -re '.fields.frame_timestamp? // empty')"; then
    debug_log_file "ERROR: jq failed to extract .fields.frame_timestamp from input"
    printf "Error: Failed to extract frame_timestamp from JSON input" >&2
    exit 12
fi

if ! _code_type="$(printf '%s\n' "$_json_input" | jq -re '.fields.code_type? // empty')"; then
    debug_log_file "ERROR: jq failed to extract .fields.code_type from input"
    printf "Error: Failed to extract code_type from JSON input" >&2
    exit 12
fi

if ! _code_position_size="$(printf '%s\n' "$_json_input" | jq -re '.fields.code_position_size? // empty')"; then
    debug_log_file "ERROR: jq failed to extract .fields.code_position_size from input"
    printf "Error: Failed to extract code_position_size from JSON input" >&2
    exit 12
fi

# Validate that we got non-empty values for required fields
if [ -z "$_decoded_value" ] || [ -z "$_decoded_time" ] || [ -z "$_code_type" ] || [ -z "$_code_position_size" ]; then
    debug_log_file "ERROR: One or more required fields are empty"
    printf "Error: Required fields cannot be empty. decoded_value: %s, time: %s, code_type: %s, code_position_size: %s" \
        "$_decoded_value" "$_decoded_time" "$_code_type" "$_code_position_size" >&2
    exit 12
fi

debug_log_file "Extracted fields - decoded_value: $_decoded_value, time: $_decoded_time, code_type: $_code_type, code_position_size: $_code_position_size"

# Convert Unix timestamp to ACS format "YYYY-MM-DD HH:MM:SS"
# The frame_timestamp is in seconds since epoch
if ! _occurrence_time=$(date -d "@$_decoded_time" '+%Y-%m-%d %H:%M:%S' 2>/dev/null); then
    debug_log_file "ERROR: Failed to format timestamp: $_decoded_time"
    printf "Error: Failed to format timestamp '%s'" "$_decoded_time" >&2
    exit 13
fi
debug_log_file "Formatted timestamp: $_occurrence_time"

# Log the ACS source identifier
debug_log_file "Using source identifier: $ACS_SOURCE"

# Construct the API endpoint URL
_api_url="https://${ACS_SERVER_IP}:${ACS_PORT}/Acs/Api/ExternalDataFacade/AddExternalData"

# Build the JSON payload for ACS API using jq to safely escape special characters
# The API expects a nested structure with addExternalDataRequest containing
# the use case specific fields.
if ! _json_payload=$(jq -n \
    --arg occurrenceTime "$_occurrence_time" \
    --arg source "$ACS_SOURCE" \
    --arg externalDataType "$ACS_EXTERNAL_DATA_TYPE" \
    --arg decodedValue "$_decoded_value" \
    --arg codeType "$_code_type" \
    --arg codePositionSize "$_code_position_size" \
    '{
        "addExternalDataRequest": {
            "occurrenceTime": $occurrenceTime,
            "source": $source,
            "externalDataType": $externalDataType,
            "data": {
                "Decoded Value": $decodedValue,
                "Code Type": $codeType,
                "Position and Size": $codePositionSize
            }
        }
    }'); then
    debug_log_file "ERROR: Failed to build JSON payload"
    printf "Error: Failed to build JSON payload" >&2
    exit 12
fi

debug_log_file "JSON payload: $_json_payload"

# Make the API call using curl
# The endpoint uses HTTPS and requires basic authentication and proper JSON content type
# Error responses are captured for debugging purposes
# We capture both the response body and HTTP status code
_api_stderr_file=$(mktemp)
_api_response=$(curl --silent --show-error $_curl_insecure_flag \
    --user "${ACS_USERNAME}:${ACS_PASSWORD}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$_json_payload" \
    --write-out "\n%{http_code}" \
    "$_api_url" 2>"$_api_stderr_file")
_api_exit=$?

# Extract HTTP status code (last line) and response body (everything else)
_api_http_code=$(echo "$_api_response" | tail -n 1)
_api_response_body=$(echo "$_api_response" | sed '$d')

# Check if API call has errors
if has_api_error "$_api_exit" "$_api_http_code"; then
    log_api_error "$_api_stderr_file" "$_api_exit" "$_api_http_code" "$_api_response_body" "$_api_url"
fi

debug_log_file "ACS API call successful - HTTP status: $_api_http_code, Response: $_api_response_body"

exit 0
