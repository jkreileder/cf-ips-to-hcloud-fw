#!/bin/sh
# Download the docker/scout-action binary with an authenticated request
# before the action step runs.
#
# The action downloads its binary from its GitHub release without passing
# its github-token (docker/scout-action#116). That anonymous request to
# api.github.com counts against the 60-per-hour limit of the runner's IP
# address, and on shared egress addresses it fails with HTTP 403. The action
# uses a binary that already sits in its dist/ directory instead of
# downloading one, so this script puts it there with GH_TOKEN.
#
# Every failure here only warns: the action then downloads the binary
# itself, as it would without this script. Remove it once the action
# authenticates the download (#1644).
#
# Needs GH_TOKEN plus the runner's RUNNER_WORKSPACE, RUNNER_OS and
# RUNNER_ARCH.

set -u

warn() {
    echo "::warning::Docker Scout binary prefetch: $1; the action downloads it itself"
}

case "${RUNNER_OS:-}/${RUNNER_ARCH:-}" in
Linux/X64) binary=docker-scout-action_linux_amd64 ;;
Linux/ARM64) binary=docker-scout-action_linux_arm64 ;;
*)
    warn "unsupported runner ${RUNNER_OS:-?}/${RUNNER_ARCH:-?}"
    exit 0
    ;;
esac

# The runner checks out every action of the job at setup, under
# _actions/<owner>/<repo>/<ref> next to the workspace directory.
actions_dir="$(dirname "$RUNNER_WORKSPACE")/_actions/docker/scout-action"
if [ ! -d "$actions_dir" ]; then
    warn "no docker/scout-action checkout under $actions_dir"
    exit 0
fi

found=0
for action_dir in "$actions_dir"/*/; do
    [ -f "${action_dir}index.js" ] || continue
    found=1
    dist="${action_dir}dist"

    if [ -f "$dist/$binary" ]; then
        echo "$dist/$binary already exists"
        continue
    fi

    # The bundled index.js names the release it downloads from.
    version=$(sed -n 's/^[[:space:]]*const version = "\(v[^"]*\)";$/\1/p' \
        "${action_dir}index.js" | head -n 1)
    if [ -z "$version" ]; then
        warn "no release version found in ${action_dir}index.js"
        continue
    fi

    # Download beside the target and rename it into place only when complete:
    # the action would run a truncated binary from dist/ without checking it.
    tmp=$(mktemp -d "${action_dir}prefetch.XXXXXX") || {
        warn "cannot create a temporary directory"
        continue
    }
    if gh release download "$version" --repo docker/scout-action \
        --pattern "$binary" --dir "$tmp" &&
        mkdir -p "$dist" && mv "$tmp/$binary" "$dist/$binary"; then
        echo "Prefetched $binary $version into $dist"
    else
        warn "downloading $binary $version failed"
    fi
    rm -rf "$tmp"
done

if [ "$found" -eq 0 ]; then
    warn "no docker/scout-action checkout under $actions_dir"
fi
exit 0
