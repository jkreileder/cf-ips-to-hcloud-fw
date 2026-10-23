# Build policy for Dockerfile, loaded automatically by buildx (>= 0.31) for
# every build of it, local and CI alike. Deny by default: the build context is
# allowed, and images only from the repositories below and only when pinned by
# digest. Nothing else (ADD of URLs or git repositories) is allowed.
#
# Image signatures are not checked here: astral/uv keeps its signed provenance
# in GitHub's attestation store, not in the registry, so `input.image.signatures`
# is empty for it. The docker-build workflow verifies that with
# `gh attestation verify` instead.
package docker

default allow := false

# Base images, the `# syntax=` frontend, and the SBOM scanner that the
# docker-build workflow passes to buildx as `--sbom generator=` on push builds.
allowed_repos := {
	"docker.io/astral/uv",
	"docker.io/docker/dockerfile",
	"docker.io/docker/scout-sbom-indexer",
	"docker.io/library/python",
}

allow if input.local

allow if {
	input.image.fullRepo in allowed_repos
	input.image.isCanonical
}

deny_msg contains msg if {
	not allow
	input.image
	not input.image.fullRepo in allowed_repos
	msg := sprintf("image %s is not in the allowed repositories", [input.image.ref])
}

deny_msg contains msg if {
	not allow
	input.image
	not input.image.isCanonical
	msg := sprintf("image %s is not pinned by digest", [input.image.ref])
}

decision := {"allow": allow, "deny_msg": deny_msg}
