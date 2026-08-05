"""Sequential Kronos finetuning orchestrator: tokenizer stage, then predictor.

Ported from the upstream Kronos project (``finetune_csv/train_sequential.py``),
https://github.com/shiyu-coder/Kronos (MIT License). Credit to the original
Kronos authors; adapted for the ZERO trading terminal.

Runs both finetuning stages from a single YAML config:

1. **Tokenizer stage** — finetunes ``KronosTokenizer`` on your CSV
   (``finetune_tokenizer.train_tokenizer``).
2. **Base-model stage** — loads the stage-1 tokenizer and finetunes the
   ``Kronos`` predictor (``finetune_model.train_model``).

Best checkpoints land under ``<base_save_path>/{tokenizer,basemodel}/best_model``
(by default ``D:\\ZERO_FRESH\\db\\kronos_finetune\\models\\<exp_name>\\...``).

Adaptations relative to upstream: single-device only (all torchrun/DDP/rank
handling removed), Comet ML removed, models come from the vendored
``engine.kronos`` package, and a missing torch install exits gracefully
with instructions instead of a traceback. Upstream's qlib pipeline
(``finetune/train_tokenizer.py`` / ``train_predictor.py``) is reference-only
and not orchestrated here.

Usage (from ``D:\\ZERO_FRESH``)::

    python -m engine.kronos_finetune.run_sequential --config engine/kronos_finetune/configs/example_nifty_daily.yaml

Optional flags: ``--skip-tokenizer``, ``--skip-basemodel``, ``--skip-existing``,
``--device {auto,cpu,cuda}``.
"""

import argparse
import os
import sys
import time

from .config_loader import CustomFinetuneConfig
from . import finetune_model
from . import finetune_tokenizer
from .finetune_tokenizer import require_torch, resolve_device, set_seed


def _banner(text: str) -> str:
    line = "=" * 60
    return f"\n{line}\n{text}\n{line}"


class SequentialTrainer:
    """Drives the two finetuning stages from one config (single device).

    Args:
        config: Path to a YAML config, an already-built
            :class:`CustomFinetuneConfig`, or None for the packaged example.
    """

    def __init__(self, config=None):
        if isinstance(config, CustomFinetuneConfig):
            self.config = config
        else:
            self.config = CustomFinetuneConfig(config)
        self.device = resolve_device(self.config)
        self.config.print_config_summary()
        print(f"Using device: {self.device}")

    def _check_existing_models(self):
        tokenizer_exists = os.path.exists(self.config.tokenizer_best_model_path)
        basemodel_exists = os.path.exists(self.config.basemodel_best_model_path)

        print(f"Tokenizer model exists: {tokenizer_exists}")
        print(f"Basemodel model exists: {basemodel_exists}")

        return tokenizer_exists, basemodel_exists

    def _create_directories(self):
        os.makedirs(self.config.tokenizer_save_path, exist_ok=True)
        os.makedirs(self.config.basemodel_save_path, exist_ok=True)
        os.makedirs(self.config.log_dir, exist_ok=True)
        print(f"Created directory: {self.config.tokenizer_save_path}")
        print(f"Created directory: {self.config.basemodel_save_path}")
        print(f"Created directory: {self.config.log_dir}")

    # ------------------------------------------------------------------
    # Stage 1: tokenizer
    # ------------------------------------------------------------------
    def train_tokenizer_phase(self) -> bool:
        print(_banner("STAGE 1/2: Tokenizer fine-tuning"))

        tokenizer_exists, _ = self._check_existing_models()
        if tokenizer_exists and self.config.skip_existing:
            print("Tokenizer model already exists, skipping training")
            return True

        logger = finetune_tokenizer.setup_logging(self.config.exp_name, self.config.log_dir, 0)

        set_seed(self.config.seed)

        tokenizer = finetune_tokenizer.load_tokenizer_for_training(self.config, logger)
        tokenizer = tokenizer.to(self.device)

        model_size = sum(p.numel() for p in tokenizer.parameters())
        logger.info(f"Tokenizer parameters: {model_size:,}")

        logger.info("=== Training Configuration ===")
        logger.info(f"Data path: {self.config.data_path}")
        logger.info(f"Lookback window: {self.config.lookback_window}")
        logger.info(f"Predict window: {self.config.predict_window}")
        logger.info(f"Batch size: {self.config.batch_size}")
        logger.info(f"Learning rate: {self.config.tokenizer_learning_rate}")
        logger.info(f"Training epochs: {self.config.tokenizer_epochs}")
        logger.info(f"Device: {self.device}")

        logger.info("Starting tokenizer fine-tuning training...")
        start_time = time.time()
        best_val_loss = finetune_tokenizer.train_tokenizer(
            tokenizer,
            self.device,
            self.config,
            self.config.tokenizer_save_path,
            logger,
        )
        training_time = time.time() - start_time

        logger.info(
            f"Tokenizer training completed! Best validation loss: {best_val_loss:.4f}\n"
            f"Training time: {training_time / 60:.2f} minutes\n"
            f"Model saved to: {self.config.tokenizer_best_model_path}"
        )

        return True

    # ------------------------------------------------------------------
    # Stage 2: base model (predictor)
    # ------------------------------------------------------------------
    def train_basemodel_phase(self) -> bool:
        print(_banner("STAGE 2/2: Basemodel (predictor) fine-tuning"))

        if getattr(self.config, "pre_trained_tokenizer", True):
            if not os.path.exists(self.config.finetuned_tokenizer_path):
                raise FileNotFoundError(
                    f"Fine-tuned tokenizer does not exist: {self.config.finetuned_tokenizer_path}. "
                    "Run the tokenizer stage first or set experiment.train_tokenizer: true."
                )

        _, basemodel_exists = self._check_existing_models()
        if basemodel_exists and self.config.skip_existing:
            print("Basemodel model already exists, skipping training")
            return True

        logger = finetune_model.setup_logging(self.config.exp_name, self.config.log_dir, 0)

        set_seed(self.config.seed)

        model, tokenizer = finetune_model.load_models_for_training(self.config, logger)
        tokenizer = tokenizer.to(self.device)
        model = model.to(self.device)

        model_size = sum(p.numel() for p in model.parameters())
        logger.info(f"Model parameters: {model_size:,}")

        logger.info("=== Training Configuration ===")
        logger.info(f"Data path: {self.config.data_path}")
        logger.info(f"Lookback window: {self.config.lookback_window}")
        logger.info(f"Predict window: {self.config.predict_window}")
        logger.info(f"Batch size: {self.config.batch_size}")
        logger.info(f"Learning rate: {self.config.predictor_learning_rate}")
        logger.info(f"Training epochs: {self.config.basemodel_epochs}")
        logger.info(f"Device: {self.device}")
        logger.info(f"Tokenizer path: {self.config.finetuned_tokenizer_path}")
        logger.info(f"Pretrained model path: {self.config.pretrained_predictor_path}")

        logger.info("Starting fine-tuning training...")
        start_time = time.time()
        best_val_loss = finetune_model.train_model(
            model,
            tokenizer,
            self.device,
            self.config,
            self.config.basemodel_save_path,
            logger,
        )
        training_time = time.time() - start_time

        logger.info(
            f"Basemodel training completed! Best validation loss: {best_val_loss:.4f}\n"
            f"Training time: {training_time / 60:.2f} minutes\n"
            f"Model saved to: {self.config.basemodel_best_model_path}"
        )

        return True

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------
    def run_training(self) -> bool:
        print("Starting Kronos model sequential fine-tuning training")
        print(f"Experiment name: {self.config.experiment_name}")
        print(f"Experiment description: {self.config.experiment_description}")

        self._create_directories()
        self._check_existing_models()

        total_start_time = time.time()

        try:
            if self.config.train_tokenizer:
                success = self.train_tokenizer_phase()
                if not success:
                    print("Tokenizer training failed, terminating training")
                    return False
            else:
                print("Skipping Tokenizer training phase")

            if self.config.train_basemodel:
                success = self.train_basemodel_phase()
                if not success:
                    print("Basemodel training failed, terminating training")
                    return False
            else:
                print("Skipping Basemodel training phase")

            total_time = time.time() - total_start_time

            print(_banner("Training completed!"))
            print(f"Total training time: {total_time / 60:.2f} minutes")
            print(f"Tokenizer checkpoint: {self.config.tokenizer_best_model_path}")
            print(f"Basemodel checkpoint: {self.config.basemodel_best_model_path}")
            print(f"Training logs:        {self.config.log_dir}")
            print("=" * 60)
            print(
                "Use these checkpoints with engine.kronos (KronosPredictor) by "
                "loading the tokenizer and model from the paths above."
            )

            return True

        except Exception as e:
            print(f"Error occurred during training: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(description="Kronos Model Sequential Fine-tuning Training")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Configuration file path (default: packaged configs/example_nifty_daily.yaml)",
    )
    parser.add_argument("--skip-tokenizer", action="store_true",
                        help="Skip tokenizer training phase")
    parser.add_argument("--skip-basemodel", action="store_true",
                        help="Skip basemodel training phase")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip training for existing models")
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=("auto", "cpu", "cuda"),
        help="Override device.use_cuda from the config (default: auto = follow config)",
    )

    args = parser.parse_args()

    # Graceful, actionable exit when torch is not installed.
    if require_torch() is None:
        print("Aborting: install PyTorch and re-run this command.")
        sys.exit(2)

    try:
        trainer_config = CustomFinetuneConfig(args.config)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Could not load config: {exc}")
        sys.exit(1)

    if args.device == "cpu":
        trainer_config.use_cuda = False
    elif args.device == "cuda":
        trainer_config.use_cuda = True

    if args.skip_tokenizer:
        trainer_config.train_tokenizer = False
    if args.skip_basemodel:
        trainer_config.train_basemodel = False
    if args.skip_existing:
        trainer_config.skip_existing = True

    try:
        trainer_config.validate()
    except ValueError as exc:
        print(exc)
        sys.exit(1)

    trainer = SequentialTrainer(trainer_config)
    success = trainer.run_training()

    if success:
        print("Training completed successfully!")
        sys.exit(0)
    else:
        print("Training failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
