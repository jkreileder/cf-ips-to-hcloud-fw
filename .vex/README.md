# VEX statements

The [OpenVEX](https://openvex.dev) documents here tell Docker Scout that a vulnerability it reports
does not affect a specific package version in the container image.
Both Scout scans read them: the build-time scan in `.github/workflows/docker-build.yaml` and the
daily rescan in `.github/workflows/rescan.yaml`, via `vex-location: .vex`.
Scout only accepts statements whose `author` matches the workflows' `vex-author`
(`<jk@blackdown.de>`).

Grype does not read these files; its suppressions, if any, live in `.grype.yaml`.

Each statement names exact package versions (`pkg:apk/...@<version>`), so it stops applying as
soon as the image ships a different version, and a genuinely vulnerable version is still reported.
Every statement must state its removal condition below.

| File | Vulnerability | Why it is suppressed | Remove when |
| --- | --- | --- | --- |
| `cve-2026-107891.openvex.json` | CVE-2026-107891 in `musl` / `musl-utils` 1.2.6-r3 | Alpine 3.24 fixes it in 1.2.6-r3 (secdb `v3.24/main`), but Scout applies Alpine edge's 1.2.6-r6 threshold to 3.24 packages ([docker/scout-cli#248](https://github.com/docker/scout-cli/issues/248)). Grype reports it correctly. | Scout fixes docker/scout-cli#248, or the image no longer ships musl 1.2.6-r3 |
