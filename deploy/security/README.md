# Chromium security policies

`chromium-seccomp.json` основан на Moby default allowlist:
`moby/profiles@61eaf32614c7c71b60bd8927d3e6a4ffc8ff1f31` (Apache-2.0).
Delta: clone/setns/unshare для Chromium user namespace и unconditional chroot
для namespace sandbox setup. Outer container по-прежнему cap_drop ALL;
CAP_SYS_CHROOT не выдаётся.

`offline-reels-collector.apparmor` основан на docker-default того же revision,
ABI 4.0, с Unix sockets и userns только для named profile.
Profile enforcing; host-wide Ubuntu userns restrictions не отключаются.

Изменение baseline требует diff review и повторной networkless
[Linux sandbox приёмки](../../docs/operations/stage-10-linux-staging.md).
Не заменять policies на unconfined и не включать --no-sandbox.
