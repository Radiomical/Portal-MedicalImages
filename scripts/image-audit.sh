#!/bin/sh
# Synthetic CI image checks only. No access to deployment secrets.
set -eu
mkdir -p image-audit
trivy version > image-audit/trivy-version.txt
for image in portal:0.1.0-distroless-ci portal:0.1.0-slim-baseline-ci; do
    name=$(printf '%s' "$image" | tr ':/' '--')
    docker image inspect "$image" > "image-audit/$name-inspect.json"
    trivy image --scanners vuln --format json --output "image-audit/$name-trivy.json" "$image"
done
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 portal:0.1.0-distroless-ci
