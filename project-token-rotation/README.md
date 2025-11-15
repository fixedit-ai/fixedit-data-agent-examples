# Example of token rotation for the FixedIT Data Agent

When sending data to the cloud from the FixedIT Data Agent we might want to use token rotation so that any specific token is not used for too long.

## Parts of the project

- `test_scripts/example_server.py`: Example server that receives data from the FixedIT Data Agent and shows it in the terminal. This server will also be responsible for creating new tokens.
- `inputs.conf`: Telegraf config for creation of data.
- `output.conf`: Telegraf config for sending data to the example server.
- `*.sh`: Helper scripts for the FixedIT Data Agent.

## Authentication flow

From the start, all devices share a bootstrapping key. The first time a new device connects to the server, it will be issued a new token. After this, the bootstrap token will no longer be accepted by the server for this particular device.

The device has a workflow that will request the latest active token from the server's `/generate-token` endpoint every 5 seconds. The workflow will then save this token to the `${HELPER_FILES_DIR}/token.txt` file.

All the workflows in the device that are pushing data to the server will make use of the `send_metrics.sh` script which will read the token from the `${HELPER_FILES_DIR}/token.txt` file and use it to authenticate the request.
