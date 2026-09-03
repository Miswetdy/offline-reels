# ADR 015: Hardened Ubuntu Chromium Collector boundary

## Status

Accepted for Stage 10 repository preparation; Linux runtime acceptance is pending.

## Context

The Collector visits externally controlled pages and therefore requires
Chromium's Linux sandbox. Playwright disables Chromium sandboxing unless it is
explicitly enabled. Docker's default seccomp policy blocks the user-namespace
syscalls recommended for sandboxed Playwright crawling. Ubuntu 24.04 also
restricts unprivileged user namespaces through AppArmor; on the staging host,
plain non-root `unshare` is denied by the `unprivileged_userns` policy even
though the kernel and sysctls support user namespaces.

The sandbox must not be made functional with `--no-sandbox`, a root browser,
a privileged container, `SYS_ADMIN`, unconfined seccomp/AppArmor, host
networking, or a Docker socket mount.

## Decision

Set `chromium_sandbox=True` on the shared Collector Playwright launch. Run the
Collector image as UID/GID 10001 with every Linux capability dropped,
`no-new-privileges`, a read-only root filesystem, private `/dev/shm`, bounded
process/memory/CPU resources, and no published ports.

Use two reviewed host policies only for Collector containers:

1. A Moby default-deny seccomp allowlist pinned at
   `moby/profiles@61eaf32614c7c71b60bd8927d3e6a4ffc8ff1f31`, extended with
   Playwright's `clone`, `setns`, and `unshare` rule plus an unconditional
   `chroot` rule. Chromium's namespace sandbox uses `chroot` during its sandbox
   setup; the outer container still has `cap_drop: ALL`, so it is not granted
   `CAP_SYS_CHROOT`. All other capability-gated syscalls remain unchanged.
2. An enforcing AppArmor profile based on Moby `docker-default`, using ABI
   4.0 and adding `userns,` for this container label. The Ubuntu-wide userns
   restriction stays enabled.

Keep the live Collector an explicit one-shot Compose profile. Give it only
the internal application network plus a separate outbound network. Keep the
synthetic proof in a standalone Compose model with `network_mode: none`, no
secrets, no data services, no persistent volumes, and no ports.

Acceptance requires runtime evidence from `/proc`: non-root Chromium,
`NoNewPrivs=1`, enforcing AppArmor, seccomp filter mode, and no
`--no-sandbox`. Linux capabilities are interpreted relative to each process's
user namespace: the container and Chromium processes in its outer namespace
must have zero effective capabilities, while a Chromium zygote may temporarily
have capabilities inside a Chromium-created nested user namespace. Positive
sandbox evidence still requires a nested-namespace Chromium child with zero
effective capabilities and an additional seccomp-BPF filter.

## Consequences

The named AppArmor profile must be installed and loaded by a host operator
before Compose can create either Collector service. This small root-owned host
step is explicit and auditable; application deployment remains non-root.

The standalone smoke can fail closed on a kernel/Chromium incompatibility
before any OfflineReels data service or external network path is started. A
failure requires policy/runtime investigation, not a sandbox bypass. The
live profile → Collector chain remains gated until Linux synthetic acceptance
and a separately reviewed authenticated-profile bootstrap are complete.
