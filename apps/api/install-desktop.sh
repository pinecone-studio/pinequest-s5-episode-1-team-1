#!/usr/bin/env bash
# Installs BEKHI on this Mac as an app: its Python packages, its window (the web app built to talk
# to this Mac's API) and BEKHI.app in ~/Applications (Launchpad, Spotlight; drag it to the Dock).
# Run it again after pulling new code. Nothing starts with the Mac: BEKHI runs while its window is open.
#
#   bash apps/api/install-desktop.sh
set -euo pipefail
api="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$api/../.." && pwd)"
data="$HOME/Library/Application Support/BEKHI"
app="$HOME/Applications/BEKHI.app"

command -v uv >/dev/null || { echo 'uv is missing: brew install uv  (or https://docs.astral.sh/uv/)'; exit 1; }
command -v npm >/dev/null || { echo 'Node.js is missing: brew install node'; exit 1; }

echo '1/4 Python packages'
uv sync --frozen --no-dev --inexact --project "$api"
[ -f "$api/.env" ] || echo 'WARNING: apps/api/.env is missing: copy .env.example and put in the API keys, or BEKHI cannot talk.'

echo '2/4 The window (web app)'
(cd "$repo" && { [ -d node_modules ] || npm install; })
# The window talks to the API that serves it, on this Mac (an empty value would let .env's cloud address in).
(cd "$repo/apps/mobile" && EXPO_PUBLIC_API_URL='http://127.0.0.1:8000' CI=1 npx expo export -p web --output-dir "$api/web")

echo '3/4 Icon'
mkdir -p "$data"
iconset="$(mktemp -d)/BEKHI.iconset"
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$repo/apps/mobile/assets/icon.png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$repo/apps/mobile/assets/icon.png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$data/BEKHI.icns"

echo '4/4 BEKHI.app'
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$data/BEKHI.icns" "$app/Contents/Resources/BEKHI.icns"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>BEKHI</string>
  <key>CFBundleDisplayName</key><string>BEKHI</string>
  <key>CFBundleIdentifier</key><string>mn.bekhi.desktop</string>
  <key>CFBundleExecutable</key><string>BEKHI</string>
  <key>CFBundleIconFile</key><string>BEKHI</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSAppleEventsUsageDescription</key><string>BEKHI types what you say and changes the volume for you.</string>
</dict>
</plist>
PLIST
# The app runs the project's own Python (.venv), from this checkout.
{
  echo '#!/bin/bash'
  printf 'cd %q\n' "$api"
  printf 'exec %q %q\n' "$api/.venv/bin/python" "$api/bekhi_desktop.pyw"
} > "$app/Contents/MacOS/BEKHI"
chmod +x "$app/Contents/MacOS/BEKHI"
touch "$app"  # Finder picks up the new icon
echo "Done. Open BEKHI from Launchpad or Spotlight ($app)."
echo 'The first time, allow the microphone, and for typing allow BEKHI in System Settings → Privacy & Security → Accessibility.'
