#!/bin/sh
# Write GCP SA JSON from Secrets Manager into a file for Google ADC, then exec the app.
# Do not log GCP_SERVICE_ACCOUNT_JSON.
set -e

CREDS_PATH="${GOOGLE_APPLICATION_CREDENTIALS:-/tmp/gcp-sa.json}"

if [ -n "${GCP_SERVICE_ACCOUNT_JSON:-}" ]; then
  umask 077
  printf '%s' "$GCP_SERVICE_ACCOUNT_JSON" > "$CREDS_PATH"
  export GOOGLE_APPLICATION_CREDENTIALS="$CREDS_PATH"
fi

exec "$@"
