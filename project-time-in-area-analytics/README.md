# Time-in-Area Analytics

This project demonstrates how to implement time-in-area analytics for Axis fisheye cameras using the [FixedIT Data Agent](https://fixedit.ai/products-data-agent/). While AXIS Object Analytics natively supports time-in-area detection for traditional cameras, fisheye cameras lack this capability. This solution bridges that gap by consuming real-time object detection metadata from fisheye cameras and implementing custom time-in-area logic using Telegraf's Starlark processor. The system uses object tracking IDs from [AXIS Scene Metadata](https://developer.axis.com/analytics/axis-scene-metadata/reference/concepts/) to track objects within a defined rectangular area, measures time in area, and triggers both warning (TODO) and alert notifications via MQTT (TODO) when objects remain in the monitored zone beyond configured thresholds.

## How It Works

The system consumes real-time object detection data from Axis fisheye cameras and implements custom time-in-area analytics logic to track object time in area and trigger appropriate responses.

```mermaid
flowchart TD
    A["📹 config_input_scene_detections.conf:<br/>Consume analytics scene description from the camera using the inputs.execd plugin and axis_scene_detection_consumer.sh"] -->|detection_frame| B["Filter by area & type (TODO)"]
    X0["Configuration variables: HELPER_FILES_DIR"] --> A
    X1["Configuration variables: TODO"] --> B
    B -->|detection_frame| C1

    subgraph TimeLogic ["config_process_track_duration.conf:<br/>Time-in-area Logic Details"]
        C1{"First time seeing<br/>this object ID?"}
        C1 -->|Yes| C2["Save first timestamp<br/>object_id → now()"] --> C4
        C1 -->|No| C3["Get saved timestamp"]
        C3 --> C4["Calculate time diff<br/>now() - first_timestamp"]
        C4 --> C5["Append time in area<br/>to metric"]

        C2 --> CX["💾 Persistent state"]
        CX --> C3
    end

    C5 -->|detection_frame| D["config_process_threshold_filter.conf:<br/>Filter for<br/>time in area > ALERT_THRESHOLD_SECONDS"]
    X2["Configuration variables: ALERT_THRESHOLD_SECONDS"] --> D

    D -->|alerting_frame| E["🚨 MQTT Output<br/>Alert messages (TODO)"]
    X3["Configuration variables: TODO"] --> E

    D -->|alerting_frame| E1["config_process_rate_limit.conf:<br/>Rate limit to 1 message per second<br/>using Starlark state"]
    E1 -->|rate_limited_alert_frame| F["config_process_overlay_transform.conf:<br/>Recalculate coordinates for overlay visualization"]
    F -->|overlay_frame| G["📺 config_output_overlay.conf:<br/>Overlay Manager with the outputs.exec plugin and overlay_manager.sh"]
    X4["Configuration variables:<br/>VAPIX_USERNAME<br/>VAPIX_PASSWORD<br/>HELPER_FILES_DIR<br/>VAPIX_IP<br/>TELEGRAF_DEBUG<br/>FONT_SIZE"] --> G
    G --> H["📺 VAPIX Overlay API"]

    style A fill:#e8f5e9,stroke:#43a047
    style B fill:#f3e5f5,stroke:#8e24aa
    style TimeLogic fill:#f3e5f5,stroke:#8e24aa
    style C1 fill:#ffffff,stroke:#673ab7
    style C2 fill:#ffffff,stroke:#673ab7
    style C3 fill:#ffffff,stroke:#673ab7
    style C4 fill:#ffffff,stroke:#673ab7
    style C5 fill:#ffffff,stroke:#673ab7
    style CX fill:#fff3e0,stroke:#fb8c00
    style D fill:#f3e5f5,stroke:#8e24aa
    style E fill:#ffebee,stroke:#e53935
    style E1 fill:#f3e5f5,stroke:#8e24aa
    style F fill:#f3e5f5,stroke:#8e24aa
    style G fill:#ffebee,stroke:#e53935
    style H fill:#ffebee,stroke:#e53935
    style X0 fill:#f5f5f5,stroke:#9e9e9e
    style X1 fill:#f5f5f5,stroke:#9e9e9e
    style X2 fill:#f5f5f5,stroke:#9e9e9e
    style X3 fill:#f5f5f5,stroke:#9e9e9e
    style X4 fill:#f5f5f5,stroke:#9e9e9e
```

Color scheme:

- Light green: Input nodes / data ingestion
- Purple: Processing nodes / data processing and logic
- Orange: Storage nodes / persistent data
- Red: Output nodes / notifications
- Light gray: Configuration data
- White: Logical operations

## Why Choose This Approach?

**No C/C++ development required!** This project demonstrates how to implement advanced analytics that would typically require custom ACAP development using the [FixedIT Data Agent](https://fixedit.ai/products-data-agent/) instead. Rather than writing complex embedded C++ code for fisheye camera analytics, system integrators and IT professionals can implement sophisticated time-in-area logic using familiar configuration files and simple scripting. The solution leverages existing object detection capabilities from AXIS Object Analytics and adds the missing time-in-area functionality through data processing pipelines, making it accessible to teams without embedded development expertise.

## Table of Contents

<!-- toc -->

- [Compatibility](#compatibility)
  - [AXIS OS Compatibility](#axis-os-compatibility)
  - [FixedIT Data Agent Compatibility](#fixedit-data-agent-compatibility)
- [Quick Setup](#quick-setup)
  - [TODO](#todo)
  - [Troubleshooting](#troubleshooting)
    - [Make sure AXIS Object Analytics is enabled](#make-sure-axis-object-analytics-is-enabled)
    - [Verbose Logging](#verbose-logging)
    - [Gradual Testing](#gradual-testing)
    - [Unresolved variable errors](#unresolved-variable-errors)
    - ["Text area is too big!" in overlay](#text-area-is-too-big-in-overlay)
- [Configuration Files](#configuration-files)
  - [config_input_scene_detections.conf and axis_scene_detection_consumer.sh](#config_input_scene_detectionsconf-and-axis_scene_detection_consumersh)
  - [config_process_track_duration.conf and track_duration_calculator.star](#config_process_track_durationconf-and-track_duration_calculatorstar)
  - [config_process_threshold_filter.conf](#config_process_threshold_filterconf)
  - [config_process_rate_limit.conf](#config_process_rate_limitconf)
  - [config_process_overlay_transform.conf](#config_process_overlay_transformconf)
  - [config_output_overlay.conf and overlay_manager.sh](#config_output_overlayconf-and-overlay_managersh)
  - [test_files/config_output_stdout.conf](#test_filesconfig_output_stdoutconf)
  - [test_files/sample_data_feeder.sh](#test_filessample_data_feedersh)
- [Future Enhancements](#future-enhancements)
- [Local Testing on Host](#local-testing-on-host)
  - [Prerequisites](#prerequisites)
  - [Host Testing Limitations](#host-testing-limitations)
  - [Test Commands](#test-commands)
    - [Test Time in Area Calculation Only](#test-time-in-area-calculation-only)
    - [Test Alert Pipeline](#test-alert-pipeline)
    - [Test Alert Pipeline with Rate Limit](#test-alert-pipeline-with-rate-limit)
    - [Test with Real Device Data](#test-with-real-device-data)
    - [Test Overlay Functionality Only](#test-overlay-functionality-only)
- [Analytics Data Structure](#analytics-data-structure)
  - [Raw Analytics Data (from camera)](#raw-analytics-data-from-camera)
  - [Data Transformed for Telegraf](#data-transformed-for-telegraf)
  - [Data Transformed for Overlay](#data-transformed-for-overlay)
- [Recording Real Device Data](#recording-real-device-data)
- [Track Activity Visualization](#track-activity-visualization)
- [Automated Testing](#automated-testing)
  - [GitHub Workflow](#github-workflow)
  - [Test Data](#test-data)
  - [PR Comments](#pr-comments)

<!-- tocstop -->

## Compatibility

### AXIS OS Compatibility

- **Minimum AXIS OS version**: AXIS OS 12+
- **Required tools**: Uses `message-broker-cli` which was not stable before AXIS OS 12. Uses `jq` for JSON processing which was not available in older AXIS OS versions, `sed` for text filtering, and standard Unix utilities (`sh`). Uses the analytics scene description message broker topic `com.axis.analytics_scene_description.v0.beta` which is available in AXIS OS 12.

### FixedIT Data Agent Compatibility

- **Minimum Data Agent version**: 1.1
- **Required features**: Uses the `inputs.execd`, `processors.starlark` plugins and the `HELPER_FILES_DIR` environment variable set by the FixedIT Data Agent. It is recommended to use version 1.1 or higher since the load order of config files was not visible in the web user interface in version 1.0.

## Quick Setup

### TODO

Create a combined file by running:

```bash
cat config_input_scene_detections.conf \
    config_process_track_duration.conf \
    config_process_threshold_filter.conf \
    config_process_rate_limit.conf \
    config_process_overlay_transform.conf \
    config_output_overlay.conf > combined.conf
```

Then upload `combined.conf` as a config file and `overlay_manager.sh`, `axis_scene_detection_consumer.sh` and `track_duration_calculator.star` as helper files.

Set `Extra Env` to `ALERT_THRESHOLD_SECONDS=30` and set valid credentials in the parameters `Vapix username` and `Vapix password`.

### Troubleshooting

#### Make sure AXIS Object Analytics is enabled

This project is making use of scene detection data from AXIS Object Analytics. Make sure the AXIS Object Analytics app is running in the camera. You can go to the `Analytics` -> `Metadata visualization` page and verify that there are actual detections.

#### Verbose Logging

Enable the `Debug` option in the FixedIT Data Agent for detailed logs. Debug files will appear in the `Uploaded helper files` section (refresh page to see updates).

**Note**: Don't leave debug enabled long-term as it creates large log files.

#### Gradual Testing

You can test the logic gradually in the camera by adding more and more complexity:

1. **Basic Detection**: Upload `config_input_scene_detections.conf`, `axis_scene_detection_consumer.sh` and `config_output_stdout.conf` to see if the camera is sending out detection messages

   ![Camera Detections Configuration](.images/camera-detections-config.png)
   _Configuration files uploaded to the camera_

   ![Camera Detections Log](.images/camera-detections.png)
   _Log messages showing detection data from the camera_

2. **Time Calculation**: Upload `config_process_track_duration.conf` and `track_duration_calculator.star` to see if the time in area is calculated correctly
3. **Threshold Filtering**: Upload `config_process_threshold_filter.conf` to see if the threshold filter is working correctly
4. **Rate Limiting**: Upload `config_process_rate_limit.conf` to protect the overlay API from being overloaded
5. **Overlay Display**: Finally, upload `config_process_overlay_transform.conf` and `config_output_overlay.conf` to draw the overlays on the live video

#### Unresolved variable errors

If you see an error like this:

```
[2025-08-20 11:43:40] 2025-08-20T09:43:40Z E! [telegraf] Error running agent: could not initialize processor processors.starlark: :6:23: unexpected input character '$'
```

It usually means an environment variable (like `ALERT_THRESHOLD_SECONDS`) is not set correctly as an `Extra Env` variable.

#### "Text area is too big!" in overlay

If the only text you see in the overlay is "Text area is too big!", it means that too much text is being rendered or that the text size is too big. Try reducing the font size by setting `FONT_SIZE=32` in the `Extra Env` variable.

## Configuration Files

This project uses several configuration files that work together to create a time-in-area analytics pipeline:

### config_input_scene_detections.conf and axis_scene_detection_consumer.sh

Configuration and script pair that work together to consume real-time object detection data from the camera's analytics scene description stream. The configuration file (`config_input_scene_detections.conf`) uses the consumer script (`axis_scene_detection_consumer.sh`) to connect directly to the camera's internal message broker and transform the raw analytics data into individual detection messages.

Can also be used for reproducible testing on host systems by setting `CONSUMER_SCRIPT="test_files/sample_data_feeder.sh"` to use a file reader that simulates the camera's detection data output. This allows you to test the processing pipeline using pre-recorded sample data without needing live camera hardware.

**Environment Variables:**

- `HELPER_FILES_DIR`: Directory containing project files (required)
- `CONSUMER_SCRIPT`: Path to consumer script (defaults to `axis_scene_detection_consumer.sh`)
- `SAMPLE_FILE`: Path to sample data file (required when using `sample_data_feeder.sh`)

### config_process_track_duration.conf and track_duration_calculator.star

Calculates time in area for each detected object using the external Starlark script `track_duration_calculator.star`. This processor:

- Tracks first seen and last seen timestamps for each `track_id`
- Calculates `time_in_area_seconds` for each detection
- Automatically cleans up stale tracks (not seen for 60+ seconds)
- Outputs debug messages when tracks are removed

### config_process_threshold_filter.conf

Filters detection frames based on the configured alert threshold. Only detections where time in area (`time_in_area_seconds`) exceeds `ALERT_THRESHOLD_SECONDS` are passed through to the output stage.

### config_process_rate_limit.conf

Rate limits messages to protect the overlay API from being overloaded. This processor:

- Uses system time (not message timestamps) to enforce rate limiting
- Only allows one message per second to pass through
- Drops messages that arrive too soon after the last one
- Maintains state using Starlark to track the last update time

### config_process_overlay_transform.conf

Transforms analytics data into the format expected by the overlay manager (e.g. center coordinates in -1 ... 1 range and box size).

### config_output_overlay.conf and overlay_manager.sh

Displays text overlays on the video. This configuration:

- Uses Telegraf's exec output plugin to trigger the `overlay_manager.sh` script
- Shows overlay text at the center of detected objects using the VAPIX overlay API
- Displays time in area, object class, and size information
- Positions overlays using pre-calculated coordinates from the Starlark processor
- Automatically removes overlays after 1 second for clean video display

### test_files/config_output_stdout.conf

Outputs processed metrics to stdout in JSON format for testing and debugging.

### test_files/sample_data_feeder.sh

Helper script that simulates camera metadata stream by reading sample JSON files line by line. This script is used for host testing to simulate the output of the live camera's message broker without requiring actual camera hardware.

## Future Enhancements

This example should implement a minimal viable solution and can be easily extended:

- **Warning Threshold**: Add a warning level before the main alert threshold
- **Deactivation Messages**: Send alerts when objects leave the area after being alerted
- **Time-of-Day Rules**: Apply different thresholds based on time of day
- **Multiple Areas**: Monitor multiple rectangular areas with different configurations
- **Advanced Shapes**: Implement polygon-based areas instead of simple rectangles

## Local Testing on Host

You can test the processing logic locally using Telegraf before deploying to your Axis device.

### Prerequisites

- Install Telegraf on your development machine
- Local MQTT broker (mosquitto) for testing output
- Sample object detection JSON data for testing

### Host Testing Limitations

**Works on Host:**

- Starlark processor logic testing with sample data
- MQTT output configuration validation (TODO)
- Alert threshold configuration testing

**Only works in the Axis Device:**

- Real object detection metadata consumption (camera-specific message broker) - in host testing, you can use the `sample_data_feeder.sh` script to simulate the camera metadata stream using pre-recorded data in the `test_files/simple_tracks.jsonl` or `test_files/real_device_data.jsonl` files.
- The VAPIX overlay API requires direct access to the Axis device and cannot be tested on host systems.

### Test Commands

#### Test Time in Area Calculation Only

Test the time in area calculator without threshold filtering to see all detections with their calculated time in area:

```bash
# Set up test environment
export HELPER_FILES_DIR="$(pwd)"
export CONSUMER_SCRIPT="test_files/sample_data_feeder.sh"
export SAMPLE_FILE="test_files/simple_tracks.jsonl"

# Test time in area calculation only (shows all detections + debug messages)
telegraf --config config_input_scene_detections.conf \
         --config config_process_track_duration.conf \
         --config test_files/config_output_stdout.conf \
         --once
```

**How it works:** By setting `CONSUMER_SCRIPT="test_files/sample_data_feeder.sh"`, we override the default live camera script with a file reader that simulates the camera's message broker output by reading from the file specified in `SAMPLE_FILE`. This allows us to test the processing pipeline on the host using pre-recorded sample data instead of connecting to the live camera infrastructure.

**Expected Output:**
All detections with `time_in_area_seconds` field.

Example output:

```json
{
  "fields": {
    "bounding_box_bottom": 0.62,
    "bounding_box_left": 0.22,
    "bounding_box_right": 0.32,
    "bounding_box_top": 0.42,
    "frame": "2024-01-15T10:00:02.789012Z",
    "object_type": "Human",
    "timestamp": "2024-01-15T10:00:02.789012Z",
    "track_id": "track_001",
    "time_in_area_seconds": 1.67
  },
  "name": "detection_frame",
  "tags": { "host": "test-host" },
  "timestamp": 1755677033
}
```

The `time_in_area_seconds` field is added by the time-in-area processor, showing how long this object has been tracked in the monitored area.

#### Test Alert Pipeline

Test the alert generation pipeline with threshold filtering:

```bash
# Set up test environment
export HELPER_FILES_DIR="$(pwd)"
export CONSUMER_SCRIPT="test_files/sample_data_feeder.sh"
export SAMPLE_FILE="test_files/simple_tracks.jsonl"
export ALERT_THRESHOLD_SECONDS="2"  # Alert threshold in seconds

# Test time in area calculation + threshold filtering
telegraf --config config_input_scene_detections.conf \
         --config config_process_track_duration.conf \
         --config config_process_threshold_filter.conf \
         --config test_files/config_output_stdout.conf \
         --once
```

**How it works:** Same as above - we use the file reader script to simulate camera data on the host by reading from the file specified in `SAMPLE_FILE`, allowing us to test the complete pipeline including threshold filtering without needing live camera hardware.

**Expected Output:**
Only detections with time in area (`time_in_area_seconds`) > `ALERT_THRESHOLD_SECONDS`.

#### Test Alert Pipeline with Rate Limit

Test the complete pipeline including threshold filtering and rate limiting for overlay protection:

```bash
# Set up test environment
export HELPER_FILES_DIR="$(pwd)"
export CONSUMER_SCRIPT="test_files/sample_data_feeder.sh"
export SAMPLE_FILE="test_files/simple_tracks.jsonl"
export ALERT_THRESHOLD_SECONDS="2"  # Alert threshold in seconds

# Test complete pipeline with rate limiting
telegraf --config config_input_scene_detections.conf \
         --config config_process_track_duration.conf \
         --config config_process_threshold_filter.conf \
         --config config_process_rate_limit.conf \
         --config test_files/config_output_stdout.conf \
         --once
```

**How it works:** Same as the alert pipeline test, but adds the rate limiting processor that ensures no more than one message per second is passed through to protect the overlay API from being overloaded.

**Expected Output:**
Only the first message with a `time_in_area_seconds` > `ALERT_THRESHOLD_SECONDS` is passed through, the other are suppressed.

#### Test with Real Device Data

You can also test with real analytics scene description data recorded from an Axis device:

```bash
# Set up test environment with real device data
export HELPER_FILES_DIR="$(pwd)"
export CONSUMER_SCRIPT="test_files/sample_data_feeder.sh"
export SAMPLE_FILE="test_files/real_device_data.jsonl"

# Test time in area calculation with real data
telegraf --config config_input_scene_detections.conf \
         --config config_process_track_duration.conf \
         --config test_files/config_output_stdout.conf \
         --once
```

**How it works:** We set `CONSUMER_SCRIPT="test_files/sample_data_feeder.sh"` to use a file reader that simulates the camera's message broker output. This allows us to test on the host using pre-recorded real device data instead of connecting to the live camera infrastructure. The `real_device_data.jsonl` file contains actual analytics scene description data recorded from an Axis device, providing realistic testing with real track IDs, timestamps, and object detection patterns.

#### Test Overlay Functionality Only

Test just the overlay functionality with a single detection from a static file. To run this, you need to have access to an Axis device which will show the overlay on the video.

```bash
# Set up camera info
export VAPIX_USERNAME="your-username"
export VAPIX_PASSWORD="your-password"
export VAPIX_IP="your-device-ip"

# Set up test environment for overlay testing only
export HELPER_FILES_DIR="$(pwd)"
export SAMPLE_FILE="test_files/single_overlay_test.jsonl"
export TELEGRAF_DEBUG="true"

# Test overlay functionality with single detection
telegraf --config test_files/config_input_overlay_test.conf \
         --config config_process_overlay_transform.conf \
         --config config_output_overlay.conf \
         --once
```

**How it works:**

1. `config_input_overlay_test.conf` reads a single detection from `single_overlay_test.jsonl`
2. `config_process_overlay_transform.conf` transforms coordinates and standardizes fields
3. `config_output_overlay.conf` receives the transformed data and executes the overlay manager
4. Creates an overlay on the video showing the object information
5. Removes the overlay after 1 second

**Expected Result:** A red text overlay will appear on the video showing:

```
← ID: b1718a5c-0...
  Type: Human
  Time in area: 00:00:52
  Last seen at: 2025-10-13 16:36:55 UTC
```

The overlay text will point at 55% from the left of the video and 76% from the top to the bottom of the video.

## Analytics Data Structure

The analytics data goes through three formats:

### Raw Analytics Data (from camera)

Each line contains a JSON object with this structure:

```json
{
  "frame": {
    "observations": [
      {
        "bounding_box": {
          "bottom": 0.6,
          "left": 0.2,
          "right": 0.3,
          "top": 0.4
        },
        "class": { "type": "Human" },
        "timestamp": "2024-01-15T10:00:01Z",
        "track_id": "track_001"
      }
    ],
    "operations": [],
    "timestamp": "2024-01-15T10:00:01Z"
  }
}
```

- **Sparse Output**: Frames are primarily output when objects are detected, with occasional empty frames
- **Time Gaps**: Periods with no activity result in no output (creating gaps in timestamps)
- **Occasional Empty Frames**: Sporadically output with `"observations": []`, usually for cleanup operations or periodic heartbeats
- **Optional Classification**: The `class` field may be missing from observations, especially for short-lived tracks where classification hasn't completed yet

### Data Transformed for Telegraf

The raw analytics data needs transformation for Telegraf's JSON parser because metrics must be flat - the contained list of detections would cause strange concatenations if parsed directly. Both the `sample_data_feeder.sh` script and the real `axis_metadata_consumer.sh` running on the camera perform this transformation.

**From:** Frame-based format (multiple observations per frame)

```json
{
  "frame": {
    "observations": [
      {"track_id": "track_001", "class": {"type": "Human"}, ...},
      {"track_id": "track_002", "class": {"type": "Human"}, ...}
    ],
    "timestamp": "2024-01-15T10:00:01Z"
  }
}
```

**To:** Individual detection messages (one observation per message, multiple messages per frame)

```json
{
  "name": "detection_frame",
  "fields": {
    "frame": "2024-01-15T10:00:01Z",
    "timestamp": "2024-01-15T10:00:01Z",
    "track_id": "track_001",
    "object_type": "Human",
    "bounding_box_bottom": 0.6,
    "bounding_box_left": 0.2,
    "bounding_box_right": 0.3,
    "bounding_box_top": 0.4
  }
}
{
  "name": "detection_frame",
  "fields": {
    "frame": "2024-01-15T10:00:01Z",
    "timestamp": "2024-01-15T10:00:01Z",
    "track_id": "track_002",
    "object_type": "Human",
    "bounding_box_bottom": 0.58,
    "bounding_box_left": 0.14,
    "bounding_box_right": 0.20,
    "bounding_box_top": 0.38
  }
}
```

This transformation:

- **Splits** nested observations into individual messages
- **Flattens** nested objects automatically (Telegraf's JSON parser adds the parent field name as prefix, e.g., `bounding_box_left`)
- **Simplifies** object classification to just the type
- **Skips** frames with no observations entirely
- **Adds** metric name and fields structure for Telegraf
- **Preserves** string fields like timestamps and IDs

### Data Transformed for Overlay

The `config_process_overlay_transform.conf` processor transforms the `detection_frame` into an `overlay_frame` intended to be more suitable for use with the VAPIX overlay API:

1. **Coordinate Transformation**:
   - Input: `bounding_box_left`, `bounding_box_right`, `bounding_box_top`, `bounding_box_bottom` (range 0.0 to 1.0)
   - Output: `center_x`, `center_y` (range -1.0 to 1.0)

2. **Field Preservation**:
   - Copies `object_type`, `track_id`, `time_in_area_seconds`, and `timestamp`
   - These fields are used for overlay text content

Note that when we draw the overlay text in `overlay_manager.sh`, the coordinate for the text indicates the top-left corner of the text box. This is also where we place the arrow pointing to the object center.

## Recording Real Device Data

You can record real analytics scene description data from your Axis camera for deterministic testing and analysis. This allows you to run the analytics pipeline on your host machine with reproducible results.

```bash
python test_scripts/record_real_data.py --host <device_ip> --username <username>
```

The recorded data works with the track heatmap visualization and other analysis tools. For detailed usage instructions, see the [test_scripts README](test_scripts/README.md).

## Track Activity Visualization

This project includes a track heatmap visualization script that shows when different track IDs are active over time, helping you analyze track patterns and activity density in your data.

```bash
python test_scripts/track_heatmap_viewer.py test_files/simple_tracks.jsonl
```

For installation, usage details, and examples, see the [test_scripts README](test_scripts/README.md).

![Track Heatmap Example](.images/track-heatmap-120s.png)
_Example heatmap showing track activity over time with labeled components (10s alarm threshold)_

## Automated Testing

This project includes comprehensive automated testing to ensure both the visualization script and Telegraf pipeline work correctly and produce consistent results.

### GitHub Workflow

The automated tests run on every push and pull request via the `project-time-in-area-test-analytics.yml` workflow, which includes:

**Two Independent Test Jobs:**

- **Track Heatmap Viewer Tests**: Validates alarm detection in the visualization script
- **Telegraf Pipeline Tests**: Validates time-in-area calculations and threshold filtering

**Three Test Scenarios per Tool:**

- **No alarms scenario**: High threshold (15s) should produce no alarms
- **Some alarms scenario**: Moderate threshold (2s) should identify 3 specific tracks
- **All alarms scenario**: Low threshold (0s) should identify all 4 tracks

Both tools now behave identically, calculating total time-in-area including brief gaps under 60 seconds. If a gap is longer than 60 seconds (should not happen in data from the Axis cameras!?), then the Telegraf pipeline would forget about the track and the time-in-area would be reset to 0 once the track reappears.

### Test Data

The tests use `test_files/simple_tracks.jsonl` which contains simplified track data with:

- `track_001`: Appears twice with 8s gap (total time: 11.33s)
- `track_002`: Continuous presence for 2.22s
- `track_003`: Continuous presence for 2.22s
- `track_004`: Single appearance (0s)
- `track_005`: Long duration track for 2.5 minutes (150s)

![Example data visualized](./.images/track-heatmap-simple.png)

### PR Comments

The workflow automatically posts detailed comments to pull requests with:

- ✅ Success confirmation when all tests pass
- ❌ Specific failure diagnostics and troubleshooting steps when tests fail

This ensures both tools maintain consistent alarm detection behavior and helps catch regressions early in the development process.
