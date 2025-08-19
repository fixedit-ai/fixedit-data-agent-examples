#!/usr/bin/env python3
# pylint: disable=too-many-lines
"""
Track Heatmap Viewer.

This script creates a heatmap visualization showing when different track IDs are
active over time.
The visualization displays:
- X-axis: Time (timestamps of frames with observations)
- Y-axis: Track IDs
- Green cells: Track is present in that frame
- Gray cells: Track is not present in that frame

Note: Only frames with observations are shown. Gaps in time are not represented.
This helps visualize track lifecycles and identify patterns in object detection
data.
"""

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

import click
import matplotlib.pyplot as plt
import numpy as np

# Color constants for heatmap visualization
COLOR_ABSENT = "#CCCCCC"  # Gray - track is absent
COLOR_PRESENT = "#4CAF50"  # Green - track is present (classified)
COLOR_UNCLASSIFIED = "#000000"  # Black - track is present but unclassified
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
    def track_ids(self) -> Set[str]:
        """
        Get all unique track IDs present in this frame.

        Returns:
            Set[str]: Set of unique track IDs in this frame.

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
            >>> sorted(frame.track_ids)
            ['track_001', 'track_002']
        """
        return {detection.track_id for detection in self.detections}

    @property
    def class_names(self) -> Dict[str, str]:
        """
        Get mapping of track IDs to class names for this frame.

        Returns:
            Dict[str, str]: Mapping from track_id to class name. Keys are ordered
            to match `track_ids` for deterministic representation.

        Examples:
            >>> bbox1 = BoundingBox(0.1, 0.2, 0.3, 0.4)
            >>> bbox2 = BoundingBox(0.2, 0.3, 0.4, 0.5)
            >>> detection1 = Detection(
            ...     "track_001", "2024-01-15T10:00:01Z", bbox1, ObjectClass("Human")
            ... )
            >>> detection2 = Detection(
            ...     "track_002", "2024-01-15T10:00:02Z", bbox2, ObjectClass("Vehicle")
            ... )
            >>> frame = Frame(1, "2024-01-15T10:00:01Z", [detection1, detection2])
            >>> frame.class_names
            {'track_001': 'Human', 'track_002': 'Vehicle'}
        """
        seen: Dict[str, str] = {}
        for detection in self.detections:
            track_id = detection.track_id
            class_type = detection.class_info.type

            # Only update if we don't have this track_id yet, or if the new
            # class_type is not "Unknown"
            if track_id not in seen or (
                class_type != "Unknown" and seen[track_id] == "Unknown"
            ):
                seen[track_id] = class_type

        return {track_id: seen[track_id] for track_id in sorted(seen.keys())}


@dataclass
class TrackData:
    """Container for parsed track data from JSONL file."""

    frames: List[Frame]

    @property
    def all_track_ids(self) -> Set[str]:
        """
        Get all unique track IDs found across all frames.

        Returns:
            Set of all unique track IDs.

        Examples:
            >>> # Create test data - 2 tracks
            >>> bbox = BoundingBox(0.1, 0.2, 0.3, 0.4)
            >>> human_class = ObjectClass("Human")
            >>> vehicle_class = ObjectClass("Vehicle")
            >>>
            >>> # Frame 1: track_001 (Human)
            >>> det1 = Detection("track_001", "2024-01-01T00:00:01Z", bbox, human_class)
            >>> frame1 = Frame(1, "2024-01-01T00:00:01Z", [det1])
            >>>
            >>> # Frame 2: track_002 (Vehicle)
            >>> det2 = Detection("track_002", "2024-01-01T00:00:02Z", bbox, vehicle_class)
            >>> frame2 = Frame(2, "2024-01-01T00:00:02Z", [det2])
            >>>
            >>> frames = [frame1, frame2]
            >>> track_data = TrackData(frames=frames)
            >>> sorted(track_data.all_track_ids)
            ['track_001', 'track_002']
        """
        all_ids = set()
        for frame in self.frames:
            all_ids.update(frame.track_ids)
        return all_ids

    @property
    def track_class_map(self) -> Dict[str, str]:
        """
        Get mapping of all track IDs to their class types.

        Returns:
            Dict mapping track_id to class type for all tracks found in frames.

        Examples:
            >>> # Create test data - 2 tracks with different classes
            >>> bbox = BoundingBox(0.1, 0.2, 0.3, 0.4)
            >>> human_class = ObjectClass("Human")
            >>> vehicle_class = ObjectClass("Vehicle")
            >>>
            >>> # Frame 1: track_001 (Human)
            >>> det1 = Detection("track_001", "2024-01-01T00:00:01Z", bbox, human_class)
            >>> frame1 = Frame(1, "2024-01-01T00:00:01Z", [det1])
            >>>
            >>> # Frame 2: track_002 (Vehicle)
            >>> det2 = Detection("track_002", "2024-01-01T00:00:02Z", bbox, vehicle_class)
            >>> frame2 = Frame(2, "2024-01-01T00:00:02Z", [det2])
            >>>
            >>> frames = [frame1, frame2]
            >>> track_data = TrackData(frames=frames)
            >>> track_data.track_class_map
            {'track_001': 'Human', 'track_002': 'Vehicle'}
        """
        track_class_map: Dict[str, str] = {}

        # Collect class information from all frames, prioritizing non-"Unknown" values
        for frame in self.frames:
            for track_id, class_name in frame.class_names.items():
                # Only update if we don't have this track_id yet, or if the new
                # class_name is not "Unknown"
                if track_id not in track_class_map or (
                    class_name != "Unknown" and track_class_map[track_id] == "Unknown"
                ):
                    track_class_map[track_id] = class_name

        return track_class_map


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


def _parse_frame_data(frame_data: Dict, line_num: int) -> Frame:
    """
    Parse a single frame data dictionary into a Frame object.

    Args:
        frame_data: Frame dictionary from JSONL data
        line_num: Line number to use as frame number

    Returns:
        Frame object

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

    for obs in observations:
        if "track_id" in obs:
            detection = _parse_observation_to_detection(obs)
            detections.append(detection)

    # Create Frame object
    frame = Frame(
        frame_number=line_num,
        timestamp=frame_timestamp,
        detections=detections,
    )

    return frame


def _parse_jsonl_line(line: str, line_num: int) -> Frame:
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
        >>> frame = _parse_jsonl_line(line, 1)
        >>> frame.frame_number
        1
        >>> frame.timestamp
        '2024-01-15T10:00:01Z'
        >>> len(frame.detections)
        1
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

    frame = _parse_frame_data(data["frame"], line_num)
    return frame


def parse_jsonl_file(file_path: Path) -> TrackData:
    """
    Parse JSONL file and extract frame data.

    Args:
        file_path: Path to the JSONL file

    Returns:
        TrackData containing all frames

    Raises:
        FileNotFoundError: If the input file doesn't exist
        OSError: If there's an error reading the file
        ValueError: If JSON is invalid or missing expected 'frame' key
    """
    frames = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    frame = _parse_jsonl_line(line, line_num)
                    frames.append(frame)

                except ValueError as e:
                    raise ValueError(f"Error parsing line {line_num}: {e}") from e

    except FileNotFoundError as e:
        raise FileNotFoundError(f"File not found: {file_path}") from e
    except OSError as e:
        raise OSError(f"Error reading file {file_path}: {e}") from e

    return TrackData(frames=frames)


def _combine_heatmap_and_alarm_matrices(
    heatmap_matrix: np.ndarray, alarm_matrix: np.ndarray
) -> np.ndarray:
    """
    Combine heatmap and alarm matrices, ensuring alarms override classification status.

    Args:
        heatmap_matrix: Matrix with values 0=absent, 1=unclassified, 2=classified
        alarm_matrix: Matrix with values 0=no alarm, 1=alarm

    Returns:
        Combined matrix with values 0=absent, 1=unclassified, 2=classified, 3=alarm

    Examples:
        >>> # Test data: 2 tracks, 3 frames
        >>> # track1: unclassified, unclassified, classified
        >>> # track2: absent, unclassified, unclassified
        >>> heatmap = np.array([[1, 1, 2], [0, 1, 1]])
        >>> # track1: no alarm, no alarm, alarm
        >>> # track2: no alarm, no alarm, alarm
        >>> alarm = np.array([[0, 0, 1], [0, 0, 1]])
        >>> combined = _combine_heatmap_and_alarm_matrices(heatmap, alarm)
        >>> combined.tolist()
        [[1, 1, 3], [0, 1, 3]]
    """
    combined_matrix = heatmap_matrix.copy()
    # Any track with an alarm gets value 3 (red), regardless of classification
    combined_matrix[alarm_matrix > 0] = 3
    return combined_matrix


def _create_heatmap_matrix(
    frames: List[Frame], sorted_track_ids: List[str]
) -> np.ndarray:
    """
    Create the heatmap matrix from frame data, distinguishing classified vs unclassified tracks.

    Args:
        frames: List of Frame objects
        sorted_track_ids: Sorted list of track IDs. The order determines the row positions
            in the returned matrix - track_ids[0] maps to row 0, track_ids[1] to row 1, etc.
            This ensures consistent visual ordering in the heatmap.

    Returns:
        2D numpy array: 0=absent, 1=unclassified, 2=classified. Rows correspond to
        track IDs in the same order as sorted_track_ids.

    Examples:
        >>> # Create test data - 3 frames, 2 tracks
        >>> bbox = BoundingBox(0.1, 0.2, 0.3, 0.4)
        >>>
        >>> # Frame 1: only track_001 (unclassified)
        >>> det1 = Detection("track_001", "2024-01-01T00:00:01Z", bbox, ObjectClass("Unknown"))
        >>> frame1 = Frame(1, "2024-01-01T00:00:01Z", [det1])
        >>>
        >>> # Frame 2: both tracks (track_001 now classified, track_002 unclassified)
        >>> det2a = Detection("track_001", "2024-01-01T00:00:02Z", bbox, ObjectClass("Human"))
        >>> det2b = Detection("track_002", "2024-01-01T00:00:02Z", bbox, ObjectClass("Unknown"))
        >>> frame2 = Frame(2, "2024-01-01T00:00:02Z", [det2a, det2b])
        >>>
        >>> # Frame 3: only track_002 (still unclassified)
        >>> det3 = Detection("track_002", "2024-01-01T00:00:03Z", bbox, ObjectClass("Unknown"))
        >>> frame3 = Frame(3, "2024-01-01T00:00:03Z", [det3])
        >>>
        >>> frames = [frame1, frame2, frame3]
        >>> track_ids = ["track_001", "track_002"]
        >>> matrix = _create_heatmap_matrix(frames, track_ids)
        >>> matrix.shape
        (2, 3)
        >>> matrix.tolist()
        [[1.0, 2.0, 0.0], [0.0, 1.0, 1.0]]
    """
    num_tracks = len(sorted_track_ids)
    num_frames = len(frames)
    heatmap_matrix = np.zeros((num_tracks, num_frames))

    for frame_idx, frame in enumerate(frames):
        frame_track_ids = set(frame.track_ids)
        for track_idx, track_id in enumerate(sorted_track_ids):
            if track_id in frame_track_ids:
                # Check if track has class info in this specific frame
                class_type = frame.class_names.get(track_id, "Unknown")
                if class_type != "Unknown":
                    heatmap_matrix[track_idx, frame_idx] = 2  # Classified
                else:
                    heatmap_matrix[track_idx, frame_idx] = 1  # Unclassified

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
        sorted_track_ids: Sorted list of track IDs for consistent matrix ordering. The order
            determines the row positions in the returned matrix - track_ids[0] maps to row 0,
            track_ids[1] to row 1, etc. This ensures the alarm matrix rows align with the
            heatmap matrix rows for proper combination.
        alarm_threshold: Time threshold in seconds for alarm conditions

    Returns:
        2D numpy array: 1 where track exceeds threshold, 0 otherwise. Rows correspond to
        track IDs in the same order as sorted_track_ids, ensuring alignment with the heatmap matrix.

    Raises:
        ValueError: If timestamp parsing fails or data is invalid

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


def _create_heatmap_imshow(
    ax: plt.Axes, combined_matrix: np.ndarray, show_alarm_colors: bool
) -> tuple[plt.matplotlib.image.AxesImage, str, list, list]:
    """
    Create imshow plot with appropriate colormap configuration and return title.

    This function handles different color schemes:
    1. Alarm colors (4 discrete values): 0=absent, 1=unclassified, 2=classified, 3=alarm
    2. Basic colors (3 discrete values): 0=absent, 1=unclassified, 2=classified

    Both use BoundaryNorm for consistent discrete color boundaries, ensuring exact
    value-to-color mapping.

    Args:
        ax: Matplotlib axes to plot on
        combined_matrix: 2D numpy array with track presence/alarm data
        show_alarm_colors: Whether to include alarm colors (4-color scheme) or basic colors
            (3-color scheme)

    Returns:
        Tuple of (matplotlib image object from imshow, title string, tick positions, tick labels)

    Examples:
        >>> import matplotlib.pyplot as plt
        >>> fig, ax = plt.subplots()
        >>> matrix = np.array([[0, 1], [2, 0]])
                >>> im, title, ticks, labels = _create_heatmap_imshow(ax, matrix, False)
        >>> im is not None
        True
        >>> "Classified" in title
        True
        >>> len(ticks) == 3
        True

        >>> im, title, ticks, labels = _create_heatmap_imshow(ax, matrix, True)
        >>> "Alarm" in title
        True
        >>> len(ticks) == 4
        True
    """
    if show_alarm_colors:
        # 4-class case: 0=absent, 1=unclassified, 2=classified, 3=alarm
        colors = [COLOR_ABSENT, COLOR_UNCLASSIFIED, COLOR_PRESENT, COLOR_ALARM]
        title = (
            "Track Activity Heatmap\n"
            "(Gray = Absent, Black = Unclassified, Green = Classified, Red = Alarm)"
        )
        bounds = [0, 1, 2, 3, 4]
        num_colors = 4
        tick_positions = [0.5, 1.5, 2.5, 3.5]
        tick_labels = ["Absent", "Unclassified", "Classified", "Alarm"]
    else:
        # 3-class case: 0=absent, 1=unclassified, 2=classified
        colors = [COLOR_ABSENT, COLOR_UNCLASSIFIED, COLOR_PRESENT]
        title = (
            "Track Activity Heatmap\n"
            "(Gray = Absent, Black = Unclassified, Green = Classified)"
        )
        bounds = [0, 1, 2, 3]
        num_colors = 3
        tick_positions = [0.5, 1.5, 2.5]
        tick_labels = ["Absent", "Unclassified", "Classified"]

    # Create colormap and imshow
    cmap = plt.matplotlib.colors.ListedColormap(colors, N=num_colors)
    norm = plt.matplotlib.colors.BoundaryNorm(bounds, cmap.N)

    im = ax.imshow(
        combined_matrix,
        cmap=cmap,
        aspect="auto",
        interpolation="nearest",
        norm=norm,
    )

    return im, title, tick_positions, tick_labels


def _setup_heatmap_plot(
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
        Tuple of (axes, image, tick positions, tick labels) from matplotlib
    """
    height = max(8, num_tracks * 0.4)
    width = max(12, num_frames * 0.1)
    _, ax = plt.subplots(figsize=(width, height))

    # Create combined matrix: 0=absent, 1=present&unclassified, 2=present&classified, 3=alarm
    # (if alarm_matrix provided)
    if alarm_matrix is not None:
        combined_matrix = _combine_heatmap_and_alarm_matrices(
            heatmap_matrix, alarm_matrix
        )
        show_alarm_colors = True
    else:
        combined_matrix = heatmap_matrix
        show_alarm_colors = False

    # Create the imshow plot with appropriate colormap settings and get title + tick info
    im, title, tick_positions, tick_labels = _create_heatmap_imshow(
        ax, combined_matrix, show_alarm_colors
    )

    ax.set_xlabel("Time (Frames with Observations)")
    ax.set_ylabel("Track ID")
    ax.set_title(title)

    return ax, im, tick_positions, tick_labels


@dataclass
class HeatmapData:  # pylint: disable=too-many-instance-attributes
    """Container for processed heatmap data and statistics."""

    track_data: TrackData
    heatmap_matrix: np.ndarray
    alarm_matrix: Optional[np.ndarray]
    alarm_tracks: Set[str]
    alarm_threshold: float
    num_tracks: int
    num_frames: int
    frames_with_activity: int
    activity_percentage: float


def process_heatmap_data(
    track_data: TrackData,
    alarm_threshold: float = float("inf"),
) -> Optional[HeatmapData]:
    """
    Process track data and calculate heatmap matrices and statistics.

    This function processes track data to create:
    1. Base heatmap matrix: Track presence over time
    2. Alarm matrix: Tracks that exceed time-in-area threshold (optional)
    3. Statistics: Activity percentages and alarm counts

    Args:
        track_data: TrackData object containing frames and track information
        alarm_threshold: Time threshold in seconds for alarm calculation (default: inf = no alarms)

    Returns:
        HeatmapData object containing processed matrices and statistics, or None if no data
    """
    if not track_data.frames:
        return None

    if not track_data.all_track_ids:
        return None

    sorted_track_ids = sorted(track_data.all_track_ids)
    num_tracks = len(sorted_track_ids)
    num_frames = len(track_data.frames)

    heatmap_matrix = _create_heatmap_matrix(track_data.frames, sorted_track_ids)

    # Only create alarm matrix if user requested alarm calculation
    alarm_matrix = None
    alarm_tracks = set()
    if alarm_threshold != float("inf"):
        alarm_matrix = _create_alarm_matrix(
            track_data.frames, sorted_track_ids, alarm_threshold
        )

        # Find tracks that have at least one alarm
        for track_idx, track_id in enumerate(sorted_track_ids):
            if np.any(alarm_matrix[track_idx, :] > 0):
                alarm_tracks.add(track_id)

        # Print alarm tracks to stdout for Telegraf comparison with class info and observation count
        if alarm_tracks:
            print(f"\nTracks with alarms (>= {alarm_threshold}s):")
            for track_id in sorted(alarm_tracks):
                class_type = track_data.track_class_map.get(track_id, "Unknown")
                # Count alarm occurrences for this track
                track_idx = sorted_track_ids.index(track_id)
                alarm_count = int(np.sum(alarm_matrix[track_idx, :] > 0))
                # Print track ID on its own line
                print(f"  {track_id}")
                # Print additional info on next line
                print(f"    Class: {class_type}, Alarms: {alarm_count}")
        else:
            print(f"\nNo tracks exceeded alarm threshold of {alarm_threshold}s")

    # Calculate statistics
    frames_with_activity = np.sum(np.sum(heatmap_matrix, axis=0) >= 1)
    activity_percentage = (
        (frames_with_activity / num_frames) * 100 if num_frames > 0 else 0
    )

    return HeatmapData(
        track_data=track_data,
        heatmap_matrix=heatmap_matrix,
        alarm_matrix=alarm_matrix,
        alarm_tracks=alarm_tracks,
        alarm_threshold=alarm_threshold,
        num_tracks=num_tracks,
        num_frames=num_frames,
        frames_with_activity=frames_with_activity,
        activity_percentage=activity_percentage,
    )


def _format_track_labels_for_yaxis(
    track_ids: List[str], track_class_map: Dict[str, str]
) -> List[str]:
    """
    Format track IDs with shortened class names for y-axis labels.

    Args:
        track_ids: List of track IDs to format
        track_class_map: Dictionary mapping track IDs to class names

    Returns:
        List of formatted track labels in "track_id (class)" format

    Examples:
        >>> track_ids = ["track_001", "track_002", "track_003"]
        >>> class_map = {"track_001": "Human", "track_002": "Vehicle", "track_003": "Unknown"}
        >>> _format_track_labels_for_yaxis(track_ids, class_map)
        ['track_001 (Huma.)', 'track_002 (Vehi.)', 'track_003 (Unkn.)']

        >>> _format_track_labels_for_yaxis(["track_001"], {"track_001": "Cat"})
        ['track_001 (Cat)']

        >>> _format_track_labels_for_yaxis(["track_001"], {})
        ['track_001 (Unkn.)']
    """
    y_labels = []
    for track_id in track_ids:
        class_type = track_class_map.get(track_id, "Unknown")
        if len(class_type) > 4:
            class_short = class_type[:4] + "."
        else:
            class_short = class_type
        y_labels.append(f"{track_id} ({class_short})")
    return y_labels


def _format_timestamps_for_xaxis(frames: List[Frame], x_ticks: range) -> List[str]:
    """
    Format timestamps from frames to show just time (HH:MM:SS) for x-axis labels.

    Args:
        frames: List of Frame objects with timestamp data
        x_ticks: Range of frame indices to format

    Returns:
        List of formatted time strings in HH:MM:SS format

        Examples:
        >>> from datetime import datetime
        >>> frames = [
        ...     Frame(1, "2024-01-01T10:30:00.123Z", []),
        ...     Frame(2, "2024-01-01T10:31:00.456Z", []),
        ...     Frame(3, "2024-01-01T10:32:00.789Z", [])
        ... ]
        >>> _format_timestamps_for_xaxis(frames, range(0, 3))
        ['10:30:00', '10:31:00', '10:32:00']

        >>> _format_timestamps_for_xaxis(frames, range(0, 3, 2))
        ['10:30:00', '10:32:00']

        >>> _format_timestamps_for_xaxis(frames, range(1, 2))
        ['10:31:00']
    """
    x_labels = []
    for i in x_ticks:
        timestamp_str = frames[i].timestamp
        # Parse ISO timestamp and format as HH:MM:SS
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        x_labels.append(dt.strftime("%H:%M:%S"))
    return x_labels


def render_heatmap(
    heatmap_data: HeatmapData,
) -> None:
    """
    Render the heatmap visualization using matplotlib.

    Args:
        heatmap_data: Processed heatmap data and statistics
    """
    # Set up heatmap image the plot
    ax, im, tick_positions, tick_labels = _setup_heatmap_plot(
        heatmap_data.heatmap_matrix,
        heatmap_data.num_tracks,
        heatmap_data.num_frames,
        heatmap_data.alarm_matrix,
    )

    # Set y-axis labels (track IDs with class information)
    ax.set_yticks(range(heatmap_data.num_tracks))
    sorted_track_ids = sorted(heatmap_data.track_data.all_track_ids)
    y_labels = _format_track_labels_for_yaxis(
        sorted_track_ids, heatmap_data.track_data.track_class_map
    )
    ax.set_yticklabels(y_labels)

    ax.tick_params(axis="y", labelsize=9)  # Smaller font size for better fit
    plt.setp(ax.get_yticklabels(), ha="right")  # Right-align labels

    # Set x-axis labels (timestamps)
    step = max(1, heatmap_data.num_frames // 20)  # Show ~20 labels max
    x_ticks = range(0, heatmap_data.num_frames, step)
    x_labels = _format_timestamps_for_xaxis(heatmap_data.track_data.frames, x_ticks)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, rotation=45)

    # Add grid for better readability
    ax.set_xticks(np.arange(-0.5, heatmap_data.num_frames, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, heatmap_data.num_tracks, 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=0.5)

    # Add colorbar legend using tick information from setup function
    cbar = plt.colorbar(im, ax=ax, shrink=0.6)
    cbar.set_ticks(tick_positions)
    cbar.set_ticklabels(tick_labels)

    # Render statistics text overlay
    stats_text = (
        f"Tracks: {heatmap_data.num_tracks} | Frames: {heatmap_data.num_frames} | "
        f"Activity: {heatmap_data.activity_percentage:.1f}%"
        + (
            f" | Alarms: {len(heatmap_data.alarm_tracks)}"
            if heatmap_data.alarm_threshold != float("inf")
            else ""
        )
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

    # Adjust layout to ensure Y-axis labels are fully visible with more padding
    plt.subplots_adjust(left=0.15, right=0.85, top=0.92, bottom=0.15)
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
    help="Time threshold in seconds for alarm visualization "
    "(tracks exceeding this show in red).",
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
        heatmap_data = process_heatmap_data(track_data, alarm_threshold)

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
