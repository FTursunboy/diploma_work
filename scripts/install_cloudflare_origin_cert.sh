#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-meros-ai.tj}"
CERT_DIR="storage/nginx/certs"
CERT_FILE="${CERT_DIR}/${DOMAIN}.pem"
KEY_FILE="${CERT_DIR}/${DOMAIN}.key"

mkdir -p "${CERT_DIR}"

echo "Paste Cloudflare Origin Certificate for ${DOMAIN}."
echo "Finish with Ctrl+D on an empty new line:"
cat > "${CERT_FILE}"

echo
echo "Paste Cloudflare Origin Private Key for ${DOMAIN}."
echo "Finish with Ctrl+D on an empty new line:"
cat > "${KEY_FILE}"

chmod 600 "${CERT_FILE}" "${KEY_FILE}"

echo
echo "Saved:"
ls -l "${CERT_FILE}" "${KEY_FILE}"

echo
echo "Restarting nginx..."
docker compose up -d nginx
docker compose logs --tail=40 nginx
