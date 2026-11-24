#!/usr/bin/env bash
# Fetch Tesseract's Latin-script model next to the English one (.runtime/tessdata, git-ignored).
# The English model alone misreads é/ø/ă in names; see docs/tutorial/10-evaluation.md.
set -euo pipefail
cd "$(dirname "$0")/.."
dir=.runtime/tessdata
mkdir -p "$dir"
[ -s "$dir/Latin.traineddata" ] || curl -fsSL -o "$dir/Latin.traineddata" \
  https://github.com/tesseract-ocr/tessdata_fast/raw/main/script/Latin.traineddata
[ -s "$dir/eng.traineddata" ] || curl -fsSL -o "$dir/eng.traineddata" \
  https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata
ls -la "$dir"
