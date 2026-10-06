# ADR 015: Linux Chromium sandbox

Принято. Collector включает `chromium_sandbox=True`; UID/GID 10001,
cap_drop ALL, no-new-privileges, read-only rootfs, private shm,
bounded resources и отсутствие опубликованных портов обязательны.

Seccomp: pinned Moby default-deny плюс clone/setns/unshare и unconditional chroot.
AppArmor: enforcing docker-default-derived profile с userns только для
`offline-reels-collector`. Host-wide Ubuntu userns restrictions сохраняются.
Происхождение policies — [security README](../../deploy/security/README.md).

Networkless smoke должен подтвердить outer UID/capabilities, NoNewPrivs,
AppArmor, Docker seccomp и nested-namespace Chromium child с нулевыми
capabilities и дополнительным seccomp-BPF. Все HTTP(S) requests отсутствуют.
Capabilities zygote внутри его namespace не равны host capabilities.

Нельзя исправлять сбой через no-sandbox/root/privileged/SYS_ADMIN,
unconfined policies, host networking или Docker socket.
После изменения host/browser/policies повторяется runtime smoke.
