"""Kronos tokenizer finetuning on CSV K-line data (stage 1 of 2).

Ported from the upstream Kronos project (``finetune_csv/finetune_tokenizer.py``),
https://github.com/shiyu-coder/Kronos (MIT License). Credit to the original
Kronos authors; adapted for the ZERO trading terminal.

Training logic is kept faithful to upstream:

* AdamW on all tokenizer parameters with ``tokenizer_learning_rate`` and
  ``adam_weight_decay`` (upstream deliberately uses default betas here).
* OneCycleLR (``pct_start=0.03``, ``div_factor=10``), stepped per batch.
* Loss = (MSE(z_pre, x) + MSE(z, x) + BSQ quantiser loss) / 2, with manual
  gradient accumulation over ``accumulation_steps`` sub-batches.
* Gradient-norm clipping at 2.0.
* Validation loss = sample-weighted MSE(z, x); the best checkpoint is
  written via ``save_pretrained`` to ``<save_dir>/best_model``.

Adaptations relative to upstream:

* Single-device training only (CPU or one CUDA GPU); all torchrun/DDP
  machinery (DistributedSampler, all_reduce, rank gating) was removed.
* tqdm progress bars (optional; plain iteration if tqdm is unavailable).
* Model classes are imported lazily from the vendored ``engine.kronos``
  package instead of the upstream ``model`` package.
* Comet ML experiment tracking was removed (upstream carried a
  ``use_comet`` flag through this script without using it).
* Console output goes through the logger (which mirrors to stdout) instead
  of upstream's duplicated ``logger.info`` + ``print`` pairs.
* All torch/numpy imports happen inside functions so the module imports
  cleanly without torch installed.

Note: upstream also ships a qlib-based tokenizer trainer
(``finetune/train_tokenizer.py``); only the CSV pipeline is ported here.

Usage (from ``D:\\ZERO_FRESH``)::

    python -m engine.kronos_finetune.finetune_tokenizer --config <config.yaml>
"""

import datetime
import logging
import os
import random
import time
from logging.handlers import RotatingFileHandler

from .config_loader import CustomFinetuneConfig
from .dataset import create_dataloaders


# ---------------------------------------------------------------------------
# Shared helpers (also used by finetune_model.py and run_sequential.py)
# ---------------------------------------------------------------------------
def require_torch():
    """Return the torch module, or None (with an actionable message) if absent."""
    try:
        import torch  # lazy heavy import
        return torch
    except ImportError:
        print(
            "PyTorch is required for Kronos finetuning but is not installed.\n"
            "Install a build suited to your hardware, e.g.:\n"
            "  pip install torch            (CPU)\n"
            "  pip install torch --index-url https://download.pytorch.org/whl/cu121  (CUDA 12.1)\n"
            "See https://pytorch.org/get-started/locally/ for other options."
        )
        return None


def import_kronos_classes():
    """Lazily import the vendored Kronos model classes.

    Returns:
        tuple: ``(Kronos, KronosTokenizer)`` classes from ``engine.kronos``.

    Raises:
        RuntimeError: if the vendored package is missing, with instructions.
    """
    try:
        from engine.kronos import Kronos, KronosTokenizer  # lazy heavy import
        return Kronos, KronosTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "The vendored Kronos model package (engine.kronos) is not "
            "available. It provides the Kronos / KronosTokenizer classes "
            "this pipeline finetunes. Ensure D:\\ZERO_FRESH\\engine\\kronos "
            "exists (mirrored from upstream Kronos model/) and that you run "
            f"from the ZERO project root. Original import error: {exc}"
        ) from exc


def set_seed(seed: int, rank: int = 0):
    """Seed python/numpy/torch RNGs for reproducibility (single process)."""
    import numpy as np  # lazy heavy import
    import torch  # lazy heavy import

    actual_seed = seed + rank
    random.seed(actual_seed)
    np.random.seed(actual_seed)
    torch.manual_seed(actual_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(actual_seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def get_model_size(model) -> str:
    """Human-readable count of trainable parameters, e.g. '24.7M'."""
    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if total_params >= 1e9:
        return f"{total_params / 1e9:.1f}B"
    elif total_params >= 1e6:
        return f"{total_params / 1e6:.1f}M"
    else:
        return f"{total_params / 1e3:.1f}K"


def format_time(seconds: float) -> str:
    return str(datetime.timedelta(seconds=int(seconds)))


def resolve_device(config):
    """Pick the training device from the config (single device, no DDP).

    Honours ``device.use_cuda`` / ``device.device_id`` and falls back to CPU
    with a notice when CUDA is requested but unavailable.
    """
    import torch  # lazy heavy import

    if getattr(config, "use_cuda", True):
        if torch.cuda.is_available():
            device_id = int(getattr(config, "device_id", 0))
            if device_id >= torch.cuda.device_count():
                print(
                    f"Warning: device.device_id={device_id} not present "
                    f"({torch.cuda.device_count()} CUDA device(s)); using cuda:0"
                )
                device_id = 0
            return torch.device(f"cuda:{device_id}")
        print("CUDA requested but not available; training on CPU instead.")
    return torch.device("cpu")


def maybe_tqdm(iterable, **kwargs):
    """Wrap an iterable in a tqdm progress bar when tqdm is installed."""
    try:
        from tqdm import tqdm  # lazy optional import
        return tqdm(iterable, **kwargs)
    except ImportError:
        return iterable


def setup_logging(exp_name: str, log_dir: str, rank: int = 0) -> logging.Logger:
    """Rotating file log + console echo for the tokenizer stage.

    The ``rank`` parameter is kept for upstream signature compatibility; the
    ZERO port always runs single-process (rank 0).
    """
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(f"kronos_finetune.tokenizer_rank_{rank}")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    log_file = os.path.join(log_dir, f"tokenizer_training_rank_{rank}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("=== Tokenizer Training Started ===")
    logger.info(f"Experiment Name: {exp_name}")
    logger.info(f"Log Directory: {log_dir}")
    logger.info(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return logger


def _tokenizer_from_arch_config(config_json_path: str):
    """Randomly initialise a KronosTokenizer from a local config.json.

    Used when ``experiment.pre_trained_tokenizer`` is false. Requires a local
    checkpoint directory (a bare Hugging Face hub id has no local config.json).
    """
    import json

    _, KronosTokenizer = import_kronos_classes()

    if not os.path.exists(config_json_path):
        raise FileNotFoundError(
            f"Cannot randomly initialise tokenizer: {config_json_path} not found. "
            "With experiment.pre_trained_tokenizer=false, "
            "model_paths.pretrained_tokenizer must be a local directory "
            "containing a config.json describing the architecture."
        )
    with open(config_json_path, "r") as f:
        arch = json.load(f)
    return KronosTokenizer(
        d_in=arch.get("d_in", 6),
        d_model=arch.get("d_model", 256),
        n_heads=arch.get("n_heads", 4),
        ff_dim=arch.get("ff_dim", 512),
        n_enc_layers=arch.get("n_enc_layers", 4),
        n_dec_layers=arch.get("n_dec_layers", 4),
        ffn_dropout_p=arch.get("ffn_dropout_p", 0.0),
        attn_dropout_p=arch.get("attn_dropout_p", 0.0),
        resid_dropout_p=arch.get("resid_dropout_p", 0.0),
        s1_bits=arch.get("s1_bits", 10),
        s2_bits=arch.get("s2_bits", 10),
        beta=arch.get("beta", 0.05),
        gamma0=arch.get("gamma0", 1.0),
        gamma=arch.get("gamma", 1.1),
        zeta=arch.get("zeta", 0.05),
        group_size=arch.get("group_size", 4),
    )


def load_tokenizer_for_training(config, logger=None):
    """Load the pretrained tokenizer (or random-init it) per the config."""
    _, KronosTokenizer = import_kronos_classes()

    if getattr(config, "pre_trained_tokenizer", True):
        msg = f"Loading pretrained tokenizer: {config.pretrained_tokenizer_path}"
        (logger.info if logger else print)(msg)
        tokenizer = KronosTokenizer.from_pretrained(config.pretrained_tokenizer_path)
    else:
        msg = "pre_trained_tokenizer=False, randomly initializing Tokenizer architecture"
        (logger.info if logger else print)(msg)
        cfg_path = os.path.join(config.pretrained_tokenizer_path, "config.json")
        tokenizer = _tokenizer_from_arch_config(cfg_path)
    return tokenizer


# ---------------------------------------------------------------------------
# Training loop (faithful port, single device)
# ---------------------------------------------------------------------------
def train_tokenizer(model, device, config, save_dir, logger):
    """Finetune the tokenizer; returns the best validation loss.

    Saves the best-validation-loss checkpoint (``save_pretrained``) to
    ``<save_dir>/best_model`` whenever validation improves.
    """
    import torch  # lazy heavy import
    import torch.nn.functional as F  # lazy heavy import

    logger.info("Starting tokenizer training...")

    train_loader, val_loader, train_dataset, val_dataset = create_dataloaders(config)

    # Upstream intentionally leaves AdamW betas at their defaults here
    # (unlike the predictor stage); kept faithful.
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.tokenizer_learning_rate,
        weight_decay=config.adam_weight_decay,
    )

    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=config.tokenizer_learning_rate,
        steps_per_epoch=len(train_loader),
        epochs=config.tokenizer_epochs,
        pct_start=0.03,
        div_factor=10,
    )

    best_val_loss = float("inf")
    batch_idx_global = 0
    accumulation_steps = getattr(config, "accumulation_steps", 1)
    training_start_time = time.time()

    for epoch in range(config.tokenizer_epochs):
        epoch_start_time = time.time()
        model.train()

        # Upstream epoch-seed convention (drives the deterministic
        # window-start formula inside the dataset).
        train_dataset.set_epoch_seed(epoch * 10000)
        val_dataset.set_epoch_seed(0)

        progress = maybe_tqdm(
            train_loader,
            desc=f"[tokenizer] epoch {epoch + 1}/{config.tokenizer_epochs}",
            leave=False,
        )
        for batch_idx, (ori_batch_x, _) in enumerate(progress):
            ori_batch_x = ori_batch_x.to(device, non_blocking=True)

            # Manual gradient accumulation over sub-batches (faithful port).
            current_batch_total_loss = 0.0
            for j in range(accumulation_steps):
                start_idx = j * (ori_batch_x.shape[0] // accumulation_steps)
                end_idx = (j + 1) * (ori_batch_x.shape[0] // accumulation_steps)
                batch_x = ori_batch_x[start_idx:end_idx]

                zs, bsq_loss, _, _ = model(batch_x)
                z_pre, z = zs

                recon_loss_pre = F.mse_loss(z_pre, batch_x)
                recon_loss_all = F.mse_loss(z, batch_x)
                recon_loss = recon_loss_pre + recon_loss_all
                loss = (recon_loss + bsq_loss) / 2

                loss_scaled = loss / accumulation_steps
                current_batch_total_loss += loss.item()
                loss_scaled.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            avg_loss = current_batch_total_loss / accumulation_steps
            lr = optimizer.param_groups[0]["lr"]
            if hasattr(progress, "set_postfix"):
                progress.set_postfix(loss=f"{avg_loss:.4f}", lr=f"{lr:.2e}")

            if (batch_idx_global + 1) % config.log_interval == 0:
                logger.info(
                    f"[Epoch {epoch + 1}/{config.tokenizer_epochs}, "
                    f"Step {batch_idx + 1}/{len(train_loader)}] "
                    f"LR: {lr:.6f}, Loss: {avg_loss:.4f}"
                )
                logger.info(
                    f"  - VQ Loss: {bsq_loss.item():.4f}\n"
                    f"  - Recon Loss Pre: {recon_loss_pre.item():.4f}\n"
                    f"  - Recon Loss All: {recon_loss_all.item():.4f}"
                )

            batch_idx_global += 1

        # ------------------------- validation -------------------------
        model.eval()
        tot_val_loss_sum = 0.0
        val_sample_count = 0

        with torch.no_grad():
            val_progress = maybe_tqdm(
                val_loader,
                desc=f"[tokenizer] val {epoch + 1}/{config.tokenizer_epochs}",
                leave=False,
            )
            for ori_batch_x, _ in val_progress:
                ori_batch_x = ori_batch_x.to(device, non_blocking=True)
                zs, _, _, _ = model(ori_batch_x)
                _, z = zs
                val_loss_item = F.mse_loss(z, ori_batch_x)

                tot_val_loss_sum += val_loss_item.item() * ori_batch_x.size(0)
                val_sample_count += ori_batch_x.size(0)

        avg_val_loss = tot_val_loss_sum / val_sample_count if val_sample_count > 0 else 0.0

        epoch_time = time.time() - epoch_start_time
        logger.info(
            f"\n--- Epoch {epoch + 1}/{config.tokenizer_epochs} Summary ---\n"
            f"Validation Loss: {avg_val_loss:.4f}\n"
            f"Epoch Time: {format_time(epoch_time)}\n"
            f"Total Training Time: {format_time(time.time() - training_start_time)}\n"
        )

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            model_save_path = os.path.join(save_dir, "best_model")
            os.makedirs(model_save_path, exist_ok=True)
            model.save_pretrained(model_save_path)
            logger.info(
                f"Best model saved to: {model_save_path} "
                f"(validation loss: {best_val_loss:.4f})"
            )

    return best_val_loss


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Kronos Tokenizer Fine-tuning Training")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Configuration file path (default: packaged example config)",
    )
    args = parser.parse_args()

    torch = require_torch()
    if torch is None:
        raise SystemExit(2)

    config = CustomFinetuneConfig(args.config)
    config.validate()

    device = resolve_device(config)
    print(f"Using device: {device}")

    os.makedirs(config.tokenizer_save_path, exist_ok=True)
    logger = setup_logging(config.exp_name, config.log_dir, 0)

    set_seed(config.seed)

    tokenizer = load_tokenizer_for_training(config, logger)
    tokenizer = tokenizer.to(device)

    model_size = get_model_size(tokenizer)
    logger.info(f"Tokenizer parameters: {model_size}")

    logger.info("=== Training Configuration ===")
    logger.info(f"Data path: {config.data_path}")
    logger.info(f"Lookback window: {config.lookback_window}")
    logger.info(f"Predict window: {config.predict_window}")
    logger.info(f"Batch size: {config.batch_size}")
    logger.info(f"Learning rate: {config.tokenizer_learning_rate}")
    logger.info(f"Training epochs: {config.tokenizer_epochs}")
    logger.info(f"Device: {device}")

    logger.info("Starting tokenizer fine-tuning training...")
    best_val_loss = train_tokenizer(tokenizer, device, config, config.tokenizer_save_path, logger)

    logger.info(
        f"Tokenizer training completed! Best validation loss: {best_val_loss:.4f}\n"
        f"Model saved to: {config.tokenizer_best_model_path}"
    )


if __name__ == "__main__":
    main()
