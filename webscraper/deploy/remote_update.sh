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

# SSM runs commands as root but with a bare environment — $HOME is unset, which
# makes `git config --global` fail with "$HOME not set". Set it explicitly.
export HOME="${HOME:-/root}"

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

# SSM runs this as root, but the checkout is owned by ec2-user — git would abort
# with "dubious ownership". Trust all repos for the user running this (root here)
# BEFORE any other git call. Idempotent so /root/.gitconfig doesn't accumulate.
if ! git config --global --get-all safe.directory 2>/dev/null | grep -Fxq '*'; then
  git config --global --add safe.directory '*'
fi

# Guard: a clear error if $APP is a plain copy (scp) rather than a git checkout.
if ! git -C "$APP" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: $APP is not a git checkout — 'git pull' can't work there."
  echo "Re-clone the repo on the instance (see .github/DEPLOY_CICD.md)."
  exit 1
fi

# Fast-forward the checkout to the deployed commit on main. .env and the
# app.db/Log.txt volume are untracked / external, so reset --hard leaves them.
git -C "$APP" fetch --prune origin main
git -C "$APP" checkout main
git -C "$APP" reset --hard origin/main

# Rebuild + restart the stack (webapp + caddy). Idempotent.
cd "$APP"
docker compose up -d --build
docker compose ps
