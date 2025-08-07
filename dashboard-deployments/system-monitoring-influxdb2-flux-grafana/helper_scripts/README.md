# Helper scripts

## [install-docker-aws-ec2.sh](./install-docker-aws-ec2.sh)

This script can be used to install docker with docker compose on an AWS EC2 instance with Amazon Linux 2. This makes it easy to deploy the example dashboard to an AWS EC2 instance.

Just copy the script to the EC2 instance and run it with `./install-docker-aws-ec2.sh`.

## [generate-env.sh](./generate-env.sh)

This script generates an `env.sh` file with secure random values for all environment variables required by the production docker-compose setup (`docker-compose.prod.yml`).

The script generates:

- **Unique project name**: `monitoring-{suffix}` for container isolation where `{suffix}` is a random 6-character hex string (e.g., `a1b2c3`)
- **Random port numbers**: For InfluxDB and Grafana (to avoid conflicts)
- **Secure passwords**: For InfluxDB and Grafana
- **Secure admin token**: For InfluxDB
- **Placeholder for Slack webhook URL**: (needs manual update)

Usage:

```bash
./helper_scripts/generate-env.sh
```

This will create an `env.sh` file in the project root. To use it:

```bash
source env.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
