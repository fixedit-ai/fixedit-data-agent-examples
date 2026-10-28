#!/bin/sh
#
# Set dynamic overlay template text (#D1, #D2, ...) via dynamicoverlay.cgi.
#
# Reads overlay updates from stdin, one per line:
#   <template_id> <text>
#
# Template IDs are numeric: 1 = #D1, 2 = #D2, etc. The text is the
# text to set for the template.
#
# Required environment variables:
#   VAPIX_USERNAME: Username for camera authentication
#   VAPIX_PASSWORD: Password for camera authentication
#
# Optional:
#   CAMERA_IP: IP address of the camera (default 127.0.0.1)
#   TELEGRAF_DEBUG: Enable debug logging when set to "true"
#   HELPER_FILES_DIR: directory for set_overlay_text.debug log file
#                     (automatically set by the FixedIT Data Agent)
#
# Debug log (only when TELEGRAF_DEBUG=true and HELPER_FILES_DIR is set):
#   ${HELPER_FILES_DIR}/set_overlay_text.debug

set -e

CAMERA_IP="${CAMERA_IP:-127.0.0.1}"
URL="http://${CAMERA_IP}/axis-cgi/dynamicoverlay.cgi"
DEBUG="${TELEGRAF_DEBUG:-false}"
DEBUG_FILE="${HELPER_FILES_DIR}/set_overlay_text.debug"

debug_log() {
  _debug_log_msg="$1"
  if [ "$DEBUG" = "true" ] && [ -n "${HELPER_FILES_DIR}" ]; then
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$_debug_log_msg" >> "$DEBUG_FILE" 2>/dev/null || true
  fi
  return 0
}

debug_log "set_overlay_text.sh invoked (CAMERA_IP=${CAMERA_IP}, URL=${URL})"

if [ -z "${VAPIX_USERNAME}" ] || [ -z "${VAPIX_PASSWORD}" ]; then
  msg="set_overlay_text.sh: VAPIX_USERNAME and VAPIX_PASSWORD must be set"
  echo "$msg" >&2
  debug_log "ERROR: $msg"
  exit 1
fi

debug_log "VAPIX_USERNAME=${VAPIX_USERNAME} (password set)"

set_overlay_text() {
  template_id="$1"
  text="$2"

  if [ -z "$template_id" ]; then
    msg="set_overlay_text.sh: missing template_id"
    echo "$msg" >&2
    debug_log "ERROR: $msg"
    return 1
  fi

  # Empty text clears the overlay template.
  debug_log "setting overlay template_id=${template_id} text_len=${#text}"

  # curl --fail exits non-zero on 4xx/5xx after digest auth. Disable errexit
  # around the command substitution so we can log the failure before exiting.
  set +e
  response=$(curl -sSk --fail --digest -u "${VAPIX_USERNAME}:${VAPIX_PASSWORD}" \
    --get \
    --data-urlencode "action=settext" \
    --data-urlencode "text_index=${template_id}" \
    --data-urlencode "text=${text}" \
    "${URL}" 2>&1)
  curl_exit=$?
  set -e

  debug_log "curl exit=${curl_exit} response=${response:-<empty>} template_id=${template_id}"

  if [ $curl_exit -ne 0 ]; then
    msg="set_overlay_text.sh: request failed for template_id=${template_id} (exit ${curl_exit}): ${response:-<empty>}"
    echo "$msg" >&2
    debug_log "ERROR: $msg"
    return 1
  fi

  case "$response" in
    *'"error"'*)
      msg="set_overlay_text.sh: API error for template_id=${template_id}: ${response}"
      echo "$msg" >&2
      debug_log "ERROR: $msg"
      return 1
      ;;
    *)
      ;;
  esac

  debug_log "OK: overlay updated for template_id=${template_id}"
  return 0
}

# Each line is "<template_id> <text>".
# IFS splits on the first space only.
while IFS=' ' read -r template_id text || [ -n "$template_id" ]; do
  # Skip empty lines.
  [ -z "$template_id" ] && continue

  # Set the overlay text for the template.
  set_overlay_text "$template_id" "$text"
done
