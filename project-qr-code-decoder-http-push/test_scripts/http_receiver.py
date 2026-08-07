#!/usr/bin/env python3
from flask import Flask, request
from datetime import datetime
import click
import sys
import json

app = Flask(__name__)
output_file = None


@app.route("/webhook", methods=["POST"])
def webhook():
    """Log request metadata to stderr and write body to stdout or a file."""
    timestamp = datetime.now().isoformat()
    print(f"\nReceived request at {timestamp}", file=sys.stderr)
    print(f"Method: {request.method} {request.path}", file=sys.stderr)
    print("Headers:", file=sys.stderr)
    for header, value in request.headers.items():
        print(f"  {header}: {value}", file=sys.stderr)

    data = request.get_data(as_text=True)
    if output_file == "-":
        print(data, flush=True)
    else:
        with open(output_file, "w") as f:
            f.write(data)
        print(f"Message saved to: {output_file}", file=sys.stderr)

    return "OK", 200


@click.command()
@click.option("--output", "-o", default="-", help="Output file (use - for stdout)")
@click.option("--port", "-p", default=8080, help="Port to listen on")
def main(output, port):
    """HTTP receiver for QR code detection metrics."""
    global output_file
    output_file = output

    print(f"Starting HTTP receiver on http://localhost:{port}/webhook", file=sys.stderr)
    print("Press Ctrl+C to stop", file=sys.stderr)
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
