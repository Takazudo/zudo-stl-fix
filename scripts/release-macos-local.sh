#!/bin/bash
# Build the macOS release archive on a local Apple silicon Mac and optionally attach it
# to a DRAFT GitHub Release. Owner decision 2026-11-08: no macOS GitHub Actions runners
# (cost); release binaries are built locally and .github/workflows/release.yml only
# verifies the uploaded assets on Linux.
#
# Usage:
#   scripts/release-macos-local.sh [--upload vX.Y.Z] [--out-dir DIR]
#
# --upload vX.Y.Z  Attach the archive and .sha256 to the Release for that tag
#                  (gh release upload --clobber). A missing Release is created as a
#                  DRAFT targeting HEAD; publishing the draft is a separate, manual step.
# --out-dir DIR    Where to write the release files (default build/release).
#
# Output contract (checked by scripts/verify_release_asset.py and release.yml):
#   zudo-stl-fix-{version}-macos-arm64.zip         ditto archive of zudo-stl-fix.app
#   zudo-stl-fix-{version}-macos-arm64.zip.sha256  "<sha256>  <archive name>"
#   {version} = CFBundleShortVersionString in packaging/Info.plist, no leading "v".
# The app is ad hoc signed only: not Developer ID signed or notarized.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

upload_tag=""
out_dir="$ROOT/build/release"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --upload) upload_tag=${2:?--upload needs a tag}; shift 2 ;;
    --out-dir) out_dir=${2:?--out-dir needs a path}; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

version=$(plutil -extract CFBundleShortVersionString raw packaging/Info.plist)
archive="zudo-stl-fix-${version}-macos-arm64.zip"
head=$(git rev-parse HEAD)
if [[ -n $(git status --porcelain) ]]; then
  echo "Commit or stash changes first; a release must build from a clean tree." >&2; exit 2
fi
if [[ -n $upload_tag ]]; then
  [[ $upload_tag == "v$version" ]] || { echo "Tag $upload_tag does not match Info.plist version $version (expected v$version)." >&2; exit 2; }
  git fetch --quiet --tags origin
  [[ -n $(git branch -r --contains "$head") ]] || { echo "Push $head first; the Release must target a commit on GitHub." >&2; exit 2; }
  if tagged=$(git rev-parse --verify --quiet "refs/tags/$upload_tag^{commit}"); then
    [[ $tagged == "$head" ]] || { echo "$upload_tag points to $tagged, not HEAD $head." >&2; exit 2; }
  fi
fi

log=$(mktemp)
trap 'rm -f "$log"' EXIT
PYTHON=${PYTHON:-python3.12} bash scripts/build-macos.sh 2>&1 | tee "$log"
built=$(sed -n 's/^Local archive (not notarized or released): //p' "$log" | tail -1)
[[ -f $built ]] || { echo "Package gate did not report an archive." >&2; exit 1; }

mkdir -p "$out_dir"
cp "$built" "$out_dir/$archive"
( cd "$out_dir" && shasum -a 256 "$archive" > "$archive.sha256" )
"${PYTHON:-python3.12}" scripts/verify_release_asset.py "$out_dir" --version "$version" --commit "$head"
echo "Release files:"
echo "  $out_dir/$archive"
echo "  $out_dir/$archive.sha256"

if [[ -z $upload_tag ]]; then
  echo "Not uploaded. To attach them: scripts/release-macos-local.sh --upload v$version"
  exit 0
fi
if ! gh release view "$upload_tag" >/dev/null 2>&1; then
  echo "Creating DRAFT Release $upload_tag at $head"
  gh release create "$upload_tag" --draft --target "$head" --title "zudo-stl-fix $upload_tag" \
    --notes "macOS 27 or later on Apple silicon (arm64). Ad hoc signed only: not Developer ID signed or notarized, so Gatekeeper asks for confirmation on first launch. Built locally with scripts/release-macos-local.sh; see BUILD-INFO.txt inside the app."
fi
gh release upload "$upload_tag" "$out_dir/$archive" "$out_dir/$archive.sha256" --clobber
echo "Uploaded to $upload_tag. Review the draft, then publish it; release.yml re-verifies the assets."
