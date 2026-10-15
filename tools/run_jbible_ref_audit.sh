#!/usr/bin/env bash
# Usage:
#   bash run_jbible_ref_audit.sh 31 40
#   bash run_jbible_ref_audit.sh all
#   bash run_jbible_ref_audit.sh 31 500 --reparse
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if (( $# == 0 )); then
  echo "Usage: bash $0 <start> <end> [--reparse] OR bash $0 all [--reparse]" >&2
  exit 2
fi
if [[ "$1" == "all" ]]; then
  shift
  exec python3 "$HERE/jbible_ref_audit.py" --copy-images "$@"
elif (( $# >= 2 )) && [[ "$1" =~ ^[0-9]+$ && "$2" =~ ^[0-9]+$ ]]; then
  START="$1"
  END="$2"
  shift 2
  exec python3 "$HERE/jbible_ref_audit.py" --start-page "$START" --end-page "$END" --copy-images "$@"
else
  echo "Usage: bash $0 <start> <end> [--reparse] OR bash $0 all [--reparse]" >&2
  exit 2
fi
