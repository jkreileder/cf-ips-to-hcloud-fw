---
description: 'Address review feedback on the active cf-ips-to-hcloud-fw pull
request, then commit fixes with DCO sign-off + GPG signing and push.'
name: 'Address PR Feedback'
argument-hint: 'Optional: specific comment, reviewer, or area to focus on'
agent: 'agent'
---
<!-- markdownlint-disable-file MD041 -->

Address the review feedback on the current pull request for this repository.

1. Gather the open review comments and CI/check failures on the active PR. Use
   the VS Code GitHub Pull Requests `address-pr-comments` tool if it's available;
   otherwise fall back to `gh` (`gh pr view --comments`, `gh api` for review
   threads). If a specific reviewer, thread, or area was named in the argument,
   focus there first.
2. For each actionable comment, make the change in the codebase. Follow existing
   patterns; keep edits scoped to what the comment asks — don't reflow unrelated
   code.
3. Before committing, run the quality gates with `make check` (`make lint` then
   `make test`, coverage ≥ 80%). Fix anything that fails.
4. Commit the fixes with a Conventional Commits message that references the
   feedback, using **DCO sign-off and GPG signing** (repo policy requires both):
   `git commit -s -S -m "<type>(<scope>): address review feedback"`.
   Group related fixes; use separate commits if changes are logically distinct.
5. Push to the PR branch (`git push`). Do not force-push unless history was
   intentionally rewritten and the user agreed.
6. Reply to / resolve the addressed review threads where appropriate, and post a
   concise summary comment of what changed. Report back which comments were
   addressed and which (if any) need the author's decision.

Constraints:

- Keep PR title/commits in Conventional Commits format.
- Never bypass signing or sign-off.
- If a comment is ambiguous or you disagree, ask the user instead of guessing.
