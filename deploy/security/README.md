# Stage 10 Chromium security profiles

`chromium-seccomp.json` is the Moby default seccomp allowlist pinned at
`moby/profiles@61eaf32614c7c71b60bd8927d3e6a4ffc8ff1f31`, with one rule prepended
to allow `clone`, `setns`, and `unshare`. This is the narrow delta recommended
by Playwright for a sandboxed non-root Chromium container. Kernel capability
checks still apply, and Compose drops every capability.
The upstream Moby profile is distributed under Apache-2.0; its immutable
source revision is recorded above for review and regeneration.

`offline-reels-collector.apparmor` follows the same pinned Moby
`docker-default` rules under ABI 4.0, explicitly retains Unix sockets, and
adds only `userns,`. Ubuntu 24.04 otherwise
applies its `unprivileged_userns` restriction before Chromium can establish
its sandbox. The profile remains enforcing; it is not an AppArmor
`flags=(unconfined)` workaround.

When updating either upstream baseline, review the diff and repeat the full
Stage 10 Linux synthetic acceptance. Never replace these files with
`seccomp=unconfined` or disable the Ubuntu host-wide userns restriction.
