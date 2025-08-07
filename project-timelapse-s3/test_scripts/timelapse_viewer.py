#!/usr/bin/env python3
"""Timelapse viewer for FixedIT Data Agent S3 timelapse files.

This module provides functionality to view and analyze timelapse videos
created by the FixedIT Data Agent and stored in AWS S3.
"""

import base64
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import boto3
import click
import cv2
import numpy as np
from botocore.exceptions import ClientError
from PIL import Image
from tqdm import tqdm


def handle_s3_client_error(e: ClientError, bucket: str) -> None:
    """Handle S3 ClientError and provide user-friendly error messages.

    Args:
        e: The ClientError exception from boto3
        bucket: The S3 bucket name for error context

    Raises:
        click.Abort: Always raised after displaying error message
    """
    error_code = e.response["Error"]["Code"]
    error_message = e.response["Error"]["Message"]

    if error_code == "AccessDenied":
        click.echo(
            f"Error: Access denied to S3 bucket '{bucket}'. "
            f"Please check your AWS credentials and permissions.",
            err=True,
        )
        click.echo(f"Details: {error_message}", err=True)
    else:
        click.echo(f"Error: AWS S3 error ({error_code}): {error_message}", err=True)

    raise click.Abort()


class TimelapseViewer:
    """A viewer for timelapse videos stored in AWS S3.

    This class provides functionality to fetch, decode, and display timelapse
    images stored as JSON files in S3 buckets.
    """

    def __init__(self, bucket_name: str, aws_region: Optional[str] = None):
        """Initialize the timelapse viewer with S3 connection.

        Args:
            bucket_name: The S3 bucket name containing timelapse files
            aws_region: The AWS region for the S3 bucket (optional)
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3", region_name=aws_region)

    def _paginated_s3_request(self, **request_params) -> Iterator[dict]:
        """Generate S3 API responses across all pages.

        S3 list_objects_v2 has a default limit of 1000 objects per response.
        When a bucket contains more than 1000 objects, the response includes
        IsTruncated=True and NextContinuationToken for the next page.
        This generator handles pagination automatically to ensure all data
        is retrieved, not just the first 1000.

        Args:
            **request_params: Parameters to pass to list_objects_v2

        Yields:
            S3 API response dictionaries from all pages
        """
        continuation_token = None

        while True:
            # Add continuation token if we have one
            if continuation_token:
                request_params["ContinuationToken"] = continuation_token

            # Make the S3 API call
            response = self.s3_client.list_objects_v2(**request_params)

            # Yield the response from this page
            yield response

            # Check if there are more pages
            if not response.get("IsTruncated", False):
                break

            # Get continuation token for next page
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break

    def _paginated_s3_list(self, **request_params) -> Iterator[dict]:
        """Generate S3 objects across all pages.

        Uses the shared pagination logic to iterate through all objects.

        Args:
            **request_params: Parameters to pass to list_objects_v2

        Yields:
            S3 object dictionaries from all pages
        """
        for response in self._paginated_s3_request(**request_params):
            if "Contents" in response:
                yield from response["Contents"]

    def _paginated_s3_common_prefixes(self, **request_params) -> Iterator[str]:
        """Generate S3 common prefixes across all pages.

        Uses the shared pagination logic to iterate through all common prefixes.
        When using Delimiter="/", S3 returns CommonPrefixes instead of Contents.

        Args:
            **request_params: Parameters to pass to list_objects_v2

        Yields:
            Common prefix strings from all pages
        """
        for response in self._paginated_s3_request(**request_params):
            if "CommonPrefixes" in response:
                yield from (prefix["Prefix"] for prefix in response["CommonPrefixes"])

    def list_timelapse_files(
        self, device_serial: str, date: Optional[str] = None
    ) -> List[str]:
        """List all timelapse files for a device, optionally filtered by date.

        Args:
            device_serial: The device serial number to search for
            date: Optional date filter in YYYY-MM-DD format

        Returns:
            List of S3 keys for timelapse JSON files
        """
        prefix = f"{device_serial}/"
        if date:
            prefix += f"{date}/"

        timelapse_files = []

        # Use pagination helper to get all objects
        for obj in self._paginated_s3_list(Bucket=self.bucket_name, Prefix=prefix):
            key = obj["Key"]
            if "timelapse-" in key and key.endswith(".json"):
                timelapse_files.append(key)

        # Sort by filename (which includes timestamp)
        timelapse_files.sort()
        return timelapse_files

    def fetch_image_from_s3(self, s3_key: str) -> Tuple[Image.Image, datetime]:
        """Fetch a single image from S3 and decode it.

        Args:
            s3_key: The S3 key for the JSON file containing the image

        Returns:
            Tuple of (PIL Image, UTC datetime timestamp)

        Raises:
            ValueError: If JSON structure is invalid or image data is corrupted
        """
        # Download the JSON file
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
        json_data = json.loads(response["Body"].read().decode("utf-8"))

        # Validate required JSON structure
        if "fields" not in json_data:
            raise ValueError(f"Missing 'fields' key in JSON data from {s3_key}")

        fields = json_data["fields"]
        if "image_base64" not in fields:
            raise ValueError(f"Missing 'image_base64' key in fields from {s3_key}")

        # Extract base64 image data
        image_base64 = fields["image_base64"]

        # Validate that image_base64 is not empty
        if not image_base64:
            raise ValueError(f"Empty image_base64 data in {s3_key}")

        # Decode base64 image data
        try:
            image_data = base64.b64decode(image_base64)
        except Exception as e:
            raise ValueError(f"Invalid base64 data in {s3_key}: {e}") from e

        # Convert to PIL Image
        try:
            image = Image.open(io.BytesIO(image_data))
        except Exception as e:
            raise ValueError(f"Failed to decode image data from {s3_key}: {e}") from e

        # Extract UTC timestamp from JSON timestamp field (nanoseconds)
        # The timestamp is at the root level, not inside fields
        if "timestamp" not in json_data:
            raise ValueError(
                f"Missing 'timestamp' field in JSON data from {s3_key}. "
                f"JSON structure: {json_data.keys()}"
            )

        # Convert timestamp to datetime
        timestamp_s = json_data["timestamp"]

        # Validate that timestamp is a number
        if not isinstance(timestamp_s, (int, float)):
            raise ValueError(
                f"Invalid timestamp type in {s3_key}: expected number, "
                f"got {type(timestamp_s)}"
            )

        timestamp = datetime.fromtimestamp(timestamp_s, tz=timezone.utc)

        return image, timestamp

    def _prepare_image_for_display(
        self, img: Image.Image, timestamp: datetime
    ) -> np.ndarray:
        """Convert PIL image to OpenCV format and add UTC timestamp information.

        Args:
            img: PIL Image to convert
            timestamp: UTC timestamp to display

        Returns:
            OpenCV image array with timestamp overlay
        """
        # Convert PIL image to OpenCV format
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Format UTC timestamp for display
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Add UTC timestamp
        cv2.putText(
            img_cv,
            timestamp_str,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
        )

        return img_cv

    def image_generator(
        self, files: List[str]
    ) -> Iterator[Tuple[Image.Image, datetime, int]]:
        """Generate images one at a time from S3.

        This approach provides several benefits:
        1. Memory efficiency: Only one image is loaded at a time instead of all images
        2. Faster startup: No preprocessing delay - images are fetched on-demand
        3. Scalability: Can handle very large timelapses without memory issues
        4. Streaming: Enables real-time processing as images are fetched (theoretically)

        Args:
            files: List of S3 keys for timelapse files

        Yields:
            Tuple of (image, timestamp, frame_number) for each image
        """
        for frame_num, s3_key in enumerate(files, 1):
            image, timestamp = self.fetch_image_from_s3(s3_key)
            yield image, timestamp, frame_num

    def save_images_to_video(
        self, files: List[str], output_file: Path, fps: int = 10
    ) -> None:
        """Save images as a video file using a generator to avoid loading all images into memory.

        This method uses the image_generator to stream images one at a time,
        significantly reducing memory usage for large timelapses.

        Args:
            files: List of S3 keys for timelapse files
            output_file: Path where the MP4 video will be saved
            fps: Frames per second for the output video
        """
        if not files:
            click.echo("No files to process", err=True)
            return

        # Initialize video writer lazily - will be created with first image
        out = None
        height = width = None

        click.echo(f"Processing {len(files)} images at {fps} FPS")
        click.echo(f"Saving video to: {output_file}")

        # Process images using generator to avoid memory issues
        with tqdm(total=len(files), desc="Writing video frames", unit="frame") as pbar:
            for image, timestamp, _ in self.image_generator(files):
                # Lazy initialization of video writer with first image
                if out is None:
                    height, width = image.size[
                        ::-1
                    ]  # PIL uses (width, height), OpenCV uses (height, width)
                    fourcc = cv2.VideoWriter_fourcc(  # type: ignore[attr-defined]
                        *"mp4v"
                    )
                    out = cv2.VideoWriter(
                        str(output_file), fourcc, fps, (width, height)
                    )
                    click.echo(
                        f"Video writer initialized with dimensions: {width}x{height}"
                    )

                img_cv = self._prepare_image_for_display(image, timestamp)
                out.write(img_cv)
                pbar.update(1)

        if out is None:
            click.echo("No valid images found to create video", err=True)
            return

        # Cleanup
        out.release()
        click.echo(f"Video saved successfully to: {output_file}")

    def show_images_live(self, files: List[str], fps: int = 10) -> None:
        """Display images as a live video using a generator to avoid loading all images into memory.

        This method streams images one at a time, making it suitable for very large timelapses
        that would otherwise consume excessive memory.

        Args:
            files: List of S3 keys for timelapse files
            fps: Frames per second for playback
        """
        if not files:
            click.echo("No files to process", err=True)
            return

        click.echo(f"Displaying {len(files)} images at {fps} FPS")

        # Display images using generator
        for image, timestamp, _ in self.image_generator(files):
            img_cv = self._prepare_image_for_display(image, timestamp)

            # Display the image
            cv2.imshow("Timelapse Viewer", img_cv)

            # Wait for key press or frame duration
            key = cv2.waitKey(int(1000 / fps)) & 0xFF
            if key == ord("q"):
                break
            if key == ord(" "):  # Spacebar to pause
                cv2.waitKey(0)

        # Cleanup
        cv2.destroyAllWindows()

    def create_timelapse(
        self,
        device_serial: str,
        date: Optional[str] = None,
        fps: int = 10,
        output_file: Optional[Path] = None,
    ) -> None:
        """Create and display a timelapse for a specific device and date.

        Args:
            device_serial: The device serial number to create timelapse for
            date: Optional date filter in YYYY-MM-DD format
            fps: Frames per second for playback/saving
            output_file: Optional path to save MP4 video file
        """
        click.echo(f"Fetching timelapse files for device {device_serial}...")

        # List all timelapse files
        files = self.list_timelapse_files(device_serial, date)
        if not files:
            click.echo(f"No timelapse files found for device {device_serial}", err=True)
            return

        click.echo(f"Found {len(files)} timelapse files")
        click.echo("Using streaming approach - images will be fetched on-demand")

        # Create video or display live using generator
        if output_file:
            self.save_images_to_video(files, output_file, fps)
        else:
            self.show_images_live(files, fps)

    def list_devices(self) -> List[str]:
        """List all devices (device serials) in the bucket.

        Returns:
            List of device serial numbers found in the bucket
        """
        devices = []

        # Use pagination helper to get all common prefixes
        for prefix in self._paginated_s3_common_prefixes(
            Bucket=self.bucket_name, Delimiter="/"
        ):
            device = prefix.rstrip("/")
            devices.append(device)

        return devices

    def list_dates(self, device_serial: str) -> List[str]:
        """List all dates available for a device.

        Args:
            device_serial: The device serial number to list dates for

        Returns:
            List of date strings in YYYY-MM-DD format
        """
        prefix = f"{device_serial}/"

        dates = []

        # Use pagination helper to get all common prefixes
        for prefix_path in self._paginated_s3_common_prefixes(
            Bucket=self.bucket_name, Prefix=prefix, Delimiter="/"
        ):
            date = prefix_path.split("/")[-2]  # Extract date from path
            dates.append(date)

        return sorted(dates)


@click.group()
def cli():
    """Timelapse Viewer for FixedIT Data Agent S3 Timelapse.

    This script fetches timelapse images from AWS S3 and displays them as a video.
    It can also save the timelapse as an MP4 file.

    Examples:
        # List all devices in the bucket
        python timelapse_viewer.py list-devices --bucket my-timelapse-bucket

        # List dates for a specific device
        python timelapse_viewer.py list-dates --bucket my-timelapse-bucket --device CAMERA-001

        # View timelapse for a device (all dates)
        python timelapse_viewer.py view --bucket my-timelapse-bucket --device CAMERA-001 --fps 10

        # View timelapse for a specific date
        python timelapse_viewer.py view --bucket my-timelapse-bucket \
            --device CAMERA-001 --date 2025-08-06 --fps 15

        # Save timelapse as MP4 file
        python timelapse_viewer.py view --bucket my-timelapse-bucket \
            --device CAMERA-001 --date 2025-08-06 --output timelapse.mp4
    """


@cli.command()
@click.option(
    "--bucket", required=True, help="S3 bucket name containing timelapse files"
)
@click.option("--region", help="AWS region (optional, uses default if not specified)")
def list_devices(bucket: str, region: Optional[str]):
    """List all devices (cameras) in the S3 bucket.

    Args:
        bucket: S3 bucket name containing timelapse files
        region: AWS region (optional, uses default if not specified)
    """
    try:
        viewer = TimelapseViewer(bucket, region)
        devices = viewer.list_devices()

        if devices:
            click.echo("Available devices:")
            for device in devices:
                click.echo(f"  {device}")
        else:
            click.echo("No devices found in the bucket")
    except ClientError as e:
        handle_s3_client_error(e, bucket)


@cli.command()
@click.option(
    "--bucket", required=True, help="S3 bucket name containing timelapse files"
)
@click.option("--device", required=True, help="Device serial number")
@click.option("--region", help="AWS region (optional, uses default if not specified)")
def list_dates(bucket: str, device: str, region: Optional[str]):
    """List all dates available for a specific device.

    Args:
        bucket: S3 bucket name containing timelapse files
        device: Device serial number
        region: AWS region (optional, uses default if not specified)
    """
    try:
        viewer = TimelapseViewer(bucket, region)
        dates = viewer.list_dates(device)

        if dates:
            click.echo(f"Available dates for device {device}:")
            for date in dates:
                click.echo(f"  {date}")
        else:
            click.echo(f"No dates found for device {device}")
    except ClientError as e:
        handle_s3_client_error(e, bucket)


@cli.command()
@click.option(
    "--bucket", required=True, help="S3 bucket name containing timelapse files"
)
@click.option("--device", required=True, help="Device serial number")
@click.option(
    "--date",
    help="Date in YYYY-MM-DD format (optional, shows all dates if not specified)",
)
@click.option("--fps", default=10, help="Frames per second for playback (default: 10)")
@click.option("--output", type=click.Path(), help="Output MP4 file path (optional)")
@click.option("--region", help="AWS region (optional, uses default if not specified)")
def view(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    bucket: str,
    device: str,
    date: Optional[str],
    fps: int,
    output: Optional[Path],
    region: Optional[str],
):
    """View timelapse video for a device.

    Displays the timelapse as an interactive video with keyboard controls:
    - Press 'q' to quit
    - Press 'space' to pause/unpause

    If --output is specified, the video will also be saved as an MP4 file.

    Args:
        bucket: S3 bucket name containing timelapse files
        device: Device serial number
        date: Date in YYYY-MM-DD format (optional, shows all dates if not specified)
        fps: Frames per second for playback (default: 10)
        output: Output MP4 file path (optional)
        region: AWS region (optional, uses default if not specified)
    """
    try:
        viewer = TimelapseViewer(bucket, region)

        # Validate output path if specified
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                if not click.confirm(f"File {output_path} already exists. Overwrite?"):
                    return
        else:
            output_path = None

        viewer.create_timelapse(device, date, fps, output_path)
    except ClientError as e:
        handle_s3_client_error(e, bucket)


if __name__ == "__main__":
    cli()
