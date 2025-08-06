#!/usr/bin/env python3

import base64
import io
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Iterator

import boto3
import click
import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm


class TimelapseViewer:
    def __init__(self, bucket_name: str, aws_region: Optional[str] = None):
        """Initialize the timelapse viewer with S3 connection."""
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3", region_name=aws_region)

    def list_timelapse_files(
        self, device_serial: str, date: Optional[str] = None
    ) -> List[str]:
        """List all timelapse files for a device, optionally filtered by date."""
        prefix = f"{device_serial}/"
        if date:
            prefix += f"{date}/"

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=prefix
            )

            if "Contents" not in response:
                return []

            # Filter for timelapse files and sort by timestamp
            timelapse_files = []
            for obj in response["Contents"]:
                key = obj["Key"]
                if "timelapse-" in key and key.endswith(".json"):
                    timelapse_files.append(key)

            # Sort by filename (which includes timestamp)
            timelapse_files.sort()
            return timelapse_files

        except Exception as e:
            click.echo(f"Error listing files: {e}", err=True)
            return []

    def fetch_image_from_s3(
        self, s3_key: str
    ) -> Tuple[Optional[Image.Image], Optional[datetime]]:
        """Fetch a single image from S3 and decode it."""
        try:
            # Download the JSON file
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            json_data = json.loads(response["Body"].read().decode("utf-8"))

            # Extract base64 image data
            image_base64 = json_data["fields"]["image_base64"]
            image_data = base64.b64decode(image_base64)

            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_data))

            # Extract timestamp from filename
            # Format: DEVICE_SERIAL/YYYY-MM-DD/timelapse-HH-MM-SS.json
            filename = s3_key.split("/")[-1]
            time_str = filename.replace("timelapse-", "").replace(".json", "")
            date_str = s3_key.split("/")[-2]
            timestamp_str = f"{date_str} {time_str.replace('-', ':')}"
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

            return image, timestamp

        except Exception as e:
            click.echo(f"Error fetching image from {s3_key}: {e}", err=True)
            return None, None

    def _prepare_image_for_display(
        self, img: Image.Image, frame_num: int, total_frames: int
    ) -> np.ndarray:
        """Convert PIL image to OpenCV format and add frame information."""
        # Convert PIL image to OpenCV format
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Add frame number and timestamp
        cv2.putText(
            img_cv,
            f"Frame {frame_num}/{total_frames}",
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
        """
        Generator that yields images one at a time from S3.

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
            if image and timestamp:
                yield image, timestamp, frame_num

    def save_images_to_video(
        self, files: List[str], output_file: Path, fps: int = 10
    ) -> None:
        """
        Save images as a video file using a generator to avoid loading all images into memory.

        This method uses the image_generator to stream images one at a time,
        significantly reducing memory usage for large timelapses.
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
            for image, timestamp, frame_num in self.image_generator(files):
                # Lazy initialization of video writer with first image
                if out is None:
                    height, width = image.size[
                        ::-1
                    ]  # PIL uses (width, height), OpenCV uses (height, width)
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    out = cv2.VideoWriter(
                        str(output_file), fourcc, fps, (width, height)
                    )
                    click.echo(
                        f"Video writer initialized with dimensions: {width}x{height}"
                    )

                img_cv = self._prepare_image_for_display(image, frame_num, len(files))
                out.write(img_cv)
                pbar.update(1)

        if out is None:
            click.echo("No valid images found to create video", err=True)
            return

        # Cleanup
        out.release()
        click.echo(f"Video saved successfully to: {output_file}")

    def show_images_live(self, files: List[str], fps: int = 10) -> None:
        """
        Display images as a live video using a generator to avoid loading all images into memory.

        This method streams images one at a time, making it suitable for very large timelapses
        that would otherwise consume excessive memory.
        """
        if not files:
            click.echo("No files to process", err=True)
            return

        click.echo(f"Displaying {len(files)} images at {fps} FPS")

        # Display images using generator
        for image, timestamp, frame_num in self.image_generator(files):
            img_cv = self._prepare_image_for_display(image, frame_num, len(files))

            # Display the image
            cv2.imshow("Timelapse Viewer", img_cv)

            # Wait for key press or frame duration
            key = cv2.waitKey(int(1000 / fps)) & 0xFF
            if key == ord("q"):
                break
            elif key == ord(" "):  # Spacebar to pause
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
        """
        Create and display a timelapse for a specific device and date.

        This method now uses generators to avoid loading all images into memory at once.
        This provides significant benefits:
        - Reduced memory usage: Only one image is loaded at a time
        - Faster startup: No preprocessing delay - images are fetched on-demand
        - Better scalability: Can handle very large timelapses
        - Streaming approach: Enables real-time processing
        """
        click.echo(f"Fetching timelapse files for device {device_serial}...")

        # List all timelapse files
        files = self.list_timelapse_files(device_serial, date)
        if not files:
            click.echo(f"No timelapse files found for device {device_serial}", err=True)
            return

        click.echo(f"Found {len(files)} timelapse files")
        click.echo("Using streaming approach - images will be fetched on-demand")

        # Get time range info (fetch first and last images)
        if files:
            first_image, first_timestamp, _ = next(self.image_generator([files[0]]))
            last_image, last_timestamp, _ = next(self.image_generator([files[-1]]))
            click.echo(f"Time range: {first_timestamp} to {last_timestamp}")

        # Create video or display live using generator
        if output_file:
            self.save_images_to_video(files, output_file, fps)
        else:
            self.show_images_live(files, fps)

    def list_devices(self) -> List[str]:
        """List all devices (device serials) in the bucket."""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Delimiter="/"
            )

            devices = []
            if "CommonPrefixes" in response:
                for prefix in response["CommonPrefixes"]:
                    device = prefix["Prefix"].rstrip("/")
                    devices.append(device)

            return devices

        except Exception as e:
            click.echo(f"Error listing devices: {e}", err=True)
            return []

    def list_dates(self, device_serial: str) -> List[str]:
        """List all dates available for a device."""
        prefix = f"{device_serial}/"

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=prefix, Delimiter="/"
            )

            dates = []
            if "CommonPrefixes" in response:
                for prefix_obj in response["CommonPrefixes"]:
                    date_path = prefix_obj["Prefix"]
                    date = date_path.split("/")[-2]  # Extract date from path
                    dates.append(date)

            return sorted(dates)

        except Exception as e:
            click.echo(f"Error listing dates: {e}", err=True)
            return []


@click.group()
def cli():
    """Timelapse Viewer for FixedIT Data Agent S3 Timelapse

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
        python timelapse_viewer.py view --bucket my-timelapse-bucket --device CAMERA-001 --date 2025-08-06 --fps 15

        # Save timelapse as MP4 file
        python timelapse_viewer.py view --bucket my-timelapse-bucket --device CAMERA-001 --date 2025-08-06 --output timelapse.mp4
    """


@cli.command()
@click.option(
    "--bucket", required=True, help="S3 bucket name containing timelapse files"
)
@click.option("--region", help="AWS region (optional, uses default if not specified)")
def list_devices(bucket: str, region: Optional[str]):
    """List all devices (cameras) in the S3 bucket."""
    viewer = TimelapseViewer(bucket, region)
    devices = viewer.list_devices()

    if devices:
        click.echo("Available devices:")
        for device in devices:
            click.echo(f"  {device}")
    else:
        click.echo("No devices found in the bucket")


@cli.command()
@click.option(
    "--bucket", required=True, help="S3 bucket name containing timelapse files"
)
@click.option("--device", required=True, help="Device serial number")
@click.option("--region", help="AWS region (optional, uses default if not specified)")
def list_dates(bucket: str, device: str, region: Optional[str]):
    """List all dates available for a specific device."""
    viewer = TimelapseViewer(bucket, region)
    dates = viewer.list_dates(device)

    if dates:
        click.echo(f"Available dates for device {device}:")
        for date in dates:
            click.echo(f"  {date}")
    else:
        click.echo(f"No dates found for device {device}")


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
def view(
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
    """
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


if __name__ == "__main__":
    cli()
