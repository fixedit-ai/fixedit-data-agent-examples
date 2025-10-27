#!/usr/bin/env python3
"""
Visualize AXIS Object Analytics zones on camera images.

This script takes zone vertices in normalized coordinates [-1, 1] and draws
them on a camera image for visualization.
"""

import json
import click
import cv2
import numpy as np


def normalize_to_pixel(x, y, width, height):
    """
    Convert normalized coordinates [-1, 1] to pixel coordinates.

    In AXIS coordinate system:
    - x: -1 (left) to 1 (right)
    - y: -1 (bottom) to 1 (top)

    In image pixel coordinates:
    - x: 0 (left) to width (right)
    - y: 0 (top) to height (bottom)

    Args:
        x: Normalized x coordinate in range [-1, 1]
        y: Normalized y coordinate in range [-1, 1]
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Tuple of (pixel_x, pixel_y)
    """
    # Convert from [-1, 1] to [0, width] and [0, height]
    # Note: Y axis is inverted (y=-1 is bottom, but pixel y=0 is top)
    pixel_x = int((x + 1) * width / 2)
    pixel_y = int((1 - y) * height / 2)
    return pixel_x, pixel_y


@click.command()
@click.option(
    "--vertices",
    "-v",
    required=True,
    help="Zone vertices as JSON array, e.g., '[[-0.97,-0.97],[-0.97,0.97],[0.12,0.96]]'",
)
@click.option(
    "--image",
    "-i",
    required=True,
    type=click.Path(exists=True),
    help="Path to the image file",
)
@click.option(
    "--save-to", "-s", type=click.Path(), help="Save the output image to this path"
)
@click.option(
    "--no-show", is_flag=True, help="Do not display the image (useful with --save-to)"
)
@click.option(
    "--color",
    "-c",
    default="0,255,0",
    help="Polygon color in BGR format (default: 0,255,0 for green)",
)
@click.option(
    "--thickness",
    "-t",
    default=3,
    type=int,
    help="Line thickness in pixels (default: 3)",
)
@click.option(
    "--fill-alpha",
    "-a",
    default=0.3,
    type=float,
    help="Fill transparency (0.0-1.0, default: 0.3)",
)
def visualize_zone(vertices, image, save_to, no_show, color, thickness, fill_alpha):
    """
    Visualize AXIS Object Analytics zone on a camera image.

    By default, the visualization is displayed on screen. Use --save-to to save
    and --no-show to skip the display.

    Example usage:

        # Display only (default)
        python visualize_zone.py -v '[[-0.97,-0.97],[-0.97,0.97],[-0.12,0.96]]' -i snapshot.jpg

        # Display and save
        python visualize_zone.py -v '[...]' -i snapshot.jpg --save-to output.jpg

        # Save only (no display)
        python visualize_zone.py -v '[...]' -i snapshot.jpg --save-to output.jpg --no-show
    """
    try:
        # Parse vertices JSON
        vertices_list = json.loads(vertices)
        if not isinstance(vertices_list, list) or len(vertices_list) < 3:
            raise ValueError("Vertices must be a list with at least 3 points")

        # Parse color
        color_bgr = tuple(map(int, color.split(",")))
        if len(color_bgr) != 3:
            raise ValueError("Color must be in BGR format: B,G,R")

        # Load image
        img = cv2.imread(image)
        if img is None:
            raise ValueError(f"Failed to load image: {image}")

        height, width = img.shape[:2]

        # Convert normalized coordinates to pixel coordinates
        pixel_points = []
        for vertex in vertices_list:
            if len(vertex) != 2:
                raise ValueError(f"Invalid vertex format: {vertex}")
            x, y = vertex
            px, py = normalize_to_pixel(x, y, width, height)
            pixel_points.append([px, py])

        # Convert to numpy array for OpenCV
        pts = np.array(pixel_points, dtype=np.int32)

        # Create overlay for semi-transparent fill
        overlay = img.copy()

        # Draw filled polygon on overlay
        cv2.fillPoly(overlay, [pts], color_bgr)

        # Blend overlay with original image
        cv2.addWeighted(overlay, fill_alpha, img, 1 - fill_alpha, 0, img)

        # Draw polygon outline
        cv2.polylines(img, [pts], isClosed=True, color=color_bgr, thickness=thickness)

        # Draw vertices as circles
        for point in pixel_points:
            cv2.circle(img, tuple(point), radius=5, color=color_bgr, thickness=-1)

        # Add text info
        text = f"Zone: {len(pixel_points)} vertices"
        cv2.putText(
            img,
            text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color_bgr,
            2,
            cv2.LINE_AA,
        )

        # Save if requested
        if save_to:
            cv2.imwrite(save_to, img)
            click.echo(f"✓ Saved visualization to: {save_to}")

        # Display unless --no-show is specified
        if not no_show:
            window_name = "Zone Visualization (press any key to close)"
            cv2.imshow(window_name, img)
            click.echo("✓ Displaying image. Press any key to close...")
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        # Print zone info
        click.echo(f"\n📊 Zone Information:")
        click.echo(f"   Image size: {width}x{height}")
        click.echo(f"   Vertices: {len(pixel_points)}")
        click.echo(f"\n   Normalized → Pixel coordinates:")
        for i, (norm_pt, pixel_pt) in enumerate(zip(vertices_list, pixel_points)):
            click.echo(
                f"   [{i}] ({norm_pt[0]:+.4f}, {norm_pt[1]:+.4f}) → ({pixel_pt[0]}, {pixel_pt[1]})"
            )

    except json.JSONDecodeError as e:
        click.echo(f"✗ Error parsing vertices JSON: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    visualize_zone()
