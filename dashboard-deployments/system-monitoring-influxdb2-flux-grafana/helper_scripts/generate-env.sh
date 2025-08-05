#!/bin/bash
set -euo pipefail

# Script to generate environment variables for prod docker-compose setup
# This script creates an env.sh file with secure random values for all required variables

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../env.sh"

# Check if openssl is available
if ! command -v openssl &> /dev/null; then
    echo "❌ Error: openssl is required but not installed."
    echo "Please install openssl and try again."
    exit 1
fi

# Check if env.sh already exists to prevent accidental overwrite
if [[ -f "$ENV_FILE" ]]; then
    echo "❌ Error: $ENV_FILE already exists."
    echo "To prevent accidental loss of secrets, please delete it manually first."
    echo "Run: rm $ENV_FILE"
    exit 1
fi

echo "Generating production environment variables..."

# Generate secure passwords (~32 characters)
# 24 bytes -> base64 (32 chars) -> remove "=+/" -> ~32 chars
INFLUXDB_PASSWORD=$(openssl rand -base64 24 | tr -d "=+/")
GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -d "=+/")

# Generate secure admin token (32 bytes = 64 hex characters)
INFLUXDB_ADMIN_TOKEN=$(openssl rand -hex 32)

# Generate random ports within safe ranges
# InfluxDB: 10000-19999 (10k ports)
# Grafana: 20000-29999 (10k ports)
INFLUXDB_PORT=$((10000 + RANDOM % 10000))
GRAFANA_PORT=$((20000 + RANDOM % 10000))

# Create the env.sh file with secure permissions.
OLD_UMASK=$(umask)
umask 077
cat > "$ENV_FILE" << EOF
#!/bin/bash
# Generated environment variables for production docker-compose setup
# Generated on: $(date)
# 
# To use these variables, source this file:
# source env.sh
#
# Then run docker-compose with production overrides:
# docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Port Configuration
export INFLUXDB_PORT="$INFLUXDB_PORT"
export GRAFANA_PORT="$GRAFANA_PORT"

# InfluxDB Configuration
export INFLUXDB_PASSWORD="$INFLUXDB_PASSWORD"
export INFLUXDB_ADMIN_TOKEN="$INFLUXDB_ADMIN_TOKEN"

# Grafana Configuration
export GRAFANA_ADMIN_PASSWORD="$GRAFANA_ADMIN_PASSWORD"

# Ouroboros Configuration (Slack notifications)
# Replace this with your actual Slack webhook URL
export OUROBOROS_SLACK_HOOK_URL="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"

EOF

# Restore original umask. This is mostly important if someone would
# source the script instead of running it.
umask "$OLD_UMASK"

# Print a summary of the generated values and some instructions.
echo "✅ Environment file generated: $ENV_FILE"
echo ""
echo "📋 Generated values:"
echo "  INFLUXDB_PORT: $INFLUXDB_PORT"
echo "  GRAFANA_PORT: $GRAFANA_PORT"
echo "  INFLUXDB_PASSWORD: $INFLUXDB_PASSWORD"
echo "  INFLUXDB_ADMIN_TOKEN: $INFLUXDB_ADMIN_TOKEN"
echo "  GRAFANA_ADMIN_PASSWORD: $GRAFANA_ADMIN_PASSWORD"
echo ""
echo "⚠️  IMPORTANT:"
echo "  1. Update OUROBOROS_SLACK_HOOK_URL with your actual Slack webhook URL"
echo "  2. Keep this file secure and don't commit it to version control"
echo "  3. To use: source env.sh && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d" 