#!/bin/sh
# Read-only Ubuntu 24.04 / Docker host validation. This script never loads a
# profile, changes a sysctl, builds an image, or starts a container.
set -eu

EXPECTED_DOCKER_VERSION=29.7.2
EXPECTED_COMPOSE_VERSION=5.5.0
EXPECTED_APPARMOR_PROFILE=offline-reels-collector

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${1:-}

fail() {
  printf 'stage10-preflight: FAIL: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

kernel_option_enabled() {
  option=$1
  if [ -r /proc/config.gz ]; then
    gzip -cd /proc/config.gz | grep -qx "$option=y"
    return
  fi
  config=/boot/config-$(uname -r)
  [ -r "$config" ] || fail "kernel config is not readable"
  grep -qx "$option=y" "$config"
}

[ "$(id -u)" -ne 0 ] || fail "run Docker checks as the non-root deployment user"
[ "$(uname -s)" = Linux ] || fail "Linux is required"
[ "$(uname -m)" = x86_64 ] || fail "amd64/x86_64 is required"

for command_name in docker python3 grep gzip stat aa-status sudo; do
  require_command "$command_name"
done

docker_version=$(docker version --format '{{.Server.Version}}')
[ "$docker_version" = "$EXPECTED_DOCKER_VERSION" ] || fail "unexpected Docker Engine version"
compose_version=$(docker compose version --short)
compose_version=${compose_version#v}
[ "$compose_version" = "$EXPECTED_COMPOSE_VERSION" ] || fail "unexpected Docker Compose version"
[ "$(docker info --format '{{.CgroupVersion}}')" = 2 ] || fail "cgroup v2 is required"
security_options=$(docker info --format '{{json .SecurityOptions}}')
printf '%s' "$security_options" | grep -q 'name=seccomp' || fail "Docker seccomp is unavailable"
printf '%s' "$security_options" | grep -q 'name=apparmor' || fail "Docker AppArmor is unavailable"

[ "$(cat /sys/module/apparmor/parameters/enabled 2>/dev/null)" = Y ] || fail "AppArmor is inactive"
apparmor_status=$(sudo -n aa-status 2>/dev/null) || \
  fail "cannot read AppArmor profile set; run sudo -v before Stage 10 preflight"
printf '%s\n' "$apparmor_status" | grep -q "^[[:space:]]*$EXPECTED_APPARMOR_PROFILE$" || \
  fail "Stage 10 AppArmor profile is not loaded"

kernel_option_enabled CONFIG_USER_NS || fail "CONFIG_USER_NS is disabled"
kernel_option_enabled CONFIG_SECCOMP || fail "CONFIG_SECCOMP is disabled"
kernel_option_enabled CONFIG_SECCOMP_FILTER || fail "CONFIG_SECCOMP_FILTER is disabled"
[ "$(cat /proc/sys/kernel/unprivileged_userns_clone)" = 1 ] || fail "unprivileged userns is disabled"
[ "$(cat /proc/sys/user/max_user_namespaces)" -gt 0 ] || fail "no user namespaces are available"
if [ -r /proc/sys/kernel/apparmor_restrict_unprivileged_userns ]; then
  [ "$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns)" = 1 ] || \
    fail "Ubuntu AppArmor userns restriction was disabled host-wide"
fi

cd "$REPOSITORY_ROOT"

python3 - "deploy/security/chromium-seccomp.json" <<'PY'
import json
import sys

profile = json.load(open(sys.argv[1], encoding="utf-8"))
assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
rule = profile["syscalls"][0]
assert rule["action"] == "SCMP_ACT_ALLOW"
assert set(rule["names"]) == {"clone", "setns", "unshare"}
assert "io_uring_setup" not in {
    name
    for item in profile["syscalls"]
    if item["action"] == "SCMP_ACT_ALLOW"
    for name in item["names"]
}
PY

docker compose -f deploy/docker-compose.stage10-sandbox-smoke.yml config --quiet
if [ -n "$ENV_FILE" ]; then
  [ -f "$ENV_FILE" ] || fail "missing Stage 10 environment file"
  [ "$(stat -c '%a' "$ENV_FILE")" = 600 ] || \
    fail "Stage 10 environment file must have mode 0600"
  [ "$(stat -c '%u' "$ENV_FILE")" = "$(id -u)" ] || \
    fail "Stage 10 environment file owner mismatch"
  docker compose --env-file "$ENV_FILE" -f deploy/docker-compose.stage10.yml \
    --profile sandbox-smoke --profile collector config --quiet
fi

printf 'stage10-preflight: PASS (read-only; no container started)\n'
