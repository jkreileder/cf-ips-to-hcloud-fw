"""Plan and prepare automated security releases.

Used by the auto-release workflows. The version, changelog and pinned-version
edits mirror the manual cut-release procedure, so a release made here looks the
same as one cut by hand. Standard library only: the workflows run it with the
runner's system Python, without syncing the project environment.

Subcommands:

- ``plan``: compare Grype JSON reports of the released image and a fresh
  ``main`` image, and decide whether ``main`` fixes anything worth releasing.
- ``apply-release`` / ``apply-dev-cycle``: edit the version files in place.
- ``notes``: print a version's CHANGELOG entry (the GitHub release body).
- ``commit``: create a branch and a single GitHub-signed commit through the
  GraphQL API (``createCommitOnBranch``), so no signing key is needed.
- ``await-merge``: wait for an auto-merge PR, keeping it current with main.
- ``verify``: check the image built for a release tag against the fixes its
  CHANGELOG entry claims.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap
import time
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NoReturn

PYPROJECT = Path("pyproject.toml")
UV_LOCK = Path("uv.lock")
CHANGELOG = Path("CHANGELOG.md")
DOCKERFILE = Path("Dockerfile")
# Files that pin the latest released version in examples.
PINNED_VERSION_FILES = (
    Path("README.md"),
    Path(".github/ISSUE_TEMPLATE/bug_report.md"),
)
PROJECT_NAME = "cf-ips-to-hcloud-fw"
WRAP_WIDTH = 100
DEV_CYCLE_BULLET = "- Start new development cycle"
# CHANGELOG headings separate the version and the date with an en dash.
DASH = "\N{EN DASH}"

FINAL_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
DEV_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.dev\d+$")
PYPROJECT_VERSION_RE = re.compile(r'^version = "([^"]+)"$', re.MULTILINE)
UV_LOCK_VERSION_RE = re.compile(
    rf'(^name = "{re.escape(PROJECT_NAME)}"\nversion = ")[^"]+(")', re.MULTILINE
)
CHANGELOG_UNRELEASED_RE = re.compile(
    rf"^## \[v([^\]]+)\] {DASH} Unreleased$", re.MULTILINE
)
CHANGELOG_HEADING_RE = re.compile(r"^## \[v", re.MULTILINE)
PIN_RE = re.compile(rf"\b{re.escape(PROJECT_NAME)}:(\d+\.\d+\.\d+)\b")
MINOR_TAG_RE = re.compile(
    r"`\d+\.\d+`(: This tag always points to the latest )`\d+\.\d+\.x`"
)
# A "**Security:** Fixed <id> (<severity>) in `a` and `b`, ..." bullet,
# matched on unwrapped text.
SECURITY_BULLET_RE = re.compile(
    r"\*\*Security:\*\* Fixed (\S+?)(?: \([a-z]+\))? in ((?:`[^`]+`(?:, | and )?)+),"
)
FROM_RE = re.compile(
    r"^FROM\s+(?:--platform=\S+\s+)?(\S+?):([^@\s]+)@(sha256:[0-9a-f]+)\s+AS\s+(\S+)",
    re.MULTILINE | re.IGNORECASE,
)

Version = tuple[int, int, int]


@dataclass(frozen=True)
class Finding:
    """One fixable vulnerability match in one package."""

    vulnerability: str
    severity: str
    package: str
    installed: str
    fixed_in: tuple[str, ...]


def fail(message: str) -> NoReturn:
    """Exit with a GitHub Actions error annotation.

    Raises:
        SystemExit: Always, with status 1.
    """
    sys.stderr.write(f"::error::{message}\n")
    raise SystemExit(1)


def parse_final(version: str) -> Version:
    """Parse ``X.Y.Z`` into a comparable tuple.

    Returns:
        Version: The major, minor and patch numbers.
    """
    match = FINAL_VERSION_RE.match(version)
    if match is None:
        fail(f"not a final X.Y.Z version: {version!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def format_version(version: Version) -> str:
    """Format a version tuple.

    Returns:
        str: The version as ``X.Y.Z``.
    """
    return ".".join(str(part) for part in version)


def git(*args: str) -> str:
    """Run git in the current directory.

    Returns:
        str: The command's standard output, stripped.
    """
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        ["git", *args],  # ruff: ignore[start-process-with-partial-path]
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def released_versions() -> list[Version]:
    """List the repository's final release tags.

    Returns:
        list[Version]: Every ``vX.Y.Z`` tag, ascending.
    """
    tags = git("tag", "--list", "v*").splitlines()
    return sorted(
        parse_final(tag[1:]) for tag in tags if FINAL_VERSION_RE.match(tag[1:])
    )


def project_version() -> str:
    """Read the project version.

    Returns:
        str: The ``version`` from pyproject.toml.
    """
    match = PYPROJECT_VERSION_RE.search(PYPROJECT.read_text(encoding="utf-8"))
    if match is None:
        fail("could not read the version from pyproject.toml")
    return match.group(1)


def next_release(last: Version, current: str) -> Version:
    """Choose the patch release that follows the highest tag.

    Automated releases are security patches only. A dev version heading for a
    new minor or major means feature work is on main, and a final version above
    the highest tag means a release merged but was never tagged; both need a
    person. The result always sorts after every existing tag: a version whose
    publish failed is burned (Docker Hub tags are immutable).

    Returns:
        Version: The version to release.
    """
    following = (last[0], last[1], last[2] + 1)
    dev = DEV_VERSION_RE.match(current)
    if dev is not None:
        major, minor, patch = (int(part) for part in dev.groups())
        if (major, minor) != last[:2]:
            fail(
                f"main is heading for {major}.{minor}.{patch} (from {current}), "
                "not a patch release; cut this one by hand"
            )
        return max((major, minor, patch), following)
    if parse_final(current) > last:
        fail(
            f"main is at {current}, which is not tagged yet; finish that "
            "release (cut-release steps 7-10) before another one"
        )
    return following


def unreleased_span(text: str) -> tuple[int, int]:
    """Locate the CHANGELOG's Unreleased section.

    Returns:
        tuple[int, int]: Start and end offsets of the section, or an empty span
        before the first release heading when there is none.
    """
    unreleased = CHANGELOG_UNRELEASED_RE.search(text)
    if unreleased is None:
        first = CHANGELOG_HEADING_RE.search(text)
        position = first.start() if first else len(text)
        return position, position
    following = CHANGELOG_HEADING_RE.search(text, unreleased.end())
    return unreleased.start(), following.start() if following else len(text)


def unreleased_entries(text: str) -> str:
    """Read the hand-written part of the CHANGELOG's Unreleased section.

    Returns:
        str: The section's entries other than the dev-cycle bullet.
    """
    start, end = unreleased_span(text)
    body = CHANGELOG_UNRELEASED_RE.sub("", text[start:end], count=1)
    return body.replace(DEV_CYCLE_BULLET, "").strip()


FindingKey = tuple[str, str]


@dataclass(frozen=True)
class Report:
    """The parts of a Grype JSON report the plan needs."""

    labels: dict[str, str]
    findings: dict[FindingKey, Finding]

    def label(self, name: str) -> str:
        """Read an OCI label of the scanned image.

        Returns:
            str: The label's value, or an empty string when it is missing.
        """
        return self.labels.get(name, "")


def load_report(path: Path) -> Report:
    """Load a Grype JSON report.

    Findings are keyed by (vulnerability, package), and matches for several
    copies or versions of a package merge into one finding. A vulnerability
    counts as fixed only when no copy of the package has it any more: neither
    versions nor locations identify a copy reliably (a Python package's path
    contains its version, so an in-place upgrade moves it).

    Returns:
        Report: The scanned image's labels and its findings.
    """
    report = json.loads(path.read_text(encoding="utf-8"))
    labels = (report.get("source") or {}).get("target", {}).get("labels") or {}
    findings: dict[FindingKey, Finding] = {}
    for match in report.get("matches") or []:
        vulnerability = match["vulnerability"]
        artifact = match["artifact"]
        fix = vulnerability.get("fix") or {}
        key = (vulnerability["id"], artifact["name"])
        installed: set[str] = {artifact["version"]}
        fixed_in: set[str] = set(fix.get("versions") or ())
        if key in findings:
            installed |= set(findings[key].installed.split(", "))
            fixed_in |= set(findings[key].fixed_in)
        findings[key] = Finding(
            vulnerability=key[0],
            severity=str(vulnerability.get("severity") or "Unknown"),
            package=key[1],
            installed=", ".join(sorted(installed)),
            fixed_in=tuple(sorted(fixed_in)),
        )
    return Report(labels={k: str(v) for k, v in labels.items()}, findings=findings)


def code_list(items: list[str]) -> str:
    """Join names as inline code in prose.

    Returns:
        str: ``a``, ``a` and `b``, or ``a`, `b` and `c``.
    """
    quoted = [f"`{item}`" for item in items]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def bullet(text: str) -> str:
    """Wrap a CHANGELOG bullet at the repository's Markdown width.

    Returns:
        str: The bullet, with continuation lines indented by two spaces.
    """
    return textwrap.fill(
        text,
        width=WRAP_WIDTH,
        initial_indent="- ",
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def security_bullets(fixed: list[Finding], previous: str) -> list[str]:
    """Describe fixed findings, one bullet per vulnerability.

    Returns:
        list[str]: CHANGELOG bullets marked ``**Security:**``.
    """
    by_id: dict[str, list[Finding]] = {}
    for finding in fixed:
        by_id.setdefault(finding.vulnerability, []).append(finding)
    bullets = []
    for vulnerability, findings in sorted(by_id.items()):
        severity = findings[0].severity.lower()
        label = (
            vulnerability if severity == "unknown" else f"{vulnerability} ({severity})"
        )
        packages = code_list(sorted({finding.package for finding in findings}))
        installed = ", ".join(sorted({finding.installed for finding in findings}))
        fixed_in = ", ".join(
            sorted({version for finding in findings for version in finding.fixed_in})
        )
        text = (
            f"**Security:** Fixed {label} in {packages}, "
            f"which the v{previous} image shipped at {installed}"
        )
        if fixed_in:
            text += f" (fixed in {fixed_in})"
        bullets.append(bullet(text))
    return bullets


def short_image(name: str) -> str:
    """Drop the Docker Hub registry and library prefixes from an image name.

    Returns:
        str: ``python`` for ``docker.io/library/python``, and so on.
    """
    for prefix in ("docker.io/library/", "docker.io/"):
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return name


def dockerfile_stages(dockerfile: str) -> dict[str, tuple[str, str, str]]:
    """Map each pinned ``FROM ... AS stage`` to its image.

    Stages are keyed by their ``AS`` name because one image (``python``) can
    back several stages with different tags.

    Returns:
        dict[str, tuple[str, str, str]]: Stage name to (image, tag, digest).
    """
    return {
        alias: (short_image(name), tag, digest)
        for name, tag, digest, alias in FROM_RE.findall(dockerfile)
    }


def base_image_bullet(previous_tag: str) -> str | None:
    """Summarize Dockerfile FROM changes since the previous release.

    Each image is named once with its version change, e.g. ``python`` 3.15.0
    → 3.15.1 for both its alpine and trixie stages. The full tags appear only
    when more than the version moved (say, a new Alpine release). An image
    whose tags kept their version reads as new digests.

    Returns:
        str | None: A CHANGELOG bullet, or None when no pinned image changed.
    """
    old = dockerfile_stages(git("show", f"{previous_tag}:{DOCKERFILE}"))
    new = dockerfile_stages(DOCKERFILE.read_text(encoding="utf-8"))
    moved: dict[str, list[str]] = {}
    redigested: dict[str, list[str]] = {}
    for alias, (name, tag, digest) in new.items():
        if alias not in old or old[alias] == (name, tag, digest):
            continue
        old_tag = old[alias][1]
        old_version, _, old_rest = old_tag.partition("-")
        version, _, rest = tag.partition("-")
        if old_tag == tag:
            target, change = redigested, version
        elif old_rest == rest:
            target, change = moved, f"{old_version} → {version}"
        else:
            target, change = moved, f"{old_tag} → {tag}"
        changes = target.setdefault(name, [])
        if change not in changes:
            changes.append(change)
    parts = [f"`{name}` {' and '.join(changes)}" for name, changes in moved.items()]
    parts += [
        f"new `{name}:{version}` digests"
        for name, versions in redigested.items()
        if name not in moved
        for version in versions
    ]
    if not parts:
        return None
    return bullet(f"Refreshed the pinned base images ({', '.join(parts)})")


def runtime_packages(lock: str) -> dict[str, str]:
    """Resolve the project's runtime dependency closure from a uv.lock.

    Follows each package's ``dependencies`` from the project entry, leaving
    out dev dependencies, which never ship in the image or the wheel.

    Returns:
        dict[str, str]: Package name to version (several versions joined).
    """
    entries: dict[str, list[dict[str, object]]] = {}
    for package in tomllib.loads(lock).get("package", []):
        entries.setdefault(str(package["name"]), []).append(package)
    found: dict[str, str] = {}
    pending = [PROJECT_NAME]
    while pending:
        name = pending.pop()
        if name in found or name not in entries:
            continue
        versions = sorted({str(entry.get("version", "")) for entry in entries[name]})
        found[name] = ", ".join(versions)
        for entry in entries[name]:
            dependencies = entry.get("dependencies") or []
            assert isinstance(dependencies, list)  # ruff: ignore[assert]
            pending.extend(str(dependency["name"]) for dependency in dependencies)
    found.pop(PROJECT_NAME, None)
    return found


def dependency_bullet(previous_tag: str) -> str | None:
    """Summarize runtime dependency changes since the previous release.

    Returns:
        str | None: A CHANGELOG bullet, or None when nothing changed.
    """
    old = runtime_packages(git("show", f"{previous_tag}:{UV_LOCK}"))
    new = runtime_packages(UV_LOCK.read_text(encoding="utf-8"))
    parts = [
        f"`{name}` {old[name]} → {version}"
        for name, version in sorted(new.items())
        if name in old and old[name] != version
    ]
    parts += [
        f"`{name}` {version} (new)"
        for name, version in sorted(new.items())
        if name not in old
    ]
    parts += [f"`{name}` (removed)" for name in sorted(old) if name not in new]
    if not parts:
        return None
    return bullet(f"Updated the runtime dependencies ({', '.join(parts)})")


def write_outputs(**values: str) -> None:
    """Append step outputs for later workflow steps and echo them."""
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(lines)
    sys.stdout.write(lines)


def cmd_plan(args: argparse.Namespace) -> None:
    """Decide whether main fixes findings that the released image still has.

    The released report holds only fixable findings, the candidate report all
    of them: a vulnerability that main still has without a published fix must
    not count as fixed just because an only-fixed scan leaves it out.

    The ``previous`` output is the version inside the scanned release image,
    which can trail the highest tag (a burned version, or a rehearsal against
    an older image). The CHANGELOG names that image and diffs against it.
    """
    released_report = load_report(args.released)
    candidate_report = load_report(args.candidate)
    shipped = released_report.label("org.opencontainers.image.version")
    if not FINAL_VERSION_RE.match(shipped):
        fail(f"the released image has no final version label (got {shipped!r})")
    released = released_report.findings
    candidate = candidate_report.findings
    fixed = [finding for key, finding in released.items() if key not in candidate]
    for key, finding in candidate.items():
        if key not in released and finding.fixed_in:
            sys.stderr.write(
                "::warning::main has a fixable finding the release does not: "
                f"{finding.vulnerability} in {finding.package} {finding.installed}\n"
            )
    versions = released_versions()
    if not versions:
        fail("no vX.Y.Z tags found; fetch tags before planning")
    if not fixed:
        write_outputs(release="false", previous=shipped)
        return
    version = next_release(versions[-1], project_version())
    hand_written = unreleased_entries(CHANGELOG.read_text(encoding="utf-8"))
    if hand_written:
        fail(
            "the CHANGELOG's Unreleased section has hand-written entries; "
            "automated releases only ship security fixes, so cut this one by hand"
        )
    args.fixed_out.write_text(
        json.dumps([asdict(finding) for finding in fixed], indent=2) + "\n",
        encoding="utf-8",
    )
    write_outputs(release="true", version=format_version(version), previous=shipped)


def replace_version_pins(new: str) -> None:
    """Point the documented example version at the new release.

    The old version is whatever the README pins now, which need not be the
    previous release. Only pin-shaped occurrences change (image references,
    ``VERSION=``, the tag list entry and the issue template example), so prose
    that mentions an old version stays as written.
    """
    readme = PINNED_VERSION_FILES[0].read_text(encoding="utf-8")
    current = PIN_RE.search(readme)
    if current is None:
        fail(f"no `{PROJECT_NAME}:X.Y.Z` pin found in {PINNED_VERSION_FILES[0]}")
    old = re.escape(current.group(1))
    pattern = re.compile(
        rf"(?<=\b{re.escape(PROJECT_NAME)}:){old}(?!\d)"
        rf"|(?<=\bVERSION=){old}(?!\d)"
        rf"|(?<=^- `){old}(?=`: This tag points to the specific `)"
        rf"|(?<=This tag points to the specific `){old}(?=` release)"
        rf"|(?<=\[e\.g\. ){old}(?=\])",
        re.MULTILINE,
    )
    for path in PINNED_VERSION_FILES:
        text, count = pattern.subn(new, path.read_text(encoding="utf-8"))
        if count == 0:
            fail(f"no version pins to update in {path}")
        path.write_text(text, encoding="utf-8")
    # The README also describes the floating major.minor tag.
    major, minor, _ = parse_final(new)
    readme = PINNED_VERSION_FILES[0].read_text(encoding="utf-8")
    PINNED_VERSION_FILES[0].write_text(
        MINOR_TAG_RE.sub(f"`{major}.{minor}`\\g<1>`{major}.{minor}.x`", readme),
        encoding="utf-8",
    )


def set_project_version(version: str) -> None:
    """Set the version in pyproject.toml and the project's uv.lock entry."""
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    PYPROJECT.write_text(
        PYPROJECT_VERSION_RE.sub(f'version = "{version}"', pyproject, count=1),
        encoding="utf-8",
    )
    lock, count = UV_LOCK_VERSION_RE.subn(
        rf"\g<1>{version}\g<2>", UV_LOCK.read_text(encoding="utf-8")
    )
    if count != 1:
        fail(f"expected one {PROJECT_NAME} entry in uv.lock, found {count}")
    UV_LOCK.write_text(lock, encoding="utf-8")


def read_fixed(path: Path) -> list[Finding]:
    """Read the findings written by ``plan``.

    Returns:
        list[Finding]: The findings the release fixes.
    """
    return [
        Finding(
            vulnerability=item["vulnerability"],
            severity=item["severity"],
            package=item["package"],
            installed=item["installed"],
            fixed_in=tuple(item["fixed_in"]),
        )
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]


def cmd_apply_release(args: argparse.Namespace) -> None:
    """Edit the version files for a release."""
    version, previous = args.version, args.previous
    bullets = security_bullets(read_fixed(args.fixed), previous)

    # The Unreleased section holds only the dev-cycle bullet (plan refuses to
    # release over hand-written entries), so the release entry replaces it.
    text = CHANGELOG.read_text(encoding="utf-8")
    start, end = unreleased_span(text)
    for extra in (dependency_bullet(f"v{previous}"), base_image_bullet(f"v{previous}")):
        if extra:
            bullets.append(extra)
    section = f"## [v{version}] {DASH} {args.date}\n\n" + "\n".join(bullets) + "\n\n"
    CHANGELOG.write_text(text[:start] + section + text[end:], encoding="utf-8")

    set_project_version(version)
    replace_version_pins(version)


def cmd_apply_dev_cycle(args: argparse.Namespace) -> None:
    """Start the next patch's development cycle after a release.

    Does nothing unless main is still at the version just released: a person
    may have started the next cycle, or cut another release, while this one
    was publishing.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    if project_version() != args.version or CHANGELOG_UNRELEASED_RE.search(text):
        return
    major, minor, patch = parse_final(args.version)
    upcoming = format_version((major, minor, patch + 1))
    set_project_version(f"{upcoming}.dev1")
    # Without an Unreleased section this is the spot before the first release.
    position, _ = unreleased_span(text)
    section = f"## [v{upcoming}] {DASH} Unreleased\n\n{DEV_CYCLE_BULLET}\n\n"
    CHANGELOG.write_text(text[:position] + section + text[position:], encoding="utf-8")


def changelog_entry(version: str) -> str:
    """Read a version's CHANGELOG entry without its heading.

    Returns:
        str: The entry's bullets.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    heading = re.search(
        rf"^## \[v{re.escape(version)}\] {DASH} .*$", text, re.MULTILINE
    )
    if heading is None:
        fail(f"no CHANGELOG entry for v{version}")
    following = CHANGELOG_HEADING_RE.search(text, heading.end())
    end = following.start() if following else len(text)
    return text[heading.end() : end].strip()


def cmd_notes(args: argparse.Namespace) -> None:
    """Print a version's CHANGELOG entry without its heading."""
    sys.stdout.write(changelog_entry(args.version) + "\n")


def claimed_fixes(entry: str) -> list[FindingKey]:
    """List the (vulnerability, package) pairs a CHANGELOG entry says it fixes.

    Reads the ``**Security:** Fixed ...`` bullets ``security_bullets`` writes.

    Returns:
        list[FindingKey]: One pair per vulnerability and package.
    """
    claims: list[FindingKey] = []
    for match in SECURITY_BULLET_RE.finditer(" ".join(entry.split())):
        packages = re.findall(r"`([^`]+)`", match.group(2))
        claims.extend((match.group(1), package) for package in packages)
    return claims


def cmd_verify(args: argparse.Namespace) -> None:
    """Check that the built release image has none of the fixes it claims.

    The release can include commits merged after the scan that planned it,
    so the claims are checked against the image actually built for the tag
    before the release is published.
    """
    claims = claimed_fixes(changelog_entry(args.version))
    if not claims:
        fail(f"the v{args.version} CHANGELOG entry claims no security fixes")
    findings = load_report(args.report).findings
    still_there = [
        f"{vuln} in {package}"
        for vuln, package in claims
        if (vuln, package) in findings
    ]
    if still_there:
        fail(
            f"the v{args.version} image still has vulnerabilities its CHANGELOG "
            f"claims as fixed: {', '.join(still_there)}"
        )
    sys.stdout.write(
        f"v{args.version} image verified: {len(claims)} claimed fixes absent\n"
    )


def run_gh(*args: str, payload: object = None) -> subprocess.CompletedProcess[str]:
    """Run gh, sending ``payload`` as JSON on standard input.

    Returns:
        subprocess.CompletedProcess[str]: The finished process, which may
        have failed.
    """
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        ["gh", *args],  # ruff: ignore[start-process-with-partial-path]
        check=False,
        capture_output=True,
        text=True,
        input=json.dumps(payload) if payload is not None else None,
    )


def gh_error(args: tuple[str, ...], result: subprocess.CompletedProcess[str]) -> str:
    """Describe a failed gh call; gh prints the API's error (GraphQL too).

    Returns:
        str: The command and its collapsed error output.
    """
    details = " ".join((result.stderr + result.stdout).split())
    return f"gh {' '.join(args[:2])} failed: {details}"


def gh(*args: str) -> str:
    """Run a gh command and fail the run if it fails.

    Returns:
        str: The command's standard output, stripped.
    """
    result = run_gh(*args)
    if result.returncode != 0:
        fail(gh_error(args, result))
    return result.stdout.strip()


def gh_api(*args: str, payload: object = None) -> dict[str, object]:
    """Call ``gh api`` and fail the run if the call fails.

    Returns:
        dict[str, object]: The decoded JSON response.
    """
    stdin_args = ("--input", "-") if payload is not None else ()
    command = ("api", *args, *stdin_args)
    result = run_gh(*command, payload=payload)
    if result.returncode != 0:
        fail(gh_error(command, result))
    return json.loads(result.stdout)


COMMIT_MUTATION = """
mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) { commit { oid } }
}
"""


def branch_exists(repo: str, branch: str) -> bool:
    """Check whether a branch exists on GitHub.

    Returns:
        bool: True if ``refs/heads/<branch>`` exists.
    """
    return run_gh("api", f"repos/{repo}/git/ref/heads/{branch}").returncode == 0


def bot_signoff(app_slug: str) -> str:
    """Build the DCO sign-off for the App's bot account.

    Returns:
        str: A ``Signed-off-by:`` trailer with the bot's noreply address.
    """
    bot = f"{app_slug}[bot]"
    user = gh_api(f"users/{app_slug}%5Bbot%5D")
    return f"Signed-off-by: {bot} <{user['id']}+{bot}@users.noreply.github.com>"


def cmd_commit(args: argparse.Namespace) -> None:
    """Point a branch at the base commit and add one signed commit to it.

    The commit holds every file the ``apply-*`` subcommands edited in the
    working tree (``git diff``), so callers don't repeat the file list. A
    branch left over from an earlier failed or abandoned attempt is reset: the
    workflows only get here when no PR from these branches is open.
    """
    ref = f"refs/heads/{args.branch}"
    if branch_exists(args.repo, args.branch):
        gh_api(
            f"repos/{args.repo}/git/{ref}",
            "--method",
            "PATCH",
            payload={"sha": args.base_sha, "force": True},
        )
    else:
        gh_api(
            f"repos/{args.repo}/git/refs",
            "--method",
            "POST",
            payload={"ref": ref, "sha": args.base_sha},
        )
    signoff = bot_signoff(args.app_slug)
    additions = [
        {
            "path": path,
            "contents": base64.b64encode(Path(path).read_bytes()).decode("ascii"),
        }
        for path in git("diff", "--name-only").splitlines()
    ]
    if not additions:
        fail("no edited files to commit")
    message = {"headline": args.headline, "body": signoff}
    commit_input = {
        "branch": {"repositoryNameWithOwner": args.repo, "branchName": args.branch},
        # Fails the mutation if the branch moved since it was created.
        "expectedHeadOid": args.base_sha,
        "message": message,
        "fileChanges": {"additions": additions},
    }
    response = gh_api(
        "graphql",
        payload={"query": COMMIT_MUTATION, "variables": {"input": commit_input}},
    )
    data = response.get("data")
    if response.get("errors") or not isinstance(data, dict):
        fail(f"createCommitOnBranch failed: {response.get('errors')}")
    write_outputs(sha=data["createCommitOnBranch"]["commit"]["oid"], signoff=signoff)


def cmd_await_merge(args: argparse.Namespace) -> None:
    """Wait for an auto-merge PR to merge, keeping it current with main.

    Strict up-to-date checks block auto-merge whenever main moves, and GitHub
    does not update the branch by itself. Updating by rebase keeps the PR's
    one signed-off commit (a merge update would add a commit without a DCO
    sign-off). A conflict cannot resolve itself, so it fails right away.

    The merge state lags behind an update, so the branch is updated at most
    once per head commit.
    """
    deadline = time.monotonic() + args.minutes * 60
    last = updated_head = ""
    while time.monotonic() < deadline:
        time.sleep(30)
        state, merge_state, head = gh(
            "pr", "view", args.url, "--json", "state,mergeStateStatus,headRefOid",
            "--jq", '"\\(.state) \\(.mergeStateStatus) \\(.headRefOid)"',
        ).split()  # fmt: skip
        if f"{state} {merge_state}" != last:
            last = f"{state} {merge_state}"
            sys.stdout.write(f"{args.url}: {last}\n")
        if state == "MERGED":
            return
        if state == "CLOSED":
            fail(f"{args.url} was closed without merging")
        if merge_state == "DIRTY":
            fail(f"{args.url} conflicts with main; resolve it by hand")
        if merge_state == "BEHIND" and head != updated_head:
            updated_head = head
            result = run_gh("pr", "update-branch", args.url, "--rebase")
            if result.returncode != 0:
                # A GitHub App cannot move a branch across commits that
                # change workflow files without the Workflows permission.
                fail(
                    f"could not update {args.url} with main "
                    f"({gh_error(('pr', 'update-branch'), result)}); update it by hand"
                )
    fail(f"{args.url} did not merge within {args.minutes} minutes (last: {last})")


def cmd_version(args: argparse.Namespace) -> None:
    """Print the project version, optionally requiring a final release."""
    version = project_version()
    if args.require_final and not FINAL_VERSION_RE.match(version):
        fail(f"pyproject.toml has non-final version {version!r}")
    sys.stdout.write(version + "\n")


def main() -> None:
    """Dispatch to a subcommand."""
    parser = argparse.ArgumentParser(description="Plan and prepare releases.")
    sub = parser.add_subparsers(required=True)

    plan = sub.add_parser("plan", help="decide whether to release")
    plan.add_argument("--released", type=Path, required=True)
    plan.add_argument("--candidate", type=Path, required=True)
    plan.add_argument("--fixed-out", type=Path, required=True)
    plan.set_defaults(func=cmd_plan)

    release = sub.add_parser("apply-release", help="edit files for a release")
    release.add_argument("--version", required=True)
    release.add_argument("--previous", required=True)
    release.add_argument("--fixed", type=Path, required=True)
    release.add_argument("--date", default=dt.datetime.now(dt.UTC).date().isoformat())
    release.set_defaults(func=cmd_apply_release)

    dev = sub.add_parser("apply-dev-cycle", help="start the next dev cycle")
    dev.add_argument("--version", required=True, help="the version just released")
    dev.set_defaults(func=cmd_apply_dev_cycle)

    notes = sub.add_parser("notes", help="print a CHANGELOG entry")
    notes.add_argument("--version", required=True)
    notes.set_defaults(func=cmd_notes)

    commit = sub.add_parser("commit", help="create a branch with one signed commit")
    commit.add_argument("--repo", required=True)
    commit.add_argument("--branch", required=True)
    commit.add_argument("--base-sha", required=True)
    commit.add_argument("--headline", required=True)
    commit.add_argument("--app-slug", required=True, help="signs off as its bot")
    commit.set_defaults(func=cmd_commit)

    await_merge = sub.add_parser("await-merge", help="wait for a PR to merge")
    await_merge.add_argument("url")
    await_merge.add_argument("--minutes", type=int, default=45)
    await_merge.set_defaults(func=cmd_await_merge)

    verify = sub.add_parser("verify", help="check a built image for claimed fixes")
    verify.add_argument("--version", required=True)
    verify.add_argument("--report", type=Path, required=True, help="Grype JSON")
    verify.set_defaults(func=cmd_verify)

    version = sub.add_parser("version", help="print the project version")
    version.add_argument("--require-final", action="store_true")
    version.set_defaults(func=cmd_version)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
