#!/bin/sh
# Update + restart the admin webapp on the EC2 instance.
#
# Run on the instance by the "Deploy webapp (EC2 via SSM)" GitHub Actions
# workflow via AWS Systems Manager Run Command (AWS-RunShellScript, as root).
# The workflow prepends a `WEBAPP_DIR='...'` line from the optional repo variable
# before this script; leave it empty to auto-detect the app directory.
#
# POSIX sh only (no bashisms) — the SSM agent executes this with /bin/sh.
set -eux

: "${WEBAPP_DIR:=}"

# Locate the directory that holds docker-compose.yml. WEBAPP_DIR (if set) wins,
# then the known locations for the Terraform-provisioned and manual setups.
APP=""
for d in "$WEBAPP_DIR" /opt/app/repo/webscraper /home/ec2-user/KML/webscraper /home/ec2-user/webscraper; do
  [ -n "$d" ] || continue
  if [ -f "$d/docker-compose.yml" ]; then APP="$d"; break; fi
done
if [ -z "$APP" ]; then
  echo "ERROR: could not find webscraper/docker-compose.yml on the instance."
  echo "Set the WEBAPP_DIR repo variable to the directory that contains it."
  exit 1
fi

# Fast-forward the checkout to the deployed commit on main. .env and the
# app.db/Log.txt volume are untracked / external, so reset --hard leaves them.
TOP=$(git -C "$APP" rev-parse --show-toplevel)
git config --global --add safe.directory "$TOP"
git -C "$TOP" fetch --prune origin main
git -C "$TOP" checkout main
git -C "$TOP" reset --hard origin/main

# Rebuild + restart the stack (webapp + caddy). Idempotent.
cd "$APP"
docker compose up -d --build
docker compose ps
