"""Stage 10 Linux deployment and Chromium sandbox invariants."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.scripts.verify_chromium_sandbox import (
    ProcessEvidence,
    SandboxEvidenceError,
    _is_chromium_executable,
    validate_chromium_evidence,
)

ROOT = Path(__file__).resolve().parents[4]


def test_stage10_compose_has_two_opt_in_hardened_collector_services() -> None:
    compose = (ROOT / "deploy" / "docker-compose.stage10.yml").read_text(encoding="utf-8")
    assert "path: docker-compose.prod.yml" in compose
    assert 'NEXT_PUBLIC_STAGE7_COLLECTION_TARGET: "3"' in compose
    assert "profiles: [sandbox-smoke]" in compose
    assert "profiles: [collector]" in compose
    assert 'user: "10001:10001"' in compose
    assert "read_only: true" in compose
    assert "cap_drop: [ALL]" in compose
    assert "no-new-privileges=true" in compose
    assert "seccomp=./security/chromium-seccomp.json" in compose
    assert "apparmor=offline-reels-collector" in compose
    assert "privileged:" not in compose
    assert "cap_add:" not in compose
    assert "SYS_ADMIN" not in compose
    assert "seccomp=unconfined" not in compose
    assert "network_mode: host" not in compose
    assert "ipc: host" not in compose
    assert "pid: host" not in compose
    assert "docker.sock" not in compose

    smoke = compose.split("  collector-sandbox-smoke:", 1)[1].split("\n  collector:", 1)[0]
    assert "network_mode: none" in smoke
    assert "ports:" not in smoke
    collector = compose.split("\n  collector:", 1)[1].split("\nnetworks:", 1)[0]
    assert "app_private" in collector
    assert "collector_egress" in collector
    assert "ports:" not in collector

    smoke_compose = (
        ROOT / "deploy" / "docker-compose.stage10-sandbox-smoke.yml"
    ).read_text(encoding="utf-8")
    assert "network_mode: none" in smoke_compose
    assert "networks:" not in smoke_compose
    assert "volumes:" not in smoke_compose
    assert "ports:" not in smoke_compose
    for required in (
        'user: "10001:10001"',
        "read_only: true",
        "cap_drop: [ALL]",
        "no-new-privileges=true",
        "seccomp=./security/chromium-seccomp.json",
        "apparmor=offline-reels-collector",
    ):
        assert required in smoke_compose
    for forbidden in (
        "privileged:",
        "cap_add:",
        "SYS_ADMIN",
        "unconfined",
        "docker.sock",
        "ipc: host",
        "pid: host",
    ):
        assert forbidden not in smoke_compose


def test_stage10_ingress_is_localhost_only_hardened_and_preserves_backend_paths() -> None:
    compose = (ROOT / "deploy" / "docker-compose.stage10.yml").read_text(
        encoding="utf-8"
    )
    ingress = compose.split("  stage10-ingress:", 1)[1].split("\n  login-browser:", 1)[0]
    caddyfile = (ROOT / "deploy" / "Caddyfile.stage10").read_text(encoding="utf-8")
    caddy_dockerfile = (ROOT / "deploy" / "Dockerfile.stage10-caddy").read_text(
        encoding="utf-8"
    )
    production_compose = (ROOT / "deploy" / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )

    assert "profiles: [production-ingress]" in compose
    assert "ports: !reset []" in compose
    assert "dockerfile: Dockerfile.stage10-caddy" in ingress
    assert "FROM caddy:2.11.4-alpine" in caddy_dockerfile
    assert "setcap -r /usr/bin/caddy" in caddy_dockerfile
    assert 'user: "10001:10001"' in ingress
    assert "read_only: true" in ingress
    assert "cap_drop: [ALL]" in ingress
    assert "no-new-privileges=true" in ingress
    assert '"127.0.0.1:13080:8080"' in ingress
    assert "caddy_web" in ingress
    assert "caddy_api" in ingress
    for forbidden in (
        "0.0.0.0",
        "::",
        "app_private",
        "collector_egress",
        "docker.sock",
        "privileged:",
        "cap_add:",
        "network_mode: host",
        "seccomp=unconfined",
    ):
        assert forbidden not in ingress

    assert "@backend path /videos /videos/* /health/* /api/*" in caddyfile
    assert "reverse_proxy api:8000" in caddyfile
    assert "@login path /connect/* /remote/*" in caddyfile
    assert "reverse_proxy login-gateway:8080" in caddyfile
    assert "reverse_proxy web:3000" in caddyfile
    assert "-Server" in caddyfile
    assert 'X-Content-Type-Options "nosniff"' in caddyfile
    assert 'Referrer-Policy "strict-origin-when-cross-origin"' in caddyfile
    for forbidden in ("handle_path", "uri ", "rewrite ", "encode ", "cache"):
        assert forbidden not in caddyfile

    assert "MANAGEMENT_ORIGIN: ${MANAGEMENT_ORIGIN:?MANAGEMENT_ORIGIN must be set}" in compose
    assert "Caddyfile.stage10" not in production_compose
    assert '"80:80"' in production_compose
    assert '"443:443"' in production_compose


def test_stage10_login_boundary_is_opt_in_hardened_and_profile_is_shared() -> None:
    compose = (ROOT / "deploy" / "docker-compose.stage10.yml").read_text(
        encoding="utf-8"
    )
    browser = compose.split("\n  login-browser:", 1)[1].split(
        "\n  login-gateway:", 1
    )[0]
    browser_security = compose.split("x-login-browser-security:", 1)[1].split(
        "\nservices:", 1
    )[0]
    gateway = compose.split("\n  login-gateway:", 1)[1].split(
        "\n  profile-reset:", 1
    )[0]
    collector = compose.split("\n  collector:", 1)[1].split("\nnetworks:", 1)[0]
    service = (ROOT / "apps" / "login-browser" / "browser_service.py").read_text(
        encoding="utf-8"
    )

    assert "profiles: [instagram-login]" in browser
    assert 'user: "10001:10001"' in browser_security
    assert "read_only: true" in browser_security
    assert "cap_drop: [ALL]" in browser_security
    assert "no-new-privileges=true" in browser_security
    assert "seccomp=./security/chromium-seccomp.json" in browser_security
    assert "apparmor=offline-reels-collector" in browser_security
    assert "collector_profile_stage10:/login-profiles" in browser
    assert "login_control" in browser and "login_egress" in browser
    assert "ports:" not in browser
    assert "privileged:" not in browser_security
    assert "cap_add:" not in browser_security
    assert "seccomp=unconfined" not in browser_security
    assert "docker.sock" not in browser_security

    profile_reset = compose.split("\n  profile-reset:", 1)[1].split(
        "\n  collector-sandbox-smoke:", 1
    )[0]
    assert "profiles: [instagram-profile-reset]" in profile_reset
    assert "app.scripts.stage4_profile_reset" in profile_reset
    assert "LOGIN_RESET_DELETE_PROFILE: \"false\"" in profile_reset
    assert "LOGIN_GATEWAY_SESSION_SECRET" in profile_reset
    assert "LOGIN_BROWSER_CONTROL_SECRET" in profile_reset
    assert "collector_profile_stage10:/login-profiles" in profile_reset
    assert 'user: "10001:10001"' in profile_reset
    assert "read_only: true" in profile_reset
    assert "cap_drop: [ALL]" in profile_reset
    assert "ports:" not in profile_reset

    assert "profiles: [instagram-login]" in gateway
    assert 'user: "10001:10001"' in gateway
    assert "--no-access-log" in gateway
    assert "LOGIN_GATEWAY_ORIGIN: ${MANAGEMENT_ORIGIN" in gateway
    assert "collector_profile_stage10" not in gateway
    assert "ports:" not in gateway
    assert "login_control" in gateway and "caddy_login" in gateway

    assert "collector_profile_stage10:/collector/profile" in collector
    assert 'lock_path = PROFILE / ".collector.lock"' in service
    assert "fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)" in service
    assert "_require_runtime_boundary()" in service
    assert "_require_profile_permissions()" in service
    assert '"--no-sandbox"' not in service
    assert "CHROMIUM_EXECUTABLE" in service
    assert '"--disable-setuid-sandbox"' not in service

    preflight = (ROOT / "scripts" / "stage10-login-preflight.sh").read_text(
        encoding="utf-8"
    )
    assert "compose config --quiet" in preflight
    assert "STAGE10_LOGIN_COLLECTOR_RUNNING" in preflight
    assert "10001:10001:700" in preflight
    assert "docker inspect" in preflight
    for forbidden in (
        "docker compose down",
        "docker compose up",
        "docker volume rm",
        "docker system prune",
        "rm -rf",
    ):
        assert forbidden not in preflight


def test_stage10_uses_one_placeholder_origin_without_tracking_a_hostname() -> None:
    env_lines = (ROOT / "deploy" / ".env.stage10.example").read_text(
        encoding="utf-8"
    ).splitlines()
    values = dict(
        line.split("=", 1)
        for line in env_lines
        if line and not line.startswith("#") and "=" in line
    )

    expected_origin = "https://REPLACE_WITH_TAILSCALE_HOSTNAME"
    assert values["NEXT_PUBLIC_API_BASE_URL"] == expected_origin
    assert values["FRONTEND_ORIGIN"] == expected_origin
    assert values["MANAGEMENT_ORIGIN"] == expected_origin
    assert len(values["LOGIN_GATEWAY_SESSION_SECRET"]) >= 32
    assert len(values["LOGIN_BROWSER_CONTROL_SECRET"]) >= 32


def test_stage10_seccomp_is_pinned_default_deny_plus_chromium_deltas() -> None:
    profile = json.loads(
        (ROOT / "deploy" / "security" / "chromium-seccomp.json").read_text(
            encoding="utf-8"
        )
    )
    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
    assert profile["defaultErrnoRet"] == 1
    userns_delta, chroot_delta = profile["syscalls"][:2]
    assert userns_delta == {
        "comment": "Stage 10: allow Chromium to create and enter its own user namespace",
        "names": ["clone", "setns", "unshare"],
        "action": "SCMP_ACT_ALLOW",
        "args": [],
        "includes": {},
        "excludes": {},
    }
    assert chroot_delta == {
        "comment": "Stage 10: allow Chromium namespace sandbox chroot with outer cap_drop ALL",
        "names": ["chroot"],
        "action": "SCMP_ACT_ALLOW",
        "args": [],
        "includes": {},
        "excludes": {},
    }

    baseline = {**profile, "syscalls": profile["syscalls"][2:]}
    baseline_canonical = json.dumps(
        baseline, sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(baseline_canonical).hexdigest() == (
        "9da637d2ab0a204fcbd91bd88f1be9e004a3acab61c571a9f5b8870e588a17d2"
    )
    allowed = {
        name
        for rule in profile["syscalls"]
        if rule["action"] == "SCMP_ACT_ALLOW"
        for name in rule["names"]
    }
    assert "io_uring_setup" not in allowed
    assert "io_uring_enter" not in allowed
    assert "io_uring_register" not in allowed


def test_stage10_apparmor_keeps_docker_default_denials_and_adds_hardening() -> None:
    profile = (ROOT / "deploy" / "security" / "offline-reels-collector.apparmor").read_text(
        encoding="utf-8"
    )
    assert 'profile "offline-reels-collector"' in profile
    assert "  userns create," in profile
    assert "\n  userns,\n" not in profile
    assert "abi <abi/4.0>" in profile
    assert "network unix," in profile
    assert "deny network alg" in profile
    assert "deny network vsock," in profile
    assert "deny /run/docker.sock rwklx," in profile
    assert "deny /var/run/docker.sock rwklx," in profile
    assert "deny mount" in profile
    assert "deny /sys/kernel/security/**" in profile
    assert "flags=(unconfined)" not in profile


def test_collector_launch_and_entrypoint_require_explicit_sandboxed_commands() -> None:
    browser = (
        ROOT / "apps" / "api" / "app" / "instagram" / "collector" / "runtime" / "browser_feed.py"
    ).read_text(encoding="utf-8")
    entrypoint = (ROOT / "apps" / "api" / "docker" / "collector-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    dockerfile = (ROOT / "apps" / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert '"chromium_sandbox": True' in browser
    assert "sandbox-smoke)" in entrypoint
    assert "live)" in entrypoint
    assert "xvfb-run" in entrypoint
    assert "--no-sandbox" not in entrypoint
    collector_target = dockerfile.split("FROM base AS collector", 1)[1].split(
        "FROM base AS test", 1
    )[0]
    assert "USER collector" in collector_target
    assert "tini xauth xvfb" in " ".join(
        collector_target.split()
    )
    assert "playwright install --with-deps chromium" in collector_target
    assert "xauth" in collector_target
    assert "xvfb" in collector_target


def test_read_only_preflight_uses_noninteractive_sudo_only_for_apparmor_status() -> None:
    script = (ROOT / "scripts" / "stage10-linux-preflight.sh").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "operations" / "stage-10-linux-staging.md").read_text(
        encoding="utf-8"
    )
    assert "docker compose" in script
    assert "config --quiet" in script
    assert "apparmor_status=$(sudo -n aa-status 2>/dev/null)" in script
    assert "aa-status 2>/dev/null |" not in script
    assert "run sudo -v before Stage 10 preflight" in script
    assert "sudo -v\nsh scripts/stage10-linux-preflight.sh" in runbook
    assert script.count("sudo -n") == 1
    for forbidden in (
        "docker compose up",
        "docker compose run",
        "docker compose build",
        "apparmor_parser",
        "sysctl -w",
        "tee /proc",
    ):
        assert forbidden not in script


def _evidence(**overrides) -> ProcessEvidence:
    values = {
        "pid": 100,
        "arguments": ("/ms-playwright/chromium/chrome", "--type=renderer"),
        "uid": 10001,
        "effective_capabilities": 0,
        "no_new_privileges": 1,
        "seccomp_mode": 2,
        "seccomp_filters": 2,
        "apparmor_profile": "offline-reels-collector",
        "uid_map": "10001 10001 1",
    }
    values.update(overrides)
    return ProcessEvidence(**values)


def _outer_process(**overrides) -> ProcessEvidence:
    values = {
        "pid": 1,
        "arguments": ("python",),
        "seccomp_filters": 1,
        "uid_map": "0 0 4294967295",
    }
    values.update(overrides)
    return _evidence(**values)


def test_runtime_evidence_accepts_nested_zygote_caps_with_sandboxed_renderer() -> None:
    own = _outer_process()
    browser = _outer_process(
        pid=101,
        arguments=("/ms-playwright/chromium/chrome",),
    )
    zygote = _evidence(
        pid=102,
        arguments=("/ms-playwright/chromium/chrome", "--type=zygote"),
        effective_capabilities=0x200000,
        seccomp_filters=1,
    )
    renderer = _evidence(pid=103)

    result = validate_chromium_evidence(
        own, [browser, zygote, renderer], "offline-reels-collector"
    )

    assert result == {"chromium_process_count": 3, "sandboxed_process_count": 1}


def test_runtime_evidence_requires_zero_cap_nested_child_with_extra_seccomp_filter() -> None:
    own = _outer_process()
    privileged_zygote = _evidence(
        arguments=("/ms-playwright/chromium/chrome", "--type=zygote"),
        effective_capabilities=0x200000,
        seccomp_filters=1,
    )

    with pytest.raises(SandboxEvidenceError, match="CHROMIUM_SANDBOX_EVIDENCE_MISSING"):
        validate_chromium_evidence(own, [privileged_zygote], "offline-reels-collector")


def test_runtime_evidence_rejects_outer_capability_leaks() -> None:
    own = _outer_process()
    renderer = _evidence()
    outer_browser_with_caps = _outer_process(
        pid=101,
        arguments=("/ms-playwright/chromium/chrome",),
        effective_capabilities=0x200000,
    )

    with pytest.raises(SandboxEvidenceError, match="OUTER_CAPABILITY_LEAK"):
        validate_chromium_evidence(
            own, [outer_browser_with_caps, renderer], "offline-reels-collector"
        )

    with pytest.raises(SandboxEvidenceError, match="OUTER_CAPABILITY_LEAK"):
        validate_chromium_evidence(
            replace(own, effective_capabilities=1), [renderer], "offline-reels-collector"
        )


def test_runtime_evidence_requires_nested_userns_and_extra_seccomp_filter() -> None:
    own = _outer_process()

    for process in (
        replace(_evidence(), uid_map=own.uid_map),
        replace(_evidence(), seccomp_filters=own.seccomp_filters),
    ):
        with pytest.raises(SandboxEvidenceError, match="CHROMIUM_SANDBOX_EVIDENCE_MISSING"):
            validate_chromium_evidence(own, [process], "offline-reels-collector")


def test_runtime_evidence_rejects_no_sandbox_and_root_chromium() -> None:
    own = _outer_process()
    invalid = (
        (replace(_evidence(), arguments=(*_evidence().arguments, "--no-sandbox")), "NO_SANDBOX"),
        (replace(_evidence(), uid=0), "ROOT_CHROMIUM"),
    )
    for process, reason in invalid:
        with pytest.raises(SandboxEvidenceError, match=reason):
            validate_chromium_evidence(own, [process], "offline-reels-collector")


def test_chromium_process_detection_accepts_only_pinned_playwright_binary() -> None:
    assert _is_chromium_executable("/ms-playwright/chromium-123/chrome")
    assert not _is_chromium_executable("/usr/lib/chromium/chromium")
