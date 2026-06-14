# FixedIT Data Agent Examples

This repository provides resources for the [FixedIT Data Agent ACAP](https://fixedit.ai/products-data-agent/) for the Axis network cameras and other Axis devices.

## Table of Contents

<!-- toc -->

- [Server-side Dashboards](#server-side-dashboards)
  - [System Monitoring with InfluxDB2 and Grafana](#system-monitoring-with-influxdb2-and-grafana)
- [Edge Device Customization Examples](#edge-device-customization-examples)
  - [Older Examples](#older-examples)
  - [Hello, World!](#hello-world)
  - [Visualizing a GitHub Workflow Status with an Axis Strobe](#visualizing-a-github-workflow-status-with-an-axis-strobe)
  - [Creating a Timelapse with AWS S3 Upload](#creating-a-timelapse-with-aws-s3-upload)
- [Developer Tools](#developer-tools)
  - [Combine Configuration Files and Scripts](#combine-configuration-files-and-scripts)

<!-- tocstop -->

## Server-side Dashboards

The [dashboard-deployments](./dashboard-deployments) directory contains visualization dashboards that work with the FixedIT Data Agent. Some work directly with the bundled configurations (just spin them up and start visualizing), while others can be used as-is or customized for your needs. Advanced users often combine edge device customization with dashboard modifications to visualize new data types.

### System Monitoring with InfluxDB2 and Grafana

The dashboard stack in the image below is the system monitoring example for the bundled configuration in the FixedIT Data Agent, for more details see the [README](./dashboard-deployments/system-monitoring-influxdb2-flux-grafana/README.md) in the dashboard-deployments directory.

![Grafana Dashboard Overview](./dashboard-deployments/system-monitoring-influxdb2-flux-grafana/.images/laptop-with-grafana-for-monitoring.png)

## Edge Device Customization Examples

Project implementation examples that show how to extend and customize the FixedIT Data Agent by uploading custom configuration files and scripts. This makes it easy to create tailored edge applications for Axis devices without starting from scratch using the AXIS ACAP SDK.

### Older Examples

Looking for project examples for an older version of the FixedIT Data Agent? You can [browse the tags to find a snapshot](https://github.com/fixedit-ai/fixedit-data-agent-examples/tags) of the repository at that time. Examples will typically be compatible within the same major version and for the same or newer minor. E.g. a project compatible with FixedIT Data Agent v1.1 is compatible with v1.2, v1.3, etc. but not with v1.0 or v0.1. It might or might not work with v2.0 since a new major version typically introduces breaking changes.

### Hello, World!

The [Hello, World!](./project-hello-world) project demonstrates how to use the FixedIT Data Agent to upload custom config files and print messages to the standard output of the Telegraf process, which will be captured by the FixedIT Data Agent and displayed in the `Logs` tab.

The following diagram shows the data flow of the "Hello, World!" project. For more details see the [README](./project-hello-world/README.md) in the `project-hello-world` directory.

```mermaid
flowchart TD
    X0["⚙️ Configuration Variables:<br/>SYNC_INTERVAL_SECONDS, TELEGRAF_DEBUG"] --> X1
    X1["Telegraf Agent"]

    X2["Configuration override:<br/>'interval'"] --> A2

    A1["📥 Hello World Input 1<br/>Global Interval"] --> C
    A2["📥 Hello World Input 2<br/>5s Override Interval"] --> C
    C["📤 Output to stdout<br/>JSON format"]

    style X0 fill:#f5f5f5,stroke:#9e9e9e
    style X1 fill:#f5f5f5,stroke:#9e9e9e
    style X2 fill:#f5f5f5,stroke:#9e9e9e
    style A1 fill:#90EE90,stroke:#43a047
    style A2 fill:#90EE90,stroke:#43a047
    style C fill:#ffebee,stroke:#e53935
```

### Visualizing a GitHub Workflow Status with an Axis Strobe

The [Strobe Color From GitHub Workflow](./project-strobe-color-from-github-workflow) project demonstrates real-time CI/CD status visualization by automatically controlling an Axis strobe light based on GitHub Actions workflow results. When your workflow succeeds, the strobe glows green; when it fails, it turns red; and yellow indicates tests are running. The FixedIT Data Agent should be running on the Axis strobe device, since this will poll the GitHub API, no other infrastructure is required.

![Axis strobe with green color](./project-strobe-color-from-github-workflow/.images/strobe.jpg)

The following diagram shows the data flow of the "Strobe Color From GitHub Workflow" project. For more details see the [README](./project-strobe-color-from-github-workflow/README.md) in the `project-strobe-color-from-github-workflow` directory.

```mermaid
flowchart TD
    XAgent["config_agent.conf:<br/>Agent Configuration<br/>interval=5s, collection_jitter=1s"] --> A
    XDebug["TELEGRAF_DEBUG"] --> XAgent

    A["📡 config_input_github.conf:<br/>Fetch GitHub Actions API<br/>Get recent workflow runs"] -->|github_workflow| B["🔍 config_process_filter_by_name.conf:<br/>Filter by workflow name<br/>Keep only target workflow"]

    XGithubCreds["GITHUB_TOKEN<br/>GITHUB_USER<br/>GITHUB_REPO<br/>GITHUB_BRANCH"] --> A
    XWorkflowName["GITHUB_WORKFLOW"] --> B

    B -->|github_workflow_filtered| C1

    subgraph SelectLatest ["config_process_select_latest.conf:<br/>Select Latest Workflow Run"]
        C1{"Compare run_number<br/>with state"}
        C1 -->|"run_number ≥ latest"| C2["Update state<br/>latest_run_number = run_number"]
        C1 -->|"run_number < latest"| C3["Drop older run"]
        C2 --> C4["Pass through metric"]

        C2 -.->|"💾 Persistent state"| CX["state.latest_run_number"]
        CX -.-> C1
    end

    C4 -->|github_workflow_latest| D["🎨 config_process_status_to_color.conf:<br/>Map workflow conclusion to color<br/>success → green<br/>failure → red<br/>running → yellow"]

    D -->|workflow_color| E["🚨 config_output_strobe.conf:<br/>Execute trigger_strobe.sh script<br/>Enable target color profile<br/>Disable other profiles"]

    XVapix["HELPER_FILES_DIR<br/>VAPIX_USERNAME<br/>VAPIX_PASSWORD<br/>VAPIX_IP"] --> E

    style XAgent fill:#f5f5f5,stroke:#9e9e9e
    style XDebug fill:#f5f5f5,stroke:#9e9e9e
    style XGithubCreds fill:#f5f5f5,stroke:#9e9e9e
    style XWorkflowName fill:#f5f5f5,stroke:#9e9e9e
    style XVapix fill:#f5f5f5,stroke:#9e9e9e
    style A fill:#e8f5e9,stroke:#43a047
    style B fill:#f3e5f5,stroke:#8e24aa
    style SelectLatest fill:#f3e5f5,stroke:#8e24aa
    style C1 fill:#ffffff,stroke:#673ab7
    style C2 fill:#ffffff,stroke:#673ab7
    style C3 fill:#ffffff,stroke:#673ab7
    style C4 fill:#ffffff,stroke:#673ab7
    style CX fill:#fff3e0,stroke:#fb8c00
    style D fill:#f3e5f5,stroke:#8e24aa
    style E fill:#ffebee,stroke:#e53935
```

This example showcases how simple configuration files and shell scripts can create powerful edge intelligence in your Axis strobes without traditional embedded development complexity. The project could easily be adapted to work together with other APIs to visualize statuses such as server health monitoring, weather warnings (like high wind alerts), IoT sensor data (temperature, moisture, etc.), security system states, or any REST API (or most other APIs) that provides status information.

### Creating a Timelapse with AWS S3 Upload

The [Timelapse with AWS S3 Upload](./project-timelapse-s3) project demonstrates automated timelapse video creation using the FixedIT Data Agent. This solution captures images at regular intervals from an AXIS device and uploads them to AWS S3 with timestamped filenames, creating a chronological sequence perfect for timelapse generation. Perfect for construction sites, environmental monitoring, safety applications, or any scenario requiring periodic visual documentation.

[![Timelapse Preview](./project-timelapse-s3/.images/timelapse-preview.jpg)](https://youtu.be/mcw3iAlBOj8)

_Click the image above to watch the timelapse video on YouTube_

The following diagram shows the data flow of the "Timelapse with AWS S3 Upload" project. For more details see the [README](./project-timelapse-s3/README.md) in the `project-timelapse-s3` directory.

```mermaid
flowchart TD
    A["⏳ Interval<br/>Trigger capture"] --> B1["📥 VAPIX API Call<br/>Fetch JPEG image"]
    B4 --> J["☁️ S3<br/>.jpg object"]
    B5 --> M["☁️ S3<br/>.json metadata"]

    GT["📌 Telegraf:<br/>[global_tags]"]

    XMeta["DEVICE_PROP_*<br/>AREA, SITE, GEO, …<br/>APP_VERSION, …"]
    XMeta --> GT

    XVapix["VAPIX_USERNAME<br/>VAPIX_PASSWORD"]
    XVapix --> B1

    XAws["AWS_ACCESS_KEY_ID<br/>AWS_SECRET_ACCESS_KEY<br/>AWS_REGION<br/>S3_BUCKET"]
    XAws --> B4
    XAws --> B5

    subgraph "axis_image_consumer.sh"
        B1["📥 VAPIX API Call<br/>Fetch JPEG image"] --> B2["🔄 Base64 Encode<br/>Metric field only"]
        B2 --> B3["📤 Exec metric<br/>image field + resolution tag"]
    end

    subgraph "outputs.remotefile (×2)"
        B3 --> B4["Template:<br/>b64dec → JPEG bytes"]
        B3 --> B5["Template:<br/>metadata JSON"]
    end

    style A fill:#f1f8e9
    style GT fill:#f3e5f5
    style J fill:#e8f5e8
    style M fill:#e8f5e8
    style B1 fill:#fff3e0
    style B2 fill:#fff3e0
    style B3 fill:#fff3e0
    style B4 fill:#e3f2fd
    style B5 fill:#e3f2fd
    style XMeta fill:#f5f5f5,stroke:#9e9e9e
    style XVapix fill:#f5f5f5,stroke:#9e9e9e
    style XAws fill:#f5f5f5,stroke:#9e9e9e
```

The system leverages the FixedIT Data Agent's built-in capabilities to create sophisticated data workflow graphs without traditional embedded programming. Frames are transported through Telegraf as base64 inside a metric; two remotefile sinks write the same basename JPEG plus a lightweight JSON metadata file with timestamps and tags. This also demonstrates the AWS S3 output integration via the Telegraf remotefile plugin.

## Developer Tools

The [tools](./tools) directory contains utilities to help developers work more efficiently with FixedIT Data Agent projects. These tools run on your local development machine and are designed to streamline the development and deployment workflow.

### Combine Configuration Files and Scripts

The [combine-files](./tools/combine-files) tool solves a common deployment challenge: many FixedIT Data Agent projects consist of multiple configuration files (`.conf`), Starlark scripts (`.star`), and shell scripts (`.sh`) that all need to be uploaded separately to the device. While keeping files separate during development makes the codebase easier to navigate and test, it complicates deployment.

This Python script combines multiple configuration files into a single file and can inline both Starlark and shell scripts, creating a self-contained configuration that's easy to deploy. The tool supports variable expansion, making it possible to generate different configurations for production vs. testing.

For detailed usage instructions and examples, see the [README](./tools/combine-files/README.md) in the combine-files directory.
