"""Kronos base-model (predictor) finetuning on CSV K-line data (stage 2 of 2).

Ported from the upstream Kronos project (``finetune_csv/finetune_base_model.py``),
https://github.com/shiyu-coder/Kronos (MIT License). Credit to the original
Kronos authors; adapted for the ZERO trading terminal.

The stage loads the tokenizer finetuned in stage 1 (frozen: it only encodes
inputs under ``torch.no_grad()``), then trains the autoregressive Kronos
model on next-token prediction over the tokenized K-line windows.

Training logic is kept faithful to upstream:

* AdamW with ``predictor_learning_rate``, betas ``(adam_beta1, adam_beta2)``
  and ``adam_weight_decay``.
* OneCycleLR (``pct_start=0.03``, ``div_factor=10``), stepped per batch.
* On-the-fly tokenisation via ``tokenizer.encode(batch_x, half=True)``;
  inputs/targets are the token sequences shifted by one step; loss comes
  from ``model.head.compute_loss`` (S1 + S2 cross-entropy).
* Gradient-norm clipping at 3.0.
* Best checkpoint (lowest validation loss) saved via ``save_pretrained``
  to ``<save_dir>/best_model``.

Adaptations relative to upstream (mirroring ``finetune_tokenizer.py``):

* Single-device training only; DDP/torchrun machinery removed.
* tqdm progress bars (optional), lazy torch imports, models imported from
  the vendored ``engine.kronos`` package, no Comet ML.
* ``tokenizer.eval()`` is called explicitly before training (the upstream
  CSV script left the tokenizer in train mode; the upstream qlib pipeline
  calls ``eval()``, and it is strictly more correct for a frozen encoder —
  a no-op for the default dropout-free tokenizer configs).

Note: upstream also ships a qlib-based predictor trainer
(``finetune/train_predictor.py``); only the CSV pipeline is ported here.

Usage (from ``D:\\ZERO_FRESH``)::

    python -m engine.kronos_finetune.finetune_model --config <config.yaml>
"""

import datetime
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler

from .config_loader import CustomFinetuneConfig
from .dataset import create_dataloaders
from .finetune_tokenizer import (
    format_time,
    get_model_size,
    import_kronos_classes,
    maybe_tqdm,
    require_torch,
    resolve_device,
    set_seed,
)


def setup_logging(exp_name: str, log_dir: str, rank: int = 0) -> logging.Logger:
    """Rotating file log + console echo for the base-model stage.

    ``rank`` is kept for upstream signature compatibility (always 0 here).
    """
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(f"kronos_finetune.basemodel_rank_{rank}")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    log_file = os.path.join(log_dir, f"basemodel_training_rank_{rank}.log")
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

    logger.info("=== Basemodel Training Started ===")
    logger.info(f"Experiment Name: {exp_name}")
    logger.info(f"Log Directory: {log_dir}")
    logger.info(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return logger


def _predictor_from_arch_config(config_json_path: str):
    """Randomly initialise a Kronos predictor from a local config.json.

    Used when ``experiment.pre_trained_predictor`` is false. Requires a local
    checkpoint directory (a bare Hugging Face hub id has no local config.json).
    """
    Kronos, _ = import_kronos_classes()

    if not os.path.exists(config_json_path):
        raise FileNotFoundError(
            f"Cannot randomly initialise predictor: {config_json_path} not found. "
            "With experiment.pre_trained_predictor=false, "
            "model_paths.pretrained_predictor must be a local directory "
            "containing a config.json describing the architecture."
        )
    with open(config_json_path, "r") as f:
        arch = json.load(f)
    print("model_config: ", arch)
    return Kronos(
        s1_bits=arch.get("s1_bits", 10),
        s2_bits=arch.get("s2_bits", 10),
        n_layers=arch.get("n_layers", 12),
        d_model=arch.get("d_model", 832),
        n_heads=arch.get("n_heads", 16),
        ff_dim=arch.get("ff_dim", 2048),
        ffn_dropout_p=arch.get("ffn_dropout_p", 0.2),
        attn_dropout_p=arch.get("attn_dropout_p", 0.0),
        resid_dropout_p=arch.get("resid_dropout_p", 0.2),
        token_dropout_p=arch.get("token_dropout_p", 0.0),
        learn_te=arch.get("learn_te", True),
    )


def load_models_for_training(config, logger=None):
    """Load the (finetuned) tokenizer and the Kronos predictor per config.

    Returns:
        tuple: ``(model, tokenizer)`` — the trainable Kronos predictor and
        the frozen tokenizer used for on-the-fly encoding.
    """
    Kronos, KronosTokenizer = import_kronos_classes()
    emit = logger.info if logger else print

    # --- tokenizer: the stage-1 finetuned checkpoint (or random init) ---
    if getattr(config, "pre_trained_tokenizer", True):
        if not os.path.exists(config.finetuned_tokenizer_path):
            raise FileNotFoundError(
                f"Fine-tuned tokenizer does not exist: {config.finetuned_tokenizer_path}. "
                "Run the tokenizer stage first (finetune_tokenizer / run_sequential) "
                "or point model_paths.finetuned_tokenizer at an existing checkpoint."
            )
        emit(f"Loading fine-tuned tokenizer: {config.finetuned_tokenizer_path}")
        tokenizer = KronosTokenizer.from_pretrained(config.finetuned_tokenizer_path)
    else:
        emit("pre_trained_tokenizer=False, randomly initializing Tokenizer architecture for Predictor training")
        from .finetune_tokenizer import _tokenizer_from_arch_config
        cfg_path = os.path.join(config.pretrained_tokenizer_path, "config.json")
        tokenizer = _tokenizer_from_arch_config(cfg_path)

    # --- predictor: pretrained weights (or random init from arch json) ---
    if getattr(config, "pre_trained_predictor", True):
        emit(f"Loading pretrained predictor: {config.pretrained_predictor_path}")
        model = Kronos.from_pretrained(config.pretrained_predictor_path)
    else:
        emit("pre_trained_predictor=False, randomly initializing Predictor architecture")
        cfg_path = os.path.join(config.pretrained_predictor_path, "config.json")
        model = _predictor_from_arch_config(cfg_path)

    return model, tokenizer


def train_model(model, tokenizer, device, config, save_dir, logger):
    """Finetune the Kronos predictor; returns the best validation loss.

    The tokenizer is only used to encode batches (no gradients); the best
    predictor checkpoint is written to ``<save_dir>/best_model``.
    """
    import torch  # lazy heavy import

    logger.info("Starting training...")

    train_loader, val_loader, train_dataset, val_dataset = create_dataloaders(config)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.predictor_learning_rate,
        betas=(config.adam_beta1, config.adam_beta2),
        weight_decay=config.adam_weight_decay,
    )

    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=config.predictor_learning_rate,
        steps_per_epoch=len(train_loader),
        epochs=config.basemodel_epochs,
        pct_start=0.03,
        div_factor=10,
    )

    tokenizer.eval()  # frozen encoder (see module docstring)

    best_val_loss = float("inf")
    batch_idx_global = 0

    for epoch in range(config.basemodel_epochs):
        epoch_start_time = time.time()
        model.train()

        train_dataset.set_epoch_seed(epoch * 10000)
        val_dataset.set_epoch_seed(0)

        epoch_train_loss = 0.0
        train_batches = 0

        progress = maybe_tqdm(
            train_loader,
            desc=f"[basemodel] epoch {epoch + 1}/{config.basemodel_epochs}",
            leave=False,
        )
        for batch_idx, (batch_x, batch_x_stamp) in enumerate(progress):
            batch_x = batch_x.to(device, non_blocking=True)
            batch_x_stamp = batch_x_stamp.to(device, non_blocking=True)

            # Tokenize the continuous K-line window on the fly.
            with torch.no_grad():
                token_seq_0, token_seq_1 = tokenizer.encode(batch_x, half=True)

            # Next-token prediction: inputs are tokens [0..T-1], targets [1..T].
            token_in = [token_seq_0[:, :-1], token_seq_1[:, :-1]]
            token_out = [token_seq_0[:, 1:], token_seq_1[:, 1:]]

            logits = model(token_in[0], token_in[1], batch_x_stamp[:, :-1, :])
            loss, s1_loss, s2_loss = model.head.compute_loss(
                logits[0], logits[1], token_out[0], token_out[1]
            )

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=3.0)
            optimizer.step()
            scheduler.step()

            epoch_train_loss += loss.item()
            train_batches += 1

            lr = optimizer.param_groups[0]["lr"]
            if hasattr(progress, "set_postfix"):
                progress.set_postfix(loss=f"{loss.item():.4f}", lr=f"{lr:.2e}")

            if (batch_idx_global + 1) % config.log_interval == 0:
                logger.info(
                    f"[Epoch {epoch + 1}/{config.basemodel_epochs}, "
                    f"Step {batch_idx + 1}/{len(train_loader)}] "
                    f"LR: {lr:.6f}, Loss: {loss.item():.4f} "
                    f"(S1: {s1_loss.item():.4f}, S2: {s2_loss.item():.4f})"
                )

            batch_idx_global += 1

        # ------------------------- validation -------------------------
        model.eval()
        val_loss = 0.0
        val_batches = 0

        with torch.no_grad():
            val_progress = maybe_tqdm(
                val_loader,
                desc=f"[basemodel] val {epoch + 1}/{config.basemodel_epochs}",
                leave=False,
            )
            for batch_x, batch_x_stamp in val_progress:
                batch_x = batch_x.to(device, non_blocking=True)
                batch_x_stamp = batch_x_stamp.to(device, non_blocking=True)

                token_seq_0, token_seq_1 = tokenizer.encode(batch_x, half=True)
                token_in = [token_seq_0[:, :-1], token_seq_1[:, :-1]]
                token_out = [token_seq_0[:, 1:], token_seq_1[:, 1:]]

                logits = model(token_in[0], token_in[1], batch_x_stamp[:, :-1, :])
                loss, _, _ = model.head.compute_loss(
                    logits[0], logits[1], token_out[0], token_out[1]
                )

                val_loss += loss.item()
                val_batches += 1

        avg_train_loss = epoch_train_loss / train_batches if train_batches > 0 else 0.0
        avg_val_loss = val_loss / val_batches if val_batches > 0 else 0.0

        epoch_time = time.time() - epoch_start_time
        logger.info(
            f"\n--- Epoch {epoch + 1}/{config.basemodel_epochs} Summary ---\n"
            f"Training Loss: {avg_train_loss:.4f}\n"
            f"Validation Loss: {avg_val_loss:.4f}\n"
            f"Epoch Time: {format_time(epoch_time)}\n"
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

    parser = argparse.ArgumentParser(description="Kronos Basemodel Fine-tuning Training")
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

    os.makedirs(config.basemodel_save_path, exist_ok=True)
    logger = setup_logging(config.exp_name, config.log_dir, 0)

    set_seed(config.seed)

    logger.info("Loading pretrained model or random initialization...")
    model, tokenizer = load_models_for_training(config, logger)
    tokenizer = tokenizer.to(device)
    model = model.to(device)

    logger.info(f"Model parameters: {get_model_size(model)}")

    logger.info("=== Training Configuration ===")
    logger.info(f"Data path: {config.data_path}")
    logger.info(f"Lookback window: {config.lookback_window}")
    logger.info(f"Predict window: {config.predict_window}")
    logger.info(f"Batch size: {config.batch_size}")
    logger.info(f"Learning rate: {config.predictor_learning_rate}")
    logger.info(f"Training epochs: {config.basemodel_epochs}")
    logger.info(f"Device: {device}")
    logger.info(f"Tokenizer path: {config.finetuned_tokenizer_path}")
    logger.info(f"Pretrained model path: {config.pretrained_predictor_path}")

    logger.info("Starting fine-tuning training...")
    best_val_loss = train_model(model, tokenizer, device, config, config.basemodel_save_path, logger)

    logger.info(
        f"Training completed! Best validation loss: {best_val_loss:.4f}\n"
        f"Model saved to: {config.basemodel_best_model_path}"
    )


if __name__ == "__main__":
    main()
