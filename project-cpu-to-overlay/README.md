# CPU Usage on Overlay

This project demonstrates how to monitor CPU usage on an AXIS device using the [FixedIT Data Agent](https://fixedit.ai/products-data-agent).

Telegraf collects the device's total CPU usage and makes the value available in the FixedIT Data Agent logs. The CPU usage is also displayed as a dynamic overlay on the camera's video stream, using VAPIX to update the overlay text.

The solution provides a simple way to monitor CPU usage directly on the camera without requiring custom ACAP development.

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
6. Go to the camera's Video->Overlays tab and add a new "Linegraph" overlay widget, configure it to use `#D0` as data source.
   To use another modifier, for example `#D2`, add `OVERLAY_TEMPLATE_ID=2` under "Extra Telegraf variables" in Configuration->Variables, and use `#D2` as the data source. Write the number only, `2`, not `#D2`.

![Linegraph overlay widget](.images/cpu-overlay.png)

## Files

## Configuration Details
