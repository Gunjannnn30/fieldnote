#!/usr/bin/env bash
# Bring up Fieldnote in Docker and publish it.
#
#   ./scripts/docker_up.sh
#
# Builds the image, starts the service, waits for it to become healthy,
# then opens a public https tunnel and prints the URL.
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"

command -v docker >/dev/null || { echo "docker is not on PATH"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose v2 is required"; exit 1; }

echo "==> building the image (models are baked in, so this takes a while)"
docker compose build

echo "==> starting the service"
docker compose up -d

echo "==> waiting for it to become healthy (the first start builds the corpus)"
for i in $(seq 1 120); do
  state=$(docker inspect -f '{{.State.Health.Status}}' fieldnote 2>/dev/null || echo "starting")
  case "$state" in
    healthy) echo "    healthy"; break ;;
    unhealthy) echo "    container reported unhealthy"; docker compose logs --tail=40; exit 1 ;;
  esac
  sleep 5
  if [ "$i" -eq 120 ]; then echo "    timed out waiting for health"; docker compose logs --tail=40; exit 1; fi
done

echo
echo "    local     http://localhost:${PORT}/"
echo "    api docs  http://localhost:${PORT}/docs"

if command -v cloudflared >/dev/null; then
  echo
  echo "==> opening a public tunnel"
  ( cloudflared tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate 2>&1 | tee /tmp/fieldnote-tunnel.log ) &
  tunnel_pid=$!
  for i in $(seq 1 60); do
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/fieldnote-tunnel.log 2>/dev/null | head -1 || true)
    if [ -n "$url" ]; then
      echo
      echo "    LIVE UI   ${url}/"
      echo "    LIVE API  ${url}/docs"
      break
    fi
    sleep 1
  done
  echo "    (the tunnel closes when this script is stopped)"
  wait "$tunnel_pid"
else
  echo
  echo "cloudflared is not installed - the service is on localhost only."
  echo "install it, or put a reverse proxy in front of port ${PORT}."
  docker compose logs -f
fi
