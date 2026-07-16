#!/usr/bin/env bash
# Installs dependencies and zips the drift auditor Lambda into a deployment
# package. Run from anywhere - paths are resolved relative to this script.
set -euo pipefail

cd "$(dirname "$0")"

rm -rf build okta-drift-auditor.zip
mkdir -p build

pip install --target build -r requirements.txt
cp -r src/. build/
cp managed_resources.json build/

cd build
zip -r ../okta-drift-auditor.zip . -x '*.pyc' '__pycache__/*'
