#!/usr/bin/env python3
"""
Extract center coordinates from bounding boxes in detection data.

Parses JSON detection frames from a JSONL file and outputs the center point (cx, cy)
for each detection in both coordinate systems:
- [0, 1]: Detection bounding box coordinate system
- [-1, 1]: AXIS normalized coordinate system (zone polygon system)

Dependencies:
- click: Command-line interface framework
- prettytable: ASCII table formatting
- matplotlib: For zone and detection visualization
- numpy: For numerical operations
"""

import json
import re
import sys
from pathlib import Path

import click
import cv2
import numpy as np
from prettytable import PrettyTable

# Import visualization functions from visualize_zone
sys.path.insert(0, str(Path(__file__).parent))
from visualize_zone import draw_zone_on_image, normalize_to_pixel


def parse_json(data_str):
    """Parse JSONL data and return list of observation dicts."""
    observations = []
    for line in data_str.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            frame_data = json.loads(line)
            observations.extend(frame_data["frame"]["observations"])

    return observations


def parse_zone_from_file(filepath):
    """Extract zone polygons from JSONL file comments.

    Expected format: # Use zone: [[[x1,y1],[x2,y2],...]] (array of zones)

    Returns:
        Tuple of (zones_list, bbox_tuple) where:
        - zones_list: List of zones, where each zone is a list of [x, y] coordinates
        - bbox_tuple: (x_min, x_max, y_min, y_max) for visualization (covering all zones)

    Raises:
        ValueError: If zone definition comment is not found in file.
    """
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# Use zone:"):
                # Parse the JSON array of zones format: [[[x1,y1],[x2,y2],...]]
                match = re.search(r"# Use zone:\s*(\[\[\[.*\]\]\])", line)

                if match:
                    try:
                        zone_str = match.group(1)
                        # Parse JSON array of zones
                        zones = json.loads(zone_str)

                        # Validate zones format
                        if not isinstance(zones, list) or len(zones) == 0:
                            raise ValueError(
                                "Expected array of zones with at least one zone"
                            )

                        # Validate each zone
                        for i, zone in enumerate(zones):
                            if not isinstance(zone, list) or len(zone) < 3:
                                raise ValueError(
                                    f"Zone {i} must have at least 3 vertices"
                                )

                        # Calculate bounding box covering all zones
                        all_x_coords = []
                        all_y_coords = []
                        for zone in zones:
                            all_x_coords.extend([v[0] for v in zone])
                            all_y_coords.extend([v[1] for v in zone])

                        bbox = (
                            min(all_x_coords),
                            max(all_x_coords),
                            min(all_y_coords),
                            max(all_y_coords),
                        )

                        return zones, bbox
                    except (
                        json.JSONDecodeError,
                        ValueError,
                        TypeError,
                        IndexError,
                    ) as e:
                        raise ValueError(
                            f"Failed to parse zone polygon.\n"
                            f"Expected format: '# Use zone: [[[x1,y1],[x2,y2],...]]' (array of zones)\n"
                            f"Got: '{line}'\n"
                            f"Error: {e}"
                        )
                else:
                    raise ValueError(
                        f"Zone definition format mismatch.\n"
                        f"Expected format: '# Use zone: [[[x1,y1],[x2,y2],...]]' (array of zones)\n"
                        f"Got: '{line}'"
                    )

    raise ValueError(
        f"Zone definition not found in {filepath}.\n"
        f"File must contain a comment line with format:\n"
        f"# Use zone: [[x1,y1],[x2,y2],...] in [-1, 1] range"
    )


def draw_detections_on_image(img, observations, detection_labels):
    """Draw detection centers on image with labels.

    Args:
        img: OpenCV image (modified in place)
        observations: List of observation dictionaries with bounding_box
        detection_labels: List of detection labels (a, b, c, etc.)
    """
    height, width = img.shape[:2]

    for idx, (obs, label) in enumerate(zip(observations[:26], detection_labels)):
        bbox = obs["bounding_box"]
        # Convert [0,1] bounding box to [-1,1] for consistency
        cx_0_1 = (bbox["left"] + bbox["right"]) / 2
        cy_0_1 = (bbox["top"] + bbox["bottom"]) / 2
        cx_minus1_1 = cx_0_1 * 2 - 1
        cy_minus1_1 = 1 - cy_0_1 * 2

        # Convert to pixel coordinates
        px, py = normalize_to_pixel(cx_minus1_1, cy_minus1_1, width, height)

        # Draw center point
        color = (0, 255, 0)  # Green in BGR
        cv2.circle(img, (px, py), radius=8, color=color, thickness=-1)
        cv2.circle(img, (px, py), radius=8, color=(0, 0, 0), thickness=2)

        # Draw label
        cv2.putText(
            img,
            label,
            (px + 12, py - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )


def visualize_zone_and_detections(observations, zones, output_file=None, display=False):
    """Create visualization of zone(s) and detections.

    Args:
        observations: List of observation dictionaries
        zones: List of zones, where each zone is a list of [x, y] coordinates in [-1,1] range
        output_file: Optional path to save visualization
        display: Whether to display the image (requires output_file to be None or file saved first)
    """
    # Create blank image (normalized coordinate space visualization)
    img_size = 600
    img = (
        np.ones((img_size, img_size, 3), dtype=np.uint8) * 240
    )  # Light gray background

    # Draw all zones using different colors
    zone_colors = [
        (200, 100, 100),  # Blue-ish (BGR)
        (100, 200, 100),  # Green-ish
        (100, 100, 200),  # Red-ish
        (200, 200, 100),  # Cyan-ish
        (200, 100, 200),  # Magenta-ish
    ]

    for i, zone_vertices in enumerate(zones):
        color = zone_colors[i % len(zone_colors)]
        draw_zone_on_image(img, zone_vertices, color, 2, 0.2)

    # Draw detections
    detection_labels = [chr(ord("a") + i) for i in range(len(observations[:26]))]
    draw_detections_on_image(img, observations, detection_labels)

    # Add coordinate system labels
    cv2.putText(img, "-1.0", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(
        img, "+1.0", (img_size - 50, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1
    )
    cv2.putText(
        img, "-1.0", (10, img_size - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1
    )
    cv2.putText(img, "+1.0", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    # Save if requested
    if output_file:
        cv2.imwrite(output_file, img)
        click.echo(f"✓ Saved visualization to: {output_file}")

    # Display if requested
    if display:
        window_name = "Zone and Detections (press any key to close)"
        cv2.imshow(window_name, img)
        click.echo("✓ Displaying visualization. Press any key to close...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return img


@click.command()
@click.argument("jsonl_file", type=click.Path(exists=True))
@click.option(
    "--no-visualize", is_flag=True, help="Disable visualization (only print table)"
)
@click.option(
    "--save-to",
    "-s",
    type=click.Path(),
    help="Save visualization image to this path instead of displaying",
)
def main(jsonl_file, no_visualize, save_to):
    """Extract center coordinates from detections in JSONL_FILE."""
    with open(jsonl_file, "r") as f:
        data = f.read()

    observations = parse_json(data)

    if len(observations) > 26:
        click.echo(
            f"Warning: Only first 26 detections will be shown (found {len(observations)})",
            err=True,
        )

    # Parse zones from file
    try:
        zones, _ = parse_zone_from_file(jsonl_file)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        zones = None

    # Create table first
    table = PrettyTable()
    table.field_names = [
        "Detection",
        "Track ID",
        "Center X (0...1)",
        "Center Y (0...1)",
        "Center X (-1...1)",
        "Center Y (-1...1)",
    ]
    table.align["Track ID"] = "l"

    for idx, obs in enumerate(observations[:26]):
        bbox = obs["bounding_box"]
        track_id = obs["track_id"]

        cx_0_1 = (bbox["left"] + bbox["right"]) / 2
        cy_0_1 = (bbox["top"] + bbox["bottom"]) / 2

        # Convert to [-1, 1] coordinate system
        cx_minus1_1 = cx_0_1 * 2 - 1
        cy_minus1_1 = 1 - cy_0_1 * 2

        detection_label = chr(ord("a") + idx)

        table.add_row(
            [
                detection_label,
                track_id,
                f"{cx_0_1:.2g}",
                f"{cy_0_1:.2g}",
                f"{cx_minus1_1:.2g}",
                f"{cy_minus1_1:.2g}",
            ]
        )

    click.echo(table)

    # Create visualization unless disabled
    if not no_visualize and zones:
        # Display live by default, save to file if --save-to provided
        display = not save_to
        visualize_zone_and_detections(
            observations, zones, output_file=save_to, display=display
        )


if __name__ == "__main__":
    main()
