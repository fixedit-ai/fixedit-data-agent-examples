# CPU Usage on Overlay

## How It Works

## Why Choose This Approach?

With the FixedIT Data Agent, you can create your own edge-based workflows and automations that run directly in the Axis devices. You can do this without knowing anything about the Axis [ACAP SDK](https://www.axis.com/for-developers/acap), C and C++ programming. This makes the edge available to a much wider audience of developers, system integrators and IT professionals.

This project shows how to get a value from the device into the video itself. Telegraf reads the CPU usage, and the `exec` output passes it to a small shell script that updates an overlay through the camera's VAPIX API. The same pattern works for any value you can collect with Telegraf, such as memory usage.

## Table Of Contents

## Compatibility

## Quick Setup

1. Disable the bundled configuration files under Configuration->Files.
2. Upload and enable all `.conf` files under Configuration->Files by pressing the "Upload Config" button and then "Enable" next to the uploaded file.
3. Upload `set_overlay_text.sh` by pressing the "Upload helper file" button and mark it as "Make Executable".
4. Unselect the "Clear all values" slider under the "VAPIX credentials" section and input the username and password of a VAPIX account that has at least operator access.
5. Verify that you see blue lines in the "Logs" tab with the current CPU usage.
6. Go to the camera's Video->Overlays tab and add a new "Linegraph" overlay widget, configure it to use `#D1` as data source.

![Linegraph overlay widget](.images/cpu-overlay.png)

## Files

- `config_agent.conf`: Sets the global Telegraf collection and flush intervals.
- `config_input_cpu.conf`: Collects total CPU usage as the `cpu_sample` metric.
- `config_output_logs.conf`: Writes `cpu_sample` metrics to the FixedIT Data Agent logs.
- `config_output_overlay.conf`: Sends `cpu_sample` metrics to the camera overlay by running `set_overlay_text.sh`.
- `set_overlay_text.sh`: Helper script run by `config_output_overlay.conf`; it updates the overlay text through the VAPIX API.

## Configuration Details
