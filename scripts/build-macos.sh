#!/bin/bash
# Local development build only. Does not use signing credentials or publish.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
if [[ $(uname -s) != Darwin ]]; then
  echo "macOS is required; a Linux-frozen helper is not a Mac artifact." >&2
  exit 2
fi
cd "$ROOT"
PYTHON=${PYTHON:-python3.12}
export ZUDO_BUILD_ARCH
ZUDO_BUILD_ARCH=$("$PYTHON" -c 'import platform; print(platform.machine())')
case "$ZUDO_BUILD_ARCH" in arm64|x86_64) ;; *) echo "Unsupported architecture" >&2; exit 2 ;; esac
"$PYTHON" -c 'import sys; assert sys.version_info[:3] == (3,12,14), "Use CPython 3.12.14 for the pinned build"'
if [[ $(uname -m) != "$ZUDO_BUILD_ARCH" ]]; then
  echo "Build Python must match the active shell architecture." >&2; exit 2
fi
export MACOSX_DEPLOYMENT_TARGET=14.0
OUT="$ROOT/build/macos-$ZUDO_BUILD_ARCH"
mkdir -p "$OUT"
"$PYTHON" -m venv --clear "$OUT/venv"
PY="$OUT/venv/bin/python"
"$PY" -m pip install --require-hashes --only-binary=:all: -r packaging/requirements-macos.lock
"$PY" -m pip check
"$PY" -m PyInstaller --noconfirm --clean --distpath "$OUT/helper" --workpath "$OUT/pyinstaller" packaging/worker.spec
# Point the opt-in real-worker XCTest at this build's own hash-locked venv so
# the packaging run exercises engine/worker.py instead of skipping it.
if [[ $(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0) == 1 ]]; then
  # Under Rosetta 2, swift test lists tests with an arm64-only helper that cannot load
  # an x86_64 bundle; run the built bundle with xctest's own x86_64 slice instead.
  swift build --package-path app --build-tests --arch "$ZUDO_BUILD_ARCH"
  TESTS=$(swift build --package-path app --build-tests --arch "$ZUDO_BUILD_ARCH" --show-bin-path)/ZudoSTLFixCoreTests.xctest
  ZUDO_WORKER_PYTHON="$PY" arch "-$ZUDO_BUILD_ARCH" "$(xcrun --find xctest)" "$TESTS"
else
  ZUDO_WORKER_PYTHON="$PY" swift test --package-path app
fi
swift build --package-path app -c release --arch "$ZUDO_BUILD_ARCH"
BIN=$(swift build --package-path app -c release --arch "$ZUDO_BUILD_ARCH" --show-bin-path)
# Build into a new private directory; never recursively delete a user-selected path.
STAGE=$(mktemp -d "$OUT/app-stage.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
APP="$STAGE/zudo-stl-fix.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Helpers" "$APP/Contents/Resources"
cp "$BIN/ZudoSTLFix" "$APP/Contents/MacOS/ZudoSTLFix"
cp packaging/Info.plist "$APP/Contents/Info.plist"
ditto "$OUT/helper/STLWorker.app" "$APP/Contents/Helpers/STLWorker.app"
"$PY" scripts/generate_notices.py "$APP/Contents/Resources/ThirdPartyNotices"
{
  sw_vers
  xcodebuild -version
  xcrun --show-sdk-version
  xcrun --show-sdk-path
  swift --version
  "$PY" --version
  "$PY" -m pip freeze --all
  git rev-parse HEAD
  git status --short
  echo "architecture=$ZUDO_BUILD_ARCH"
  echo "deployment_target=$MACOSX_DEPLOYMENT_TARGET (not proof of runtime compatibility)"
} > "$APP/Contents/Resources/BUILD-INFO.txt"
# PyInstaller signs nested Mach-O files ad hoc. Validate those signatures before
# signing the enclosing native app; never use --deep as a signing shortcut.
codesign --verify --deep --strict "$APP/Contents/Helpers/STLWorker.app"
codesign --force --sign - --timestamp=none "$APP"
codesign --verify --deep --strict "$APP"
"$PY" scripts/smoke_bundle.py "$APP"
VERIFIED=$(mktemp -d "$OUT/verified.XXXXXX")
ARCHIVE="$VERIFIED/zudo-stl-fix-macos-$ZUDO_BUILD_ARCH-local.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ARCHIVE"
mv "$APP" "$VERIFIED/zudo-stl-fix.app"
shasum -a 256 "$ARCHIVE" > "$ARCHIVE.sha256"
echo "Local ad-hoc development app: $VERIFIED/zudo-stl-fix.app"
echo "Local archive (not notarized or released): $ARCHIVE"
