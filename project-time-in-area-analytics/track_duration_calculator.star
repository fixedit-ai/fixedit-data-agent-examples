load("time.star", "time")

def parse_timestamp_to_seconds(timestamp_str):
    """Parse ISO 8601 timestamp string to Unix seconds

    Note: Starlark uses 32-bit signed integers (max: 2,147,483,647).
    Unix timestamps will overflow after year 2038.
    """
    time_format = "2006-01-02T15:04:05Z"
    time_obj = time.parse_time(timestamp_str, format=time_format)
    return int(time_obj.unix)

def get_time_in_area_seconds(track_id, current_seconds, track_state):
    """Get the time in area for a track ID and update its last seen time

    Args:
        track_id: The object tracking ID
        current_seconds: Current timestamp in Unix seconds
        track_state: State dictionary for tracking objects

    Returns:
        Time in area in seconds for this track ID
    """
    if track_id not in track_state:
        # First time seeing this track ID - initialize with current timestamp in seconds
        track_state[track_id] = {
            "first_seen_seconds": current_seconds,
            "last_seen_seconds": current_seconds
        }
        return 0  # Time in area is 0 on first detection

    # Update last seen time
    track_state[track_id]["last_seen_seconds"] = current_seconds

    # Calculate time in area - simple subtraction since both are in seconds
    first_seen_seconds = track_state[track_id]["first_seen_seconds"]
    time_in_area = current_seconds - first_seen_seconds
    return time_in_area

def cleanup_stale_tracks(current_seconds, track_state, max_stale_seconds):
    """Remove tracks that haven't been seen for too long

    Args:
        current_seconds: Current timestamp in Unix seconds
        track_state: State dictionary for tracking objects
        max_stale_seconds: Maximum time since last seen before removing track

    Returns:
        List of debug metrics for removed tracks
    """
    # Find tracks to remove (can't modify dict while iterating)
    tracks_to_remove = []
    debug_metrics = []

    for track_id, track_data in track_state.items():
        last_seen = track_data["last_seen_seconds"]
        time_since_seen = current_seconds - last_seen
        if time_since_seen > max_stale_seconds:
            tracks_to_remove.append(track_id)

            # Create debug metric for this removal
            debug_metric = Metric("track_cleanup_debug")
            debug_metric.fields["track_id"] = track_id
            debug_metric.fields["time_since_seen"] = time_since_seen
            debug_metric.fields["max_stale_seconds"] = max_stale_seconds
            debug_metric.fields["action"] = "removed_stale_track"
            debug_metrics.append(debug_metric)

    # Remove stale tracks
    for track_id in tracks_to_remove:
        track_state.pop(track_id)

    return debug_metrics

def apply(metric):
    # Get track_id and timestamp from the metric
    track_id = metric.fields.get("track_id", "")
    timestamp = metric.fields.get("timestamp", "")

    # Skip messages without track_id
    if track_id == "" or timestamp == "":
        return metric

    # Parse timestamp to seconds
    current_seconds = parse_timestamp_to_seconds(timestamp)

    # Initialize track state subdict if it doesn't exist
    if "track_state" not in state:
        state["track_state"] = {}

    # Clean up stale tracks (not seen for 60 seconds) and get debug metrics
    debug_metrics = cleanup_stale_tracks(current_seconds, state["track_state"], 60)

    # Get the time in area for this track ID
    time_in_area = get_time_in_area_seconds(track_id, current_seconds, state["track_state"])

    # Add the time in area to the metric (always add it, filtering happens in next processor)
    metric.fields["time_in_area_seconds"] = time_in_area

    # Prepare results list
    results = []

    # Add debug metrics first (if any)
    results.extend(debug_metrics)

    # Always add the main metric with dwell time
    results.append(metric)

    # Return list of metrics
    return results
