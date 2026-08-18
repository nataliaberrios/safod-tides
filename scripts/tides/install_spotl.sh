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
else
  echo "Using cached SPOTL archive: $ARCHIVE"
fi

size=$(wc -c < "$ARCHIVE")
if (( size < 100000000 )); then
  echo "ERROR: SPOTL archive is unexpectedly small ($size bytes)."
  exit 3
fi

TMP="$ROOT/external/spotl_unpack"
rm -rf "$TMP"
mkdir -p "$TMP"
echo "Extracting SPOTL archive..."
tar -xzf "$ARCHIVE" -C "$TMP"

# The 2013 manual calls the compiler script install.compile, while the
# distributed archive in some mirrors/releases uses install.comp.
INSTALL=$(find "$TMP" -type f \( -name 'install.comp' -o -name 'install.compile' \) | head -1 || true)
if [[ -z "$INSTALL" ]]; then
  echo "ERROR: could not locate install.comp or install.compile in archive."
  echo "Install-like files found in the archive:"
  find "$TMP" -maxdepth 4 -type f -name 'install*' -print | sort | head -50 || true
  echo "Top-level archive entries:"
  tar -tzf "$ARCHIVE" | head -50 || true
  exit 4
fi

SRCROOT=$(dirname "$INSTALL")
INSTALL_NAME=$(basename "$INSTALL")
rm -rf "$EXT"
mv "$SRCROOT" "$EXT"

echo "SPOTL source root: $EXT"
echo "Compiler script: $INSTALL_NAME"
cd "$EXT"
chmod +x "$INSTALL_NAME" || true

run_compile() {
  local tag="$1"
  set +e
  bash "./$INSTALL_NAME" > "${INSTALL_NAME}.${tag}.stdout" 2> "${INSTALL_NAME}.${tag}.stderr"
  local rc=$?
  set -e
  return $rc
}

if run_compile first && [[ -x "$EXT/bin/ertid" ]]; then
  echo "SPOTL compiled successfully on first attempt."
else
  echo "First compile attempt failed. Applying GNU compatibility settings and retrying."

  MAKEFILE=""
  for candidate in "$EXT/src/Makefile" "$EXT/src/MAKEFILE"; do
    if [[ -f "$candidate" ]]; then
      MAKEFILE="$candidate"
      break
    fi
  done

  if [[ -z "$MAKEFILE" ]]; then
    echo "ERROR: could not find src/Makefile or src/MAKEFILE."
    exit 5
  fi

  if [[ ! -f "$MAKEFILE.original" ]]; then
    cp "$MAKEFILE" "$MAKEFILE.original"
  fi

  # Modern GCC rejects the old implicit-int declarations in SPOTL's C helper.
  # Both functions return int, so make the return type explicit before retrying.
  ISPAND="$EXT/src/ispand.c"
  if [[ -f "$ISPAND" ]]; then
    if ! grep -q '^int ispand (' "$ISPAND"; then
      sed -i 's/^ispand (/int ispand (/' "$ISPAND"
    fi
    if ! grep -q '^int ispand_(' "$ISPAND"; then
      sed -i 's/^ispand_(/int ispand_(/' "$ISPAND"
    fi
  fi

  # Put explicit GNU settings at the END of the makefile so they override
  # older compiler selections without deleting the original choices.
  cat >> "$MAKEFILE" <<'EOF'

# --- SAFOD Sherlock compatibility override ---
FTN = gfortran
F77 = gfortran
FC = gfortran
CC = gcc
FFLAGS += -O2 -std=legacy -fallow-argument-mismatch -fno-range-check -fno-backslash
CFLAGS += -c
# --- end SAFOD Sherlock compatibility override ---
EOF

  if ! run_compile retry; then
    echo "ERROR: SPOTL compilation failed after GNU compatibility retry."
    echo "See:"
    echo "  $EXT/${INSTALL_NAME}.first.stderr"
    echo "  $EXT/${INSTALL_NAME}.retry.stderr"
    exit 6
  fi
fi

if [[ ! -x "$EXT/bin/ertid" ]]; then
  echo "ERROR: compilation finished but did not create $EXT/bin/ertid"
  echo "See $EXT/${INSTALL_NAME}.*.stdout and *.stderr"
  exit 7
fi

echo "SPOTL installed successfully: $EXT/bin/ertid"
