load("logging.star", "log")
load("json.star", "json")

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


def is_point_in_polygon(x, y, vertices):
    """
    Check if a point (x, y) is inside a polygon defined by vertices.
    Uses ray tracing algorithm: cast a ray to the right and count intersections.

    This implementation uses only basic operations for easy porting to Starlark.

    Args:
        x: X coordinate of the point (normalized, 0 to 1 range for detection coords)
        y: Y coordinate of the point (normalized, 0 to 1 range for detection coords)
        vertices: List of [x, y] vertices defining the polygon (in detection coords)

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


def normalize_vertex_to_detection_coords(vertex):
    """
    Convert zone vertices from normalized AXIS coordinates [-1, 1] to detection coords [0, 1].

    In AXIS coordinate system:
    - x: -1 (left) to 1 (right)
    - y: -1 (bottom) to 1 (top)

    In detection bounding box coordinates:
    - x: 0 (left) to 1 (right)
    - y: 0 (top) to 1 (bottom)

    Args:
        vertex: [x, y] in AXIS normalized coordinates [-1, 1]

    Returns:
        [x, y] in detection coordinates [0, 1]
    """
    x, y = vertex
    x_normalized = (x + 1) / 2.0
    y_normalized = (1 - y) / 2.0
    return [x_normalized, y_normalized]


def get_bounding_box_center(bbox_left, bbox_right, bbox_top, bbox_bottom):
    """
    Calculate the center point of a bounding box.

    Args:
        bbox_left: Left edge of bounding box (0 to 1)
        bbox_right: Right edge of bounding box (0 to 1)
        bbox_top: Top edge of bounding box (0 to 1)
        bbox_bottom: Bottom edge of bounding box (0 to 1)

    Returns:
        [center_x, center_y] in detection coordinates [0, 1]
    """
    center_x = (bbox_left + bbox_right) / 2.0
    center_y = (bbox_top + bbox_bottom) / 2.0
    return [center_x, center_y]


def parse_zone_polygon_json(json_str):
    """
    Parse zone polygon from JSON string using json.decode().

    Supports both formats:
    - Single polygon: [[-0.6, -0.4], [0.2, -0.4], ...]
    - Array of zones: [[...], [...], ...]

    Args:
        json_str: JSON string containing zone polygon(s)

    Returns:
        List of zones, where each zone is a list of [x, y] vertices in AXIS coords [-1, 1].
        Returns None if parsing fails.
    """
    log.debug("parse_zone_polygon_json: input = " + repr(json_str))

    # Use json.decode with default parameter (None if parsing fails)
    parsed = json.decode(json_str, default=None)

    if parsed == None:
        log.error("parse_zone_polygon_json: Failed to decode JSON. Input was: " + repr(json_str) + ".")
        return None

    if not parsed:
        log.error("parse_zone_polygon_json: Decoded JSON is empty. Input was: " + repr(json_str))
        return None

    # Expected format: Array of zones [[[-0.6, -0.4], [0.2, -0.4], ...], [[...], ...]]
    # Each zone is an array of [x, y] vertices

    # Check if parsed is a list
    if type(parsed) != "list":
        log.error("parse_zone_polygon_json: Expected array of zones. Got type: " + str(type(parsed)))
        return None

    # Check if it's an array of zones (each element should be a list of vertices)
    if len(parsed) == 0:
        log.error("parse_zone_polygon_json: Array of zones is empty")
        return None

    # Validate that first element is a list (zone)
    if type(parsed[0]) != "list":
        log.error("parse_zone_polygon_json: Expected array of zones (array of arrays). First element is not a list. Got: " + repr(parsed))
        return None

    zones = parsed
    log.debug("parse_zone_polygon_json: Parsed " + str(len(zones)) + " zone(s)")
    return zones


def get_or_parse_zone(state, zone_polygon_json):
    """
    Get cached zone or parse and cache a new one from JSON string.

    This function implements lazy parsing and caching to avoid re-parsing
    the zone on every metric. The zone is cached in Telegraf's shared state dict.

    Args:
        state: Telegraf's shared state dictionary (persists across apply calls)
        zone_polygon_json: JSON string containing zone polygon(s)

    Returns:
        Tuple of (zone_vertices, zone_vertices_normalized) or (None, None) if not configured
        - zone_vertices: List of [x, y] in AXIS coords [-1, 1]
        - zone_vertices_normalized: List of [x, y] in detection coords [0, 1]
    """
    # Check if zone is already cached
    if state.get("zone_cached"):
        log.debug("get_or_parse_zone: Using cached zone")
        return state.get("zone_vertices"), state.get("zone_vertices_normalized")

    # If no zone JSON provided, return None
    if zone_polygon_json == "" or zone_polygon_json == None or zone_polygon_json[:2] == "${":
        # Don't log any error here, instead let the caller use a default (or complain)...
        return None, None

    # Parse the zone
    log.debug("get_or_parse_zone: Parsing zone_polygon_json = " + repr(zone_polygon_json))
    zones = parse_zone_polygon_json(zone_polygon_json)

    if zones == None or len(zones) == 0:
        log.warn("get_or_parse_zone: Failed to parse zone polygon")
        return None, None

    if len(zones) > 1:
        log.error("get_or_parse_zone: Only one zone supported, but got " + str(len(zones)))
        return None, None

    zone = zones[0]

    if len(zone) < 3:
        log.error("get_or_parse_zone: Zone must have at least 3 vertices, but got " + str(len(zone)))
        return None, None

    log.info("get_or_parse_zone: Successfully parsed zone with " + str(len(zone)) + " vertices")

    # Normalize vertices from AXIS coords [-1, 1] to detection coords [0, 1]
    normalized_vertices = []
    for vertex in zone:
        normalized_vertices.append(normalize_vertex_to_detection_coords(vertex))

    # Cache the zone in Telegraf's shared state
    state["zone_cached"] = True
    state["zone_vertices"] = zone
    state["zone_vertices_normalized"] = normalized_vertices

    return zone, normalized_vertices


def apply(metric):
    """
    Filter detection metrics based on whether their center is inside the configured zone.

    The zone is defined by zone_polygon_json constant (passed via Telegraf config).
    Only one zone is currently supported.

    Telegraf provides a special 'state' dictionary that persists across apply() calls,
    which we use to cache the parsed zone and avoid re-parsing on every metric.

    Args:
        metric: Telegraf metric object

    Returns:
        The metric renamed to detection_frame_in_zone. If no zone is configured, all metrics
        pass through. If a zone is configured, only metrics with centers inside the zone pass through.
    """
    # Get or parse the zone (uses Telegraf's state dict for caching)
    zone_vertices, zone_vertices_normalized = get_or_parse_zone(state, zone_polygon_json)

    # If no zone is configured, pass all metrics through with renamed metric name,
    # but show a warning since it might be unintended.
    if zone_vertices == None:
        log.warn("No INCLUDE_ZONE_POLYGON configured - passing all detections through. " +
                 "To explicitly include the entire frame, set INCLUDE_ZONE_POLYGON=" +
                 "[[[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]]]")
        pass_through_metric = deepcopy(metric)
        pass_through_metric.name = "detection_frame_in_zone"
        return pass_through_metric

    # Extract bounding box coordinates from metric
    bbox_left = metric.fields.get("bounding_box_left")
    bbox_right = metric.fields.get("bounding_box_right")
    bbox_top = metric.fields.get("bounding_box_top")
    bbox_bottom = metric.fields.get("bounding_box_bottom")

    if bbox_left == None or bbox_right == None or bbox_top == None or bbox_bottom == None:
        log.warning("apply: Metric missing bounding box fields")
        return metric

    # Calculate center point of bounding box
    center_x, center_y = get_bounding_box_center(bbox_left, bbox_right, bbox_top, bbox_bottom)

    # Get track_id for logging
    track_id = metric.fields.get("track_id", "unknown")

    # Check if center is inside the zone
    if is_point_in_polygon(center_x, center_y, zone_vertices_normalized):
        log.debug("apply: track_id=" + str(track_id) + " center=(" + str(center_x) + "," + str(center_y) + ") INSIDE zone")
        # Create a new metric with the zone-filtered name
        filtered_metric = deepcopy(metric)
        filtered_metric.name = "detection_frame_in_zone"
        return filtered_metric
    else:
        log.debug("apply: track_id=" + str(track_id) + " center=(" + str(center_x) + "," + str(center_y) + ") OUTSIDE zone - filtering out")
        return None
