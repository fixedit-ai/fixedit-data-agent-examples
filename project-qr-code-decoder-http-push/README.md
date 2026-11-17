# HTTP Push for the FixedIT QR Code Decoder

This example uses the [FixedIT Data Agent](https://fixedit.ai/products-data-agent/) to consume QR or barcode detections from the FixedIT QR Code Decoder ACAP application and push them to an HTTP endpoint.

## How It Works

The FixedIT QR Code Decoder ACAP application has the capability to write each detected code as a JSON message to a Unix domain socket. We make use of this in the FixedIT Data Agent and uses the `inputs.socket_listener` plugin to read the messages from the socket.

The messages are then pushed to an HTTP endpoint using the `outputs.http` plugin.

## Compatibility

### AXIS OS Compatibility

- **Minimum AXIS OS version**: AXIS OS 10.9 or newer.
- **Required tools**: `sh`, `hostname` and `tr`, which are included in AXIS OS. They are used to read the camera's IP addresses.

### FixedIT Data Agent Compatibility

- **Minimum Data Agent version**: 1.2.0
- **Required features**:
  - `inputs.socket_listener` with the `json_v2` parser, to read the detections from the FixedIT QR Code Decoder.
  - `inputs.exec` and `processors.starlark`, to add the camera's IP addresses to each detection as the `local_ip_addresses` tag.
  - `outputs.http`, added in v1.2.0, to push the detections to your server.
  - Custom environment variables, such as `PUSH_URL`, set in the Extra Telegraf Variables section.
- **Other notes**: requires a version of the FixedIT QR Code Decoder with the socket writer enabled.

## Quick Setup

1. **Configure FixedIT Data Agent variables:**

   Configure the parameter `PUSH_URL` to the URL of the HTTP endpoint to which to push the messages. The custom environment variable should be set in the `Extra env` parameter:

   ```txt
   PUSH_URL=http://my.server.com:8080/api/v1/metrics
   ```

2. **Disable the bundled configuration files:**

   Disable the bundled configuration files by going to the `Configuration` tab in the FixedIT Data Agent and clicking the `Disable` button next to the `Bundled config files` section.

3. **Upload the `combined.conf` file to the FixedIT Data Agent**

4. **Enable the `combined.conf` configuration file**

   Enable the `combined.conf` configuration file by clicking the `Enable` button next to the `combined.conf` file.

5. **Make sure the FixedIT QR Code Decoder ACAP application is installed and running**

For more detailed instructions, please refer to the [QUICKSTART_GUIDE.md](./QUICKSTART_GUIDE.md) file.

## Configuration

The full configuration is defined in the `combined.conf` file. It contains the following sections:

- `[agent]`: Global configuration for the Telegraf agent.
- `[global_tags]`: Global tags applied to all metrics.
- `[[inputs.socket_listener]]`: The input configuration for the socket listener.
- `[[outputs.http]]`: The output configuration for the HTTP endpoint.

## Output format

A full specification of the output format is available in the [API_SPEC.md](./API_SPEC.md) file.
