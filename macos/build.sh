#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || { echo 'macOS arm64 host required' >&2; exit 1; }
VERSION=${GITHUB_REF_NAME:-dev}
SOURCE=${GITHUB_SHA:-$(git -C "$ROOT" rev-parse HEAD)}
if [[ -n "${GITHUB_ACTIONS:-}" && ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  echo 'release builds require a semantic version tag' >&2; exit 1
fi
export MACOSX_DEPLOYMENT_TARGET=14.0
BUILD="$ROOT/macos/build"
OUT="$ROOT/dist/macos"
rm -rf "$BUILD" "$OUT"
mkdir -p "$BUILD" "$OUT"
cd "$ROOT/frontend"
mise x -- pnpm install --frozen-lockfile
VITE_LIFECYCLE_ENABLED=1 mise x -- pnpm build
cd "$ROOT/backend"
mise x -- uv sync --locked
mise x -- uv run --locked --python 3.11 --with pyinstaller==6.16.0 pyinstaller "$ROOT/windows/longtian.spec" --noconfirm --clean --distpath "$BUILD/app" --workpath "$BUILD/pyinstaller"
APP="$BUILD/app/Longtian"
test -x "$APP/Longtian"
test -x "$APP/LongtianGalleryWorker"
test -f "$APP/_internal/resources/static/index.html"
cp "$ROOT/macos/启动.command" "$APP/启动.command"
cp "$ROOT/macos/README.txt" "$APP/README.txt"
chmod +x "$APP/启动.command" "$APP/Longtian" "$APP/LongtianGalleryWorker"
ARCH=$(uname -m)
test "$ARCH" = arm64
for executable in "$APP/Longtian" "$APP/LongtianGalleryWorker"; do
  [[ "$(lipo -archs "$executable")" == arm64 ]] || { echo 'wrong executable architecture' >&2; exit 1; }
done
printf 'version=%s\nsource=%s\narchitecture=arm64\nminimum_macos=14.0\n' "$VERSION" "$SOURCE" > "$APP/BUILD-METADATA.txt"
ZIP="$OUT/Longtian-${VERSION}-macOS-arm64.zip"
mise x -- uv run --locked python "$ROOT/scripts/package_portable_zip.py" "$APP" "$ZIP"
shasum -a 256 "$ZIP" | awk -v f="$(basename "$ZIP")" '{print $1 "  " f}' > "$ZIP.sha256"
printf 'macOS arm64 artifact: %s\n' "$ZIP"
