#!/bin/sh
# Script to make HTTP requests with token-based authentication
# Supports two modes:
#   --request-metrics: Make a request to get data, output response to stdout (for Telegraf input)
#   --send-metrics: Read data from stdin, send as POST body (for Telegraf output)

# Exit codes
EXIT_SUCCESS=0
EXIT_MISSING_TOKEN_FILE=10
EXIT_EMPTY_TOKEN_FILE=11
EXIT_FAILED_TO_PARSE_TOKEN=12
EXIT_MISSING_CONFIG=13
EXIT_NO_METRICS_DATA=14
EXIT_AUTH_FAILED=20
EXIT_SERVER_ERROR=21
EXIT_UNEXPECTED_ERROR=22

# Usage function
usage() {
  echo "Usage: $0 --url URL [--send-metrics|--request-metrics] [--default-token TOKEN]" >&2
  exit 1
}

# Function to get the token from token file
# The file uses JSONL format (one JSON object per line)
# Returns the token from the last line (latest token), or empty string if not found
get_token() {
  local token_file="${HELPER_FILES_DIR}/token.txt"
  local token=""
  
  echo "[DEBUG] Looking for token file at: $token_file" >&2
  
  if [ -f "$token_file" ] && [ -s "$token_file" ]; then
    echo "[DEBUG] Token file found, reading latest token (last line)..." >&2
    # Read the last line from the JSONL file and extract the token field
    token=$(tail -n 1 "$token_file" | jq -r '.fields.token' 2>/dev/null)
    if [ -n "$token" ] && [ "$token" != "null" ]; then
      echo "[DEBUG] Token found: $(echo "$token")..." >&2
      echo "$token"
      return 0
    else
      echo "[DEBUG] Failed to parse token from file" >&2
    fi
  else
    echo "[DEBUG] Token file does not exist or is empty" >&2
  fi
  
  # Token not found, return empty
  return 0
}

# Function to send HTTP request
# Arguments: method url token [data]
send_http_request() {
  local method=$1
  local url=$2
  local token=$3
  local data=$4
  
  if [ -z "$data" ]; then
    # For requests without data body (GET, or POST with no body)
    curl -X "$method" "$url" \
      -H "Authorization: Bearer $token" \
      -H "serial: ${DEVICE_PROP_SERIAL}" \
      -H "Content-Type: application/json" \
      -w "\n%{http_code}" \
      -s
  else
    # For requests with data body
    curl -X "$method" "$url" \
      -H "Authorization: Bearer $token" \
      -H "serial: ${DEVICE_PROP_SERIAL}" \
      -H "Content-Type: application/json" \
      -d "$data" \
      -w "\n%{http_code}" \
      -s
  fi
}

# Helper function to make a request with retry logic on 401
# Arguments: method url token default_token data_or_empty_string
# Sets: REQUEST_HTTP_CODE, REQUEST_BODY
make_request_with_retry() {
  local method=$1
  local url=$2
  local token=$3
  local default_token=$4
  local data=$5
  
  RESPONSE=$(send_http_request "$method" "$url" "$token" "$data")
  REQUEST_HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
  REQUEST_BODY=$(echo "$RESPONSE" | sed '$d')
  
  # If 401 (invalid token) and we have a default token, retry with it
  if [ "$REQUEST_HTTP_CODE" = "401" ] && [ -n "$default_token" ]; then
    echo "[DEBUG] Got 401 with current token, retrying with default token" >&2
    RESPONSE=$(send_http_request "$method" "$url" "$default_token" "$data")
    REQUEST_HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
    REQUEST_BODY=$(echo "$RESPONSE" | sed '$d')
  fi
}

# Helper function to handle response and exit appropriately
# Arguments: http_code body auth_failure_msg
# Exits with appropriate code or continues if success (200)
handle_response() {
  local http_code=$1
  local body=$2
  local auth_error_msg=$3
  
  if [ "$http_code" = "200" ]; then
    return 0
  elif [ "$http_code" = "401" ]; then
    echo "ERROR: $auth_error_msg" >&2
    echo "Response: $body" >&2
    exit $EXIT_AUTH_FAILED
  elif [ "$http_code" -ge 400 ] 2>/dev/null; then
    echo "ERROR: Server error (HTTP $http_code)" >&2
    echo "Response: $body" >&2
    exit $EXIT_SERVER_ERROR
  else
    echo "ERROR: Unexpected HTTP status code: $http_code" >&2
    echo "Response: $body" >&2
    exit $EXIT_UNEXPECTED_ERROR
  fi
}

# Parse CLI arguments
MODE=""
DEFAULT_TOKEN=""
REQUEST_URL=""

while [ $# -gt 0 ]; do
  case "$1" in
    --url)
      shift
      if [ -z "$1" ]; then
        echo "ERROR: --url requires a URL value" >&2
        usage
      fi
      REQUEST_URL="$1"
      shift
      ;;
    --send-metrics)
      MODE="send"
      shift
      ;;
    --request-metrics)
      MODE="request"
      shift
      ;;
    --default-token)
      shift
      if [ -z "$1" ]; then
        echo "ERROR: --default-token requires a token value" >&2
        usage
      fi
      DEFAULT_TOKEN="$1"
      shift
      ;;
    *)
      usage
      ;;
  esac
done

if [ -z "$REQUEST_URL" ]; then
  echo "ERROR: --url is required" >&2
  usage
fi

if [ -z "$MODE" ]; then
  usage
fi

# Validate required environment variables
if [ -z "$SERVER_URL" ]; then
  echo "ERROR: SERVER_URL not set" >&2
  exit $EXIT_MISSING_CONFIG
fi

if [ -z "$DEVICE_PROP_SERIAL" ]; then
  echo "ERROR: DEVICE_PROP_SERIAL not set" >&2
  exit $EXIT_MISSING_CONFIG
fi

if [ -z "$HELPER_FILES_DIR" ]; then
  echo "ERROR: HELPER_FILES_DIR not set" >&2
  exit $EXIT_MISSING_CONFIG
fi

# Get token from file
echo "[DEBUG] Attempting to read token from file..." >&2
TOKEN=$(get_token)
echo "[DEBUG] Token from file: $([ -n "$TOKEN" ] && echo "found" || echo "not found")" >&2

# Use default token if token file didn't provide one
if [ -z "$TOKEN" ]; then
  if [ -z "$DEFAULT_TOKEN" ]; then
    echo "ERROR: No token available - token file not found and no default token provided" >&2
    exit $EXIT_MISSING_TOKEN_FILE
  fi
  echo "[DEBUG] Using default token" >&2
  TOKEN="$DEFAULT_TOKEN"
else
  echo "[DEBUG] Using token from file" >&2
fi

echo "[DEBUG] Final token: $(echo "$TOKEN")..." >&2

case "$MODE" in
  send)
    # Read metrics from stdin and send to the specified URL
    METRICS_DATA=$(cat)
    if [ -z "$METRICS_DATA" ]; then
      echo "ERROR: No metrics data received on stdin" >&2
      exit $EXIT_NO_METRICS_DATA
    fi
    # Send the metric to the server
    make_request_with_retry "POST" "$REQUEST_URL" "$TOKEN" "$DEFAULT_TOKEN" "$METRICS_DATA"
    # Check for errors or exit with success status
    handle_response "$REQUEST_HTTP_CODE" "$REQUEST_BODY" "Authentication failed (HTTP 401) - Invalid token or serial"
    exit $EXIT_SUCCESS
    ;;
  request)
    # Make request to the specified URL to get the reponse
    make_request_with_retry "POST" "$REQUEST_URL" "$TOKEN" "$DEFAULT_TOKEN" ""
    # Check for errors
    handle_response "$REQUEST_HTTP_CODE" "$REQUEST_BODY" "Failed to get token (HTTP 401)"
    # Output the response body for Telegraf to parse
    echo "$REQUEST_BODY"
    exit $EXIT_SUCCESS
    ;;
esac

