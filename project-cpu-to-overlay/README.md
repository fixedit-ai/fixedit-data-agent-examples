# CPU Usage on Overlay

This project demonstrates how to monitor CPU usage on an AXIS device using the [FixedIT Data Agent](https://fixedit.ai/products-data-agent).

Telegraf collects the device's total CPU usage and makes the value available in the FixedIT Data Agent logs. The CPU usage is also displayed as a dynamic overlay on the camera's video stream, using VAPIX to update the overlay text.

The solution provides a simple way to monitor CPU usage directly on the camera without requiring custom ACAP development.S

1. Disable the bundled configuration files under Configuration->Files.
2. Upload and enable all `.conf` files under Configuration->Files by pressing the "Upload Config" button and then "Enable" next to the uploaded file.
3. Upload `set_overlay_text.sh` by pressing the "Upload helper file" button and mark it as "Make Executable".
4. Unselect the "Clear all values" slider under the "VAPIX credentials" section and input the username and password of a VAPIX account that has at least operator access.
5. Verify that you see blue lines in the "Logs" tab with the current CPU usage.
6. Go to the camera's Video->Overlays tab and add a new "Linegraph" overlay widget, configure it to use `#D1` as data source.

![Linegraph overlay widget](.images/cpu-overlay.png)
