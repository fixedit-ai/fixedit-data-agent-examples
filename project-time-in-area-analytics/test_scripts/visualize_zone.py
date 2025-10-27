#!/usr/bin/env python3
"""
Visualize AXIS Object Analytics zones on camera images.

This script takes zone vertices in normalized coordinates [-1, 1] and draws
them on a camera image for visualization.
"""

import json
import random
import click
import cv2
import numpy as np


def edge_crosses_horizontal_line(y, y1, y2):
    """Check if an edge crosses the horizontal line at y."""
    return (y1 > y) != (y2 > y)


def calculate_edge_x_at_y(x1, y1, x2, y2, y):
    """Calculate the x-coordinate where the edge intersects the horizontal line at y."""
    return (x2 - x1) * (y - y1) / (y2 - y1) + x1


def ray_intersects_edge(x, y, x1, y1, x2, y2):
    """
    Check if a ray cast from point (x,y) to the right intersects the edge.

    Args:
        x, y: Point coordinates
        x1, y1: First vertex of edge
        x2, y2: Second vertex of edge

    Returns:
        True if the rightward ray from (x,y) intersects the edge
    """
    if not edge_crosses_horizontal_line(y, y1, y2):
        return False

    edge_x = calculate_edge_x_at_y(x1, y1, x2, y2, y)
    return x < edge_x


def is_in_zone(x, y, vertices):
    """
    Check if a point (x, y) is inside a polygon defined by vertices.
    Uses ray tracing algorithm: cast a ray to the right and count intersections.

    This implementation uses only basic Python for easy porting to Starlark.

    Args:
        x: X coordinate of the point (normalized, -1 to 1)
        y: Y coordinate of the point (normalized, -1 to 1)
        vertices: List of [x, y] vertices defining the polygon

    Returns:
        True if point is inside the polygon, False otherwise
    """
    num_vertices = len(vertices)
    inside = False

    # Check each edge of the polygon
    j = num_vertices - 1  # Start with the last vertex
    for i in range(num_vertices):
        xi, yi = vertices[i]
        xj, yj = vertices[j]

        if ray_intersects_edge(x, y, xi, yi, xj, yj):
            inside = not inside

        j = i

    return inside


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


def draw_zone_on_image(img, vertices_list, color_bgr, thickness, fill_alpha):
    """
    Draw a zone polygon on the image with semi-transparent fill.

    Args:
        img: OpenCV image (modified in place)
        vertices_list: List of [x, y] normalized vertices
        color_bgr: Tuple of (B, G, R) color values
        thickness: Line thickness for polygon outline
        fill_alpha: Transparency for fill (0.0-1.0)

    Returns:
        List of pixel coordinates for the vertices
    """
    height, width = img.shape[:2]

    # Convert normalized coordinates to pixel coordinates
    pixel_points = []
    for vertex in vertices_list:
        x, y = vertex
        px, py = normalize_to_pixel(x, y, width, height)
        pixel_points.append([px, py])

    # Convert to numpy array for OpenCV
    pts = np.array(pixel_points, dtype=np.int32)

    # Create overlay for semi-transparent fill
    overlay = img.copy()
    cv2.fillPoly(overlay, [pts], color_bgr)

    # Blend overlay with original image
    cv2.addWeighted(overlay, fill_alpha, img, 1 - fill_alpha, 0, img)

    # Draw polygon outline
    cv2.polylines(img, [pts], isClosed=True, color=color_bgr, thickness=thickness)

    # Draw vertices as circles
    for point in pixel_points:
        cv2.circle(img, tuple(point), radius=5, color=color_bgr, thickness=-1)

    return pixel_points


def draw_test_points_on_image(img, vertices_list, num_points):
    """
    Draw random test points on the image to visualize the is_in_zone algorithm.

    Args:
        img: OpenCV image (modified in place)
        vertices_list: List of [x, y] normalized vertices defining the zone
        num_points: Number of random points to generate
    """
    height, width = img.shape[:2]
    random.seed(42)  # For reproducible results

    inside_count = 0
    outside_count = 0

    for i in range(num_points):
        # Generate random normalized coordinates
        test_x = random.uniform(-1.0, 1.0)
        test_y = random.uniform(-1.0, 1.0)

        # Check if point is inside zone
        is_inside = is_in_zone(test_x, test_y, vertices_list)

        # Convert to pixel coordinates
        test_px, test_py = normalize_to_pixel(test_x, test_y, width, height)

        # Choose color: red for inside, yellow for outside
        if is_inside:
            point_color = (0, 0, 255)  # Red (BGR)
            inside_count += 1
        else:
            point_color = (0, 255, 255)  # Yellow (BGR)
            outside_count += 1

        # Draw the point
        cv2.circle(img, (test_px, test_py), radius=8, color=point_color, thickness=-1)
        cv2.circle(img, (test_px, test_py), radius=8, color=(0, 0, 0), thickness=1)

    # Add legend
    legend_y = 60
    cv2.putText(
        img,
        f"Test points: {num_points}",
        (10, legend_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.circle(img, (20, legend_y + 25), radius=8, color=(0, 0, 255), thickness=-1)
    cv2.putText(
        img,
        f"Inside: {inside_count}",
        (35, legend_y + 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.circle(img, (20, legend_y + 50), radius=8, color=(0, 255, 255), thickness=-1)
    cv2.putText(
        img,
        f"Outside: {outside_count}",
        (35, legend_y + 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


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
@click.option(
    "--add-random-points",
    "-r",
    type=int,
    help="Add N random test points (red=inside zone, yellow=outside zone)",
)
def visualize_zone(
    vertices, image, save_to, no_show, color, thickness, fill_alpha, add_random_points
):
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

        # Test the is_in_zone algorithm with random points
        python visualize_zone.py -v '[...]' -i snapshot.jpg --add-random-points 50
    """
    try:
        # Parse vertices JSON
        vertices_list = json.loads(vertices)
        if not isinstance(vertices_list, list) or len(vertices_list) < 3:
            raise ValueError("Vertices must be a list with at least 3 points")

        # Validate vertex format
        for vertex in vertices_list:
            if len(vertex) != 2:
                raise ValueError(f"Invalid vertex format: {vertex}")

        # Parse color
        color_bgr = tuple(map(int, color.split(",")))
        if len(color_bgr) != 3:
            raise ValueError("Color must be in BGR format: B,G,R")

        # Load image
        img = cv2.imread(image)
        if img is None:
            raise ValueError(f"Failed to load image: {image}")

        height, width = img.shape[:2]

        # Draw the zone polygon on the image
        pixel_points = draw_zone_on_image(
            img, vertices_list, color_bgr, thickness, fill_alpha
        )

        # Add zone info text
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

        # Draw random test points if requested
        if add_random_points:
            draw_test_points_on_image(img, vertices_list, add_random_points)

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
