#!/bin/bash
# Train the two-stage affinity prediction model on the VM

set -e

PY="$(dirname "$0")/../.venv/bin/python"
[ -x "$PY" ] || PY=python3

# Ensure we're in the right directory
cd "$(dirname "$0")/.."

# Check GPU availability
echo "=== GPU Check ==="
"$PY" -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU\"}')"

# Data paths
FACS_DATA="data/bucket/extracted/hackathon-data/her2-trastuzumab/tz_her2_facs_3classes_524346.csv.zip"
SPR_DATA="data/bucket/extracted/hackathon-data/her2-trastuzumab/trastuzumab_her2_spr_all_768.csv"

# Output directories
FACS_MODEL_DIR="models/facs"
SPR_MODEL_DIR="models/spr"

mkdir -p "$FACS_MODEL_DIR" "$SPR_MODEL_DIR"

echo ""
echo "=== Stage 1: Training FACS Classifier on 524k samples ==="
echo "Expected time on H100: 10-15 minutes"
echo ""

"$PY" pipeline/affinity_model.py train-facs \
    --data "$FACS_DATA" \
    --output "$FACS_MODEL_DIR" \
    --epochs 10 \
    --batch-size 512 \
    --lr 1e-3

echo ""
echo "=== Stage 2: Fine-tuning SPR Regressor on 190 samples ==="
echo "Expected time on H100: 2-3 minutes"
echo ""

"$PY" pipeline/affinity_model.py train-spr \
    --data "$SPR_DATA" \
    --encoder "$FACS_MODEL_DIR" \
    --output "$SPR_MODEL_DIR" \
    --epochs 300 \
    --batch-size 32 \
    --lr 1e-3

echo ""
echo "=== Training Complete ==="
echo "FACS classifier: $FACS_MODEL_DIR/facs_classifier_best.pt"
echo "SPR regressor: $SPR_MODEL_DIR/spr_regressor_best.pt"
echo ""
echo "To make predictions:"
echo "  python3 pipeline/affinity_model.py predict \\"
echo "    --sequences candidates.fasta \\"
echo "    --model $SPR_MODEL_DIR/spr_regressor_best.pt \\"
echo "    --output predictions.csv"
