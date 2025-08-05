# Strobe Color From GitHub API

This project demonstrates how the [FixedIt Data Agent](https://fixedit.ai/products-data-agent/) can be deployed on an Axis strobe light to fetch GitHub API data and dynamically control the device's color based on workflow execution status. The target GitHub repository should have a configured workflow, and this project will monitor the execution status of the latest workflow run on the main branch.

- [Strobe Color From GitHub API](#strobe-color-from-github-api)
  - [Why Choose This Approach?](#why-choose-this-approach)
  - [Demo Video](#demo-video)
  - [Setup](#setup)
    - [Creating a GitHub access token](#creating-a-github-access-token)
    - [Creating the color profiles in the Axis strobe](#creating-the-color-profiles-in-the-axis-strobe)
  - [Test GitHub API](#test-github-api)
  - [Configuration Files](#configuration-files)
    - [`config_agent.conf` - Global Settings](#config_agentconf-global-settings)
    - [`config_input_github.conf` - Data Collection](#config_input_githubconf-data-collection)
    - [`config_process_github.conf` - Data Transformation ](#config_process_githubconf-data-transformation)
    - [`config_output_strobe.conf` - Hardware Control](#config_output_strobeconf-hardware-control)
    - [`config_output_stdout.conf` - Debugging (Optional)](#config_output_stdoutconf-debugging-optional)
    - [`test_files/config_input_file.conf` - Mock input for testing](#test_filesconfig_input_fileconf-mock-input-for-testing)
  - [Local Testing](#local-testing)
    - [Prerequisites for Local Testing](#prerequisites-for-local-testing)
    - [Run locally with mock input data](#run-locally-with-mock-input-data)
    - [Test mock data with real strobe control](#test-mock-data-with-real-strobe-control)
    - [Run locally with real GitHub API data](#run-locally-with-real-github-api-data)
    - [Test the complete workflow (including strobe control)](#test-the-complete-workflow-including-strobe-control)

## Why Choose This Approach?

**No C/C++ development required!** Unlike traditional Axis ACAP applications that require complex C/C++ programming, this solution uses simple configuration files and basic shell scripting.

This example is perfect for **system integrators and IT professionals** who want to create custom device automation without the complexity of traditional embedded development. All you need is:

- Experience configuring IT services (similar to setting up monitoring tools)
- Basic shell scripting knowledge (can be learned quickly)
- Familiarity with REST APIs and JSON (common in modern IT environments)
- Access to an Axis device with strobe capability (D4100-E/D4100-VE mk II, D4200-VE, or similar)

**The result:** Custom edge intelligence that would typically require months of ACAP development can now be implemented in hours using familiar IT tools and practices.

## Demo Video

[![Watch the demo](./.images/webinar-on-youtube.png)](https://www.youtube.com/watch?v=nLwVUYieFLE)

In this demo, we show how **anyone with basic IT skills can create intelligent edge devices** using the FixedIt Data Agent—no cloud dependency, no C/C++ programming, no complex development environment setup required.

Using a GitHub Actions job as an example input, we demonstrate how to:

- Make the Axis strobe fetch external API data from the GitHub Actions CI status
- Transform data using simple Starlark scripts to decide the color of the strobe light
- Trigger a change of the strobe light color via standard HTTP API calls (VAPIX)

This effectively shows how to transform an Axis strobe to an intelligent device that can poll third party APIs and set its color based on the API return status. This can easily be adapted to use any cloud-based or locally hosted API as an input. Whether you're building smart alerts, visual indicators, or edge-based automation pipelines—this is a glimpse of what FixedIt Data Agent makes possible.

## Setup

## High-level overview

1. Create a new GitHub repo and configure a workflow to run on push to the main branch.
1. Create a new token in GitHub for programmatic access (see instructions below).
1. Create the color profiles in the Axis strobe (see instructions below).
1. Set the `GITHUB_TOKEN`, `GITHUB_USER`, `GITHUB_REPO`, `GITHUB_BRANCH`, and `GITHUB_WORKFLOW` environment variables in the FixedIT Data Agent configuration under the `Extra env` parameter by concatanating them with `;` (e.g. `GITHUB_TOKEN=my-token;GITHUB_USER=my-github-user;GITHUB_REPO=my-test-repo;GITHUB_BRANCH=main;GITHUB_WORKFLOW=My Workflow Name`)
1. Upload the configuration files to the FixedIT Data Agent.
1. Enable the configuration files in the FixedIT Data Agent.
1. The strobe light should now change color based on the status of the last job on the main branch.

### Creating the github workflow

How to create a GitHub workflow is outside the scope of this project. However, here is one example:

```yml
name: Validate JSON

on:
  # Run on push and pull requests that modify data.json
  push:
    paths:
      - "data.json"
  pull_request:
    paths:
      - "data.json"

jobs:
  validate-json:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Validate JSON
        run: |
          # Check if data.json exists
          if [ ! -f data.json ]; then
            echo "Error: data.json file not found"
            exit 1
          fi

          # Validate JSON using jq
          if ! jq '.' data.json > /dev/null 2>&1; then
            echo "Error: data.json contains invalid JSON"
            exit 1
          fi

          echo "Success: data.json is valid JSON"
```

> [!WARNING]
> Note that the `GITHUB_WORKFLOW` variable needs to be set to exactly the name of the workflow you want to monitor, specified by the `name` field in the workflow YAML file.

### Creating a GitHub access token

1. Go to Github Setting by pressing your profile picture in the top right corner
1. Click on "Developer settings"
1. Click on "Personal access tokens"
1. Click on "Tokens (classic)"
1. Select "workflow" under "Select scope"

Note that you can create a fine-grained token instead if you want to be more specific about what the token gives access to.

![GitHub token setup](./.images/github-token.png)

Copy this token and use it in the `GITHUB_TOKEN` environment variable in the FixedIT Data Agent configuration.

### Creating the color profiles in the Axis strobe

The application workflow will set the strobe light based on the name of the color profile. Before this works, you need to login to the Axis strobe and create three color profiles named `green`, `yellow`, and `red`.

1. Go to the Axis device web interface
1. Click on "Profiles"
1. Click on "Create"
1. Enter a name for the profile (e.g. "green")
1. Choose the "Pattern" and "Intensity" based on your preference
1. Set the "Color" to "Green"
1. Set "Duration" to "Time" and select e.g. 10 seconds (must be at least as long as the `interval` specified in the `config_agent.conf` file)
1. Leave "Priority" as is
1. Click on "Save"
1. Repeat for the other two profiles

![Axis strobe profile configuration](./.images/axis-strobe-profile-configuration.png)

It should now look like this:

![All profiles](./.images/axis-strobe-all-profiles.png)

## Test GitHub API

You can test the GitHub API by running the following command (slight modifications might be needed for Windows/PowerShell users):

```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
     -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/actions/runs?branch=$GITHUB_BRANCH&per_page=1" | jq .workflow_runs[0].conclusion
```

The conclusion can be `success`, `failure` or null (when it is running).

An example response is:

```json
{
  "total_count": 3,
  "workflow_runs": [
    {
      "id": 15208529511,
      "name": "Validate JSON",
      "node_id": "WFR_kwLOOvI4888AAAADin--Zw",
      "head_branch": "main",
      "head_sha": "6067d04a654d3dfaad8e8c9aa2259f7d070fa4d3",
      "path": ".github/workflows/validate-json.yml",
      "display_title": "Update data.json",
      "run_number": 3,
      "event": "push",
      "status": "completed",
      "conclusion": "success",
      "workflow_id": 163811337,
      "check_suite_id": 39027529483,
      "check_suite_node_id": "CS_kwDOOvI4888AAAAJFjjXCw",
      "url": "https://api.github.com/repos/df2test/my-test-repo/actions/runs/15208529511",
      "html_url": "https://github.com/df2test/my-test-repo/actions/runs/15208529511",
      "pull_requests": [],
      "created_at": "2025-05-23T10:49:24Z",
      "updated_at": "2025-05-23T10:49:34Z",
      "actor": {
        "login": "df2test",
        "id": 123725069,
        "node_id": "U_kgDOB1_lDQ",
        "avatar_url": "https://avatars.githubusercontent.com/u/123725069?v=4",
        "gravatar_id": "",
        "url": "https://api.github.com/users/df2test",
        "html_url": "https://github.com/df2test",
        "followers_url": "https://api.github.com/users/df2test/followers",
        "following_url": "https://api.github.com/users/df2test/following{/other_user}",
        "gists_url": "https://api.github.com/users/df2test/gists{/gist_id}",
        "starred_url": "https://api.github.com/users/df2test/starred{/owner}{/repo}",
        "subscriptions_url": "https://api.github.com/users/df2test/subscriptions",
        "organizations_url": "https://api.github.com/users/df2test/orgs",
        "repos_url": "https://api.github.com/users/df2test/repos",
        "events_url": "https://api.github.com/users/df2test/events{/privacy}",
        "received_events_url": "https://api.github.com/users/df2test/received_events",
        "type": "User",
        "user_view_type": "public",
        "site_admin": false
      },
      "run_attempt": 1,
      "referenced_workflows": [],
      "run_started_at": "2025-05-23T10:49:24Z",
      "triggering_actor": {
        "login": "df2test",
        "id": 123725069,
        "node_id": "U_kgDOB1_lDQ",
        "avatar_url": "https://avatars.githubusercontent.com/u/123725069?v=4",
        "gravatar_id": "",
        "url": "https://api.github.com/users/df2test",
        "html_url": "https://github.com/df2test",
        "followers_url": "https://api.github.com/users/df2test/followers",
        "following_url": "https://api.github.com/users/df2test/following{/other_user}",
        "gists_url": "https://api.github.com/users/df2test/gists{/gist_id}",
        "starred_url": "https://api.github.com/users/df2test/starred{/owner}{/repo}",
        "subscriptions_url": "https://api.github.com/users/df2test/subscriptions",
        "organizations_url": "https://api.github.com/users/df2test/orgs",
        "repos_url": "https://api.github.com/users/df2test/repos",
        "events_url": "https://api.github.com/users/df2test/events{/privacy}",
        "received_events_url": "https://api.github.com/users/df2test/received_events",
        "type": "User",
        "user_view_type": "public",
        "site_admin": false
      },
      "jobs_url": "https://api.github.com/repos/df2test/my-test-repo/actions/runs/15208529511/jobs",
      "logs_url": "https://api.github.com/repos/df2test/my-test-repo/actions/runs/15208529511/logs",
      "check_suite_url": "https://api.github.com/repos/df2test/my-test-repo/check-suites/39027529483",
      "artifacts_url": "https://api.github.com/repos/df2test/my-test-repo/actions/runs/15208529511/artifacts",
      "cancel_url": "https://api.github.com/repos/df2test/my-test-repo/actions/runs/15208529511/cancel",
      "rerun_url": "https://api.github.com/repos/df2test/my-test-repo/actions/runs/15208529511/rerun",
      "previous_attempt_url": null,
      "workflow_url": "https://api.github.com/repos/df2test/my-test-repo/actions/workflows/163811337",
      "head_commit": {
        "id": "6067d04a654d3dfaad8e8c9aa2259f7d070fa4d3",
        "tree_id": "e98a02d39de1fd8ab9c7fed3b0fa213fae6dd950",
        "message": "Update data.json",
        "timestamp": "2025-05-23T10:49:22Z",
        "author": {
          "name": "df2test",
          "email": "123725069+df2test@users.noreply.github.com"
        },
        "committer": {
          "name": "GitHub",
          "email": "noreply@github.com"
        }
      },
      "repository": {
        "id": 988952819,
        "node_id": "R_kgDOOvI48w",
        "name": "my-test-repo",
        "full_name": "df2test/my-test-repo",
        "private": true,
        "owner": {
          "login": "df2test",
          "id": 123725069,
          "node_id": "U_kgDOB1_lDQ",
          "avatar_url": "https://avatars.githubusercontent.com/u/123725069?v=4",
          "gravatar_id": "",
          "url": "https://api.github.com/users/df2test",
          "html_url": "https://github.com/df2test",
          "followers_url": "https://api.github.com/users/df2test/followers",
          "following_url": "https://api.github.com/users/df2test/following{/other_user}",
          "gists_url": "https://api.github.com/users/df2test/gists{/gist_id}",
          "starred_url": "https://api.github.com/users/df2test/starred{/owner}{/repo}",
          "subscriptions_url": "https://api.github.com/users/df2test/subscriptions",
          "organizations_url": "https://api.github.com/users/df2test/orgs",
          "repos_url": "https://api.github.com/users/df2test/repos",
          "events_url": "https://api.github.com/users/df2test/events{/privacy}",
          "received_events_url": "https://api.github.com/users/df2test/received_events",
          "type": "User",
          "user_view_type": "public",
          "site_admin": false
        },
        "html_url": "https://github.com/df2test/my-test-repo",
        "description": null,
        "fork": false,
        "url": "https://api.github.com/repos/df2test/my-test-repo",
        "forks_url": "https://api.github.com/repos/df2test/my-test-repo/forks",
        "keys_url": "https://api.github.com/repos/df2test/my-test-repo/keys{/key_id}",
        "collaborators_url": "https://api.github.com/repos/df2test/my-test-repo/collaborators{/collaborator}",
        "teams_url": "https://api.github.com/repos/df2test/my-test-repo/teams",
        "hooks_url": "https://api.github.com/repos/df2test/my-test-repo/hooks",
        "issue_events_url": "https://api.github.com/repos/df2test/my-test-repo/issues/events{/number}",
        "events_url": "https://api.github.com/repos/df2test/my-test-repo/events",
        "assignees_url": "https://api.github.com/repos/df2test/my-test-repo/assignees{/user}",
        "branches_url": "https://api.github.com/repos/df2test/my-test-repo/branches{/branch}",
        "tags_url": "https://api.github.com/repos/df2test/my-test-repo/tags",
        "blobs_url": "https://api.github.com/repos/df2test/my-test-repo/git/blobs{/sha}",
        "git_tags_url": "https://api.github.com/repos/df2test/my-test-repo/git/tags{/sha}",
        "git_refs_url": "https://api.github.com/repos/df2test/my-test-repo/git/refs{/sha}",
        "trees_url": "https://api.github.com/repos/df2test/my-test-repo/git/trees{/sha}",
        "statuses_url": "https://api.github.com/repos/df2test/my-test-repo/statuses/{sha}",
        "languages_url": "https://api.github.com/repos/df2test/my-test-repo/languages",
        "stargazers_url": "https://api.github.com/repos/df2test/my-test-repo/stargazers",
        "contributors_url": "https://api.github.com/repos/df2test/my-test-repo/contributors",
        "subscribers_url": "https://api.github.com/repos/df2test/my-test-repo/subscribers",
        "subscription_url": "https://api.github.com/repos/df2test/my-test-repo/subscription",
        "commits_url": "https://api.github.com/repos/df2test/my-test-repo/commits{/sha}",
        "git_commits_url": "https://api.github.com/repos/df2test/my-test-repo/git/commits{/sha}",
        "comments_url": "https://api.github.com/repos/df2test/my-test-repo/comments{/number}",
        "issue_comment_url": "https://api.github.com/repos/df2test/my-test-repo/issues/comments{/number}",
        "contents_url": "https://api.github.com/repos/df2test/my-test-repo/contents/{+path}",
        "compare_url": "https://api.github.com/repos/df2test/my-test-repo/compare/{base}...{head}",
        "merges_url": "https://api.github.com/repos/df2test/my-test-repo/merges",
        "archive_url": "https://api.github.com/repos/df2test/my-test-repo/{archive_format}{/ref}",
        "downloads_url": "https://api.github.com/repos/df2test/my-test-repo/downloads",
        "issues_url": "https://api.github.com/repos/df2test/my-test-repo/issues{/number}",
        "pulls_url": "https://api.github.com/repos/df2test/my-test-repo/pulls{/number}",
        "milestones_url": "https://api.github.com/repos/df2test/my-test-repo/milestones{/number}",
        "notifications_url": "https://api.github.com/repos/df2test/my-test-repo/notifications{?since,all,participating}",
        "labels_url": "https://api.github.com/repos/df2test/my-test-repo/labels{/name}",
        "releases_url": "https://api.github.com/repos/df2test/my-test-repo/releases{/id}",
        "deployments_url": "https://api.github.com/repos/df2test/my-test-repo/deployments"
      },
      "head_repository": {
        "id": 988952819,
        "node_id": "R_kgDOOvI48w",
        "name": "my-test-repo",
        "full_name": "df2test/my-test-repo",
        "private": true,
        "owner": {
          "login": "df2test",
          "id": 123725069,
          "node_id": "U_kgDOB1_lDQ",
          "avatar_url": "https://avatars.githubusercontent.com/u/123725069?v=4",
          "gravatar_id": "",
          "url": "https://api.github.com/users/df2test",
          "html_url": "https://github.com/df2test",
          "followers_url": "https://api.github.com/users/df2test/followers",
          "following_url": "https://api.github.com/users/df2test/following{/other_user}",
          "gists_url": "https://api.github.com/users/df2test/gists{/gist_id}",
          "starred_url": "https://api.github.com/users/df2test/starred{/owner}{/repo}",
          "subscriptions_url": "https://api.github.com/users/df2test/subscriptions",
          "organizations_url": "https://api.github.com/users/df2test/orgs",
          "repos_url": "https://api.github.com/users/df2test/repos",
          "events_url": "https://api.github.com/users/df2test/events{/privacy}",
          "received_events_url": "https://api.github.com/users/df2test/received_events",
          "type": "User",
          "user_view_type": "public",
          "site_admin": false
        },
        "html_url": "https://github.com/df2test/my-test-repo",
        "description": null,
        "fork": false,
        "url": "https://api.github.com/repos/df2test/my-test-repo",
        "forks_url": "https://api.github.com/repos/df2test/my-test-repo/forks",
        "keys_url": "https://api.github.com/repos/df2test/my-test-repo/keys{/key_id}",
        "collaborators_url": "https://api.github.com/repos/df2test/my-test-repo/collaborators{/collaborator}",
        "teams_url": "https://api.github.com/repos/df2test/my-test-repo/teams",
        "hooks_url": "https://api.github.com/repos/df2test/my-test-repo/hooks",
        "issue_events_url": "https://api.github.com/repos/df2test/my-test-repo/issues/events{/number}",
        "events_url": "https://api.github.com/repos/df2test/my-test-repo/events",
        "assignees_url": "https://api.github.com/repos/df2test/my-test-repo/assignees{/user}",
        "branches_url": "https://api.github.com/repos/df2test/my-test-repo/branches{/branch}",
        "tags_url": "https://api.github.com/repos/df2test/my-test-repo/tags",
        "blobs_url": "https://api.github.com/repos/df2test/my-test-repo/git/blobs{/sha}",
        "git_tags_url": "https://api.github.com/repos/df2test/my-test-repo/git/tags{/sha}",
        "git_refs_url": "https://api.github.com/repos/df2test/my-test-repo/git/refs{/sha}",
        "trees_url": "https://api.github.com/repos/df2test/my-test-repo/git/trees{/sha}",
        "statuses_url": "https://api.github.com/repos/df2test/my-test-repo/statuses/{sha}",
        "languages_url": "https://api.github.com/repos/df2test/my-test-repo/languages",
        "stargazers_url": "https://api.github.com/repos/df2test/my-test-repo/stargazers",
        "contributors_url": "https://api.github.com/repos/df2test/my-test-repo/contributors",
        "subscribers_url": "https://api.github.com/repos/df2test/my-test-repo/subscribers",
        "subscription_url": "https://api.github.com/repos/df2test/my-test-repo/subscription",
        "commits_url": "https://api.github.com/repos/df2test/my-test-repo/commits{/sha}",
        "git_commits_url": "https://api.github.com/repos/df2test/my-test-repo/git/commits{/sha}",
        "comments_url": "https://api.github.com/repos/df2test/my-test-repo/comments{/number}",
        "issue_comment_url": "https://api.github.com/repos/df2test/my-test-repo/issues/comments{/number}",
        "contents_url": "https://api.github.com/repos/df2test/my-test-repo/contents/{+path}",
        "compare_url": "https://api.github.com/repos/df2test/my-test-repo/compare/{base}...{head}",
        "merges_url": "https://api.github.com/repos/df2test/my-test-repo/merges",
        "archive_url": "https://api.github.com/repos/df2test/my-test-repo/{archive_format}{/ref}",
        "downloads_url": "https://api.github.com/repos/df2test/my-test-repo/downloads",
        "issues_url": "https://api.github.com/repos/df2test/my-test-repo/issues{/number}",
        "pulls_url": "https://api.github.com/repos/df2test/my-test-repo/pulls{/number}",
        "milestones_url": "https://api.github.com/repos/df2test/my-test-repo/milestones{/number}",
        "notifications_url": "https://api.github.com/repos/df2test/my-test-repo/notifications{?since,all,participating}",
        "labels_url": "https://api.github.com/repos/df2test/my-test-repo/labels{/name}",
        "releases_url": "https://api.github.com/repos/df2test/my-test-repo/releases{/id}",
        "deployments_url": "https://api.github.com/repos/df2test/my-test-repo/deployments"
      }
    }
  ]
}
```

## Configuration Files

This project uses several configuration files that work together to create a data pipeline. Each file handles a specific part of the workflow:

### `config_agent.conf` - Global Settings

Controls how often the system checks GitHub for updates (every 5 seconds by default). Also includes timing randomization to prevent multiple devices from overwhelming GitHub's servers.

### `config_input_github.conf` - Data Collection

Defines how to fetch workflow status from GitHub's REST API. Uses your GitHub token for authentication and retrieves information about the most recent workflow run on your specified branch.

### `config_process_github.conf` - Data Transformation

Contains a Starlark script that converts GitHub's workflow status (`success`, `failure`, or `null` for running) into simple color names (`green`, `red`, or `yellow`) that the strobe can understand.

### `config_output_strobe.conf` - Hardware Control

Executes the `trigger_strobe.sh` script whenever the workflow status changes. This script uses VAPIX commands to actually change the strobe light color on your Axis device.

### `config_output_stdout.conf` - Debugging (Optional)

When enabled, this outputs all pipeline data to the FixedIT Data Agent logs. Useful for troubleshooting if the strobe isn't responding as expected.

### `test_files/config_input_file.conf` - Mock input for testing

This file can be used together with the `sample.json` file to test the pipeline without having to wait for a GitHub Actions job to complete. Upload this file instead of the `config_input_github.conf` file, then upload the `sample.json` file as a helper file.

## Local Testing

You can test the workflow on your development machine before deploying to your Axis device. This requires [Telegraf](https://www.influxdata.com/time-series-platform/telegraf/) to be installed locally.

### Prerequisites for Local Testing

- Install Telegraf on your development machine
- Have `jq` installed for JSON processing (used by `trigger_strobe.sh`)
- Clone this repository and navigate to the project directory

### Run locally with mock input data

Test the API parsing pipeline using sample GitHub API data without making actual API calls:

```bash
# Set up environment
export HELPER_FILES_DIR=$(pwd)

# Run with mock input data and output to console
telegraf --config config_agent.conf \
         --config test_files/config_input_file.conf \
         --config config_process_github.conf \
         --config config_output_stdout.conf \
         --once
```

**Expected output:** You'll see Telegraf load the configs and then output a JSON line like:

```json
{
  "fields": { "color": "green" },
  "name": "workflow_color",
  "tags": {},
  "timestamp": 1754301969
}
```

This shows the pipeline successfully converted the sample GitHub "success" status into "green" color output.

### Test mock data with real strobe control

Test the data transformation and strobe control using sample data (no GitHub API calls needed):

```bash
# Set up your Axis device credentials
export VAPIX_USERNAME=root
export VAPIX_PASSWORD=your-device-password
export VAPIX_IP=your.axis.device.ip

# Set helper files directory
export HELPER_FILES_DIR=$(pwd)

# Run with mock data but real strobe control
telegraf --config config_agent.conf \
         --config test_files/config_input_file.conf \
         --config config_process_github.conf \
         --config config_output_strobe.conf \
         --config config_output_stdout.conf \
         --once
```

This will process the sample GitHub API response and **actually control your strobe light** based on the sample data (which shows a "success" status, so it should turn the strobe green).

### Run locally with real GitHub API data

Test with live GitHub API data (requires valid credentials):

```bash
# Set up your GitHub credentials
export GITHUB_TOKEN=ghp_YOUR_GITHUB_TOKEN_HERE
export GITHUB_USER=your-github-username
export GITHUB_REPO=your-repo-name
export GITHUB_BRANCH=main
export GITHUB_WORKFLOW="Your Workflow Name"

# Set helper files directory
export HELPER_FILES_DIR=$(pwd)

# Run with real GitHub API (will make actual API calls)
telegraf --config config_agent.conf \
         --config config_input_github.conf \
         --config config_process_github.conf \
         --config config_output_stdout.conf \
         --once
```

**Expected output:** With valid credentials, you'll see the JSON result like the mock test above. With invalid/expired credentials, you'll see:

```
Error in plugin: received status code 401 (Unauthorized)
```

If you get a 401 error, check that your GitHub token is valid and has the required permissions.

### Test the complete workflow (including strobe control)

```bash
# Set up your GitHub credentials
export GITHUB_TOKEN=ghp_YOUR_GITHUB_TOKEN_HERE
export GITHUB_USER=your-github-username
export GITHUB_REPO=your-repo-name
export GITHUB_BRANCH=main
export GITHUB_WORKFLOW="Your Workflow Name"

# Set up your Axis device credentials
export VAPIX_USERNAME=root
export VAPIX_PASSWORD=your-device-password
export VAPIX_IP=your.axis.device.ip

# Set helper files directory
export HELPER_FILES_DIR=$(pwd)

# Full pipeline including strobe control
telegraf --config config_agent.conf \
         --config config_input_github.conf \
         --config config_process_github.conf \
         --config config_output_strobe.conf \
         --config config_output_stdout.conf \
         --once
```

This will fetch real GitHub data AND control your strobe light based on the workflow status.
