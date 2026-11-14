#!/usr/bin/env python3
"""
GPU-Accelerated Affinity Prediction Model
Two-stage transfer learning: FACS (524k) → SPR (190)

Usage:
    # Stage 1: Train on FACS data
    python affinity_model.py train-facs --data data/bucket/extracted/hackathon-data/her2-trastuzumab/tz_her2_facs_3classes_524346.csv.zip

    # Stage 2: Fine-tune on SPR data
    python affinity_model.py train-spr --data data/bucket/extracted/hackathon-data/her2-trastuzumab/trastuzumab_her2_spr_all_768.csv

    # Inference
    python affinity_model.py predict --sequences sequences.fasta --output predictions.csv
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
from pathlib import Path
import zipfile
from typing import List, Dict, Tuple, Optional
import argparse
from tqdm import tqdm
import json
from Bio import SeqIO
from sklearn.model_selection import train_test_split
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix,
                             r2_score, mean_absolute_error)
from scipy.stats import spearmanr
import warnings
warnings.filterwarnings('ignore')

# Single seed for every train/val/test split, so stage 1 and stage 2 are reproducible
# and re-runs do not leak the test split into training.
SPLIT_SEED = 42
SPLIT_FRACTIONS = {'train': 0.70, 'val': 0.10, 'test': 0.20}


# ============================================================================
# AMINO ACID ENCODING AND FEATURE ENGINEERING
# ============================================================================

AA_ALPHABET = "ACDEFGHIKLMNPQRSTVWY"
AA_TO_IDX = {aa: idx for idx, aa in enumerate(AA_ALPHABET)}
AA_TO_IDX['X'] = len(AA_ALPHABET)  # Unknown
VOCAB_SIZE = len(AA_ALPHABET) + 1

# Physicochemical properties (normalized)
AA_PROPERTIES = {
    'A': [0.07, 0.00, 0.00],  # [hydrophobicity, charge, size]
    'C': [0.29, 0.00, 0.15],
    'D': [-0.90, -1.00, 0.23],
    'E': [-0.74, -1.00, 0.38],
    'F': [1.00, 0.00, 0.69],
    'G': [0.00, 0.00, 0.00],
    'H': [-0.40, 0.50, 0.46],
    'I': [0.73, 0.00, 0.46],
    'K': [-1.50, 1.00, 0.54],
    'L': [0.53, 0.00, 0.46],
    'M': [0.26, 0.00, 0.46],
    'N': [-0.78, 0.00, 0.31],
    'P': [0.00, 0.00, 0.31],
    'Q': [-0.85, 0.00, 0.38],
    'R': [-2.53, 1.00, 0.62],
    'S': [-0.18, 0.00, 0.15],
    'T': [-0.05, 0.00, 0.23],
    'V': [0.54, 0.00, 0.31],
    'W': [0.81, 0.00, 1.00],
    'Y': [0.26, 0.00, 0.77],
    'X': [0.00, 0.00, 0.00],
}


def seq_to_indices(seq: str, max_len: int = 15) -> torch.Tensor:
    """Convert amino acid sequence to tensor of indices"""
    indices = [AA_TO_IDX.get(aa, AA_TO_IDX['X']) for aa in seq.upper()]
    # Pad or truncate
    if len(indices) < max_len:
        indices += [AA_TO_IDX['X']] * (max_len - len(indices))
    else:
        indices = indices[:max_len]
    return torch.tensor(indices, dtype=torch.long)


def compute_features(seq: str, reference_seq: str = "WGGDGFYAMD") -> np.ndarray:
    """Compute hand-crafted features for a sequence"""
    features = []

    # 1. Sequence length
    features.append(len(seq) / 15.0)  # Normalized

    # 2. Edit distance from wild-type trastuzumab
    edit_dist = sum(a != b for a, b in zip(seq, reference_seq))
    features.append(edit_dist / len(reference_seq))

    # 3. Amino acid composition
    aa_counts = {aa: seq.count(aa) / len(seq) for aa in AA_ALPHABET}
    features.extend([aa_counts.get(aa, 0) for aa in AA_ALPHABET])

    # 4. Physicochemical properties (avg across sequence)
    props = np.array([AA_PROPERTIES.get(aa, [0, 0, 0]) for aa in seq])
    features.extend(props.mean(axis=0).tolist())  # avg hydrophobicity, charge, size

    # 5. Positional encodings (first 3 and last 3 positions)
    padded = (seq + 'XXX')[:3]  # First 3
    for aa in padded:
        features.append(AA_TO_IDX.get(aa, AA_TO_IDX['X']) / VOCAB_SIZE)
    padded = ('XXX' + seq)[-3:]  # Last 3
    for aa in padded:
        features.append(AA_TO_IDX.get(aa, AA_TO_IDX['X']) / VOCAB_SIZE)

    return np.array(features, dtype=np.float32)


# ============================================================================
# DATASETS
# ============================================================================

class FACSDataset(Dataset):
    """Dataset for FACS binding classification (524k samples)"""

    def __init__(self, csv_path: str, max_len: int = 15):
        self.max_len = max_len

        # Load data (handle zip file)
        if csv_path.endswith('.zip'):
            with zipfile.ZipFile(csv_path) as zf:
                csv_name = [n for n in zf.namelist() if n.endswith('.csv')][0]
                with zf.open(csv_name) as f:
                    self.df = pd.read_csv(f)
        else:
            self.df = pd.read_csv(csv_path)

        # Map binding classes to integers
        self.label_map = {'low': 0, 'medium': 1, 'high': 2}
        self.df['label'] = self.df['binding_class'].map(self.label_map)

        print(f"Loaded {len(self.df)} FACS samples")
        print(f"Class distribution: {self.df['binding_class'].value_counts().to_dict()}")

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        seq = row['cdrh3']
        label = row['label']

        seq_tensor = seq_to_indices(seq, self.max_len)
        return seq_tensor, label


class SPRDataset(Dataset):
    """Dataset for SPR affinity regression (190 samples with KD)"""

    def __init__(self, csv_path: str, max_len: int = 15, reference_seq: str = "WGGDGFYAMD"):
        self.max_len = max_len
        self.reference_seq = reference_seq

        # Load data
        df = pd.read_csv(csv_path)

        # Filter only quantified binding with KD values
        self.df = df[df['binding_result'] == 'quantified_binding'].copy()
        self.df = self.df.dropna(subset=['kd_nM'])

        # Log-transform KD (spans 6 orders of magnitude)
        self.df['log_kd'] = np.log10(self.df['kd_nM'])

        print(f"Loaded {len(self.df)} SPR samples with KD")
        print(f"KD range: {self.df['kd_nM'].min():.3f} - {self.df['kd_nM'].max():.1f} nM")
        print(f"Log KD range: {self.df['log_kd'].min():.2f} - {self.df['log_kd'].max():.2f}")

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        seq = row['cdrh3']
        log_kd = row['log_kd']

        seq_tensor = seq_to_indices(seq, self.max_len)
        features = compute_features(seq, self.reference_seq)

        return seq_tensor, torch.tensor(features, dtype=torch.float32), log_kd


# ============================================================================
# MODELS
# ============================================================================

class SequenceEncoder(nn.Module):
    """Transformer-based sequence encoder"""

    def __init__(self, vocab_size: int = VOCAB_SIZE, embed_dim: int = 64,
                 num_heads: int = 4, num_layers: int = 2, hidden_dim: int = 128):
        super().__init__()

        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=AA_TO_IDX['X'])

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim,
            dropout=0.1,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        self.output_dim = embed_dim

    def forward(self, x):
        # x: [batch, seq_len]
        embedded = self.embedding(x)  # [batch, seq_len, embed_dim]

        # Create padding mask
        padding_mask = (x == AA_TO_IDX['X'])

        # Transformer
        encoded = self.transformer(embedded, src_key_padding_mask=padding_mask)

        # Global average pooling (excluding padding)
        mask = (~padding_mask).unsqueeze(-1).float()
        pooled = (encoded * mask).sum(dim=1) / mask.sum(dim=1)

        return pooled


class FACSClassifier(nn.Module):
    """FACS binding classifier (high/medium/low)"""

    def __init__(self, encoder: SequenceEncoder, num_classes: int = 3):
        super().__init__()
        self.encoder = encoder

        self.classifier = nn.Sequential(
            nn.Linear(encoder.output_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes)
        )

    def forward(self, x):
        features = self.encoder(x)
        logits = self.classifier(features)
        return logits


class SPRRegressor(nn.Module):
    """SPR affinity regressor (log KD prediction)"""

    def __init__(self, encoder: SequenceEncoder, feature_dim: int):
        super().__init__()
        self.encoder = encoder

        # Freeze encoder (transfer learning from FACS)
        for param in self.encoder.parameters():
            param.requires_grad = False

        combined_dim = encoder.output_dim + feature_dim

        self.regressor = nn.Sequential(
            nn.Linear(combined_dim, 192),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(192, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1)
        )

    def forward(self, seq, features):
        seq_embedding = self.encoder(seq)
        combined = torch.cat([seq_embedding, features], dim=1)
        log_kd = self.regressor(combined)
        return log_kd.squeeze()


# ============================================================================
# TRAINING
# ============================================================================

def train_facs_classifier(data_path: str, output_dir: Path, epochs: int = 10,
                          batch_size: int = 512, lr: float = 1e-3):
    """Stage 1: Train on FACS data"""

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    torch.manual_seed(SPLIT_SEED)          # reproducible weight init / shuffling
    np.random.seed(SPLIT_SEED)

    # Load data
    dataset = FACSDataset(data_path)

    # 70 / 10 / 20 train / val / test, stratified on binding class, fixed seed
    labels = dataset.df['label'].values
    train_idx, holdout_idx = train_test_split(
        np.arange(len(dataset)), test_size=0.30, random_state=SPLIT_SEED, stratify=labels
    )
    # 20% test + 10% val out of the 30% holdout -> test is 2/3 of the holdout
    val_idx, test_idx = train_test_split(
        holdout_idx, test_size=2.0 / 3.0, random_state=SPLIT_SEED, stratify=labels[holdout_idx]
    )
    print(f"Split: train={len(train_idx)} ({len(train_idx)/len(dataset):.1%}) "
          f"val={len(val_idx)} ({len(val_idx)/len(dataset):.1%}) "
          f"test={len(test_idx)} ({len(test_idx)/len(dataset):.1%})")

    train_dataset = torch.utils.data.Subset(dataset, train_idx.tolist())
    val_dataset = torch.utils.data.Subset(dataset, val_idx.tolist())
    test_dataset = torch.utils.data.Subset(dataset, test_idx.tolist())

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, num_workers=4)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, num_workers=4)

    # Model
    encoder = SequenceEncoder()
    model = FACSClassifier(encoder).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # Training loop
    best_acc = 0
    for epoch in range(epochs):
        model.train()
        train_loss = 0

        pbar = tqdm(train_loader, desc=f'Epoch {epoch+1}/{epochs}')
        for seq, labels in pbar:
            seq, labels = seq.to(device), labels.to(device)

            optimizer.zero_grad()
            logits = model(seq)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            pbar.set_postfix({'loss': loss.item()})

        # Validation
        model.eval()
        val_preds, val_labels = [], []
        with torch.no_grad():
            for seq, labels in val_loader:
                seq = seq.to(device)
                logits = model(seq)
                preds = logits.argmax(dim=1).cpu().numpy()
                val_preds.extend(preds)
                val_labels.extend(labels.numpy())

        acc = accuracy_score(val_labels, val_preds)
        print(f"Epoch {epoch+1}: Train Loss = {train_loss/len(train_loader):.4f}, Val Acc = {acc:.4f}")

        # Save best model
        if acc > best_acc:
            best_acc = acc
            output_dir.mkdir(parents=True, exist_ok=True)
            torch.save({
                'encoder': encoder.state_dict(),
                'model': model.state_dict(),
                'epoch': epoch,
                'accuracy': acc,
                'split_seed': SPLIT_SEED,
                'split_fractions': SPLIT_FRACTIONS,
            }, output_dir / 'facs_classifier_best.pt')

        scheduler.step()

    print(f"\nBest validation accuracy: {best_acc:.4f}")

    # Held-out test evaluation, using the best-validation checkpoint
    checkpoint = torch.load(output_dir / 'facs_classifier_best.pt')
    model.load_state_dict(checkpoint['model'])
    model.eval()
    test_preds, test_labels = [], []
    with torch.no_grad():
        for seq, lbl in test_loader:
            seq = seq.to(device)
            test_preds.extend(model(seq).argmax(dim=1).cpu().numpy())
            test_labels.extend(lbl.numpy())

    test_acc = accuracy_score(test_labels, test_preds)
    test_bal_acc = balanced_accuracy_score(test_labels, test_preds)
    print(f"TEST accuracy = {test_acc:.4f}  balanced accuracy = {test_bal_acc:.4f}")
    print("TEST confusion matrix (rows=true low/medium/high):")
    print(confusion_matrix(test_labels, test_preds))

    metrics = {
        'stage': 'facs_classifier',
        'split_seed': SPLIT_SEED,
        'split_fractions': SPLIT_FRACTIONS,
        'n_train': len(train_idx), 'n_val': len(val_idx), 'n_test': len(test_idx),
        'best_epoch': int(checkpoint['epoch']) + 1,
        'val_accuracy': float(best_acc),
        'test_accuracy': float(test_acc),
        'test_balanced_accuracy': float(test_bal_acc),
        'test_confusion_matrix': confusion_matrix(test_labels, test_preds).tolist(),
    }
    (output_dir / 'facs_metrics.json').write_text(json.dumps(metrics, indent=2))
    print(f"Metrics written to {output_dir / 'facs_metrics.json'}")

    return encoder


def train_spr_regressor(data_path: str, encoder_path: Path, output_dir: Path,
                        epochs: int = 50, batch_size: int = 32, lr: float = 1e-4):
    """Stage 2: Fine-tune on SPR data"""

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    torch.manual_seed(SPLIT_SEED)          # reproducible weight init / shuffling
    np.random.seed(SPLIT_SEED)

    # Load pre-trained encoder
    encoder = SequenceEncoder()
    checkpoint = torch.load(encoder_path / 'facs_classifier_best.pt')
    encoder.load_state_dict(checkpoint['encoder'])
    print(f"Loaded encoder from FACS training (acc: {checkpoint['accuracy']:.4f})")

    # Load data
    dataset = SPRDataset(data_path)

    # 70 / 10 / 20 train / val / test, stratified on log-KD quartile so all three
    # splits span the affinity range (the set is small, so an unstratified draw can
    # put every tight binder on one side).
    indices = np.arange(len(dataset))
    strata = pd.qcut(dataset.df['log_kd'].values, q=4, labels=False, duplicates='drop')
    train_idx, holdout_idx = train_test_split(
        indices, test_size=0.30, random_state=SPLIT_SEED, stratify=strata
    )
    val_idx, test_idx = train_test_split(
        holdout_idx, test_size=2.0 / 3.0, random_state=SPLIT_SEED, stratify=strata[holdout_idx]
    )
    print(f"Split: train={len(train_idx)} ({len(train_idx)/len(dataset):.1%}) "
          f"val={len(val_idx)} ({len(val_idx)/len(dataset):.1%}) "
          f"test={len(test_idx)} ({len(test_idx)/len(dataset):.1%})")

    train_dataset = torch.utils.data.Subset(dataset, train_idx.tolist())
    val_dataset = torch.utils.data.Subset(dataset, val_idx.tolist())
    test_dataset = torch.utils.data.Subset(dataset, test_idx.tolist())

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)
    test_loader = DataLoader(test_dataset, batch_size=batch_size)

    # Get feature dimension from first sample
    _, features, _ = dataset[0]
    feature_dim = len(features)

    # Standardise target and hand-crafted features using the TRAIN split only.
    # Without this the regressor head starts near 0 while log10(KD) has mean ~2, and
    # at a small lr with ~5 steps/epoch it never reaches the target range -- which is
    # exactly the failure mode (train loss stuck at the target variance) seen before.
    y_train = dataset.df['log_kd'].values[train_idx]
    y_mean, y_std = float(y_train.mean()), float(y_train.std() + 1e-8)
    feat_train = np.stack([dataset[i][1].numpy() for i in train_idx])
    feat_mean = feat_train.mean(axis=0)
    feat_std = feat_train.std(axis=0) + 1e-8
    print(f"Target standardisation (train split): mean={y_mean:.3f} std={y_std:.3f}")
    fm = torch.tensor(feat_mean, dtype=torch.float32, device=device)
    fs = torch.tensor(feat_std, dtype=torch.float32, device=device)

    def forward_log_kd(seq, feats):
        """Model forward returning predictions in log10(KD) units."""
        return model(seq, (feats - fm) / fs) * y_std + y_mean

    # Model
    model = SPRRegressor(encoder, feature_dim).to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.AdamW(model.regressor.parameters(), lr=lr)  # Only train regressor
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5)

    # Training loop
    best_r2 = -float('inf')
    for epoch in range(epochs):
        model.train()
        train_loss = 0

        for seq, features, log_kd in train_loader:
            seq = seq.to(device)
            features = features.to(device)
            log_kd = log_kd.to(device).float()

            optimizer.zero_grad()
            pred = model(seq, (features - fm) / fs)
            loss = criterion(pred, (log_kd - y_mean) / y_std)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()

        # Validation
        model.eval()
        val_preds, val_true = [], []
        with torch.no_grad():
            for seq, features, log_kd in val_loader:
                seq = seq.to(device)
                features = features.to(device)
                pred = forward_log_kd(seq, features).cpu().numpy()
                val_preds.extend(np.atleast_1d(pred))
                val_true.extend(np.atleast_1d(log_kd.numpy()))

        val_preds = np.array(val_preds)
        val_true = np.array(val_true)

        r2 = r2_score(val_true, val_preds)
        mae = mean_absolute_error(val_true, val_preds)

        # Convert back to KD for interpretability
        kd_preds = 10 ** val_preds
        kd_true = 10 ** val_true
        kd_mae = mean_absolute_error(kd_true, kd_preds)

        print(f"Epoch {epoch+1}: Train Loss = {train_loss/len(train_loader):.4f}, "
              f"Val R² = {r2:.4f}, MAE (log) = {mae:.4f}, MAE (KD) = {kd_mae:.1f} nM")

        # Save best model
        if r2 > best_r2:
            best_r2 = r2
            output_dir.mkdir(parents=True, exist_ok=True)
            torch.save({
                'model': model.state_dict(),
                'encoder': encoder.state_dict(),
                'epoch': epoch,
                'r2': r2,
                'mae': mae,
                'feature_dim': feature_dim,
                'y_mean': y_mean, 'y_std': y_std,
                'feat_mean': feat_mean.tolist(), 'feat_std': feat_std.tolist(),
                'split_seed': SPLIT_SEED,
                'split_fractions': SPLIT_FRACTIONS,
            }, output_dir / 'spr_regressor_best.pt')

        scheduler.step(r2)

    print(f"\nBest validation R²: {best_r2:.4f}")

    # Held-out test evaluation, using the best-validation checkpoint
    checkpoint = torch.load(output_dir / 'spr_regressor_best.pt')
    model.load_state_dict(checkpoint['model'])
    model.eval()
    test_preds, test_true = [], []
    with torch.no_grad():
        for seq, feats, log_kd in test_loader:
            pred = forward_log_kd(seq.to(device), feats.to(device)).cpu().numpy()
            test_preds.extend(np.atleast_1d(pred))
            test_true.extend(np.atleast_1d(log_kd.numpy()))

    test_preds, test_true = np.array(test_preds), np.array(test_true)
    test_r2 = r2_score(test_true, test_preds)
    test_mae = mean_absolute_error(test_true, test_preds)
    test_rmse = float(np.sqrt(np.mean((test_true - test_preds) ** 2)))
    test_spearman = float(spearmanr(test_true, test_preds).correlation)
    test_kd_mae = mean_absolute_error(10 ** test_true, 10 ** test_preds)

    print(f"TEST R² = {test_r2:.4f}  Spearman rho = {test_spearman:.4f}  "
          f"MAE (log10 KD) = {test_mae:.4f}  RMSE (log10 KD) = {test_rmse:.4f}  "
          f"MAE (KD) = {test_kd_mae:.1f} nM")

    metrics = {
        'stage': 'spr_regressor',
        'split_seed': SPLIT_SEED,
        'split_fractions': SPLIT_FRACTIONS,
        'n_train': len(train_idx), 'n_val': len(val_idx), 'n_test': len(test_idx),
        'best_epoch': int(checkpoint['epoch']) + 1,
        'val_r2': float(best_r2),
        'test_r2': float(test_r2),
        'test_spearman': test_spearman,
        'test_mae_log_kd': float(test_mae),
        'test_rmse_log_kd': test_rmse,
        'test_mae_kd_nM': float(test_kd_mae),
    }
    (output_dir / 'spr_metrics.json').write_text(json.dumps(metrics, indent=2))
    print(f"Metrics written to {output_dir / 'spr_metrics.json'}")


# ============================================================================
# INFERENCE
# ============================================================================

def predict_affinity(sequences: List[str], model_path: Path) -> pd.DataFrame:
    """Predict affinity for new sequences"""

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # Load model
    checkpoint = torch.load(model_path)
    feature_dim = checkpoint['feature_dim']

    encoder = SequenceEncoder()
    model = SPRRegressor(encoder, feature_dim)
    model.load_state_dict(checkpoint['model'])
    model.to(device)
    model.eval()

    # Prepare data
    seq_tensors = torch.stack([seq_to_indices(seq) for seq in sequences])
    feature_tensors = torch.stack([
        torch.tensor(compute_features(seq), dtype=torch.float32)
        for seq in sequences
    ])

    # Apply the same standardisation that was fitted on the training split
    y_mean = checkpoint.get('y_mean', 0.0)
    y_std = checkpoint.get('y_std', 1.0)
    feat_mean = torch.tensor(checkpoint.get('feat_mean', [0.0] * feature_dim),
                             dtype=torch.float32, device=device)
    feat_std = torch.tensor(checkpoint.get('feat_std', [1.0] * feature_dim),
                            dtype=torch.float32, device=device)

    # Predict
    with torch.no_grad():
        seq_tensors = seq_tensors.to(device)
        feature_tensors = (feature_tensors.to(device) - feat_mean) / feat_std
        log_kd_pred = model(seq_tensors, feature_tensors).cpu().numpy() * y_std + y_mean

    kd_pred = 10 ** log_kd_pred

    results = pd.DataFrame({
        'cdrh3': sequences,
        'predicted_log_kd': log_kd_pred,
        'predicted_kd_nM': kd_pred
    })

    return results


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Affinity Prediction Model')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Train FACS
    train_facs = subparsers.add_parser('train-facs', help='Train classifier on FACS data')
    train_facs.add_argument('--data', required=True, help='Path to FACS CSV/zip')
    train_facs.add_argument('--output', default='models/facs', help='Output directory')
    train_facs.add_argument('--epochs', type=int, default=10)
    train_facs.add_argument('--batch-size', type=int, default=512)
    train_facs.add_argument('--lr', type=float, default=1e-3)

    # Train SPR
    train_spr = subparsers.add_parser('train-spr', help='Train regressor on SPR data')
    train_spr.add_argument('--data', required=True, help='Path to SPR CSV')
    train_spr.add_argument('--encoder', default='models/facs', help='Path to pretrained encoder')
    train_spr.add_argument('--output', default='models/spr', help='Output directory')
    train_spr.add_argument('--epochs', type=int, default=50)
    train_spr.add_argument('--batch-size', type=int, default=32)
    train_spr.add_argument('--lr', type=float, default=1e-4)

    # Predict
    predict = subparsers.add_parser('predict', help='Predict affinity for sequences')
    predict.add_argument('--sequences', required=True, help='Path to FASTA file')
    predict.add_argument('--model', default='models/spr/spr_regressor_best.pt')
    predict.add_argument('--output', required=True, help='Output CSV path')

    args = parser.parse_args()

    if args.command == 'train-facs':
        train_facs_classifier(
            args.data,
            Path(args.output),
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr
        )

    elif args.command == 'train-spr':
        train_spr_regressor(
            args.data,
            Path(args.encoder),
            Path(args.output),
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr
        )

    elif args.command == 'predict':
        # Load sequences from FASTA
        sequences = [str(rec.seq) for rec in SeqIO.parse(args.sequences, 'fasta')]

        # Predict
        results = predict_affinity(sequences, Path(args.model))

        # Save
        results.to_csv(args.output, index=False)
        print(f"Predictions saved to {args.output}")
        print(f"\nSummary:")
        print(results.describe())


if __name__ == '__main__':
    main()
