#!/usr/bin/env bash
# Run on YOUR LAPTOP, after scripts/vm_inventory_data.sh has run on the VM.
# Brings back the manifest and the small files, and leaves the bulk data on the VM.
#
#   bash scripts/pull_vm_data.sh
#
# Nothing here is committed automatically: it lands in data/bucket/ and you review
# it before adding. The .gitignore already blocks structure files and archives, so
# check `git status` and add deliberately.
set -euo pipefail

KEY="${KEY:-$HOME/.ssh/team-4}"
HOST="${HOST:-hackathon@89.169.99.24}"
REMOTE_OUT="${REMOTE_OUT:-data-inventory}"
DEST="${DEST:-data/bucket}"

[ -f "$KEY" ] || { echo "no key at $KEY -- download it from the Bitwarden Send link in Slack first" >&2; exit 1; }

mkdir -p "$DEST"

echo "== pulling manifest and sizes =="
scp -i "$KEY" "$HOST:$REMOTE_OUT/manifest.tsv" "$HOST:$REMOTE_OUT/sizes.txt" "$DEST/"

echo "== pulling the committable bundle =="
scp -i "$KEY" "$HOST:$REMOTE_OUT/committable.tar.gz" "$DEST/" || \
  echo "note: no bundle on the VM -- nothing was under the size cap"

if [ -f "$DEST/committable.tar.gz" ]; then
  # Extracted into its own directory: this is organiser-supplied content, so it is
  # read as data and never executed from where it unpacks.
  mkdir -p "$DEST/extracted"
  tar -xzf "$DEST/committable.tar.gz" -C "$DEST/extracted"
  rm -f "$DEST/committable.tar.gz"
  echo "extracted to $DEST/extracted"
fi

echo
echo "== what came back =="
find "$DEST" -type f ! -name '.DS_Store' -exec ls -l {} + | awk '{printf "%10d  %s\n", $5, $9}' | sort -k2

echo
echo "== the ten largest files still on the VM only =="
awk -F'\t' 'NR>1{printf "%12d  %s\n", $2, $1}' "$DEST/manifest.tsv" 2>/dev/null | sort -rn | head -10

cat <<'NOTE'

Review before committing. Rules of thumb:
  - Commit:  the bucket's own README.md, the Foundry/RFD4 docs, the 768-variant SPR
             table, the manifest and sizes.
  - Skip:    the 524k FACS table and anything else over a few MB. It is regenerable
             from S3, the manifest records its checksum, and the VM is where the
             compute is.
  - Best:    commit what we DERIVE from the bulk data -- the unique-CDRH3 set used by
             the novelty check, or a calibration table of confidence score against
             measured SPR. Small, and worth more to a judge than a copy of the input.

  git status && git add -p data/bucket
NOTE
