# API Specification for HTTP Push of QR Code Detection Data

The following API specification describes the HTTP API specification for the FixedIT Data Agent when the recommended `outputs.http` plugin is used. The request can be made directly with curl for more flexibility, but due to robustness and ease of maintenance, it is recommended to use the `http` plugin and follow the following specification.

## Table of Contents

<!-- toc -->

- [Basic Specification](#basic-specification)
- [Customization](#customization)
- [Retries](#retries)
- [Payload](#payload)
- [How to test a receiving server](#how-to-test-a-receiving-server)

<!-- tocstop -->

## Basic Specification

The HTTP request uses method `POST` with a JSON payload. The structure of the JSON payload is fixed, but fields can be customized and new tags can be added.

```json
{"fields": {...}, "name": "...", "tags": {...}, "timestamp": ...}
```

The JSON payload is not prettified (it is written on a single line).

`timestamp` describes when the FixedIT Data Agent received the detection from the QR Code Decoder. `name` is a configurable name of the metric. `fields` and `tags` contain information about the camera and the detection.

The headers of the request might look like this:

```text
  Host: <host:port>
  User-Agent: FixedIT-Data-Agent/<version>
  Content-Length: <content-length>
  Content-Type: application/json
  Accept-Encoding: gzip
```

`Host` is the host and port of the server the request was sent to. `User-Agent` is the version of the FixedIT Data Agent but can be customized. `Content-Length` is the length of the request body. `Content-Type` specifies json format, but can technically be customized. `Accept-Encoding` tells the server which content encoding (compression methods) the client can handle for the response body.

## Customization

Each detected QR code will trigger a separate HTTP POST request to the specified URL. This could be changed to send multiple detections in a single request, but is not recommended since it will increase latency.

We can configure the URL used for the request and add custom HTTP headers as needed.

A few different authentication options are supported, including `Basic` authentication (most common). `Digest` authentication is not supported.

## Retries

The FixedIT Data Agent will retry the request if it fails. The FixedIT Data Agent has a buffer internally (size can be configured) and will store the detections in the buffer until the HTTP post gives a 200 OK response. This means that detections will not be lost even if the network is temporarily lost.

This does, however, mean that you should always validate the timestamp of the detection to ensure that it is up-to-date. After a period with lost connectivity, a POST message might arrive for each detection that happened during the lost connectivity period. By limiting the size of the buffer, we can reduce the load on the server after a period with lost connectivity. Minimum size of the buffer is 1.

It's recommended to enable NTP time synchronization in the camera to ensure that the timestamps in the POST message are synchronized with the server's time.

## Payload

The following is an example of the json payload when used together with the QR Code Decoder, but fields and tags can be customized based on requirements.

The prettified JSON payload might look like this:

```json
{
  "fields": {
    "code_type": "QR-Code",
    "decoded_data": "K7mX9pQwR2vL8nF3sA6Y",
    "frame_timestamp": 1760538182,
    "image_height": 2160,
    "image_width": 3840,
    "norm_height": 0.19490742683410645,
    "norm_width": 0.10911458730697632,
    "norm_center_x": 0.2679687440395355,
    "norm_center_y": 0.3162037134170532,
    "number_codes_in_frame": 1
  },
  "name": "barcode_reader_app",
  "tags": {
    "architecture": "armv7hf",
    "area": "Europe",
    "data_agent_start_time": "1760454197",
    "data_agent_version": "1.1.0-rc2",
    "device_brand": "AXIS",
    "device_model": "M3045",
    "device_serial": "TEST123456",
    "device_type": "Dome Camera",
    "device_variant": "48mm",
    "firmware_version": "12.1.54",
    "geography": "Sweden",
    "host": "danielfa-ThinkPad-X1-Carbon-Gen-9",
    "input_method": "socket",
    "latitude": "55.714794",
    "level": "INFO",
    "log_type": "detection",
    "local_ip_addresses": "192.168.1.1,100.101.51.73",
    "longitude": "13.214984",
    "pid": "2474660",
    "product_full_name": "AXIS M3045-LV Dome Camera",
    "region": "Lund",
    "site": "Office",
    "soc": "Axis Artpec-7",
    "source": "BarcodeReader",
    "type": "Gate QR Detection"
  },
  "timestamp": 1760539681
}
```

Field specification:

- `code_type`: Type of code detected (e.g., "QR-Code")
- `decoded_data`: The decoded QR code content
- `frame_timestamp`: Unix timestamp when the QR Code Decoder captured the frame.
- `image_height`: Height of the source image in pixels.
- `image_width`: Width of the source image in pixels.
- `norm_height`: Normalized height of the bounding box (0-1).
- `norm_width`: Normalized width of the bounding box (0-1).
- `norm_center_x`: Normalized x-coordinate of the bounding box center (0-1).
- `norm_center_y`: Normalized y-coordinate of the bounding box center (0-1).
- `number_codes_in_frame`: Total number of codes detected in this frame.

Tag specification:

- Misc tags specified manually in the FixedIT Data Agent configuration (geo information, type tag, etc.)
- Tags set automatically by the FixedIT Data Agent (device information, app information, etc.)
- Tags set when analysing the detections (pid, source, etc.)
- A tag with all local IP addresses of the device, separated by commas. Note that the device will have multiple IP addresses in some cases, e.g. when running a VPN application in the camera.

## How to test a receiving server

The following curl command can be used to create a very similar request to the one sent by the FixedIT Data Agent.

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -H "User-Agent: FixedIT-Data-Agent/1.1.0-rc2" \
  -H "Accept-Encoding: gzip" \
  -H "Accept:" \
  -d '{"fields":{"code_type":"QR-Code","decoded_data":"K7mX9pQwR2vL8nF3sA6Y","frame_timestamp":1760538182,"image_height":2160,"image_width":3840,"norm_height":0.19490742683410645,"norm_width":0.10911458730697632,"norm_center_x":0.2679687440395355,"norm_center_y":0.3162037134170532,"number_codes_in_frame":1},"name":"barcode_reader_app","tags":{"architecture":"armv7hf","area":"Europe","data_agent_start_time":"1760454197","data_agent_version":"1.1.0-rc2","device_brand":"AXIS","device_model":"M3045","device_serial":"TEST123456","device_type":"Dome Camera","device_variant":"48mm","firmware_version":"12.1.54","geography":"Sweden","host":"axis-test123456","input_method":"socket","latitude":"55.714794","level":"INFO","local_ip_addresses":"192.168.1.1,100.101.51.73","log_type":"detection","longitude":"13.214984","pid":"2474660","product_full_name":"AXIS M3045-LV Dome Camera","region":"Lund","site":"Office","soc":"Axis Artpec-7","source":"BarcodeReader","type":"Gate QR Detection"},"timestamp":1760539681}
'
```

This curl command will send the exact same JSON payload structure that the FixedIT Data Agent would send, making it useful for testing your receiving server implementation.
