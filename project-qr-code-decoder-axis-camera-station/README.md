# AXIS Camera Station Integration for the FixedIT QR Code Decoder

This example uses the [FixedIT Data Agent](https://fixedit.ai/products-data-agent/) to consume QR or barcode detections from the FixedIT QR Code Decoder ACAP application and push them to the external data sources in the AXIS Camera Station VMS.

## How It Works

The FixedIT QR Code Decoder ACAP application has the capability to write each detected code as a JSON message to a Unix domain socket. We make use of this in the FixedIT Data Agent and uses the `inputs.socket_listener` plugin to read the messages from the socket.

TODO

### AXIS OS Compatibility

- **Minimum AXIS OS version**: Any version of AXIS OS that supports the FixedIT QR Code Decoder ACAP application and the FixedIT Data Agent.
- **Commands used**: TODO

### FixedIT Data Agent Compatibility

- **Minimum Data Agent version**: Any version.

## Quick Setup

TODO

## Configuration

TODO
