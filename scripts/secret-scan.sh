#!/bin/sh
# Pinned releases verified against their release checksum manifests.
set -eu
root=$(git rev-parse --show-toplevel)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
curl -fsSL https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz -o "$work/gitleaks.tgz"
printf '%s  %s\n' 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb "$work/gitleaks.tgz" | sha256sum -c -
curl -fsSL https://github.com/trufflesecurity/trufflehog/releases/download/v3.99.8/trufflehog_3.99.8_linux_amd64.tar.gz -o "$work/trufflehog.tgz"
printf '%s  %s\n' 7c3b02f160f28929a467e29e20fba98746e0729f6e37c3c25761e4f8789abe08 "$work/trufflehog.tgz" | sha256sum -c -
tar -xzf "$work/gitleaks.tgz" -C "$work" gitleaks
tar -xzf "$work/trufflehog.tgz" -C "$work" trufflehog
"$work/gitleaks" git --redact --no-banner "$root"
"$work/gitleaks" dir --redact --no-banner "$root"
printf '%s\n' '(^|/)(\.venv|\.git|__pycache__)/' > "$work/exclude.txt"
"$work/trufflehog" git "file://$root" --no-verification --no-update --fail --fail-on-scan-errors
"$work/trufflehog" filesystem "$root" --no-verification --no-update --fail --fail-on-scan-errors --exclude-paths "$work/exclude.txt"
