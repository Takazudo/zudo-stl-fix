---
name: l-make-release
description: "Release zudo-stl-fix as a downloadable macOS app: pick the version, bump packaging/Info.plist via a PR, build the arm64 .app archive locally with scripts/release-macos-local.sh, attach it to a draft GitHub Release, write the notes, publish, and watch release.yml verify the assets. Triggers on 'make a release', 'cut a release', 'release the app', 'bump version', '/l-make-release'."
user-invocable: true
argument-description: "Optional: patch | minor | major | X.Y.Z, plus --confirm (stop at the draft) or cancel"
---

# /l-make-release

Ship the compiled `zudo-stl-fix.app` as a GitHub Release asset, so users download it instead of building it.

The build pipeline already exists; this skill only orchestrates it. Do not reimplement it:

| Piece | Role |
| --- | --- |
| `packaging/Info.plist` `CFBundleShortVersionString` | **Version source of truth** (no leading `v`). Tag = `v<version>`. |
| `scripts/release-macos-local.sh --upload v<ver>` | Full native build + tests + relocated-helper smoke, writes `zudo-stl-fix-<ver>-macos-arm64.zip` + `.sha256`, creates a **draft** Release targeting HEAD, uploads both. Refuses a dirty tree, an unpushed HEAD, a tag/plist mismatch, or a non-draft release. |
| `scripts/verify_release_asset.py` | Checks the zip (arm64 Mach-O, Info.plist version, `LSMinimumSystemVersion` 27.0, BUILD-INFO commit, checksum). |
| `.github/workflows/release.yml` | On `release: published`, re-downloads and re-verifies the assets on Linux. |

Owner decision 2026-11-08: no macOS GitHub Actions runners. The binary is **always** built on this local Apple silicon Mac.

## Invocation & autonomy

- `/l-make-release` — judge the level from commits since the last tag (see Step 2), then run end to end: bump PR → merge → build → draft → notes → **publish** → watch `release.yml`. Invoking the skill is the owner's authorization to merge the bump PR and publish the Release (AGENTS.md: "do not publish releases unless separately authorized" — this invocation is that authorization). Do not stop to ask "publish?".
- `/l-make-release patch|minor|major|X.Y.Z` — force the level or exact version.
- `--confirm` — print the proposal and wait for approval before the first mutation; stop at the unpublished draft and tell the user to publish it (`gh release edit v<ver> --draft=false`).
- `/l-make-release cancel` — jump to [Cancel](#cancel).
- The only autonomous-mode question: a no-argument run whose commits contain a breaking change (major). Ask before bumping major.

## Boundaries

- Never replace originals or golden fixtures; never edit tests to make the build pass. A failing native gate stops the release.
- Never force-push, never `--amend`, never push a tag by hand (the draft Release creates the tag), never retarget a **published** Release or re-upload its assets — bump the version instead.
- Never use `--clobber` on a published release (the script already refuses).
- The archive is **ad hoc signed only — not Developer ID signed, not notarized.** Release notes must say so. Never tell users to strip quarantine wholesale (`xattr -cr`), disable Gatekeeper, or use admin rights; the sanctioned path is **System Settings → Privacy & Security → Open Anyway**.
- Heavy run: the build goes through `bash $HOME/.claude/scripts/heavy-guard.sh -- …` with `run_in_background: true`.

## Step 1: Preconditions (read-only)

Abort with a clear message if any fails:

```bash
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]]               # native arm64 macOS
[[ $(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0) == 0 ]]  # not Rosetta
(( $(sw_vers -productVersion | cut -d. -f1) >= 27 ))
python3.12 -c 'import sys; assert sys.version_info[:3] == (3,12,14)'
xcodebuild -version
gh auth status
git switch main && git pull --ff-only
[[ -z $(git status --porcelain) ]]
```

Also list leftover drafts — `gh release list --json tagName,isDraft --jq '.[] | select(.isDraft) | .tagName'`. A draft for the target version is resumable (Step 5 accepts a draft targeting HEAD); a draft for some other version is an orphan — mention it in the final report, do not delete it unasked.

## Step 2: Determine the version

```bash
CUR=$(plutil -extract CFBundleShortVersionString raw packaging/Info.plist)
LAST_TAG=$(git tag --list 'v*' --sort=-v:refname | head -1)    # may be empty
```

- **No tag yet (first release):** release `CUR` as is unless an argument says otherwise. No version bump.
- **`CUR` is newer than `LAST_TAG`** (already bumped, e.g. a previous run stopped after merge): release `CUR` without bumping again.
- **Otherwise** bump from `CUR`:
  - explicit `X.Y.Z` → that (must be greater than `LAST_TAG`).
  - `major|minor|patch` → that level.
  - no argument → read `git log --oneline $LAST_TAG..origin/main`: any `BREAKING`/`!:` → major (ask first); any `feat` or user-visible app/engine behaviour change → minor; otherwise patch. While `0.x`, a breaking change bumps **minor** and needs no question.
- If `LAST_TAG..origin/main` is empty, stop: nothing to release.

`CFBundleVersion` (build number) increments by 1 on every bump.

## Step 3: Draft the release notes (read-only)

Group `git log --no-merges $LAST_TAG..origin/main` (whole history for the first release; summarize at feature level, not commit-by-commit) into **Features / Fixes / Other**, user-facing wording. Skip docs-site-only and CI-only noise unless nothing else changed. Save to `$DROPBOX_CCLOGS_DIR/zudo-stl-fix/release-v<ver>-notes.md` using this frame:

```markdown
## Download

`zudo-stl-fix-<ver>-macos-arm64.zip` — macOS 27 or later on Apple silicon (arm64) only.

1. Download the zip and unzip it (double-click in Finder).
2. Move `zudo-stl-fix.app` to `/Applications`.
3. First launch: this build is ad hoc signed, **not** Developer ID signed or notarized, so macOS blocks it once. Open it, dismiss the dialog, then go to **System Settings → Privacy & Security** and click **Open Anyway**.

Verify the download (optional): `shasum -a 256 -c zudo-stl-fix-<ver>-macos-arm64.zip.sha256`

A passing check is not proof of printability — see https://zudo-stl-fix.zudolab.dev/docs/concepts/validation-is-not-printability/

## Changes

### Features
- …

### Fixes
- …
```

Print the target version and notes. With `--confirm`, wait for approval here; otherwise continue.

## Step 4: Bump PR (skip when no bump is needed and docs are current)

The repo lands everything through PRs; follow that, never push the bump straight to `main`.

```bash
git switch -c release/v<ver>          # new name; never reuse a branch
plutil -replace CFBundleShortVersionString -string <ver> packaging/Info.plist
plutil -replace CFBundleVersion -string <build+1> packaging/Info.plist
```

`plutil -replace` rewrites the file's formatting; if the diff is more than the two values, restore it and edit the two `<string>` values with the Edit tool instead.

**Docs still saying "build it yourself"** — check `grep -rln 'No public release\|公開リリースはまだ\|公開リリースは存在しません' doc/src/content README.md`. If any match (first release only), rewrite in the same PR, keeping EN and JA in sync:

- `doc/src/content/docs{,-ja}/getting-started/install-and-run.mdx`: lead with "Download" → link `https://github.com/Takazudo/zudo-stl-fix/releases/latest`, the unzip / Applications / Open Anyway steps from Step 3, then keep "Build locally" as the secondary path for developers.
- `doc/src/content/docs{,-ja}/develop/release-status.mdx`: releases are published to GitHub Releases by `/l-make-release`; still ad hoc signed, not notarized; keep the Developer ID section.
- `README.md` status sentence.

Do not edit the docs to link a version number; `releases/latest` stays correct across releases.

Then:

```bash
make verify-hashes
git add packaging/Info.plist doc/src/content README.md
git commit -m "chore(release): v<ver>"     # + Co-Authored-By trailer
git push -u origin release/v<ver>
gh pr create --base main --title "Release v<ver>" --body "<version bump + docs summary>"
```

Wait for checks with `/watch-ci` (checks.yml runs because `packaging/**` changed; the docs workflow may run too). Red CI stops the release — report it. Green: `gh pr merge --merge --delete-branch` (regular merge, not squash), then `git switch main && git pull --ff-only`.

## Step 5: Build and upload the draft (heavy, background)

On `main` at the merged HEAD (the script requires HEAD to be on the remote and the tree clean):

```bash
bash $HOME/.claude/scripts/heavy-guard.sh -- env PYTHON=python3.12 \
  bash scripts/release-macos-local.sh --upload v<ver>
```

Run with `run_in_background: true` and wait for the completion notification. It runs the engine venv install, PyInstaller helper, `swift test` (with the real worker), release build, codesign verify, relocated-bundle smoke, archive + checksum, `verify_release_asset.py`, creates the draft (`--target HEAD`) if missing, and uploads.

On failure: read the log tail, report the failing stage, stop. Do not retry by weakening anything. `verdict=ENV_SUSPECT` from heavy-guard → rerun once.

Confirm the upload:

```bash
gh release view v<ver> --json isDraft,targetCommitish,assets \
  --jq '{isDraft, targetCommitish, assets: [.assets[].name]}'
```

Must be a draft targeting the merged HEAD with exactly the `.zip` and `.zip.sha256`.

## Step 6: Notes and publish

```bash
gh release edit v<ver> --title "zudo-stl-fix v<ver>" --notes-file <notes file from Step 3>
```

- `--confirm`: stop here. Report the draft URL and `gh release edit v<ver> --draft=false --latest`.
- Default: `gh release edit v<ver> --draft=false --latest`.

## Step 7: Watch release.yml

```bash
sleep 5
RUN=$(gh run list --workflow release.yml --event release --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN" --exit-status
```

(Use Monitor or a background command rather than a foreground sleep loop.) Red: the Release is already public with unverified assets — say so plainly at the top of the report, include the failing log lines (`gh run view "$RUN" --log-failed | tail -40`), and recommend the fix path (bump to the next patch and release again; do not re-upload over the published assets).

Final smoke from the user's side: download the published asset into a fresh scratch dir and verify it.

```bash
D=$(mktemp -d)
gh release download v<ver> --dir "$D"
(cd "$D" && shasum -a 256 -c *.sha256)
python3.12 -I scripts/verify_release_asset.py "$D" --version <ver> --commit "$(git rev-parse v<ver>^{commit})"
```

## Step 8: Report

Verdict headings (user CLAUDE.md). Include: the Release URL, version, tag commit, asset names + SHA-256, release.yml result, the bump PR URL, and any orphan drafts found in Step 1. If docs changed, note the docs deploy runs from the merged PR.

## Cancel

For a draft that should not ship:

```bash
gh release list --json tagName,isDraft --jq '.[] | select(.isDraft) | .tagName'
gh release delete v<ver> --yes            # drafts only; confirm isDraft first
```

A draft does not create the git tag (publishing does), so there is no tag to clean up.

Never delete a published Release as part of cancel; that needs the owner's explicit request. A merged version bump is not reverted — the next run releases that version (Step 2 "CUR is newer than LAST_TAG").

## Failure recovery

| Situation | Action |
| --- | --- |
| Script: "Push HEAD first" | You are not on the merged `main`; `git switch main && git pull --ff-only`. |
| Script: "Release vX exists as 'false …'" | That version is already published. Bump to the next patch. |
| Script: draft targets another commit | A stale draft from an older run: `gh release delete v<ver> --yes` (it is a draft), rerun Step 5. |
| Native gate / smoke fails | Stop. Fix in a normal PR, then rerun the skill (Step 2 sees the unreleased bump). |
| release.yml red after publish | See Step 7. |
