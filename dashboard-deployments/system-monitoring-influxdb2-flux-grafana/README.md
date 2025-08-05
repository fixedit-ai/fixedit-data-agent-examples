# InfluxDB and Grafana stack

This directory contains a package with the files needed to spin up a stack with InfluxDB and Grafana where Grafana comes pre-populated with multiple dashboards useful for monitoring system metrics from the devices and the propagation of configuration parameters.

## Running the stack

This stack (defined in `docker-compose.yml`) will run:

- InfluxDB storing time series data (system metrics and configuration parameters)
- Grafana to create dashboards

To run it:

1. Run `docker compose up -d`
2. Then go to [http://127.0.0.1:8086](http://127.0.0.1:8086) and log in with username `test` and password `testtest` (from the `docker-compose.yml` file)
3. Open grafana UI on [http://127.0.0.1:3000](http://127.0.0.1:3000) and log in with username `admin` and password `test` (from the `docker-compose.yml` file).

### Example of more secure setup

The supplied `docker-compose.yml` file is for development usage with hardcoded ports and credentials for simplicity. For production, you should handle keys in a more secure way. One example of a better setup is to use the `docker-compose.prod.yml` override file.

**Helper Script Available**: There's a helper script to generate the `env.sh` file with secure random values for all environment variables required by the production docker-compose setup (`docker-compose.prod.yml`), see [helper_scripts/README.md](./helper_scripts/README.md) for more details.

```bash
# Use the helper script to generate secure environment variables
./helper_scripts/generate-env.sh
source env.sh

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Note**: The production setup uses configurable ports and unique container names to allow running multiple instances on the same server. The development setup uses hardcoded ports (8086 for InfluxDB, 3000 for Grafana) for simplicity. This can be changed by editing the `env.sh` file after generation with the `helper_scripts/generate-env.sh` script or by manually setting the environment variables before launching the stack.

## Grafana

Open the grafana UI on [http://127.0.0.1:3000](http://127.0.0.1:3000), login with user `admin` and password `test` (specified in the [./docker-compose.yml](./docker-compose.yml) file). Click on "Dashboards" and you should see the pre-populated dashboards in the "Cameras" folder.

## Helper scripts

The directory [helper_scripts](./helper_scripts/) contains scripts that can assist with deployment, see the [README](./helper_scripts/README.md) for more details.
