#!/usr/bin/env python3
"""
Script to record real analytics scene description data from Axis device.

This creates a test file with actual device data for more realistic testing.
Uses SSH to connect to the device and record analytics scene description data.
"""

import getpass
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Protocol

import click
import paramiko


class CommandRunner(Protocol):  # pylint: disable=too-few-public-methods
    """Protocol for running commands and returning output."""

    def run_command(self, command: str, timeout_seconds: int) -> Iterator[str]:
        """Run a command and yield output lines.

        Args:
            command: The command to execute
            timeout_seconds: Maximum time to wait for command completion

        """


class SSHCommandRunner:
    """SSH implementation of CommandRunner."""

    def __init__(self, host: str, username: str, password: Optional[str] = None):
        """Initialize SSH connection parameters.

        Args:
            host: SSH host to connect to
            username: SSH username
            password: SSH password (optional, will prompt if needed)
        """
        self.host = host
        self.username = username
        self.password = password
        self.client = None

    def connect(self):
        """Establish SSH connection to the device."""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Try connecting with key first, then password if provided
        if self.password:
            self.client.connect(
                hostname=self.host,
                username=self.username,
                password=self.password,
                timeout=10,
            )
        else:
            self.client.connect(hostname=self.host, username=self.username, timeout=10)

    def run_command(self, command: str, timeout_seconds: int) -> Iterator[str]:
        """Run command via SSH and yield output lines with timeout.

        Args:
            command: Command to execute on remote host
            timeout_seconds: Maximum time to wait for command completion

        Yields:
            str: Lines of output from the command

        Raises:
            RuntimeError: If SSH connection fails
        """
        if not self.client:
            raise RuntimeError("Not connected to device")

        _, stdout, _ = self.client.exec_command(command)

        # Use threading for timeout instead of signals
        lines = []
        finished = threading.Event()

        def read_output():
            try:
                for line in stdout:
                    if finished.is_set():
                        break
                    lines.append(line.strip())
            except (paramiko.SSHException, OSError, EOFError):
                pass  # Connection closed or network error
            finally:
                finished.set()

        reader_thread = threading.Thread(target=read_output)
        reader_thread.daemon = True
        reader_thread.start()

        # Wait for timeout or completion
        start_time = time.time()
        while time.time() - start_time < timeout_seconds and not finished.is_set():
            time.sleep(0.1)

        finished.set()  # Signal thread to stop
        reader_thread.join(timeout=1)  # Give thread time to finish

        yield from lines

    def close(self):
        """Close the SSH connection."""
        if self.client:
            self.client.close()


class DataRecorder:
    """Records data from a command runner, agnostic to transport method."""

    def __init__(self, runner: CommandRunner):
        """Initialize with a command runner.

        Args:
            runner: CommandRunner instance for executing commands
        """
        self.runner = runner

    def extract_json_from_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Extract and parse JSON from a line that may have a prefix.

        This handles cases where message-broker-cli output has prefixes like:
        "2024-01-01 12:00:00 {"key": "value", ...}"
        We want just the JSON part parsed as a Python object.

        Args:
            line: Input line that may contain JSON with optional prefix

        Returns:
            Parsed JSON object if found and valid, None otherwise

        Examples:
            >>> recorder = DataRecorder(None)
            >>> recorder.extract_json_from_line('{"test": "value"}')
            {'test': 'value'}

            >>> recorder.extract_json_from_line(
            ...     '2024-01-01 12:00:00 {"key": "value"}'
            ... )
            {'key': 'value'}

            >>> recorder.extract_json_from_line('no json here')

            >>> recorder.extract_json_from_line('prefix {"invalid": json}')

            >>> recorder.extract_json_from_line('')

            >>> recorder.extract_json_from_line(
            ...     'ts {"nested": {"data": [1, 2, 3]}}'
            ... )
            {'nested': {'data': [1, 2, 3]}}
        """
        # Find the first '{' character to locate potential JSON
        json_start = line.find("{")
        if json_start == -1:
            # No JSON found in this line
            return None

        json_line = line[json_start:]

        # Parse and return the JSON object
        try:
            return json.loads(json_line)
        except json.JSONDecodeError:
            # The extracted part isn't valid JSON
            return None

    def record_data(
        self, topic: str, source: str, output_file: Path, timeout_seconds: int
    ) -> int:
        """
        Record data from message broker.

        Args:
            topic: Message broker topic to consume.
            source: Message broker source.
            output_file: Path to save the recorded data.
            timeout_seconds: Maximum recording duration in seconds.

        Returns:
            int: Number of valid JSON lines recorded.
        """
        command = f'message-broker-cli consume "{topic}" "{source}"'

        line_count = 0
        with output_file.open("w") as f:
            for line in self.runner.run_command(command, timeout_seconds):
                json_obj = self.extract_json_from_line(line)
                if json_obj is not None:
                    # Convert back to compact JSON string for file output
                    # separators=(',', ':') removes spaces after commas and
                    # colons
                    # for smaller file size and consistent JSONL format
                    f.write(json.dumps(json_obj, separators=(",", ":")) + "\n")
                    f.flush()  # Ensure data is written immediately
                    line_count += 1

        return line_count


@click.command()
@click.option(
    "--host", "-h", default="192.168.1.2", help="Device IP address or hostname"
)
@click.option("--username", "-u", default="acap-fixeditdataagent", help="SSH username")
@click.option(
    "--password",
    "-p",
    default=None,
    help="SSH password (if not provided, will try key auth first, " "then prompt)",
)
@click.option(
    "--topic",
    default="com.axis.analytics_scene_description.v0.beta",
    help="Message broker topic to consume",
)
@click.option("--source", default="1", help="Message broker source")
@click.option(
    "--output-file",
    "-o",
    default="test_files/real_device_data.jsonl",
    help="Output file path",
)
@click.option("--duration", "-d", default=30, help="Recording duration in seconds")
def main(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-statements
    host: str,
    username: str,
    password: Optional[str],
    topic: str,
    source: str,
    output_file: str,
    duration: int,
):
    r"""
    Record real analytics scene description data from Axis device.

    This script connects to an Axis device via SSH and records analytics scene
    description data for testing purposes. The recorded data can be used with
    the time-in-area analytics pipeline for more realistic testing.

    Args:
        host: SSH host/IP address to connect to
        username: SSH username for authentication
        password: SSH password (optional, will prompt if needed)
        topic: Message broker topic to consume from
        source: Message broker source identifier
        output_file: Path to output JSONL file
        duration: Recording duration in seconds

    Raises:
        Abort: If user cancels password prompt
        ClickException: If output directory doesn't exist

    \b
    Authentication:
    - First tries SSH key authentication
    - Falls back to password authentication if key auth fails
    - Prompts for password if not provided via --password option

    \b
    AXIS OS Compatibility:
    - AXIS OS < 12: Can SSH as root without password restrictions
    - AXIS OS 12+: SSH as root is disabled, use FixedIT Data Agent user in
      dev mode
    """
    click.echo("Recording real analytics scene description data from device...")
    click.echo(f"Device: {username}@{host}")
    click.echo(f"Topic: {topic}")
    click.echo(f"Source: {source}")
    click.echo(f"Duration: {duration} seconds")
    click.echo(f"Output file: {output_file}")
    click.echo("")

    # Validate that output directory exists
    output_path = Path(output_file)
    if not output_path.parent.exists():
        raise click.ClickException(
            f"Output directory does not exist: {output_path.parent}"
        )

    if not password:
        try:
            # Try to connect without password first (key auth)
            ssh_runner = SSHCommandRunner(host, username)
            ssh_runner.connect()
            click.echo("✅ Connected using SSH key authentication")
        except (paramiko.AuthenticationException, paramiko.SSHException):
            # Key auth failed, prompt for password
            try:
                password = getpass.getpass(f"Password for {username}@{host}: ")
                ssh_runner = SSHCommandRunner(host, username, password)
                ssh_runner.connect()
                click.echo("✅ Connected using password authentication")
            except KeyboardInterrupt as exc:
                click.echo("\n❌ Cancelled by user")
                raise click.Abort() from exc
        except KeyboardInterrupt as exc:
            click.echo("\n❌ Cancelled by user")
            raise click.Abort() from exc
    else:
        ssh_runner = SSHCommandRunner(host, username, password)
        ssh_runner.connect()
        click.echo("✅ Connected to device")

    click.echo("Starting data recording...")

    try:
        # Record data
        recorder = DataRecorder(ssh_runner)
        line_count = recorder.record_data(topic, source, output_path, duration)

        if line_count > 0:
            click.echo(
                f"✅ Successfully recorded {line_count} lines of real device " f"data"
            )
            click.echo(f"📁 Saved to: {output_file}")
            click.echo("")
            click.echo("Sample of recorded data (first 3 lines):")
        else:
            click.echo("ℹ️ No data was recorded during the timeout period.")
            click.echo("This is normal if:")
            click.echo("   - No motion or objects were detected by the camera")
            click.echo("   - No analytics events occurred during recording")
            click.echo(
                f"   - The specified topic/source '{topic}/{source}' had no "
                f"activity"
            )
            click.echo("")
            click.echo("The connection and command executed successfully.")
    finally:
        ssh_runner.close()

    click.echo("")
    click.echo("🧪 To test with this real data, use:")
    click.echo(f'export SAMPLE_FILE="{output_file}"')
    click.echo("Then run your telegraf test commands as documented in README.md")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
