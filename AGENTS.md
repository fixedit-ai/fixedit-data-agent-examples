# Agent instructions

This file is intended for AI agents who are assisting developers who clone this repository and use it as a starting point to build or adapt FixedIT Data Agent projects.

It explains what this repository is, how the pieces fit together, and how to learn from the existing examples. It does not define pull-request style rules; those live in [.coderabbit.yaml](./.coderabbit.yaml) for contributors who open PRs against this repo.

Human-oriented overview and example links: [README.md](./README.md).

**Official guides**: see [Official learning resources](#official-learning-resources) below.

## Table of Contents

<!-- toc -->

- [What this repository contains](#what-this-repository-contains)
  - [Repository layout](#repository-layout)
  - [How to learn from existing examples](#how-to-learn-from-existing-examples)
- [Axis device environment](#axis-device-environment)
  - [Shell on devices](#shell-on-devices)
- [Components](#components)
  - [FixedIT Data Agent](#fixedit-data-agent)
    - [Live Logs in the Data Agent UI](#live-logs-in-the-data-agent-ui)
    - [Data pipeline (Telegraf model)](#data-pipeline-telegraf-model)
    - [Typical workload categories](#typical-workload-categories)
    - [Common environment variables](#common-environment-variables)
  - [AXIS Scene Metadata](#axis-scene-metadata)
    - [Consume Scene Metadata with Telegraf (FixedIT Data Agent)](#consume-scene-metadata-with-telegraf-fixedit-data-agent)
  - [FixedIT QR Code Decoder ACAP](#fixedit-qr-code-decoder-acap)
    - [Consume QR/barcode detections in the FixedIT Data Agent](#consume-qrbarcode-detections-in-the-fixedit-data-agent)
  - [YOLOv5 object detection ACAP](#yolov5-object-detection-acap)
  - [Telegraf](#telegraf)
  - [Starlark](#starlark)
  - [InfluxDB (server-side)](#influxdb-server-side)
  - [Grafana (server-side)](#grafana-server-side)
- [Host testing with Telegraf](#host-testing-with-telegraf)
  - [Mock and file inputs for host testing](#mock-and-file-inputs-for-host-testing)
- [Common challenges](#common-challenges)
  - [Detecting the absence of a message (“nothing happened”)](#detecting-the-absence-of-a-message-nothing-happened)
  - [Immediate output (no batching delay)](#immediate-output-no-batching-delay)
  - [Preserving event timestamps on metrics](#preserving-event-timestamps-on-metrics)
  - [Adding metadata to metrics with [global_tags]](#adding-metadata-to-metrics-with-global_tags)
  - [Working with raw binary data in metrics by base64 encoding](#working-with-raw-binary-data-in-metrics-by-base64-encoding)
  - [Passing large images between pipeline stages via a Unix socket](#passing-large-images-between-pipeline-stages-via-a-unix-socket)
  - [Viewing pipeline data in the Logs tab](#viewing-pipeline-data-in-the-logs-tab)
- [Example projects in this repo](#example-projects-in-this-repo)
  - [Deploying a project in the Data Agent UI](#deploying-a-project-in-the-data-agent-ui)
- [Official learning resources](#official-learning-resources)
  - [Official product documentation (PDF)](#official-product-documentation-pdf)
  - [Learning articles](#learning-articles)
  - [Frequently asked questions](#frequently-asked-questions)
- [Pull requests to this repository](#pull-requests-to-this-repository)

<!-- tocstop -->

## What this repository contains

This repository holds **example programs and dashboards** for the [FixedIT Data Agent](https://fixedit.ai/products-data-agent/) on Axis devices.

- **`project-*/`** — Edge workflows: Telegraf configuration (`.conf`), optional Starlark scripts (`.star`), portable shell scripts (`.sh`), and documentation. Each project is a self-contained project/tutorial.
- **`dashboard-deployments/`** — **Server-side only** reference stacks (InfluxDB, Grafana, etc.) for visualizing data the agent sends off-device. These do not run on the Axis device.
- **Tests on the host** — Most projects include `test_scripts/` (and sometimes `test_files/` for static test data) so you can run system or unit tests on your development machine using Telegraf installed natively, without an Axis device or a FixedIT Data Agent ACAP installed. Host tests do not replace on-device validation but speed up iteration on processors, Starlark, and data shapes. This works since the FixedIT Data Agent is built on top of Telegraf, but some features implemented in the Data Agent will be missing when running on host and needs to be mocked/stubbed out.

Example projects demonstrate real patterns: Scene Metadata filtering, GitHub API polling, S3 upload, zone analytics, overlays, and more. When starting something new, find the closest existing project, read its README and config layout, then adapt rather than inventing structure from scratch.

Each project should specify the compatibility with the FixedIT Data Agent and the AXIS OS version. Some projects might be more outdated and might do things in a more complex way than necessary. If a project that depends on a newer version of the FixedIT Data Agent is doing something in a simpler way, then that is probably a better approach. People should not be limited to an old version of the FixedIT Data Agent, so it should be safe to assume they run the latest version. Compatibility with AXIS OS is however more complex since some cameras does not support the latest version of AXIS OS.

### Repository layout

| Path                          | Purpose                                                     |
| ----------------------------- | ----------------------------------------------------------- |
| `project-*/`                  | Standalone edge example; default configs in project root    |
| `project-*/test_scripts/`     | Host-side Python/shell tools to test or visualize pipelines |
| `project-*/test_files/`       | Mock configs, sample JSONL, fixtures for host testing       |
| `dashboard-deployments/`      | Grafana/InfluxDB (etc.) deployment examples                 |
| `.project_readme_template.md` | Standard README outline for new `project-*` examples        |
| `.coderabbit.yaml`            | PR review and code-quality rules for this repo              |
| `.github/workflows/`          | CI (Prettier, Python quality per project)                   |

### How to learn from existing examples

Read [Using LLMs and AI agents when coding for the FixedIT Data Agent](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-using-llms-and-ai-agents-when-coding-for-the-fixedit-data-agent) for platform-specific guidance before generating configs or scripts.

When the user asks you to add or change a FixedIT Data Agent project:

1. **Pick a reference project** — Match the use case (API polling → `project-strobe-color-from-github-workflow`; simple pipeline → `project-hello-world`; Scene Metadata → `project-time-in-area-analytics`; binary/images → `project-timelapse-s3`).
2. **Mirror structure** — Same config naming (`config_agent.conf`, `config_input_*.conf`, `config_process_*.conf`, `config_output_*.conf`), same split between device configs and `test_files/` / `test_scripts/`.
3. **Respect Telegraf load order** — Processors that depend on earlier stages must be enabled **after** their inputs in the FixedIT Data Agent UI (later load order = later in the pipeline).
4. **Use host testing** — Run Telegraf locally with the project’s test configs where documented; use `test_scripts/` to record or visualize JSONL streams; use `inputs.mock` or `inputs.file` in `test_files/` when real device inputs are unavailable (see [Host testing with Telegraf](#host-testing-with-telegraf)).
5. **Do not copy deployment-specific values** — No real hostnames, buckets, or credentials should be used in the examples, instead use environment variables or secrets.
6. **Shell on devices** — Any `.sh` deployed to the device must be portable `/bin/sh`, not bash; see [Shell on devices](#shell-on-devices).

For terminology (AXIS product names, FixedIT Data Agent capitalization, audience framing), follow the same conventions as existing READMEs.

## Axis device environment

Axis devices run a custom Linux distribution, but the environment is heavily restricted compared to a normal server or developer machine:

- **No package manager** — you cannot `apt install` tools on the device.
- **Mostly read-only filesystem** — limited writable areas; not a general-purpose platform for dropping binaries.
- **No root access** — you cannot freely install or reconfigure system software.

The only supported way to install an edge application on the device is as an ACAP (Axis Camera Application Platform package), built and signed for the platform, then installed through the device’s ACAP mechanism.

That is why custom edge logic traditionally means C/C++ ACAP development, cross-compilation, packaging, deployment, and ongoing maintenance for every change.

The FixedIT Data Agent addresses this differently: you install one standardized ACAP (the FixedIT Data Agent). Behavior is then changed by uploading interpreted configuration (Telegraf `.conf` files) and optional Starlark or portable shell scripts that run inside that ACAP—without building and shipping a new native application for each workflow.

### Shell on devices

Bash is not available on Axis devices. Any `.sh` used on-device must be portable `/bin/sh` (see [.coderabbit.yaml](./.coderabbit.yaml) for full shell rules when contributing here). Host-only test scripts may use bash if documented as host-only.

Getting this wrong is one of the most common reasons an example works on a developer laptop but fails on the device.

## Components

The examples in this repository combine several products and open-source tools. On the Axis device, the FixedIT Data Agent ACAP (with the Telegraf runtime) is the main integration hub; AXIS Scene Metadata and companion ACAPs (QR decoder, YOLOv5 object detection, etc.) supply detection streams. Off the device, InfluxDB and Grafana store and visualize metrics. The sections below describe each component and how they connect.

### FixedIT Data Agent

The [FixedIT Data Agent](https://fixedit.ai/products-data-agent/) is an ACAP application for Axis devices that turns cameras and other Axis products into programmable edge data-processing agents. It wraps Telegraf and adds configuration management, an on-device UI for uploading configs, optional custom UIs, and Axis-specific plugins. This allows people to build both automation workflows and data integration between other applications and systems fully on the edge without low-level programming skills. The FixedIT Data Agent allows programmers to use built-in plugins combined with Python-like Starlark scripts. The Starlark scripts are sandboxed and can't interact with the system or environment other than consuming and producing metrics. This keeps them safe and robust. Shell scripts are also supported and are mainly used for file and network operations. Starlark scripts or existing plugins should be preferred over shell scripts whenever possible since they are simpler, more safe and more robust to use.

Engineers and system developers define workflows with configuration files plus optional Starlark or portable shell scripts. A system integrator can then easily deploy these workflows by installing the FixedIT Data Agent ACAP on the device and uploading the configuration files.

#### Live Logs in the Data Agent UI

The application includes a Logs page that streams Telegraf’s stdout and stderr separately in near real time—primary way to debug configs on device.

| Stream     | Typical content                                                                                                                                                   |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **stderr** | Telegraf’s own log messages (plugin errors, config warnings, `[inputs.*]` / `[outputs.*]` diagnostics). By convention, treat stderr as Telegraf internal logging. |
| **stdout** | Reserved for pipeline data you choose to emit and is not used fby Telegraf itself.                                                                                |

To show metrics or custom text in the Logs tab, add `[[outputs.file]]` with `files = ["stdout"]`. The Data Agent captures that output and displays it in the UI. See [Viewing pipeline data in the Logs tab](#viewing-pipeline-data-in-the-logs-tab) under Common challenges. It is recommended to use the `template` serializer to format the output for easy consumption by humans.

For more verbose logging, enable Debug mode in the UI which will set the `TELEGRAF_DEBUG` environment variable to `true`. This can then be used in the configs as `[agent] debug = ${TELEGRAF_DEBUG}` to log more information such as when outputs are flushed and how long the internal queue is for each output.

#### Data pipeline (Telegraf model)

Data flows through a modular pipeline:

| Stage           | Role                                                                         |
| --------------- | ---------------------------------------------------------------------------- |
| **Inputs**      | Collect from APIs, sockets, MQTT, logs, Scene Metadata, system metrics, etc. |
| **Processors**  | Filter, enrich, transform each metric                                        |
| **Aggregators** | Summarize over windows                                                       |
| **Outputs**     | Send to InfluxDB, MQTT, HTTP, S3, exec scripts, VMS, etc.                    |

#### Typical workload categories

1. **Device monitoring** — CPU, memory, disk, network, DNS, process health → InfluxDB/Grafana; buffers offline and backfills when connectivity returns.
2. **Real-time edge processing** — Consume live analytics (e.g. AXIS Scene Metadata), filter, aggregate, integrate with APIs, route to enterprise systems.
3. **Automation / event-driven** — Conditions trigger actions (HTTP, strobes, overlays, PTZ, local API calls) on the device with low latency and resilience during network outages.

Design goal: modularity. Separate ingestion, processing/business logic, automation, visualization, and integration so teams can reuse and reconfigure by picking and choosing the files they need.

#### Common environment variables

The Data Agent maps settings to environment variables that Telegraf and helper scripts read as `${VAR}` in `.conf` files. Always verify names and behavior against the latest [configuration specification (PDF)](https://fixedit-public-hosted.s3.eu-north-1.amazonaws.com/product-info/data-agent/FIXEDIT_DATA_AGENT_CONFIG_SPEC.pdf).

| Category               | App parameter                                                                             | Telegraf env (examples)                                                     | Typical use in configs                                                                                                                    |
| ---------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Debug                  | `DebugMode` (`true` / `false`)                                                            | `TELEGRAF_DEBUG`                                                            | Log more if set to `true` (`[agent] debug = ${TELEGRAF_DEBUG}`); Starlark `log.debug()` and helper `*.debug` files apply only when `true` |
| InfluxDB               | `InfluxDBHost`, `InfluxDBPort`, `InfluxDBToken`, `InfluxDBOrganization`, `InfluxDBBucket` | `INFLUX_HOST`, `INFLUX_PORT`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET` | Placeholders for `outputs.influxdb_v2` URLs and auth                                                                                      |
| Geo / site tags        | `Area`, `Geography`, `Region`, `Site`, `Type`                                             | Same names                                                                  | Tags on metrics                                                                                                                           |
| Intervals              | `SyncIntervalSeconds`, `FlushIntervalSeconds`                                             | `SYNC_INTERVAL_SECONDS`, `FLUSH_INTERVAL_SECONDS`                           | Control how often inputs sync and how often outputs flush                                                                                 |
| Device location (beta) | `DeviceLocationLatitude`, `DeviceLocationLongitude`                                       | `DEVICE_LOCATION_LATITUDE`, `DEVICE_LOCATION_LONGITUDE`                     | Map markers on dashboards                                                                                                                 |
| VAPIX (beta)           | `VapixUsername`, `VapixPassword`                                                          | `VAPIX_USERNAME`, `VAPIX_PASSWORD`                                          | Use for curl commands to VAPIX APIs in the device itself (127.0.0.1)                                                                      |
| Custom                 | `ExtraEnv` (`KEY=value;KEY2=value2`)                                                      | User-defined                                                                | Project-specific settings (zones, thresholds, etc.)                                                                                       |

**Paths and binaries (automatic on device)**

| Variable           | Meaning                                                                                                                                                                                                                                                     |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `HELPER_FILES_DIR` | Directory where the Data Agent stores **files you upload** in the UI (`.conf` helpers, `.sh`, `.star`, test fixtures, etc.). Reference scripts from Telegraf with `${HELPER_FILES_DIR}/my_script.sh` or set `CONSUMER_SCRIPT` to a filename in this folder. |
| `EXECUTABLES_DIR`  | Directory for **bundled binaries** shipped with the agent (e.g. event producer for `outputs.execd`). Use `${EXECUTABLES_DIR}/event_handler`, not a path you upload.                                                                                         |

**Device identity (`DEVICE_PROP_*`, automatic on device)**

Read from the camera’s parameter system and exposed to Telegraf configs and scripts. Commonly used as metric tags, in log messages, or when branching on model/firmware. Do not set these in `ExtraEnv`.

| Variable                | Example value             | Typical use                             |
| ----------------------- | ------------------------- | --------------------------------------- |
| `DEVICE_PROP_BRAND`     | `AXIS`                    | Brand tag on exported metrics           |
| `DEVICE_PROP_MODEL`     | `M1075-L`                 | Model-specific logic or dashboards      |
| `DEVICE_PROP_VARIANT`   | _(often empty)_           | Variant when applicable                 |
| `DEVICE_PROP_TYPE`      | `Box Camera`              | Device category in tags                 |
| `DEVICE_PROP_FULL_NAME` | `AXIS M1075-L Box Camera` | Human-readable label in UIs or logs     |
| `DEVICE_PROP_SERIAL`    | `B8A44F717321`            | Unique device id in databases           |
| `DEVICE_PROP_FIRMWARE`  | `12.5.56`                 | Compatibility checks, support matrix    |
| `DEVICE_PROP_ARCH`      | `aarch64`                 | Architecture-specific behavior          |
| `DEVICE_PROP_SOC`       | `Ambarella CV25`          | Hardware context for performance tuning |

Also set automatically: `APP_VERSION`, `APP_START_TIME`, and `HOME` (dummy path for Telegraf—do not use in project logic). Full list: [configuration specification (PDF)](https://fixedit-public-hosted.s3.eu-north-1.amazonaws.com/product-info/data-agent/FIXEDIT_DATA_AGENT_CONFIG_SPEC.pdf).

**Host vs device: `HELPER_FILES_DIR` pattern**

| Where         | `HELPER_FILES_DIR` points to                                                                                                                             |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **On device** | Set by the Data Agent to the folder where you uploaded helper files in the UI.                                                                           |
| **On host**   | You set it manually—convention in this repo: `export HELPER_FILES_DIR="$(pwd)"` from the project root, so the same relative paths work as on the camera. |

Project configs always use `${HELPER_FILES_DIR}/…` (scripts, Starlark, paths in `inputs.execd`). That way processor and output configs stay identical on device and laptop; only the input side is stubbed for host runs.

**Pattern A — stubbed input script (same input `.conf`, override via env)**

Used in [project-time-in-area-analytics](./project-time-in-area-analytics/): production `config_input_scene_detections.conf` runs:

```toml
command = ["${HELPER_FILES_DIR}/${CONSUMER_SCRIPT:-axis_scene_detection_consumer.sh}"]
```

- **Device:** omit overrides → live `axis_scene_detection_consumer.sh` (message broker).
- **Host:** point at a feeder under `test_files/`:

```bash
cd project-time-in-area-analytics
export HELPER_FILES_DIR="$(pwd)"
export CONSUMER_SCRIPT="test_files/sample_data_feeder.sh"
export SAMPLE_FILE="test_files/simple_tracks.jsonl"
# plus other ExtraEnv equivalents (ALERT_THRESHOLD_SECONDS, OBJECT_TYPE_FILTER, …)
telegraf --config config_agent.conf \
  --config config_input_scene_detections.conf \
  --config config_process_class_filter.conf \
  ...
```

`sample_data_feeder.sh` reads JSONL from `${HELPER_FILES_DIR}/${SAMPLE_FILE}` and prints one detection per line—same shape as the live consumer for `inputs.execd`.

**Pattern B — stubbed input config (`inputs.file` in `test_files/`)**

Used when the device input cannot run on host at all (e.g. [project-strobe-color-from-github-workflow/test_files/config_input_file.conf](./project-strobe-color-from-github-workflow/test_files/config_input_file.conf)):

```toml
[[inputs.file]]
  files = ["${HELPER_FILES_DIR}/${SAMPLE_FILE}"]
```

Host run swaps the **input config file** in the `telegraf --config` list, but still reuses production **processor** and **output** configs.

**Rule of thumb:** On host, set `HELPER_FILES_DIR` to the project root, stub **inputs** (Pattern A or B), mock other UI-driven vars (`INFLUX_*`, `TELEGRAF_DEBUG`, `DEVICE_PROP_*`, VAPIX, etc.), and leave paths to `.star` / `.sh` unchanged.

**Further reading:**

**Official product documentation (PDF, latest release):**

- [FixedIT Data Agent quick start guide (PDF)](https://fixedit-public-hosted.s3.eu-north-1.amazonaws.com/product-info/data-agent/QUICKSTART_GUIDE.pdf)
- [FixedIT Data Agent configuration specification (PDF)](https://fixedit-public-hosted.s3.eu-north-1.amazonaws.com/product-info/data-agent/FIXEDIT_DATA_AGENT_CONFIG_SPEC.pdf) — manual for the current released version (plugins, environment variables, UI behavior)

**Learning articles (learning.fixedit.ai):**

- [Quick start guide](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-quick-start-guide)
- [What the FixedIT Data Agent is and how it works](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-what-the-fixedit-data-agent-is-and-how-it-works)
- [Using LLMs and AI agents when coding for the FixedIT Data Agent](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-using-llms-and-ai-agents-when-coding-for-the-fixedit-data-agent)
- [FixedIT Data Agent product page](https://fixedit.ai/products-data-agent/)

### AXIS Scene Metadata

[AXIS Scene Metadata](https://developer.axis.com/analytics/axis-scene-metadata/) is built into Axis devices (not a separate FixedIT ACAP). Cameras and other sensors publish structured JSON about tracked objects—humans, vehicles, faces, license plates, and more—for real-time analytics and integrations.

**Key references (Axis developer documentation):**

- [Analytics Data Format](https://developer.axis.com/analytics/axis-scene-metadata/reference/data-formats/analytics-data-format/) — versioned schemas for `Frame`, `Object Track`, and `Object Snapshot`
- [Classification types](https://developer.axis.com/analytics/axis-scene-metadata/reference/data-formats/analytics-data-format/classification-types/) — e.g. `Human`, `Car`, `Face`, `LicensePlate`, with scores and attributes
- [Data sources & topics](https://developer.axis.com/analytics/axis-scene-metadata/reference/data-sources/) — frame-by-frame tracking, consolidated tracks, snapshots; MQTT, message broker, RTSP

On AXIS OS 12.8+ (or later), stable Analytics Data Format (ADF) v1 topics such as `com.axis.scene.frame.v1` are available (see the data-sources table). Older integrations often use the beta message-broker topic `com.axis.analytics_scene_description.v0.beta` (deprecated but still common in examples). This CLI will be removed in AXIS OS 13. There will be a new plugin coming for the FixedIT Data Agent.

#### Consume Scene Metadata with Telegraf (FixedIT Data Agent)

Configure Telegraf through the FixedIT Data Agent UI: upload `.conf` files and helper scripts, enable them, and verify metrics in the Logs tab or your chosen outputs.

**In-repo reference (developers):** [project-time-in-area-analytics](./project-time-in-area-analytics/) — `config_input_scene_detections.conf`, `axis_scene_detection_consumer.sh`, and related processors. See the project README for Telegraf config, host testing, and load order.

The consumer script calls `message-broker-cli` only on the device inside the Data Agent process. `message-broker-cli` is expected to be removed in AXIS OS 13; a dedicated FixedIT Data Agent input for Scene Metadata is planned.

**vs custom models:** Built-in Scene Metadata (this section) differs from the [YOLOv5 object detection ACAP](#yolov5-object-detection-acap), which runs your own trained detector.

### FixedIT QR Code Decoder ACAP

The FixedIT QR Code Decoder is a separate ACAP app you install on the Axis device alongside the FixedIT Data Agent. It is not part of the Data Agent itself; the two applications cooperate on the same camera.

- **Product overview:** [FixedIT ACAP applications](https://fixedit.ai/products-acaps/) (QR / barcode reader section)
- **What it does on-device:** Detects and decodes 1D and 2D barcodes (QR, EAN, Code 128, etc.), draws live overlays on the video stream, and publishes each detection as JSON over a Unix domain socket
- **Default socket path:** `/dev/shm/fixedit.qr_code_decoder.sock`
- **Typical use cases:** Access control at doors and gates, logistics parcel tracking, searchable video by shipment ID—see [From searchable video to access control: real QR code workflows at the edge](https://www.linkedin.com/pulse/from-searchable-video-access-control-real-qr-code-workflows-edge-dejze/)

**Architecture:** QR Decoder ACAP (perception + overlays) → Unix socket → FixedIT Data Agent `socket_listener` (ingest + business logic) → outputs (Axis events, InfluxDB, HTTP, MQTT, etc.).

#### Consume QR/barcode detections in the FixedIT Data Agent

Use `[[inputs.socket_listener]]` with `data_format = "json_v2"` to read newline-delimited JSON messages from the decoder socket. Set `socket_mode = "0664"` so the FixedIT QR Code Decoder process on the device can write to the socket, and size `read_buffer_size` for your largest message (QR payloads are on the order of a few KB).

**Example message shape** (one metric per code in frame):

```json
{
  "level": "INFO",
  "message": {
    "code_type": "QR-Code",
    "decoded_data": "https://fixedit.ai",
    "frame_timestamp": 1760453555,
    "norm_center_x": 0.58,
    "norm_center_y": 0.41,
    "number_codes_in_frame": 2
  },
  "source": "BarcodeReader"
}
```

**Minimal input configuration:**

```toml
[[inputs.socket_listener]]
  service_address = "unix://${READER_SOCKET_PATH:-/dev/shm/fixedit.qr_code_decoder.sock}"
  socket_mode = "0664"
  read_timeout = "30s"
  read_buffer_size = "300KiB"
  data_format = "json_v2"
  name_override = "barcode_reader_app"

  [inputs.socket_listener.tags]
    input_method = "socket"

  [[inputs.socket_listener.json_v2]]
    [[inputs.socket_listener.json_v2.object]]
      path = "@this"
      tags = ["source"]
      disable_prepend_keys = true
```

`disable_prepend_keys = true` avoids a `message_` prefix on fields nested under `message` (e.g. `decoded_data` stays `decoded_data`, not `message_decoded_data`).

**Downstream processing:** Add Starlark processors to interpret codes (allowlists, door open/closed logic), `[[outputs.execd]]` for Axis application events, or `[[outputs.influxdb_v2]]` for history. If you must detect when no code has been seen for a while (door closed, gate idle), pair this input with a heartbeat + Starlark counter—see [Detecting the absence of a message](#detecting-the-absence-of-a-message-nothing-happened).

### YOLOv5 object detection ACAP

For your own object-detection models (not only built-in AXIS analytics), use the YOLOv5 ACAP—a separate application you install on the camera to run custom YOLOv5 models at the edge. Product context: [FixedIT ACAP applications](https://fixedit.ai/products-acaps/) (deploy your own deep learning models).

| Step                                                          | Guide                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Train and deploy the YOLOv5 detection ACAP on Axis            | [How to train and deploy your own edge-based object detection models (ACAP ultimate guide)](https://learning.fixedit.ai/posts/blog-fixedit-edge-unlocked-how-to-train-and-deploy-your-own-edge-based-object-detection-models-using-deep-learning-for-the-axis-ip-cameras-with-acap-the-ultimate-guide) |
| Consume detections in the Data Agent and visualize in Grafana | [Video analytics performance dashboards: CV metrics, anomaly detection, and Grafana](https://learning.fixedit.ai/posts/blog-fixedit-edge-unlocked-video-analytics-performance-dashboards-combining-cv-metrics-with-ai-driven-anomaly-detection-and-a-natural-language-chat-interface)                  |

### Telegraf

[Telegraf](https://docs.influxdata.com/telegraf/) is an open-source data collection and processing engine (InfluxData). It is widely used for infrastructure monitoring: metrics, logs, and health from servers, apps, and networks, forwarded to InfluxDB, MQTT, cloud endpoints, or dashboards.

**Classic deployment:** one Telegraf agent per machine, collecting locally and pushing to a central time-series database.

**On Axis devices:** Telegraf runs inside the device via the FixedIT Data Agent ACAP. The agent is the wrapper and config/runtime manager. In this case, Telegraf is not a "data collection agent", but more or a workflow engine for building complex pipelines. Pipelines might or might not send data off the device.

**Why it matters here:** Telegraf is not only a metrics agent. Its plugin architecture makes it a lightweight real-time workflow engine:

- Inputs → Processors → Aggregators → Outputs

In this repo, that engine is only sometimes used for observability, but more often for analytics integration, automation, and bridging metadata between systems.

**Plugin support in the Data Agent:** Telegraf upstream has hundreds of plugins, but not every plugin is included in the FixedIT Data Agent. The shipped ACAP contains a curated set plus Axis-specific plugins. Adding plugins that are not already in your build requires requesting a tailored version of the application. Before relying on a plugin in a design, confirm it exists in your agent version. See [Are all Telegraf plugins supported in the FixedIT Data Agent?](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-are-all-telegraf-plugins-supported-in-the-fixedit-data-agent)

**Further reading:** [Telegraf: the workflow manager in the FixedIT Data Agent](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-telegraf-the-workflow-manager)

**Examples enabled by this stack:**

- Poll third-party ACAP APIs and normalize payloads
- Process Scene Metadata detections with Starlark
- Trigger alarms, overlays, or PTZ from custom logic
- Bridge incompatible metadata formats without rewriting ACAP apps

**Docs:** [Telegraf documentation](https://docs.influxdata.com/telegraf/)

### Starlark

[Starlark](https://github.com/bazelbuild/starlark/blob/master/doc/spec.md) is a small, Python-like, sandboxed language for embedded logic. It is deterministic and cannot freely access the OS unless the host allows it—suited to safe edge pipelines.

Telegraf’s Starlark processor runs scripts inside the pipeline on the device (via FixedIT Data Agent). Use it for filtering, stateful selection, mapping statuses to actions, and algorithms that are awkward in pure config.

**In this repo:** see `.star` files (e.g. `project-time-in-area-analytics/track_duration_calculator.star`) and Starlark processors in `project-strobe-color-from-github-workflow`.

**Important:** Telegraf’s Starlark API differs from Bazel’s. For Data Agent scripts, treat [Telegraf Starlark processor docs](https://docs.influxdata.com/telegraf/latest/processors/starlark/) as the primary API reference, and [Starlark: the Python-like scripting language (FixedIT learning guide)](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-starlark-the-python-like-scripting-language) for how Starlark is used in this platform.

**Intro articles:**

- [How to Use Starlark with Telegraf](https://www.influxdata.com/blog/how-use-starlark-telegraf)
- [Quick Start: Telegraf Starlark Processor](https://www.influxdata.com/blog/quick-start-telegraf-starlark-processor-plugin/)

### InfluxDB (server-side)

[InfluxDB](https://www.influxdata.com/products/influxdb/) is a time-series database optimized for timestamped telemetry: fast writes, efficient retention, and time-range queries (averages, trends, downsampling). It pairs naturally with Telegraf as a sink for metrics and analytics sent from the device.

**InfluxDB does not run on the Axis device.** It runs on a server, VM, or cloud that receives data from FixedIT Data Agent outputs (for example via the InfluxDB output plugin). This repository includes InfluxDB in `dashboard-deployments/` as reference deployments used together with some examples—not as something installed on the camera.

Typical use cases: device health, inference rates, detection counts, occupancy, latency, and other streams exported from edge workflows. Supports local or cloud deployment and retention policies for long-running fleets.

**Note:** Newer InfluxDB v3 builds include more built-in visualization; simple deployments may not need Grafana. Grafana remains common for custom dashboards and fleet views.

**Further reading:** [Using the FixedIT Data Agent with InfluxDB and Grafana to create dashboards](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-pattern-using-the-fixedit-data-agent-with-influxdb-and-grafana-to-create-dashboards)

### Grafana (server-side)

[Grafana](https://grafana.com/) is a visualization and observability UI for time-series and other sources (including InfluxDB). You build dashboards—graphs, heatmaps, alerts, custom panels—for real-time and historical analysis.

**Grafana does not run on the Axis device.** Like InfluxDB, it is server-side. The FixedIT Data Agent on the device collects and forwards data; Grafana (and InfluxDB) visualize and explore it elsewhere. The `dashboard-deployments/` folder in this repo provides ready-made server stacks for projects that document an InfluxDB/Grafana path.

With FixedIT Data Agent + InfluxDB, Grafana is the usual window into fleet health and analytics. It is also used for domain dashboards (occupancy, heatmaps, traffic congestion) when business metrics are exported from edge workflows. It can also be used for system debugging, e.g. plotting measurements to find good threshold values for automated alerts.

Official overview: [Grafana dashboards](https://grafana.com/grafana/dashboards/)

Example in this repo: [system-monitoring-influxdb2-flux-grafana](./dashboard-deployments/system-monitoring-influxdb2-flux-grafana/README.md)

**Video analytics dashboard example:** [Video analytics performance dashboards](https://learning.fixedit.ai/posts/blog-fixedit-edge-unlocked-video-analytics-performance-dashboards-combining-cv-metrics-with-ai-driven-anomaly-detection-and-a-natural-language-chat-interface) combines YOLOv5 object-detection metrics from the Data Agent with Grafana for CV performance monitoring—see also [YOLOv5 object detection ACAP](#yolov5-object-detection-acap).

## Host testing with Telegraf

Install [Telegraf](https://docs.influxdata.com/telegraf/) on your development machine. On Windows, follow [Running Telegraf locally on Windows](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-running-telegraf-locally-on-windows). Linux/macOS/WSL steps are in individual project READMEs.

Most `project-*` examples document how to run:

```bash
telegraf --config config_agent.conf \
  --config config_input_....conf \
  ...
```

On the host you run stock Telegraf, not the FixedIT Data Agent ACAP. That means Axis-specific and Data-Agent-only plugins may be missing (see [plugin support](#telegraf)); tests often swap or mock inputs while exercising processors, Starlark, and outputs (for example `stdout` or `file`).

For normalizing arbitrary JSON into Telegraf’s metric format on the device, see [Parsing complex JSON with the json_v2 parser](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-parsing-complex-json-with-the-json_v2-parser).

### Mock and file inputs for host testing

A common pattern is to replace a device-only input with something Telegraf can run locally:

| Approach              | When to use                                                                                                                                                                                                                                               |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`[[inputs.mock]]`** | Generate synthetic metrics (sine waves, random values, constants) to exercise processors without a live Scene Metadata stream or API. See [Telegraf mock input plugin](https://github.com/influxdata/telegraf/blob/master/plugins/inputs/mock/README.md). |
| **`[[inputs.file]]`** | Replay captured JSON/JSONL lines from `test_files/` (recorded earlier from a device or hand-written fixtures). Used in several projects’ `test_files/config_input_*.conf`.                                                                                |
| **`test_scripts/`**   | Python tools to record live device data, visualize results, or validate pipeline output offline.                                                                                                                                                          |

The mock plugin is especially useful when developing processors and Starlark logic: you control metric names, fields, and tags in config instead of depending on hardware. Example workflow and motivation (filtering overwhelming streams into actionable metrics): [Learning pattern: from overwhelming data streams to meaningful actions](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-pattern-from-overwhelming-data-streams-to-meaningful-actions).

Typical layout: production configs in the project root; host-only configs under `test_files/` that swap `inputs.mock` or `inputs.file` for `inputs.execd` / device APIs, then reuse the same processor and output configs.

Other patterns in the repo:

- `TELEGRAF_DEBUG` — Verbose device-side logging when enabled (see project READMEs); avoid persistent file logging on device when debug is off

Host tests validate data shapes and pipeline logic; always verify on a real Axis device before production.

## Common challenges

### Detecting the absence of a message (“nothing happened”)

Telegraf pipelines are data-driven: inputs produce messages and those messages trigger other processors and outputs. There is no built-in “timeout” or “no message received for N seconds” on a socket, HTTP poll, or analytics stream. If you need to react when activity stops—door closed again, person left the zone, QR reader went quiet—you must design that logic explicitly.

**Typical mistake:** Only processing positive detections and assuming silence means “cleared.” Without a tick, downstream outputs (events, strobes, dashboards) never receive a “back to normal” update.

**Recommended pattern: heartbeat + counter in Starlark**

1. **Primary input** — Consumes the real stream (e.g. `[[inputs.socket_listener]]` on the [FixedIT QR Code Decoder](#fixedit-qr-code-decoder-acap) socket (see [Components](#components)), AXIS Scene Metadata, HTTP, etc.).
2. **Heartbeat input** — `[[inputs.exec]]` on a fixed `interval` that always emits a small message (e.g. `alarming_state_heartbeat` with `data_format = "influx"`).
3. **Starlark processor** — `namepass` includes both the heartbeat and the detection measurement names so the script runs on every tick even when there were zero detections in that period.
4. **Persistent `state` in Starlark** — Between invocations, count how many detection messages arrived since the last heartbeat; on each heartbeat, emit a summary metric (e.g. `door_state` with `closed=true/false`) and reset the counter.

**Behavior (door / QR example):**

| Event                                 | Action                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------ |
| First detection in a period           | Emit “active” state immediately (e.g. door open / alarming).             |
| More detections before next heartbeat | Increment counter; usually suppress duplicate “active” emits per period. |
| Heartbeat with counter > 0            | End of active period; optionally report `alert_count` for the interval.  |
| Heartbeat with counter == 0           | No detections in the interval → emit “cleared” / normal state.           |

**Timing:** The cool-off is tied to the heartbeat `interval`, not wall-clock alone. Documentation in production configs often notes that processing load can delay messages slightly, so the interval should be longer than the maximum gap you expect between real detections—and that in the worst case, clearing can take almost two heartbeat periods (one full interval with zero detections after the last active one).

**In-repo reference:** The same inactivity pattern appears in [project-time-in-area-analytics/config_process_alarming_state.conf](./project-time-in-area-analytics/config_process_alarming_state.conf) (`alarming_state_heartbeat` + Starlark counting `alerting_frame_two` metrics).

**QR / door example:** A full pipeline (socket listener → Starlark door state → `outputs.execd` event + InfluxDB) is documented under [FixedIT QR Code Decoder ACAP](#fixedit-qr-code-decoder-acap) in [Components](#components); the door-state logic uses the heartbeat pattern above when the decoder goes quiet.

### Immediate output (no batching delay)

For real-time actions—strobe color changes, opening a gate, triggering an HTTP call via a shell script—Telegraf’s default output buffering can add a very large delay. Batched metrics mean the downstream script or binary runs only after a buffer fills or a flush interval, which is good for sending large amounts of data to InfluxDB but wrong for actuators.

On `[[outputs.exec]]` and `[[outputs.execd]]`, configure immediate, one-metric-at-a-time delivery:

```toml
[[outputs.exec]]
  namepass = ["workflow_color"]
  command = ["${HELPER_FILES_DIR}/trigger_strobe.sh"]
  data_format = "json"
  use_batch_format = false

  # Process one metric at a time for immediate response.
  # This ensures each detection triggers script execution immediately.
  # Higher values would batch multiple detections (undesirable for real-time control).
  metric_batch_size = 1
```

| Setting                    | Why                                                                                                                                 |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `metric_batch_size = 1`    | Main lever for low latency: each metric is passed to the output plugin as soon as it is ready, instead of waiting for a batch of N. |
| `use_batch_format = false` | Script receives a single JSON object per run, not an array of metrics.                                                              |
| `namepass`                 | Restrict to the measurement that should trigger hardware (ignore heartbeats, debug metrics, etc.).                                  |

**Do not confuse with `metric_buffer_limit`:** That setting caps how many metrics Telegraf queues when an output is slow or offline. A low limit can drop metrics under burst load. It does not by itself make exec run faster—the important setting for “actuate immediately” is `metric_batch_size = 1`. Choose `metric_buffer_limit` separately for your reliability vs. memory trade-off.

Also check `flush_interval`. The `flush_interval` affects how often outputs are flushed if they have not received a full batch of N metrics.

**In-repo reference:** [project-strobe-color-from-github-workflow/config_output_strobe.conf](./project-strobe-color-from-github-workflow/config_output_strobe.conf) and [trigger_strobe.sh](./project-strobe-color-from-github-workflow/trigger_strobe.sh) (parses one metric per invocation). Similar settings appear in [project-time-in-area-analytics/config_output_overlay.conf](./project-time-in-area-analytics/config_output_overlay.conf) for low-latency overlay updates.

### Preserving event timestamps on metrics

When JSON comes from a shell script, file, or socket input, Telegraf defaults the metric time to when the line was parsed (wall clock at ingest). That is wrong for analytics where the payload already carries the detection or event time—durations, InfluxDB charts, and ordering will be off.

Put the event time in a JSON field (e.g. `timestamp` from Scene Metadata) and tell the input plugin to use it:

```toml
[[inputs.execd]]
  data_format = "json"
  name_override = "detection_frame"
  json_string_fields = ["timestamp", "track_id", "object_type", "frame"]

  # Use the detection's own timestamp as the metric time instead of processing time
  json_time_key    = "timestamp"
  json_time_format = "RFC3339Nano"
```

| Setting            | Role                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------- |
| `json_time_key`    | JSON field name whose value becomes the Telegraf metric timestamp.                                |
| `json_time_format` | Layout of that string (`RFC3339`, `RFC3339Nano`, `unix`, etc.—must match what your script emits). |

Ensure the upstream script or parser includes that field on every line. [axis_scene_detection_consumer.sh](./project-time-in-area-analytics/axis_scene_detection_consumer.sh) copies `.timestamp` from each observation into `"timestamp"` in the flattened JSON.

**In-repo reference:** [project-time-in-area-analytics/config_input_scene_detections.conf](./project-time-in-area-analytics/config_input_scene_detections.conf) (add or verify `json_time_key` / `json_time_format` when event time must drive downstream logic).

### Adding metadata to metrics with [global_tags]

The Data Agent automatically sets a bunch of metadata variables (some from application configuration and some automatically read from the device). To add these variables as tags to every metric, use `[global_tags]`. To make sure that the variables name is not used as a fallback value if no value is set for it, you can use the `:-` pattern to set the default value to an empty string.

Example:

```toml
[global_tags]
# Geo/site (from Data Agent UI)
  area             = "${AREA:-}"
  geography        = "${GEOGRAPHY:-}"
  region           = "${REGION:-}"
  site             = "${SITE:-}"
  latitude         = "${DEVICE_LOCATION_LATITUDE:-}"
  longitude        = "${DEVICE_LOCATION_LONGITUDE:-}"
  type             = "${TYPE:-}"

# Device information automatically read from the device
  device_brand      = "${DEVICE_PROP_BRAND:-}"
  device_model      = "${DEVICE_PROP_MODEL:-}"
  device_variant    = "${DEVICE_PROP_VARIANT:-}"
  device_type       = "${DEVICE_PROP_TYPE:-}"
  product_full_name = "${DEVICE_PROP_FULL_NAME:-}"
  device_serial       = "${DEVICE_PROP_SERIAL:-}"
  firmware_version    = "${DEVICE_PROP_FIRMWARE:-}"
  architecture        = "${DEVICE_PROP_ARCH:-}"
  soc                 = "${DEVICE_PROP_SOC:-}"

# Runtime metadata set by the Data Agent
  data_agent_version     = "${APP_VERSION:-}"
  data_agent_start_time  = "${APP_START_TIME:-}"
```

### Working with raw binary data in metrics by base64 encoding

In Telegraf JSON inputs (e.g. `[[inputs.exec]]`), you usually express values as typed fields like numbers, and strings. Raw binary (JPEG files, audio chunks, etc.) can't be parsed by Telegraf since it does not have any binary data types.

**Recommended pattern:**

1. **Encode at the producer** — In the shell (or whichever plugin produces the ingest line), base64-encode the bytes and emit a JSON object with one string field (e.g. `image_base64`) holding that text.
2. **Keep as string internally** — In the Telegraf workflow, keep the field as a string and forward it downstream.
3. **Decode where you need bytes** — On `[[outputs.remotefile]]`, `[[outputs.file]]`, `[[outputs.http]]`, etc., use `data_format = "template"` so the [template serializer](https://github.com/influxdata/telegraf/blob/master/plugins/serializers/template/README.md) can turn the metric back into file bytes. For example `{{ .Field "image_base64" | b64dec }}` for a single binary object per metric.

`telegraf --test`: Test mode gathers inputs once and prints every metric. A field that contains a whole image as base64 is large. Prefer `telegraf ... --once` with real sinks, or a slim host-only config that does not funnel that field to stdout.

### Passing large images between pipeline stages via a Unix socket

A common workflow is to react to a small detection metric (for example a QR decode from `[[inputs.socket_listener]]`) by fetching a JPEG snapshot and forwarding both the trigger metadata and the image to a file upload or other output. Base64 encoding is still required (see [Working with raw binary data in metrics by base64 encoding](#working-with-raw-binary-data-in-metrics-by-base64-encoding)) but the hard part is how you move that large string through Telegraf without hitting buffer limits.

**Typical mistake:** Using `processors.execd` to enrich the detection metric in place, or relying on `[[outputs.exec]]` to return the image on the script’s stdout and expecting Telegraf to ingest it as a new metric. `processors.execd` caps the size of stdout it will read from the helper process; a full-resolution JPEG as base64 can exceed that limit and fail silently or truncate. This size limit is platform dependent, it might work on your computer but not on the device.

**Recommended workaround:** trigger metric → exec output → Unix socket → socket_listener input

Split capture into a short bridge outside Telegraf’s exec stdout buffer:

1. **Trigger** — A normal metric (e.g. `barcode_reader_app` with `decoded_data`) flows to `[[outputs.exec]]` with `metric_batch_size = 1` for immediate reaction (see [Immediate output](#immediate-output-no-batching-delay)).
2. **Capture script** — The exec command runs a shell helper (e.g. `axis_image_consumer.sh`) that calls VAPIX and prints a large JSON object with `image_base64` (and optional metadata like `resolution`). Instead of ingesting this object, pipe it to a Unix domain socket with `socat` (optionally after adding some extra metadata to the object).
3. **Re-ingest** — An `[[inputs.socket_listener]]` listens on the same socket path, uses `json_v2` to read the data (e.g. `input_data.fields.decoded_data` → `decoded_data`, `image_data.image_base64` → `image_base64`), and sets `name_override` (e.g. `image_capture`) for upload processors and outputs.

**Why sockets:** `inputs.socket_listener` is designed for large, line-delimited payloads from external producers. It does not share the small stdout buffer limit that makes `processors.execd` unsuitable for multi-megabyte base64 strings.

**In-repo reference:** [project-sftp-upload-of-qr-codes](./project-sftp-upload-of-qr-codes/) — [config_output_capture.conf](./project-sftp-upload-of-qr-codes/config_output_capture.conf) (exec + `socat`), [config_input_image_capture.conf](./project-sftp-upload-of-qr-codes/config_input_image_capture.conf) (socket_listener + `json_v2`), and [README](./project-sftp-upload-of-qr-codes/README.md) (end-to-end QR → snapshot → SFTP).

### Viewing pipeline data in the Logs tab

To see metrics or debug lines in the FixedIT Data Agent Logs tab, write them to Telegraf stdout via the [file output plugin](https://github.com/influxdata/telegraf/tree/master/plugins/outputs/file). Do not rely on Telegraf printing metrics by itself—by convention only `outputs.file` → `stdout` should use stdout for data; Telegraf diagnostics go to stderr.

**Simple example (JSON metrics)** — as in [project-hello-world](./project-hello-world/) and `test_files/config_output_stdout.conf` in other projects:

```toml
# Prints collected metrics to stdout; the Data Agent shows them in the Logs tab.
[[outputs.file]]
  metric_batch_size = 1
  files = ["stdout"]
  data_format = "json"
```

Even a simple field becomes a full JSON line with metric name, tags, and timestamp.

**Formatted lines (template)** — when JSON is too noisy or you require a special format, use `data_format = "template"`:

```toml
[[outputs.file]]
  namepass          = ["position_monitoring"]
  metric_batch_size = 1
  files             = ["stdout"]
  data_format       = "template"
  template          = "pv={{ .Field \"process_variable\" }}  sp={{ .Field \"setpoint\" }}  upl={{ .Field \"upper_process_limit\" }}  lpl={{ .Field \"lower_process_limit\" }}\n"
```

Use `metric_batch_size = 1` here if each line should appear in the Logs tab as soon as the metric is processed (same idea as [Immediate output](#immediate-output-no-batching-delay)).

## Example projects in this repo

| Project                                                                                   | Illustrates                                                  |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| [project-hello-world](./project-hello-world/)                                             | Minimal inputs/outputs, config overrides                     |
| [project-strobe-color-from-github-workflow](./project-strobe-color-from-github-workflow/) | HTTP input, Starlark processors, exec output to shell        |
| [project-timelapse-s3](./project-timelapse-s3/)                                           | Binary/image handling, AWS S3 output                         |
| [project-sftp-upload-of-qr-codes](./project-sftp-upload-of-qr-codes/)                     | QR trigger, JPEG capture, socket bridge, SFTP upload         |
| [project-time-in-area-analytics](./project-time-in-area-analytics/)                       | Scene Metadata, zones, Starlark, overlays, rich test_scripts |

Browse [README.md](./README.md) for summaries and diagrams.

### Deploying a project in the Data Agent UI

Integrators and operators typically use a finished project that someone else created. This involves uploading custom `.conf` files, helper scripts (`.sh`, `.star`), and optional UI assets in the FixedIT Data Agent web UI, setting environment variables, enabling configs in order, and checking logs. No coding required.

**Example deployment walkthrough:** [Trigger alarms and get detailed statistics about time-in-area using the FixedIT Data Agent](https://learning.fixedit.ai/posts/blog-fixedit-edge-unlocked-trigger-alarms-and-get-detailed-statistics-about-time-in-area-using-the-fixedit-data-agent) walks through deploying [project-time-in-area-analytics](./project-time-in-area-analytics/) end to end. Use it to see what the Data Agent UI looks like in practice (uploading configs and helper files, extra env vars, enabling pipelines, overlays, alarms)—even when your goal is a different pre-built project later.

| What you learn from that guide               | Why it matters                                           |
| -------------------------------------------- | -------------------------------------------------------- |
| Uploading and enabling multiple config files | How Telegraf pipelines are turned on in the UI           |
| Helper / UI file uploads                     | Where `.sh`, `.star`, and custom UI assets live          |
| Extra environment variables                  | How projects parameterize zones, thresholds, credentials |
| Logs and gradual enablement                  | How to verify a deployment step by step                  |

## Official learning resources

Curated documentation for the FixedIT Data Agent platform (complements the examples in this repo).

### Official product documentation (PDF)

| Document                            | Link                                                                                                                                                                                                                               |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Quick start guide                   | [QUICKSTART_GUIDE.pdf](https://fixedit-public-hosted.s3.eu-north-1.amazonaws.com/product-info/data-agent/QUICKSTART_GUIDE.pdf)                                                                                                     |
| Configuration spec (latest release) | [FIXEDIT_DATA_AGENT_CONFIG_SPEC.pdf](https://fixedit-public-hosted.s3.eu-north-1.amazonaws.com/product-info/data-agent/FIXEDIT_DATA_AGENT_CONFIG_SPEC.pdf) — authoritative reference for config files, plugins, and agent features |

### Learning articles

| Topic                  | Guide                                                                                                                                                                                                                                                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Quick start            | [Quick start guide](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-quick-start-guide)                                                                                                                                                  |
| Architecture           | [What the FixedIT Data Agent is and how it works](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-what-the-fixedit-data-agent-is-and-how-it-works)                                                                                      |
| LLM / AI agents        | [Using LLMs and AI agents when coding for the FixedIT Data Agent](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-using-llms-and-ai-agents-when-coding-for-the-fixedit-data-agent)                                                      |
| Telegraf in the agent  | [Telegraf: the workflow manager](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-telegraf-the-workflow-manager)                                                                                                                         |
| Plugin availability    | [Are all Telegraf plugins supported?](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-are-all-telegraf-plugins-supported-in-the-fixedit-data-agent)                                                                                     |
| Starlark               | [Starlark: the Python-like scripting language](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-starlark-the-python-like-scripting-language)                                                                                             |
| JSON parsing           | [Parsing complex JSON with json_v2](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-parsing-complex-json-with-the-json_v2-parser)                                                                                                       |
| Host testing (Windows) | [Running Telegraf locally on Windows](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-running-telegraf-locally-on-windows)                                                                                                              |
| InfluxDB + Grafana     | [Pattern: agent with InfluxDB and Grafana dashboards](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-pattern-using-the-fixedit-data-agent-with-influxdb-and-grafana-to-create-dashboards)                                              |
| Data streams → actions | [Pattern: overwhelming streams to meaningful actions](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-pattern-from-overwhelming-data-streams-to-meaningful-actions)                                                                     |
| Time-in-area deploy    | [Deploy time-in-area project in the Data Agent UI (step-by-step)](https://learning.fixedit.ai/posts/blog-fixedit-edge-unlocked-trigger-alarms-and-get-detailed-statistics-about-time-in-area-using-the-fixedit-data-agent) — for integrators, not developers  |
| YOLOv5 ACAP deploy     | [Train and deploy YOLOv5 object detection on Axis](https://learning.fixedit.ai/posts/blog-fixedit-edge-unlocked-how-to-train-and-deploy-your-own-edge-based-object-detection-models-using-deep-learning-for-the-axis-ip-cameras-with-acap-the-ultimate-guide) |
| CV metrics + Grafana   | [Video analytics dashboards: read detections in the agent](https://learning.fixedit.ai/posts/blog-fixedit-edge-unlocked-video-analytics-performance-dashboards-combining-cv-metrics-with-ai-driven-anomaly-detection-and-a-natural-language-chat-interface)   |

### Frequently asked questions

- [Is the FixedIT Data Agent an IFTTT app?](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-is-the-fixedit-data-agent-an-if-this-then-that-ifttt-app)
- [Is Starlark the same as Python?](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-is-starlark-the-same-as-python)
- [Is there anything the FixedIT Data Agent can’t do?](https://learning.fixedit.ai/posts/fixedit-data-agent-support-learning-is-there-anything-the-fixedit-data-agent-cant-do)

## Pull requests to this repository

Contributors must follow [.coderabbit.yaml](./.coderabbit.yaml): README template, portable shell rules, Prettier, Python CI workflows, no secrets in the public repo, and path-specific review criteria. CodeRabbit uses that file to standardize reviews; it links back here for product and architectural context.
