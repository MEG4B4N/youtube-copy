#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SUDO=()
if [[ "$(id -u)" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO=(sudo)
  else
    echo "ERROR: run as root or install sudo to bootstrap Docker." >&2
    exit 1
  fi
fi

DOCKER=(docker)
if ! command -v docker >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: Docker is missing and automatic installation is supported only on Ubuntu/Debian." >&2
    exit 1
  fi
  echo "Docker is not installed. Installing Docker Engine and Compose plugin..."
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y ca-certificates curl
  curl -fsSL https://get.docker.com -o /tmp/streamhub-install-docker.sh
  "${SUDO[@]}" sh /tmp/streamhub-install-docker.sh
  rm -f /tmp/streamhub-install-docker.sh
  DOCKER=("${SUDO[@]}" docker)
else
  if ! docker info >/dev/null 2>&1; then
    if [[ ${#SUDO[@]} -gt 0 ]] && sudo docker info >/dev/null 2>&1; then
      DOCKER=(sudo docker)
    else
      echo "ERROR: Docker is installed but the daemon is not running or is inaccessible." >&2
      echo "Start Docker, or run this script as a user with Docker access." >&2
      exit 1
    fi
  fi
fi

if ! "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: Docker Compose plugin is missing; install docker-compose-plugin." >&2
    exit 1
  fi
  echo "Installing Docker Compose plugin..."
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y docker-compose-plugin
fi

if [[ ! -f .env ]] && ! command -v python3 >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: Python 3 is required to generate deployment secrets." >&2
    exit 1
  fi
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y python3
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  S3_ACCESS="$(python3 -c 'import secrets; print(secrets.token_hex(12))')"
  S3_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  DB_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sed -i "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=${SECRET}|" .env
  sed -i "s|^S3_ACCESS_KEY=.*|S3_ACCESS_KEY=${S3_ACCESS}|" .env
  sed -i "s|^S3_SECRET_KEY=.*|S3_SECRET_KEY=${S3_SECRET}|" .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${DB_SECRET}|" .env
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://streamhub:${DB_SECRET}@db:5432/streamhub|" .env
  chmod 600 .env
  echo "Created .env with generated secrets. Keep this file private."
fi

echo "Building and starting StreamHub..."
"${DOCKER[@]}" compose up -d --build

echo "Waiting for API health check..."
for attempt in $(seq 1 90); do
  if "${DOCKER[@]}" compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" >/dev/null 2>&1; then
    echo ""
    echo "StreamHub is ready: http://localhost:8000"
    echo "API docs:          http://localhost:8000/docs"
    echo "RustFS console:    http://localhost:9001"
    echo "Demo accounts:     see README.md"
    exit 0
  fi
  sleep 2
done

echo "API did not become healthy. Recent logs:"
"${DOCKER[@]}" compose logs --tail=100 api worker
exit 1
