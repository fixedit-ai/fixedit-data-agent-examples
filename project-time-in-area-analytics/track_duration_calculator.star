load("logging.star", "log")

def detection_time_seconds(metric):
    """Return detection instant as Unix seconds (float).

    Telegraf always attaches metric.time. With json_time_key on the scene JSON input,
    that time is the detection instant (nanoseconds since epoch). Duration math uses
    only that, no ISO string parsing is needed.
    """
    mt = metric.time
    if mt == None or mt == 0:
        return None
    return float(mt) / 1000000000.0

def get_time_in_area_seconds(track_id, current_seconds, track_state):
    """Get the time in area for a track ID and update its last seen time

    Args:
        track_id: The object tracking ID
        current_seconds: Current timestamp in Unix seconds
        track_state: State dictionary for tracking objects

    Returns:
        Time in area as a float (seconds with microsecond precision)
    """
    if track_id not in track_state:
        # First time seeing this track ID - initialize with current timestamp
        track_state[track_id] = {
            "first_seen_seconds": current_seconds,
            "last_seen_seconds": current_seconds
        }
        log.debug("get_time_in_area_seconds: track_id=" + track_id + " first detection at " + str(current_seconds))
        # Time in area is 0 on first detection.
        # We set it to 0.0 since subsequent values will be floats,
        # and 0 gets interpreted as an integer, which can result in
        # errors when sending metrics to InfluxDB.
        return 0.0

    # Update last seen time
    track_state[track_id]["last_seen_seconds"] = current_seconds

    # Calculate time in area - simple subtraction since both are in seconds
    first_seen_seconds = track_state[track_id]["first_seen_seconds"]
    time_in_area = current_seconds - first_seen_seconds
    log.debug("get_time_in_area_seconds: track_id=" + track_id + " duration=" + str(time_in_area) + "s (first_seen=" + str(first_seen_seconds) + ", current=" + str(current_seconds) + ")")
    return time_in_area

def cleanup_stale_tracks(current_seconds, track_state, max_stale_seconds):
    """Remove tracks that haven't been seen for too long

    Args:
        current_seconds: Current timestamp in Unix seconds
        track_state: State dictionary for tracking objects
        max_stale_seconds: Maximum time since last seen before removing track
    """
    # Find tracks to remove (can't modify dict while iterating)
    tracks_to_remove = []

    for track_id, track_data in track_state.items():
        last_seen_seconds = track_data["last_seen_seconds"]
        time_since_seen = current_seconds - last_seen_seconds

        if time_since_seen > max_stale_seconds:
            tracks_to_remove.append(track_id)

    # Remove stale tracks
    if len(tracks_to_remove) > 0:
        log.debug("cleanup_stale_tracks: Removing " + str(len(tracks_to_remove)) + " stale track(s): " + str(tracks_to_remove))
    for track_id in tracks_to_remove:
        track_state.pop(track_id)

def apply(metric):
    """Calculate the time in area for each metric.

    This function will be called for each metric in the pipeline,
    the function will keep a state of all the track IDs and their
    first and last seen times. The function will calculate the time
    in area for each track ID and add it to the metric.

    Returns:
        The input metric but with the time in area added.
    """
    # Get track_id from the metric
    track_id = metric.fields.get("track_id", "")
    # Skip messages without track_id
    if track_id == "":
        return metric

    # Parse timestamp to float seconds since Unix epoch
    current_seconds = detection_time_seconds(metric)
    if current_seconds == None:
        return metric

    # Initialize track state subdict if it doesn't exist
    if "track_state" not in state:
        state["track_state"] = {}

    # Clean up stale tracks (not seen for 60 seconds)
    cleanup_stale_tracks(current_seconds, state["track_state"], 60)

    # Get the time in area for this track ID
    time_in_area = get_time_in_area_seconds(track_id, current_seconds, state["track_state"])

    # Create a new metric with duration calculated name (before adding fields)
    duration_metric = deepcopy(metric)
    duration_metric.name = "detection_frame_with_duration"

    # Add the time in area to the new metric (filtering happens in next processor)
    duration_metric.fields["time_in_area_seconds"] = time_in_area

    # Return the new metric with the time in area added
    return duration_metric
