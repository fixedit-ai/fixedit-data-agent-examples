#!/usr/bin/env python3
"""
Track Heatmap Viewer.

This script creates a heatmap visualization showing when different track IDs are active over time.
The visualization displays:
- X-axis: Time (timestamps of frames with observations)
- Y-axis: Track IDs
- Green cells: Track is present in that frame
- Gray cells: Track is not present in that frame

Note: Only frames with observations are shown. Gaps in time are not represented.
This helps visualize track lifecycles and identify patterns in object detection data.
"""

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import click
import matplotlib.pyplot as plt
import numpy as np

# Color constants for heatmap visualization
COLOR_ABSENT = "#CCCCCC"  # Gray - track is absent
COLOR_PRESENT = "#4CAF50"  # Green - track is present
COLOR_ALARM = "#F44336"  # Red - track exceeds alarm threshold


@dataclass
class BoundingBox:
    """Bounding box coordinates."""

    left: float
    top: float
    right: float
    bottom: float


@dataclass
class ObjectClass:
    """Object classification."""

    type: str


@dataclass
class Detection:
    """A single object detection with tracking information."""

    track_id: str
    timestamp: str
    bounding_box: BoundingBox
    class_info: ObjectClass


@dataclass
class Frame:
    """A single frame containing multiple detections."""

    frame_number: int
    timestamp: str
    detections: List[Detection]

    @property
    def track_ids(self) -> List[str]:
        """
        Get all track IDs present in this frame, sorted alphabetically.

        Examples:
            >>> bbox1 = BoundingBox(0.1, 0.2, 0.3, 0.4)
            >>> bbox2 = BoundingBox(0.2, 0.3, 0.4, 0.5)
            >>> detection1 = Detection(
            ...     "track_001", "2024-01-15T10:00:01Z", bbox1, ObjectClass("Human")
            ... )
            >>> detection2 = Detection(
            ...     "track_002", "2024-01-15T10:00:01Z", bbox2, ObjectClass("Vehicle")
            ... )
            >>> frame = Frame(1, "2024-01-15T10:00:01Z", [detection1, detection2])
            >>> frame.track_ids
            ['track_001', 'track_002']
        """
        return sorted({detection.track_id for detection in self.detections})


@dataclass
class TrackData:
    """Container for parsed track data from JSONL file."""

    frames: List[Frame]
    all_track_ids: Set[str]


def _parse_observation_to_detection(obs: Dict) -> Detection:
    """
    Parse a single observation dictionary into a Detection object.

    Args:
        obs: Observation dictionary from JSONL data

    Returns:
        Detection object with parsed data

    Raises:
        ValueError: If required fields are missing

    Examples:
        >>> obs = {
        ...     "track_id": "track_001",
        ...     "timestamp": "2024-01-15T10:00:01Z",
        ...     "bounding_box": {"left": 0.2, "top": 0.4, "right": 0.3, "bottom": 0.6},
        ...     "class": {"type": "Human"}
        ... }
        >>> detection = _parse_observation_to_detection(obs)
        >>> detection.track_id
        'track_001'
        >>> detection.timestamp
        '2024-01-15T10:00:01Z'
        >>> detection.bounding_box.left
        0.2
        >>> detection.class_info.type
        'Human'
    """
    # Validate required fields
    if "track_id" not in obs:
        raise ValueError("Missing required 'track_id' field in observation")
    if "timestamp" not in obs:
        raise ValueError("Missing required 'timestamp' field in observation")
    if "bounding_box" not in obs:
        raise ValueError("Missing required 'bounding_box' field in observation")
    # Create BoundingBox
    bbox_data = obs["bounding_box"]
    if not all(coord in bbox_data for coord in ["left", "top", "right", "bottom"]):
        raise ValueError(
            "Missing required bounding box coordinates (left, top, right, bottom)"
        )

    bounding_box = BoundingBox(
        left=bbox_data["left"],
        top=bbox_data["top"],
        right=bbox_data["right"],
        bottom=bbox_data["bottom"],
    )

    # Create ObjectClass (optional - some tracks may not have classification yet)
    if "class" in obs and "type" in obs["class"]:
        class_info = ObjectClass(type=obs["class"]["type"])
    else:
        # Use "Unknown" for tracks without classification
        class_info = ObjectClass(type="Unknown")

    # Create Detection
    return Detection(
        track_id=obs["track_id"],
        timestamp=obs["timestamp"],
        bounding_box=bounding_box,
        class_info=class_info,
    )


def _parse_frame_data(frame_data: Dict, line_num: int) -> Tuple[Frame, Set[str]]:
    """
    Parse a single frame data dictionary into a Frame object.

    Args:
        frame_data: Frame dictionary from JSONL data
        line_num: Line number to use as frame number

    Returns:
        Tuple of (Frame object, set of track IDs found in this frame)

    Raises:
        ValueError: If required frame fields are missing
    """
    # Validate required frame fields
    if "timestamp" not in frame_data:
        raise ValueError("Missing required 'timestamp' field in frame data")
    if "observations" not in frame_data:
        raise ValueError("Missing required 'observations' field in frame data")

    observations = frame_data["observations"]
    frame_timestamp = frame_data["timestamp"]

    # Parse observations into Detection objects
    detections = []
    frame_track_ids = set()

    for obs in observations:
        if "track_id" in obs:
            detection = _parse_observation_to_detection(obs)
            detections.append(detection)
            frame_track_ids.add(obs["track_id"])

    # Create Frame object
    frame = Frame(
        frame_number=line_num,
        timestamp=frame_timestamp,
        detections=detections,
    )

    return frame, frame_track_ids


def _parse_jsonl_line(line: str, line_num: int) -> Tuple[Frame, Set[str]]:
    """
    Parse a single line from a JSONL file into a Frame object.

    Args:
        line: JSON string from JSONL file
        line_num: Line number for error reporting and frame numbering

    Returns:
        Tuple of (Frame object, set of track IDs found in this frame)

    Raises:
        ValueError: If JSON is invalid or doesn't contain expected 'frame' key

        Examples:
        >>> line = '''{
        ...     "frame": {
        ...         "timestamp": "2024-01-15T10:00:01Z",
        ...         "observations": [{
        ...             "track_id": "track_001",
        ...             "timestamp": "2024-01-15T10:00:01Z",
        ...             "bounding_box": {"left": 0.2, "top": 0.4, "right": 0.3, "bottom": 0.6},
        ...             "class": {"type": "Human"}
        ...         }]
        ...     }
        ... }'''
        >>> frame, track_ids = _parse_jsonl_line(line, 1)
        >>> frame.frame_number
        1
        >>> frame.timestamp
        '2024-01-15T10:00:01Z'
        >>> len(frame.detections)
        1
        >>> track_ids
        {'track_001'}
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON on line {line_num}: {e}. "
            f"Expected JSONL format with one JSON object per line."
        ) from e

    # All valid lines must contain frame data
    if "frame" not in data:
        raise ValueError(
            f"Missing 'frame' key on line {line_num}. "
            f'Expected format: {{"frame": {{...}}}} but got keys: {list(data.keys())}'
        )

    return _parse_frame_data(data["frame"], line_num)


def parse_jsonl_file(file_path: Path) -> TrackData:
    """
    Parse JSONL file and extract frame data and all unique track IDs.

    Args:
        file_path: Path to the JSONL file

    Returns:
        TrackData containing frames and all unique track IDs

    Raises:
        FileNotFoundError: If the input file doesn't exist
        OSError: If there's an error reading the file
        ValueError: If JSON is invalid or missing expected 'frame' key
    """
    frames = []
    all_track_ids = set()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    frame, frame_track_ids = _parse_jsonl_line(line, line_num)
                    frames.append(frame)
                    all_track_ids.update(frame_track_ids)

                except ValueError as e:
                    raise ValueError(f"Error parsing line {line_num}: {e}") from e

    except FileNotFoundError as e:
        raise FileNotFoundError(f"File not found: {file_path}") from e
    except OSError as e:
        raise OSError(f"Error reading file {file_path}: {e}") from e

    return TrackData(frames=frames, all_track_ids=all_track_ids)


def _create_heatmap_matrix(
    frames: List[Frame], sorted_track_ids: List[str]
) -> np.ndarray:
    """
    Create the heatmap matrix from frame data.

    Args:
        frames: List of Frame objects
        sorted_track_ids: Sorted list of track IDs

    Returns:
        2D numpy array representing track presence over time

    Examples:
        >>> # Create test data - 3 frames, 2 tracks
        >>> bbox = BoundingBox(0.1, 0.2, 0.3, 0.4)
        >>> obj_class = ObjectClass("Human")
        >>>
        >>> # Frame 1: only track_001
        >>> det1 = Detection("track_001", "2024-01-01T00:00:01Z", bbox, obj_class)
        >>> frame1 = Frame(1, "2024-01-01T00:00:01Z", [det1])
        >>>
        >>> # Frame 2: both tracks
        >>> det2a = Detection("track_001", "2024-01-01T00:00:02Z", bbox, obj_class)
        >>> det2b = Detection("track_002", "2024-01-01T00:00:02Z", bbox, obj_class)
        >>> frame2 = Frame(2, "2024-01-01T00:00:02Z", [det2a, det2b])
        >>>
        >>> # Frame 3: only track_002
        >>> det3 = Detection("track_002", "2024-01-01T00:00:03Z", bbox, obj_class)
        >>> frame3 = Frame(3, "2024-01-01T00:00:03Z", [det3])
        >>>
        >>> frames = [frame1, frame2, frame3]
        >>> track_ids = ["track_001", "track_002"]
        >>> matrix = _create_heatmap_matrix(frames, track_ids)
        >>> matrix.shape
        (2, 3)
        >>> matrix.tolist()
        [[1.0, 1.0, 0.0], [0.0, 1.0, 1.0]]
    """
    num_tracks = len(sorted_track_ids)
    num_frames = len(frames)
    heatmap_matrix = np.zeros((num_tracks, num_frames))

    for frame_idx, frame in enumerate(frames):
        frame_track_ids = set(frame.track_ids)
        for track_idx, track_id in enumerate(sorted_track_ids):
            if track_id in frame_track_ids:
                heatmap_matrix[track_idx, frame_idx] = 1

    return heatmap_matrix


def _create_alarm_matrix(  # pylint: disable=too-many-locals
    frames: List[Frame], sorted_track_ids: List[str], alarm_threshold: float
) -> np.ndarray:
    """
    Create a matrix indicating which tracks exceed the alarm threshold.

    This function implements time-in-area calculation by tracking when each track first
    appears and calculating how long it has been present. When a track's time in area
    exceeds the alarm_threshold, it gets marked as an alarm condition.

    The algorithm:
    1. Track first appearance time for each track ID
    2. For each subsequent frame, calculate time elapsed since first appearance
    3. Mark frames where time_in_area >= alarm_threshold as alarm conditions

    This creates a separate "alarm layer" that gets combined with the basic presence
    heatmap to show alarm conditions in red while normal presence remains green.

    Args:
        frames: List of Frame objects with timestamps and detections
        sorted_track_ids: Sorted list of track IDs for consistent matrix ordering
        alarm_threshold: Time threshold in seconds for alarm conditions

    Returns:
        2D numpy array: 1 where track exceeds threshold, 0 otherwise

    Examples:
        >>> # Create test data - track_001 exceeds 2-second threshold
        >>> bbox = BoundingBox(0.1, 0.2, 0.3, 0.4)
        >>> obj_class = ObjectClass("Human")
        >>>
        >>> # Frame 1: track_001 appears (0 seconds elapsed)
        >>> det1 = Detection("track_001", "2024-01-01T00:00:01Z", bbox, obj_class)
        >>> frame1 = Frame(1, "2024-01-01T00:00:01Z", [det1])
        >>>
        >>> # Frame 2: track_001 still present (1 second elapsed)
        >>> det2 = Detection("track_001", "2024-01-01T00:00:02Z", bbox, obj_class)
        >>> frame2 = Frame(2, "2024-01-01T00:00:02Z", [det2])
        >>>
        >>> # Frame 3: track_001 still present (3 seconds elapsed - exceeds threshold!)
        >>> det3 = Detection("track_001", "2024-01-01T00:00:04Z", bbox, obj_class)
        >>> frame3 = Frame(3, "2024-01-01T00:00:04Z", [det3])
        >>>
        >>> # Frame 4: track_001 still present (5 seconds elapsed - still in alarm)
        >>> det4 = Detection("track_001", "2024-01-01T00:00:06Z", bbox, obj_class)
        >>> frame4 = Frame(4, "2024-01-01T00:00:06Z", [det4])
        >>>
        >>> frames = [frame1, frame2, frame3, frame4]
        >>> track_ids = ["track_001"]
        >>> alarm_matrix = _create_alarm_matrix(frames, track_ids, 2.0)
        >>> alarm_matrix.shape
        (1, 4)
        >>> alarm_matrix.tolist()
        [[0.0, 0.0, 1.0, 1.0]]
    """
    num_tracks = len(sorted_track_ids)
    num_frames = len(frames)

    # Create alarm matrix: same dimensions as heatmap, but tracks alarm conditions
    alarm_matrix = np.zeros((num_tracks, num_frames))

    # Track first appearance times as seconds - this is our "state" for time-in-area calculation
    track_first_seen: Dict[str, float] = {}

    # Reference time for converting timestamps to seconds
    reference_time: Union[datetime, None] = None

    # Process each frame chronologically to calculate cumulative time in area
    for frame_idx, frame in enumerate(frames):
        frame_track_ids = frame.track_ids
        frame_timestamp = frame.timestamp

        # All frames must have timestamps for time-in-area calculation
        if not frame_timestamp:
            raise ValueError(
                f"Missing timestamp in frame {frame_idx}. "
                "Time-in-area calculation requires timestamps in all frames."
            )

        # Convert timestamp to seconds relative to first frame
        try:
            current_datetime = datetime.fromisoformat(
                frame_timestamp.replace("Z", "+00:00")
            )
            if reference_time is None:
                reference_time = current_datetime
                current_time_seconds = 0.0
            else:
                time_diff = current_datetime - reference_time
                current_time_seconds = time_diff.total_seconds()
        except ValueError as e:
            raise ValueError(
                f"Invalid timestamp format '{frame_timestamp}' in frame {frame_idx}: {e}. "
                "Expected ISO format like '2024-01-15T10:00:01Z'"
            ) from e

        # Check each track to see if it's present and calculate time in area
        for track_idx, track_id in enumerate(sorted_track_ids):
            if track_id in frame_track_ids:
                # Record when we first see this track (start of time-in-area measurement)
                if track_id not in track_first_seen:
                    track_first_seen[track_id] = current_time_seconds

                # Calculate how long this track has been in the area
                first_time_seconds = track_first_seen[track_id]
                time_in_area = current_time_seconds - first_time_seconds

                # Mark this frame as alarm condition if track exceeds threshold
                if time_in_area >= alarm_threshold:
                    alarm_matrix[track_idx, frame_idx] = 1

    return alarm_matrix


def _setup_alarm_heatmap_plot(
    heatmap_matrix: np.ndarray,
    num_tracks: int,
    num_frames: int,
    alarm_matrix: Optional[np.ndarray] = None,
):
    """
    Set up the matplotlib plot for the heatmap with appropriate colors.

    Args:
        heatmap_matrix: 2D numpy array with track presence data
        num_tracks: Number of unique tracks
        num_frames: Number of frames
        alarm_matrix: Optional 2D numpy array with alarm data. If provided, uses 3-color scheme.

    Returns:
        Tuple of (axes, image) from matplotlib
    """
    _, ax = plt.subplots(figsize=(max(12, num_frames * 0.1), max(6, num_tracks * 0.3)))

    # Create combined matrix: 0=absent, 1=present, 2=alarm (if alarm_matrix provided)
    if alarm_matrix is not None:
        combined_matrix = heatmap_matrix + alarm_matrix
        show_alarm_colors = True
    else:
        combined_matrix = heatmap_matrix
        show_alarm_colors = False

    if show_alarm_colors:
        # Three-color colormap: gray, green, red
        colors = [COLOR_ABSENT, COLOR_PRESENT, COLOR_ALARM]
        title = "Track Activity Heatmap\n(Gray = Absent, Green = Present, Red = Alarm)"
        vmax = 2
    else:
        # Two-color colormap: gray, green
        colors = [COLOR_ABSENT, COLOR_PRESENT]
        title = "Track Activity Heatmap\n(Green = Track Present, Gray = Track Absent)"
        vmax = 1

    cmap = plt.matplotlib.colors.ListedColormap(colors)

    im = ax.imshow(
        combined_matrix,
        cmap=cmap,
        aspect="auto",
        interpolation="nearest",
        vmin=0,
        vmax=vmax,
    )

    ax.set_xlabel("Time (Frames with Observations)")
    ax.set_ylabel("Track ID")
    ax.set_title(title)

    return ax, im


@dataclass
class HeatmapData:  # pylint: disable=too-many-instance-attributes
    """Container for processed heatmap data and statistics."""

    frames: List[Frame]
    sorted_track_ids: List[str]
    heatmap_matrix: np.ndarray
    alarm_matrix: Optional[np.ndarray]
    alarm_tracks: Set[str]
    alarm_threshold: float
    num_tracks: int
    num_frames: int
    frames_with_activity: int
    activity_percentage: float


def process_heatmap_data(
    frames: List[Frame],
    all_track_ids: Set[str],
    alarm_threshold: float = float("inf"),
) -> Optional[HeatmapData]:
    """
    Process track data and calculate heatmap matrices and statistics.

    This function processes track data to create:
    1. Base heatmap matrix: Track presence over time
    2. Alarm matrix: Tracks that exceed time-in-area threshold (optional)
    3. Statistics: Activity percentages and alarm counts

    Args:
        frames: List of Frame objects with timestamps and detections
        all_track_ids: Set of all unique track IDs found in the data
        alarm_threshold: Time threshold in seconds for alarm calculation (default: inf = no alarms)

    Returns:
        HeatmapData object containing processed matrices and statistics, or None if no data
    """
    if not frames:
        return None

    if not all_track_ids:
        return None

    sorted_track_ids = sorted(list(all_track_ids))
    num_tracks = len(sorted_track_ids)
    num_frames = len(frames)

    heatmap_matrix = _create_heatmap_matrix(frames, sorted_track_ids)

    # Only create alarm matrix if user requested alarm calculation
    alarm_matrix = None
    alarm_tracks = set()
    if alarm_threshold != float("inf"):
        alarm_matrix = _create_alarm_matrix(frames, sorted_track_ids, alarm_threshold)

        # Find tracks that have at least one alarm
        for track_idx, track_id in enumerate(sorted_track_ids):
            if np.any(alarm_matrix[track_idx, :] > 0):
                alarm_tracks.add(track_id)

        # Print alarm tracks to stdout for Telegraf comparison
        if alarm_tracks:
            print(f"\nTracks with alarms (>= {alarm_threshold}s):")
            for track_id in sorted(alarm_tracks):
                print(f"  {track_id}")
        else:
            print(f"\nNo tracks exceeded alarm threshold of {alarm_threshold}s")

    # Calculate statistics
    frames_with_activity = np.sum(np.sum(heatmap_matrix, axis=0) >= 1)
    activity_percentage = (
        (frames_with_activity / num_frames) * 100 if num_frames > 0 else 0
    )

    return HeatmapData(
        frames=frames,
        sorted_track_ids=sorted_track_ids,
        heatmap_matrix=heatmap_matrix,
        alarm_matrix=alarm_matrix,
        alarm_tracks=alarm_tracks,
        alarm_threshold=alarm_threshold,
        num_tracks=num_tracks,
        num_frames=num_frames,
        frames_with_activity=frames_with_activity,
        activity_percentage=activity_percentage,
    )


def render_heatmap(heatmap_data: HeatmapData) -> None:
    """
    Render the heatmap visualization using matplotlib.

    Args:
        heatmap_data: Processed heatmap data and statistics
    """
    # Set up the plot
    if heatmap_data.alarm_matrix is not None:
        ax, im = _setup_alarm_heatmap_plot(
            heatmap_data.heatmap_matrix,
            heatmap_data.num_tracks,
            heatmap_data.num_frames,
            heatmap_data.alarm_matrix,
        )
    else:
        ax, im = _setup_alarm_heatmap_plot(
            heatmap_data.heatmap_matrix,
            heatmap_data.num_tracks,
            heatmap_data.num_frames,
        )

    # Set y-axis labels (track IDs)
    ax.set_yticks(range(heatmap_data.num_tracks))
    ax.set_yticklabels(heatmap_data.sorted_track_ids)

    # Set x-axis labels (timestamps)
    step = max(1, heatmap_data.num_frames // 20)  # Show ~20 labels max
    x_ticks = range(0, heatmap_data.num_frames, step)
    # Format timestamps to show just time (HH:MM:SS)
    x_labels = []
    for i in x_ticks:
        timestamp_str = heatmap_data.frames[i].timestamp
        # Parse ISO timestamp and format as HH:MM:SS
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        x_labels.append(dt.strftime("%H:%M:%S"))
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, rotation=45)

    # Add grid for better readability
    ax.set_xticks(np.arange(-0.5, heatmap_data.num_frames, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, heatmap_data.num_tracks, 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=0.5)

    # Add colorbar legend
    cbar = plt.colorbar(im, ax=ax, shrink=0.6)
    if heatmap_data.alarm_threshold != float("inf"):
        cbar.set_ticks([0.33, 1.0, 1.67])
        cbar.set_ticklabels(["Absent", "Present", "Alarm"])
    else:
        cbar.set_ticks([0.25, 0.75])
        cbar.set_ticklabels(["Absent", "Present"])

    # Render statistics text overlay
    alarm_count = len(heatmap_data.alarm_tracks)
    alarm_stats = (
        f" | Alarms: {alarm_count}"
        if heatmap_data.alarm_threshold != float("inf")
        else ""
    )

    stats_text = (
        f"Tracks: {heatmap_data.num_tracks} | Frames: {heatmap_data.num_frames} | "
        f"Activity: {heatmap_data.activity_percentage:.1f}%{alarm_stats}"
    )
    ax.text(
        0.02,
        0.98,
        stats_text,
        transform=ax.transAxes,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8},
        verticalalignment="top",
        fontsize=10,
    )

    plt.tight_layout()
    plt.show()


@click.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output with detailed statistics.",
)
@click.option(
    "--alarm-threshold",
    "-a",
    type=float,
    default=float("inf"),
    help="Time threshold in seconds for alarm visualization (tracks exceeding this show in red).",
)
@click.option(
    "--no-ui",
    is_flag=True,
    help="Disable matplotlib GUI display (useful for CI/CD and headless environments).",
)
def main(input_file: str, verbose: bool, alarm_threshold: float, no_ui: bool):
    """
    Create a heatmap visualization of track activity over time.

    Args:
        input_file: Path to JSONL file containing frame data with track IDs
        verbose: Enable verbose output with detailed statistics
        alarm_threshold: Time threshold in seconds for alarm visualization
        no_ui: Disable matplotlib GUI display (useful for CI/CD and headless environments)

    INPUT_FILE should be a JSONL file containing frame data with track IDs,
    such as the output from FixedIT Data Agent analytics or test data files.

    Examples:
        # Display heatmap interactively
        python track_heatmap_viewer.py test_files/simple_tracks.jsonl

        # Verbose output with statistics
        python track_heatmap_viewer.py test_files/simple_tracks.jsonl --verbose

        # Show alarms for tracks exceeding 5 seconds
        python track_heatmap_viewer.py test_files/simple_tracks.jsonl --alarm-threshold 5.0

        # Run in headless mode (no GUI display)
        python track_heatmap_viewer.py test_files/simple_tracks.jsonl --alarm-threshold 2.0 --no-ui
    """
    try:
        click.echo(f"Loading track data from: {input_file}")

        # Parse the input file
        track_data = parse_jsonl_file(Path(input_file))
        frames = track_data.frames
        all_track_ids = track_data.all_track_ids

        if verbose:
            click.echo("\nDataset Statistics:")
            click.echo(f"  Total frames: {len(frames)}")
            click.echo(f"  Unique tracks: {len(all_track_ids)}")

            if frames:
                first_timestamp = frames[0].timestamp
                last_timestamp = frames[-1].timestamp
                click.echo(f"  Time range: {first_timestamp} to {last_timestamp}")

            if all_track_ids:
                click.echo(f"  Track IDs: {', '.join(sorted(all_track_ids))}")

        # Process the heatmap data
        heatmap_data = process_heatmap_data(frames, all_track_ids, alarm_threshold)

        if heatmap_data is None:
            click.echo("No data available for visualization.")
            return

        # Render the heatmap if UI is enabled
        if not no_ui:
            render_heatmap(heatmap_data)
            click.echo("\nClose the plot window to exit.")

    except (OSError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
