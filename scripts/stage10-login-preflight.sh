#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file=${1:-deploy/.env.stage10}
case "$env_file" in
  /*) ;;
  *) env_file="$repo_root/$env_file" ;;
esac
compose_file="$repo_root/deploy/docker-compose.stage10.yml"

if [ ! -f "$env_file" ]; then
  echo "STAGE10_LOGIN_ENV_MISSING" >&2
  exit 1
fi

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" \
    --profile instagram-login --profile collector "$@"
}

compose config --quiet

if [ -n "$(compose ps --status running --services collector)" ]; then
  echo "STAGE10_LOGIN_COLLECTOR_RUNNING" >&2
  exit 1
fi

browser_id=$(compose ps -q login-browser)
gateway_id=$(compose ps -q login-gateway)
if [ -z "$browser_id" ] || [ -z "$gateway_id" ]; then
  echo "STAGE10_LOGIN_SERVICES_NOT_RUNNING" >&2
  exit 1
fi

for container_id in "$browser_id" "$gateway_id"; do
  test "$(docker inspect --format '{{.State.Running}}' "$container_id")" = "true"
  test "$(docker inspect --format '{{.Config.User}}' "$container_id")" = "10001:10001"
  test "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container_id")" = "true"
  port_bindings=$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$container_id")
  case "$port_bindings" in
    null|'{}') ;;
    *) echo "STAGE10_LOGIN_HOST_PORT_FOUND" >&2; exit 1 ;;
  esac
done

test "$(docker inspect --format '{{json .HostConfig.CapDrop}}' "$browser_id")" = '["ALL"]'
browser_security=$(docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$browser_id")
case "$browser_security" in
  *no-new-privileges=true*seccomp=*apparmor=offline-reels-collector*) ;;
  *) echo "STAGE10_LOGIN_BROWSER_SECURITY_INVALID" >&2; exit 1 ;;
esac
test "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/login-profiles"}}{{.Type}}{{end}}{{end}}' "$browser_id")" = "volume"

compose exec -T login-browser sh -ec '
  test "$(awk '\''$1 == "NoNewPrivs:" { print $2 }'\'' /proc/1/status)" = "1"
  test "$(awk '\''$1 == "Seccomp:" { print $2 }'\'' /proc/1/status)" = "2"
  test "$(awk '\''$1 == "CapEff:" { print $2 }'\'' /proc/1/status)" = "0000000000000000"
  test "$(cat /proc/1/attr/current)" = "offline-reels-collector (enforce)"
  profile="/login-profiles/$LOGIN_ACCOUNT_ID"
  test "$(stat -c "%u:%g:%a" "$profile")" = "10001:10001:700"
  test -f "$profile/.collector.lock"
'

echo "STAGE10_LOGIN_PREFLIGHT_OK"
