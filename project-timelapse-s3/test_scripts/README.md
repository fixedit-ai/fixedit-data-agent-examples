# Test Scripts

This directory contains scripts for testing and viewing the timelapse system.

## Timelapse Viewer

The `timelapse_viewer.py` script allows you to view timelapse videos using the images uploaded by the FixedIT Data Agent timelapse system. It fetches the metadata and image files from AWS S3, and displays them as a video or saves them as an MP4 file.

### Use the viewer

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Configure AWS credentials (environment variables, AWS CLI, or IAM roles)

3. View timelapse:
   ```bash
   python timelapse_viewer.py view --bucket <your-bucket> --device <DEVICE_SERIAL> --fps 10
   ```

### Commands

- `list-devices`: List all devices in the bucket
- `list-dates`: List dates available for a device
- `view`: View timelapse video with keyboard controls

Run `python timelapse_viewer.py --help` or `python timelapse_viewer.py <command> --help` for detailed usage information and examples.

### Controls

When viewing a timelapse:

- **Spacebar**: Pause/unpause playback
- **Q**: Quit the viewer
