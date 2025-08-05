# Dashboard examples for the FixedIt Data Agent

This directory contains example dashboard deployments for the FixedIT Data Agent. Depending on what the Data Agent is used for, different stacks of e.g. InfluxDB and Grafana are used together with provisioned dashboards. This makes it easy to try a setup to start visualizing the data from your Axis devices running the FixedIT Data Agent.

## [System monitoring with InfluxDB (v2) and Grafana](./system-monitoring-influxdb2-flux-grafana)

This example shows how to set up advanced dashboards for Axis device system monitoring. These dashboards works with the bundled configuration files in the FixedIT Data Agent. The dashboards are built using InfluxDB 2.x as a database and Flux as the query language.

## Open source licenses

The dashboards in this repository are open source for your convenience and are licensed under the Elastic License 2.0. This means that in most cases you can use them for both commercial and non-commercial purposes, but there are some exceptions.

- By default, you are not allowed to use the dashboards to provide a service to third parties. If you want to do that, you need to contact the FixedIT team to get a license.
- When redistributing the dashboards, you need to include our license notice in the redistributed files, source us as the original authors and include any copyright notices.

For full license details, see the [LICENSE](./LICENSE) file.

### Can I use the dashboards internally in my own business?

Yes, you are allowed to use the dashboards internally in your own business (including commercial purposes).

### Can I setup these dashboards and sell access to them to our customers?

You will need to contact the FixedIT team to get our approval, which we in most cases are happy to give.

### Can I use the dashboards internally to monitor a service we sell to customers?

Yes, you are allowed to use the dashboards internally in your own business, also for monitoring a service you sell to customers.
