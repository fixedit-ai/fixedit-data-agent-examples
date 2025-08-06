# Timelapse with AWS S3 Upload

This project demonstrates how to create automated timelapse videos using the [FixedIT Data Agent](https://fixedit.ai/products-data-agent/) by capturing images from an AXIS device and uploading them to AWS S3. The solution creates a time-series collection of images that can be used to generate timelapse videos or for long-term storage and analysis. This approach is perfect for construction sites, environmental monitoring, safety applications, or any scenario requiring periodic visual documentation.

## How It Works

The system captures images at regular intervals and uploads them to AWS S3 with timestamped filenames, creating a chronological sequence perfect for timelapse generation. Images are encoded as base64 strings within JSON files due to the Telegraf data format limitations. Telegraf does not generally support binary data, so base64 encoding is used as a workaround. The [remotefile](https://github.com/influxdata/telegraf/blob/master/plugins/outputs/remotefile/README.md) plugin only supports structured data, therefore the files are saved as json files with the base64 encoded image in them.

```mermaid
flowchart TD
    A["📷 AXIS Device<br/>Capture image via VAPIX"] --> B["🔄 Process<br/>Encode as base64"]
    B --> C["☁️ AWS S3<br/>Upload with timestamp"]
    C --> D["⏳ Wait<br/>Sleep for interval"]
    D --> A

    style A fill:#e1f5fe
    style B fill:#f3e5f5
    style C fill:#e8f5e8
    style D fill:#f1f8e9
```

## Why Choose This Approach?

**No C/C++ development required!** This solution leverages the FixedIT Data Agent's built-in capabilities to create a sophisticated timelapse system without traditional embedded programming. Instead of developing a custom ACAP application, you can achieve the same result using familiar IT tools:

- **Configuration-based setup**: Uses Telegraf configuration files instead of compiled code
- **Shell script integration**: Leverages existing VAPIX APIs through simple shell scripts
- **Cloud-native storage**: Direct integration with AWS S3 for scalable, reliable storage
- **Flexible scheduling**: Easy to adjust capture intervals and timing parameters
- **Extensible foundation**: Can be expanded with custom logic for filtering based on time, object detection, or other criteria

This approach makes timelapse functionality accessible to system integrators and IT professionals who may not have embedded development experience but are comfortable with cloud services and configuration management. The solution provides unprecedented customization capabilities not available in other timelapse software for AXIS cameras.

## Table of Contents

- [Timelapse with AWS S3 Upload](#timelapse-with-aws-s3-upload)
- [How It Works](#how-it-works)
- [Why Choose This Approach?](#why-choose-this-approach)
- [Compatibility](#compatibility)
  - [AXIS OS Compatibility](#axis-os-compatibility)
  - [FixedIT Data Agent Compatibility](#fixedit-data-agent-compatibility)
- [Quick Setup](#quick-setup)
- [Troubleshooting](#troubleshooting)
- [Files](#files)
- [Configuration Details](#configuration-details)
- [Local Testing on Host](#local-testing-on-host)
  - [Prerequisites](#prerequisites)
  - [Host Testing Limitations](#host-testing-limitations)
  - [Test Commands](#test-commands)

## Compatibility

### AXIS OS Compatibility

- **Minimum AXIS OS version**: Should be compatible with AXIS OS 11 and 12+.
- **Required tools**: Uses `jq` which was not available in older AXIS OS versions, but could easily be changed to not depend on it. Uses `curl` and `openssl` which are installed by default.
- **Authentication**: Uses HTTP to localhost with DIGEST authentication which is supported by all AXIS OS versions.

### FixedIT Data Agent Compatibility

- **Minimum Data Agent version**: 1.0
- **Required features**: Uses the `input.exec` and `output.remotefile` plugins. Uses the `TELEGRAF_DEBUG`, `HELPER_FILES_DIR` and `DEVICE_PROP_SERIAL` environment variables which are available in all FixedIT Data Agent versions.

## Quick Setup

1. **Configure FixedIT Data Agent variables:**

   Set the following environment variables in the `Extra env` parameter as a semicolon-separated list:

   ```txt
   VAPIX_USER=your_vapix_username;VAPIX_PASS=your_vapix_password;AWS_ACCESS_KEY_ID=your_aws_access_key;AWS_SECRET_ACCESS_KEY=your_aws_secret_key;AWS_REGION=your_aws_region;S3_BUCKET=your_timelapse_bucket;CAPTURE_INTERVAL_SEC=300
   ```

   **Required variables:**
   - `VAPIX_USER` / `VAPIX_PASS`: Camera authentication credentials
   - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`: AWS credentials for S3 access
   - `AWS_REGION`: AWS region (depends on your S3 bucket setup)
   - `S3_BUCKET`: Target S3 bucket name
   - `CAPTURE_INTERVAL_SEC`: Image capture interval in seconds (default: 300 = 5 minutes)

   **Optional variables:**
   - `RESOLUTION`: Image resolution (optional - if not set, camera default will be used)
   - `CAMERA_IP`: Camera IP address for image capture (optional - if not set, `localhost` will be used)

2. **Upload the files to the FixedIT Data Agent**

   Upload all configuration files and scripts to your FixedIT Data Agent instance.

3. **Enable the configuration files**

   The system will begin capturing images at the specified interval and uploading them to your S3 bucket with timestamped filenames.

### Troubleshooting

Enable the `Debug` option in the FixedIT Data Agent for detailed logs. Debug files will appear in the `Uploaded helper files` section (refresh page to see updates).

**No files are being uploaded:**

Since the upload happens asynchronously, there is no status available on successful or failed uploads in the `remotefile` plugin. You can enable debug mode which will show logs about "wrote metric", but that just means that the `remotefile` plugin has cached it locally and scheduled it for upload. If the upload fails, it is not visible in the logs.

Upload failures could be due to:

- **Invalid AWS credentials**: Check that your `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are correct
- **Incorrect bucket name**: Verify that your `S3_BUCKET` parameter matches an existing S3 bucket
- **Wrong AWS region**: Ensure your `AWS_REGION` parameter matches the region where your S3 bucket is located
- **Network connectivity issues**: The device may not have internet access or firewall rules may be blocking S3 connections
- **S3 bucket permissions**: Your AWS credentials may not have the necessary permissions to write to the specified bucket

**Note**: Don't leave debug enabled long-term as it creates large log files.

## Files

- `timelapse-to-s3.conf` - Complete Telegraf configuration combining all components
- `axis_image_consumer.sh` - Image capture script using VAPIX API
- `test_scripts/` - Testing and viewing tools (see <test_scripts/README.md>)

## Configuration Details

### Image Capture Process

1. **Exec Input Plugin**: Runs `axis_image_consumer.sh` at specified intervals
2. **Image Processing**: Script fetches JPEG from camera's VAPIX API and encodes as base64
3. **JSON Output**: Creates structured JSON with image data and metadata
4. **S3 Upload**: remotefile plugin uploads each image as individual JSON file

### AWS S3 Integration

- **File Naming**: Uses template `DEVICE_SERIAL/YYYY-MM-DD/timelapse-HH-MM-SS.json`
- **Data Format**: JSON with base64-encoded image and metadata
- **Access Control**: Uses AWS IAM credentials for authentication

### Output File Format

Each uploaded file contains a JSON object with the following structure:

```json
{
  "fields": {
    "image_base64": "/9j/4AAQSkZJRgABAQAAAQABA...",
    "length": 182812
  },
  "tags": {
    "host": "device-hostname"
  },
  "timestamp": 1691328000000000000
}
```

**Fields:**

- `image_base64`: Base64-encoded JPEG image data (starts with `/9j/` for JPEG)
- `length`: Size of the base64-encoded image data in characters
- `timestamp`: Unix timestamp in nanoseconds when the image was captured

### S3 Bucket Structure

The timelapse images are organized in the S3 bucket with the following structure:

```
s3://your-timelapse-bucket/
├── DEVICE_SERIAL_001/
│   ├── 2025-08-06/
│   │   ├── timelapse-10-38-33.json
│   │   ├── timelapse-10-38-37.json
│   │   ├── timelapse-10-38-42.json
│   │   └── ...
│   ├── 2025-08-07/
│   │   ├── timelapse-09-15-30.json
│   │   └── ...
│   └── ...
├── DEVICE_SERIAL_002/
│   ├── 2025-08-06/
│   │   └── ...
│   └── ...
└── ...
```

## Local Testing on Host

You can test this project locally using Telegraf before deploying to your AXIS device.

### Prerequisites

- Install Telegraf on your development machine
- Access to an S3 bucket for testing
- Network access to an AXIS device for image capture

### Host Testing Limitations

Everything works on host, you just need network access to a camera to capture the frames.

### Test Commands

First, set up the environment variables:

```bash
# Required variables (must be configured)
export VAPIX_USER="your_vapix_username"
export VAPIX_PASS="your_vapix_password"
export CAMERA_IP="your.camera.ip"

export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export AWS_REGION="your_aws_region"
export S3_BUCKET="your_timelapse_bucket"

# Set the directory where the shell script is located.
export HELPER_FILES_DIR="$(pwd)"

# Set the capture interval in seconds.
export CAPTURE_INTERVAL_SEC="60"

# Set image resolution (optional - if not set, camera default will be used)
export RESOLUTION="1920x1080"

# Enable debug mode (optional)
export TELEGRAF_DEBUG="true"
```

Then run the test:

```bash
# Test configuration
telegraf --config timelapse-to-s3.conf --test

# Run once to capture and upload a single image
telegraf --config timelapse-to-s3.conf --once

# Run continuously (use Ctrl+C to stop)
telegraf --config timelapse-to-s3.conf
```

### Viewing Timelapses

After uploading images to S3, you can view them using the timelapse viewer in the `test_scripts/` directory:

```bash
cd test_scripts
pip install -r requirements.txt
python timelapse_viewer.py view --bucket your-bucket --device <DEVICE_SERIAL> --fps 10
```

Run `python timelapse_viewer.py --help` for detailed usage information.
