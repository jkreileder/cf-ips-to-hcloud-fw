# VEX statements

The [OpenVEX](https://openvex.dev) documents here tell Docker Scout that a vulnerability it reports
does not affect a specific package version in the container image.
Both Scout scans read them: the build-time scan in `.github/workflows/docker-build.yaml` and the
daily rescan in `.github/workflows/rescan.yaml`, via `vex-location: .vex`.
Scout only accepts statements whose `author` matches the workflows' `vex-author`
(`<jk@blackdown.de>`).

Grype does not read these files; its suppressions, if any, live in `.grype.yaml`.

The statements take effect on `main` and tag builds, which scan the pushed image. A pull-request
build scans the image it loaded locally, and Scout still lists the finding there, so a new
statement is only seen to work on the first `main` build after it merges.

Each statement names exact package versions (`pkg:apk/...@<version>`), so it stops applying as
soon as the image ships a different version, and a genuinely vulnerable version is still reported.
Every statement must state its removal condition below.
Issue [#1584](https://github.com/jkreileder/cf-ips-to-hcloud-fw/issues/1584) tracks all scanner
suppressions, Scout's and Grype's; update it whenever a statement is added or removed.

| File | Vulnerability | Why it is suppressed | Remove when |
| --- | --- | --- | --- |
| `cve-2026-107891.openvex.json` | CVE-2026-107891 in `musl` / `musl-utils` 1.2.6-r3 | Alpine 3.24 fixes it in 1.2.6-r3 (secdb `v3.24/main`), but Scout applies Alpine edge's 1.2.6-r6 threshold to 3.24 packages ([docker/scout-cli#248](https://github.com/docker/scout-cli/issues/248)). Grype reports it correctly. | Scout fixes docker/scout-cli#248, or the image no longer ships musl 1.2.6-r3 |
| `openssl-3.5.9-r0.openvex.json` | CVE-2026-88822, CVE-2026-88823, CVE-2026-95691, CVE-2026-95692, CVE-2026-107496 in `openssl` / `libssl3` / `libcrypto3` 3.5.9-r0 | All five are rated Low by OpenSSL ([advisory](https://openssl-library.org/news/secadv/20261110.txt)) and sit in code the image never runs: the QUIC client, AES-GCM-SIV and `CMS_encrypt()`. The image only makes TLS connections over TCP through Python's `ssl` module. Alpine fixed them in edge's 3.5.9-r1; the 3.24 backport ([aports!111652](https://gitlab.alpinelinux.org/alpine/aports/-/merge_requests/111652)) is unmerged, and Scout applies the edge fix to 3.24 packages. | The image ships openssl 3.5.9-r1 or later (the statement then no longer matches) |
