#!/usr/bin/env bash
# Run ON THE TEAM VM. Syncs the hackathon bucket and builds a provenance manifest.
#
#   ssh -i ~/.ssh/team-4 hackathon@89.169.99.24 'bash -s' < scripts/vm_inventory_data.sh
#
# The ~5 GB of data stays on the VM, next to the GPU. What comes back to the repo is
# the manifest plus the files small enough to be worth versioning -- see
# scripts/pull_vm_data.sh. GitHub hard-blocks any file over 100 MB, and the repo is
# our Execution deliverable, so it carries provenance rather than a second copy of
# the inputs.
#
# Bucket layout per Leonardo Castorina (Apheris), Slack 10:17 on 14 Nov. The file
# names INSIDE each directory are not documented anywhere we hold, which is the
# point of the manifest.
set -euo pipefail

DATA_DIR="${DATA_DIR:-$HOME/hackathon-data}"
DOCS_DIR="${DOCS_DIR:-$HOME/rfd4}"
OUT="${OUT:-$HOME/data-inventory}"
MAX_COMMIT_BYTES="${MAX_COMMIT_BYTES:-4194304}"   # 4 MiB: small enough to version without thought

mkdir -p "$OUT"

echo "== syncing data (~5 GB, first run takes a while) =="
aws s3 sync s3://apheris-oslo-hackathon/data/ "$DATA_DIR/"

echo "== syncing Foundry + RFD4-Proteina docs =="
aws s3 sync s3://apheris-oslo-hackathon/rfd4-proteina/docs/ "$DOCS_DIR/"

echo "== manifest: path, bytes, sha256 =="
# Checksums are what let a judge confirm we used the data we say we used.
{
  printf 'path\tbytes\tsha256\n'
  for root in "$DATA_DIR" "$DOCS_DIR"; do
    [ -d "$root" ] || continue
    base="$(basename "$root")"
    find "$root" -type f ! -name '.DS_Store' -print0 \
      | sort -z \
      | while IFS= read -r -d '' f; do
          printf '%s/%s\t%s\t%s\n' \
            "$base" "${f#"$root"/}" \
            "$(wc -c < "$f" | tr -d ' ')" \
            "$(sha256sum "$f" | cut -d' ' -f1)"
        done
  done
} > "$OUT/manifest.tsv"

echo "== directory sizes =="
du -sh "$DATA_DIR"/* "$DOCS_DIR" 2>/dev/null | tee "$OUT/sizes.txt"

# Bundle what is worth committing: every doc, plus any data file under the cap.
# Nothing is renamed, so paths in the bundle match paths in the manifest.
echo "== bundling committable files (< $MAX_COMMIT_BYTES bytes, plus all docs) =="
BUNDLE_LIST="$OUT/bundle-files.txt"
: > "$BUNDLE_LIST"
[ -d "$DOCS_DIR" ] && find "$DOCS_DIR" -type f ! -name '.DS_Store' >> "$BUNDLE_LIST"
[ -d "$DATA_DIR" ] && find "$DATA_DIR" -type f ! -name '.DS_Store' -size -"$((MAX_COMMIT_BYTES / 512))"c >> "$BUNDLE_LIST" || true

tar -czf "$OUT/committable.tar.gz" \
  -C "$HOME" \
  $(sed "s|^$HOME/||" "$BUNDLE_LIST" | tr '\n' ' ') 2>/dev/null || \
  echo "note: nothing matched the size cap, or tar skipped entries -- check $BUNDLE_LIST"

echo
echo "== summary =="
printf 'files catalogued : %s\n' "$(( $(wc -l < "$OUT/manifest.tsv") - 1 ))"
printf 'total bytes      : %s\n' "$(awk -F'\t' 'NR>1{s+=$2} END{print s}' "$OUT/manifest.tsv")"
printf 'bundle           : %s (%s)\n' "$OUT/committable.tar.gz" \
  "$(wc -c < "$OUT/committable.tar.gz" 2>/dev/null | tr -d ' ' || echo 'not written')"
echo
echo "Largest ten files, so we know what we are deliberately NOT committing:"
awk -F'\t' 'NR>1{printf "%12d  %s\n", $2, $1}' "$OUT/manifest.tsv" | sort -rn | head -10
echo
echo "Next, from your laptop:  bash scripts/pull_vm_data.sh"
