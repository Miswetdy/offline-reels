"""Networkless Stage 10 proof that Chromium's Linux sandbox is active."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

EXPECTED_UID = 10001
FORBIDDEN_ARGUMENTS = frozenset({"--no-sandbox"})


class SandboxEvidenceError(RuntimeError):
    """A safe, bounded synthetic-acceptance failure."""


@dataclass(frozen=True)
class ProcessEvidence:
    pid: int
    arguments: tuple[str, ...]
    uid: int
    effective_capabilities: int
    no_new_privileges: int
    seccomp_mode: int
    seccomp_filters: int
    apparmor_profile: str
    uid_map: str


def main() -> int:
    try:
        payload = run_smoke()
    except SandboxEvidenceError as error:
        print(
            json.dumps(
                {"phase": "stage-10-chromium-sandbox", "verified": False, "reason": str(error)},
                sort_keys=True,
            )
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "phase": "stage-10-chromium-sandbox",
                    "verified": False,
                    "reason": "BROWSER_SMOKE_FAILED",
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


def run_smoke(proc_root: Path = Path("/proc")) -> dict[str, object]:
    if os.name != "posix" or not proc_root.is_dir():
        raise SandboxEvidenceError("LINUX_PROC_REQUIRED")
    expected_profile = os.environ.get(
        "COLLECTOR_EXPECTED_APPARMOR_PROFILE", "offline-reels-collector"
    )
    own = read_process_evidence(os.getpid(), proc_root)
    _validate_container_boundary(own, expected_profile)

    profile_root = Path(os.environ.get("COLLECTOR_PROFILE_ROOT", "/collector/profile"))
    profile = profile_root / f"sandbox-smoke-{os.getpid()}"
    profile.mkdir(mode=0o700, parents=False, exist_ok=False)
    blocked_requests: list[str] = []
    context = None
    playwright = None
    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        launch_options: dict[str, object] = {
            "headless": True,
            "chromium_sandbox": True,
        }
        context = playwright.chromium.launch_persistent_context(
            str(profile),
            **launch_options,
        )
        context.route(
            "**/*",
            lambda route, request: _route_synthetic(route, request.url, blocked_requests),
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_content(
            "<!doctype html><title>stage10</title><main id='proof'>sandboxed</main>",
            wait_until="domcontentloaded",
        )
        if page.locator("#proof").inner_text() != "sandboxed":
            raise SandboxEvidenceError("RENDERER_PROOF_FAILED")

        evidence = _wait_for_chromium_evidence(proc_root, own, expected_profile)
        if blocked_requests:
            raise SandboxEvidenceError("SYNTHETIC_NETWORK_REQUESTED")
        return {
            "phase": "stage-10-chromium-sandbox",
            "verified": True,
            "container_uid": own.uid,
            "apparmor_enforced": True,
            "capabilities_dropped": True,
            "no_new_privileges": True,
            "seccomp_enforced": True,
            "chromium_process_count": evidence["chromium_process_count"],
            "chromium_user_namespace": True,
            "chromium_seccomp_bpf": True,
            "network_requests": 0,
            "no_sandbox_argument_absent": True,
        }
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        shutil.rmtree(profile, ignore_errors=True)


def _route_synthetic(route, url: str, blocked_requests: list[str]) -> None:
    if url.startswith(("http://", "https://")):
        blocked_requests.append("blocked")
        route.abort("blockedbyclient")
    else:
        route.continue_()


def _wait_for_chromium_evidence(
    proc_root: Path,
    own: ProcessEvidence,
    expected_profile: str,
) -> dict[str, int]:
    last_error = SandboxEvidenceError("CHROMIUM_PROCESS_NOT_FOUND")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        processes = list_chromium_processes(proc_root)
        try:
            return validate_chromium_evidence(own, processes, expected_profile)
        except SandboxEvidenceError as error:
            last_error = error
            time.sleep(0.1)
    raise last_error


def _validate_container_boundary(evidence: ProcessEvidence, expected_profile: str) -> None:
    if evidence.uid != EXPECTED_UID:
        raise SandboxEvidenceError("NON_ROOT_UID_REQUIRED")
    if evidence.effective_capabilities != 0:
        raise SandboxEvidenceError("OUTER_CAPABILITY_LEAK")
    if evidence.no_new_privileges != 1:
        raise SandboxEvidenceError("NO_NEW_PRIVILEGES_REQUIRED")
    if evidence.seccomp_mode != 2 or evidence.seccomp_filters < 1:
        raise SandboxEvidenceError("SECCOMP_FILTER_REQUIRED")
    if evidence.apparmor_profile != expected_profile:
        raise SandboxEvidenceError("APPARMOR_PROFILE_REQUIRED")


def validate_chromium_evidence(
    own: ProcessEvidence,
    processes: list[ProcessEvidence],
    expected_profile: str,
) -> dict[str, int]:
    _validate_container_boundary(own, expected_profile)
    if not processes:
        raise SandboxEvidenceError("CHROMIUM_PROCESS_NOT_FOUND")
    for process in processes:
        if FORBIDDEN_ARGUMENTS.intersection(process.arguments):
            raise SandboxEvidenceError("NO_SANDBOX_ARGUMENT_PRESENT")
        if process.uid == 0:
            raise SandboxEvidenceError("ROOT_CHROMIUM_FORBIDDEN")
        if process.uid != EXPECTED_UID:
            raise SandboxEvidenceError("CHROMIUM_UID_MISMATCH")
        if process.uid_map == own.uid_map and process.effective_capabilities != 0:
            raise SandboxEvidenceError("OUTER_CAPABILITY_LEAK")
        if process.no_new_privileges != 1:
            raise SandboxEvidenceError("CHROMIUM_NO_NEW_PRIVILEGES_REQUIRED")
        if process.seccomp_mode != 2:
            raise SandboxEvidenceError("CHROMIUM_SECCOMP_REQUIRED")
        if process.apparmor_profile != expected_profile:
            raise SandboxEvidenceError("CHROMIUM_APPARMOR_REQUIRED")

    sandboxed = [
        process
        for process in processes
        if process.uid_map != own.uid_map
        and process.effective_capabilities == 0
        and process.seccomp_filters > own.seccomp_filters
    ]
    if not sandboxed:
        raise SandboxEvidenceError("CHROMIUM_SANDBOX_EVIDENCE_MISSING")
    return {
        "chromium_process_count": len(processes),
        "sandboxed_process_count": len(sandboxed),
    }


def list_chromium_processes(proc_root: Path) -> list[ProcessEvidence]:
    processes: list[ProcessEvidence] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            arguments = _read_arguments(entry / "cmdline")
            executable = arguments[0].lower() if arguments else ""
            if not _is_chromium_executable(executable):
                continue
            processes.append(read_process_evidence(int(entry.name), proc_root, arguments))
        except (
            FileNotFoundError,
            PermissionError,
            ProcessLookupError,
            SandboxEvidenceError,
            ValueError,
        ):
            continue
    return processes


def _is_chromium_executable(executable: str) -> bool:
    """Accept only the browser pinned by the Collector image."""
    normalized = executable.replace("\\", "/")
    name = Path(normalized).name.lower()
    return "/ms-playwright/" in normalized and "chrome" in name


def read_process_evidence(
    pid: int,
    proc_root: Path = Path("/proc"),
    arguments: tuple[str, ...] | None = None,
) -> ProcessEvidence:
    process = proc_root / str(pid)
    status = _read_status(process / "status")
    apparmor = (process / "attr" / "current").read_text(encoding="utf-8").strip()
    return ProcessEvidence(
        pid=pid,
        arguments=arguments if arguments is not None else _read_arguments(process / "cmdline"),
        uid=int(status["Uid"].split()[0]),
        effective_capabilities=int(status["CapEff"], 16),
        no_new_privileges=int(status["NoNewPrivs"]),
        seccomp_mode=int(status["Seccomp"]),
        seccomp_filters=int(status["Seccomp_filters"]),
        apparmor_profile=apparmor.removesuffix(" (enforce)"),
        uid_map=(process / "uid_map").read_text(encoding="ascii").strip(),
    )


def _read_status(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key] = value.strip()
    required = {"Uid", "CapEff", "NoNewPrivs", "Seccomp", "Seccomp_filters"}
    if not required.issubset(values):
        raise SandboxEvidenceError("PROC_STATUS_INCOMPLETE")
    return values


def _read_arguments(path: Path) -> tuple[str, ...]:
    return tuple(
        value.decode("utf-8", errors="replace")
        for value in path.read_bytes().split(b"\0")
        if value
    )


if __name__ == "__main__":
    raise SystemExit(main())
