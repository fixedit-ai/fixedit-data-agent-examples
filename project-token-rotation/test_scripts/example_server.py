#!/usr/bin/env python3
"""Flask server to receive and print metrics from Telegraf."""

import json
import sys
import uuid
from functools import wraps
from flask import Flask, request

app = Flask(__name__)

# Bootstrap token that all devices start with
BOOTSTRAP_TOKEN = "bootstrap-key-12345"

# Dictionary to store generated tokens for each device (serial -> token)
device_tokens = {}


def get_device_serial():
    """Extract device serial from request headers."""
    return request.headers.get("serial")


def get_token_from_header():
    """Extract token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:]  # Remove "Bearer " prefix


def authenticate_generated_token_only():
    """Authenticate using only the generated token for the device.

    Bootstrap token is not accepted.
    """
    serial = get_device_serial()
    if not serial:
        return False, "Missing 'serial' header", None

    token = get_token_from_header()
    if not token:
        return False, "Missing or invalid Authorization header", serial

    # Device must have a generated token that matches
    if serial not in device_tokens:
        return False, "Device not registered", serial

    if token == device_tokens[serial]:
        return True, None, serial

    return False, "Invalid token for device", serial


def authenticate_bootstrap_or_generated():
    """Authenticate using bootstrap token or generated token.

    Bootstrap token can be used to generate a new token.
    Generated token is also accepted.
    """
    serial = get_device_serial()
    if not serial:
        return False, "Missing 'serial' header", None

    token = get_token_from_header()
    if not token:
        return False, "Missing or invalid Authorization header", serial

    # If device already has a generated token, check that first
    if serial in device_tokens:
        print("Device already has a token", file=sys.stderr)
        if token == device_tokens[serial]:
            print("Token matches", file=sys.stderr)
            return True, None, serial
        else:
            print(
                f"Token does not match expected: {device_tokens[serial]}, is: {token}",
                file=sys.stderr,
            )
            return False, "Invalid token for device", serial

    # Device not registered yet, accept bootstrap token
    if token == BOOTSTRAP_TOKEN:
        print("Bootstrap token accepted", file=sys.stderr)
        return True, None, serial

    print("Invalid bootstrap token", file=sys.stderr)
    return False, "Invalid bootstrap token", serial


def require_generated_token(f):
    """Decorator to require only generated token authentication."""

    @wraps(f)
    def decorated(*args, **kwargs):
        is_valid, message, serial = authenticate_generated_token_only()
        if not is_valid:
            return {"status": "unauthorized", "message": message}, 401
        return f(*args, **kwargs)

    return decorated


def require_bootstrap_or_token(f):
    """Decorator to require bootstrap or generated token authentication."""

    @wraps(f)
    def decorated(*args, **kwargs):
        is_valid, message, serial = authenticate_bootstrap_or_generated()
        if not is_valid:
            return {"status": "unauthorized", "message": message}, 401
        return f(*args, **kwargs)

    return decorated


@app.route("/metrics", methods=["POST"])
@require_generated_token
def receive_metrics():
    """Receive metrics data and print to stdout.

    Requires the device's generated token (bootstrap token not accepted).
    """
    try:
        serial = get_device_serial()
        data = request.get_json()

        # Include device info in output for context
        output = {
            "device_serial": serial,
            "current_token": device_tokens.get(serial, "N/A"),
            "metrics": data,
        }

        print(json.dumps(output, indent=2), file=sys.stdout)
        sys.stdout.flush()
        return {"status": "success"}, 200
    except Exception as e:
        print(f"Error processing metrics: {e}", file=sys.stderr)
        return {"status": "error", "message": str(e)}, 400


@app.route("/generate-token", methods=["POST"])
@require_bootstrap_or_token
def generate_token():
    """Generate a new token for the device.

    Accepts bootstrap token or existing generated token.
    Returns the new token in Telegraf-compatible JSON format.
    """
    try:
        serial = get_device_serial()
        new_token = str(uuid.uuid4())
        device_tokens[serial] = new_token

        # Format response as JSON array with a single object
        # Telegraf's JSON parser will extract fields from array elements
        output = [{"serial": serial, "token": new_token}]

        print(f"[TOKEN GENERATED] Device {serial}: {new_token}", file=sys.stderr)
        return output, 200
    except Exception as e:
        print(f"Error generating token: {e}", file=sys.stderr)
        return [], 400


if __name__ == "__main__":
    print(
        "Starting metrics server on http://0.0.0.0:8000 with token rotation",
        file=sys.stderr,
    )
    print(f"Bootstrap token: {BOOTSTRAP_TOKEN}", file=sys.stderr)
    print("Endpoints:", file=sys.stderr)
    print("  POST /metrics - Send metrics (requires generated token)", file=sys.stderr)
    print(
        "  POST /generate-token - Generate new token (accepts bootstrap or existing token)",
        file=sys.stderr,
    )
    app.run(host="0.0.0.0", port=8000, debug=False)
