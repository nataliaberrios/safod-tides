#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXT="${SPOTL_DIR:-$ROOT/external/spotl}"
ARCHIVE="${SPOTL_ARCHIVE:-$ROOT/external/spotl.tar.gz}"
URL="${SPOTL_URL:-https://igppweb.ucsd.edu/~agnew/Spotl/spotl.tar.gz}"

if [[ -x "$EXT/bin/ertid" ]]; then
  echo "SPOTL already installed: $EXT/bin/ertid"
  exit 0
fi

for cmd in curl tar make gcc gfortran; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command '$cmd' not found."
    echo "On Sherlock, load a GNU compiler toolchain first (module spider gcc)."
    exit 2
  fi
done

mkdir -p "$ROOT/external"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Downloading official SPOTL distribution (~200 MB)..."
  curl -L --fail --retry 3 "$URL" -o "$ARCHIVE"
fi

size=$(wc -c < "$ARCHIVE")
if (( size < 100000000 )); then
  echo "ERROR: SPOTL archive is unexpectedly small ($size bytes)."
  exit 3
fi

TMP="$ROOT/external/spotl_unpack"
rm -rf "$TMP"
mkdir -p "$TMP"
tar -xzf "$ARCHIVE" -C "$TMP"

INSTALL=$(find "$TMP" -type f -name install.compile | head -1)
if [[ -z "$INSTALL" ]]; then
  echo "ERROR: could not locate install.compile in archive."
  exit 4
fi

SRCROOT=$(dirname "$INSTALL")
rm -rf "$EXT"
mv "$SRCROOT" "$EXT"

echo "Compiling official SPOTL in $EXT ..."
cd "$EXT"
chmod +x install.compile
set +e
./install.compile > install.compile.stdout 2> install.compile.stderr
rc=$?
set -e

if (( rc != 0 )) || [[ ! -x "$EXT/bin/ertid" ]]; then
  echo "First compile attempt failed. Trying a conservative GNU-Fortran compatibility patch."
  MAKEFILE="$EXT/src/Makefile"
  if [[ -f "$MAKEFILE" ]]; then
    cp "$MAKEFILE" "$MAKEFILE.original"
    python - "$MAKEFILE" <<'PY'
from pathlib import Path
import re, sys
p=Path(sys.argv[1])
s=p.read_text()
s=re.sub(r'(?m)^\s*(FC|F77)\s*=.*$', r'\1 = gfortran', s)
s=re.sub(r'(?m)^\s*CC\s*=.*$', 'CC = gcc', s)
# Add compatibility flags only if a recognizable flags variable exists.
if re.search(r'(?m)^\s*FFLAGS\s*=', s):
    s=re.sub(r'(?m)^(\s*FFLAGS\s*=.*)$', r'\1 -std=legacy -fallow-argument-mismatch', s, count=1)
p.write_text(s)
PY
  fi
  ./install.compile > install.compile.retry.stdout 2> install.compile.retry.stderr
fi

if [[ ! -x "$EXT/bin/ertid" ]]; then
  echo "ERROR: SPOTL compilation did not create $EXT/bin/ertid"
  echo "See $EXT/install.compile*.stderr"
  exit 5
fi

echo "SPOTL installed successfully: $EXT/bin/ertid"
