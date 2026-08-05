"""YAML configuration loading for the Kronos CSV finetuning pipeline.

Ported from the upstream Kronos project (``finetune_csv/config_loader.py``),
https://github.com/shiyu-coder/Kronos (MIT License). Credit to the original
Kronos authors; adapted for the ZERO trading terminal.

Adaptations relative to upstream:

* Default output locations live under ``<ZERO root>/db/kronos_finetune/``
  (``models/`` for checkpoints, ``logs/`` for training logs) instead of
  paths inside the Kronos repository.
* Pretrained model identifiers default to the public Hugging Face hub ids
  ``NeoQuasar/Kronos-Tokenizer-base`` (tokenizer) and
  ``NeoQuasar/Kronos-small`` (predictor), so a config only *must* specify
  the CSV ``data.data_path``.
* Missing/empty path fields fall back to sensible defaults instead of
  crashing (upstream required ``exp_name``/``base_path`` to be present).
* ``experiment.use_comet`` is accepted but ignored: experiment-tracker
  integration was removed for ZERO (a documented no-op).
* Adds :meth:`CustomFinetuneConfig.validate` with actionable error messages.

Note: upstream Kronos also ships a qlib-based finetuning pipeline
(``finetune/config.py``); only the practical CSV pipeline is ported here.

This module imports only the standard library at import time; PyYAML is
imported lazily inside the functions that need it.
"""

import os
from typing import Any, Dict

# --------------------------------------------------------------------------
# Default locations (derived from the package location so the project stays
# relocatable: <ZERO root>/engine/kronos_finetune -> <ZERO root>).
# --------------------------------------------------------------------------
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ZERO_ROOT = os.path.abspath(os.path.join(_PACKAGE_DIR, os.pardir, os.pardir))

#: Root for everything this pipeline writes: checkpoints, logs, data.
DEFAULT_OUTPUT_ROOT = os.path.join(ZERO_ROOT, "db", "kronos_finetune")
DEFAULT_MODELS_DIR = os.path.join(DEFAULT_OUTPUT_ROOT, "models")
DEFAULT_LOGS_DIR = os.path.join(DEFAULT_OUTPUT_ROOT, "logs")
DEFAULT_DATA_DIR = os.path.join(DEFAULT_OUTPUT_ROOT, "data")

#: Hugging Face hub ids used when the config does not override them.
DEFAULT_PRETRAINED_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
DEFAULT_PRETRAINED_PREDICTOR = "NeoQuasar/Kronos-small"

#: Example config shipped with the package (used when no path is given).
DEFAULT_CONFIG_PATH = os.path.join(_PACKAGE_DIR, "configs", "example_nifty_daily.yaml")


def _load_yaml_module():
    """Import PyYAML lazily so this module imports without third-party deps."""
    try:
        import yaml  # noqa: PLC0415 (deliberate lazy import)
        return yaml
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PyYAML is required to load Kronos finetuning configs. "
            "Install it with: pip install pyyaml"
        ) from exc


class ConfigLoader:
    """Low-level YAML loader with dotted-key access and dynamic path templates.

    Faithful port of upstream ``ConfigLoader``: resolves ``{exp_name}``
    placeholders in ``model_paths.base_save_path`` and
    ``model_paths.finetuned_tokenizer`` and offers section getters.
    """

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        yaml = _load_yaml_module()
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"config file not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        config = self._resolve_dynamic_paths(config)
        return config

    def _resolve_dynamic_paths(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Fill empty path fields from ``exp_name``/``base_path`` templates."""
        model_paths = config.get("model_paths", {}) or {}
        exp_name = model_paths.get("exp_name", "")
        if not exp_name:
            return config

        base_path = model_paths.get("base_path", "") or DEFAULT_MODELS_DIR
        path_templates = {
            "base_save_path": os.path.join(base_path, exp_name),
            "finetuned_tokenizer": os.path.join(base_path, exp_name, "tokenizer", "best_model"),
        }

        for key, template in path_templates.items():
            current_value = model_paths.get(key)
            if current_value == "" or current_value is None:
                # Empty value: use the generated template path.
                model_paths[key] = template
            elif isinstance(current_value, str) and "{exp_name}" in current_value:
                # Template string: substitute the experiment name.
                model_paths[key] = current_value.format(exp_name=exp_name)

        config["model_paths"] = model_paths
        return config

    def get(self, key: str, default=None):
        """Fetch a value with a dotted key, e.g. ``get('data.data_path')``."""
        keys = key.split(".")
        value = self.config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def get_data_config(self) -> Dict[str, Any]:
        return self.config.get("data", {}) or {}

    def get_training_config(self) -> Dict[str, Any]:
        return self.config.get("training", {}) or {}

    def get_model_paths(self) -> Dict[str, str]:
        return self.config.get("model_paths", {}) or {}

    def get_experiment_config(self) -> Dict[str, Any]:
        return self.config.get("experiment", {}) or {}

    def get_device_config(self) -> Dict[str, Any]:
        return self.config.get("device", {}) or {}

    def get_distributed_config(self) -> Dict[str, Any]:
        # Kept for config compatibility; the ZERO port always trains on a
        # single device, so this section is ignored.
        return self.config.get("distributed", {}) or {}

    def update_config(self, updates: Dict[str, Any]):
        """Deep-merge ``updates`` into the loaded config dict."""

        def update_nested_dict(d, u):
            for k, v in u.items():
                if isinstance(v, dict):
                    d[k] = update_nested_dict(d.get(k, {}), v)
                else:
                    d[k] = v
            return d

        self.config = update_nested_dict(self.config, updates)

    def save_config(self, save_path: str = None):
        yaml = _load_yaml_module()
        if save_path is None:
            save_path = self.config_path
        with open(save_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True, indent=2)

    def print_config(self):
        yaml = _load_yaml_module()
        print("=" * 50)
        print("Current configuration:")
        print("=" * 50)
        # Upstream called yaml.dump() without printing the result; fixed here.
        print(yaml.dump(self.config, default_flow_style=False, allow_unicode=True, indent=2))
        print("=" * 50)


class CustomFinetuneConfig:
    """Typed view over the finetuning YAML with defaults and validation.

    Faithful port of upstream ``CustomFinetuneConfig``. Every field the
    training scripts consume is exposed as an attribute; unspecified fields
    fall back to the same defaults as upstream except for paths and
    pretrained-model ids (see module docstring).

    Args:
        config_path: Path to a YAML config. Defaults to the packaged
            ``configs/example_nifty_daily.yaml``.
    """

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH

        self.loader = ConfigLoader(config_path)
        self._load_all_configs()

    def _load_all_configs(self):
        # ------------------------------ data ------------------------------
        data_config = self.loader.get_data_config()
        self.data_path = data_config.get("data_path")
        self.lookback_window = data_config.get("lookback_window", 512)
        self.predict_window = data_config.get("predict_window", 48)
        self.max_context = data_config.get("max_context", 512)
        self.clip = data_config.get("clip", 5.0)
        self.train_ratio = data_config.get("train_ratio", 0.9)
        self.val_ratio = data_config.get("val_ratio", 0.1)
        self.test_ratio = data_config.get("test_ratio", 0.0)

        # ---------------------------- training ----------------------------
        training_config = self.loader.get_training_config()
        # Tokenizer and base-model epochs are configurable separately; a
        # plain `epochs` key applies to whichever is not explicitly set.
        self.tokenizer_epochs = training_config.get("tokenizer_epochs", 30)
        self.basemodel_epochs = training_config.get("basemodel_epochs", 30)
        if "epochs" in training_config and "tokenizer_epochs" not in training_config:
            self.tokenizer_epochs = training_config.get("epochs", 30)
        if "epochs" in training_config and "basemodel_epochs" not in training_config:
            self.basemodel_epochs = training_config.get("epochs", 30)

        self.batch_size = training_config.get("batch_size", 160)
        self.log_interval = training_config.get("log_interval", 50)
        self.num_workers = training_config.get("num_workers", 0)
        self.seed = training_config.get("seed", 100)
        self.tokenizer_learning_rate = training_config.get("tokenizer_learning_rate", 2e-4)
        self.predictor_learning_rate = training_config.get("predictor_learning_rate", 4e-5)
        self.adam_beta1 = training_config.get("adam_beta1", 0.9)
        self.adam_beta2 = training_config.get("adam_beta2", 0.95)
        self.adam_weight_decay = training_config.get("adam_weight_decay", 0.1)
        self.accumulation_steps = training_config.get("accumulation_steps", 1)

        # --------------------------- model paths ---------------------------
        model_paths = self.loader.get_model_paths()
        self.exp_name = model_paths.get("exp_name") or "kronos_finetune_default"
        self.pretrained_tokenizer_path = (
            model_paths.get("pretrained_tokenizer") or DEFAULT_PRETRAINED_TOKENIZER
        )
        self.pretrained_predictor_path = (
            model_paths.get("pretrained_predictor") or DEFAULT_PRETRAINED_PREDICTOR
        )
        self.base_path = model_paths.get("base_path") or DEFAULT_MODELS_DIR
        self.base_save_path = model_paths.get("base_save_path") or os.path.join(
            self.base_path, self.exp_name
        )
        self.tokenizer_save_name = model_paths.get("tokenizer_save_name", "tokenizer")
        self.basemodel_save_name = model_paths.get("basemodel_save_name", "basemodel")
        self.finetuned_tokenizer_path = model_paths.get("finetuned_tokenizer") or os.path.join(
            self.base_save_path, self.tokenizer_save_name, "best_model"
        )
        # Training logs directory (ZERO adaptation: defaults under
        # db/kronos_finetune/logs/<exp_name>; upstream used
        # <base_save_path>/logs).
        self.log_dir = model_paths.get("log_dir") or os.path.join(DEFAULT_LOGS_DIR, self.exp_name)

        # --------------------------- experiment ----------------------------
        experiment_config = self.loader.get_experiment_config()
        self.experiment_name = experiment_config.get("name", "kronos_custom_finetune")
        self.experiment_description = experiment_config.get("description", "")
        # Accepted for upstream config compatibility but ignored: the ZERO
        # port has no experiment-tracker (Comet ML) integration.
        self.use_comet = experiment_config.get("use_comet", False)
        self.train_tokenizer = experiment_config.get("train_tokenizer", True)
        self.train_basemodel = experiment_config.get("train_basemodel", True)
        self.skip_existing = experiment_config.get("skip_existing", False)

        # `pre_trained` is a unified switch; the per-component keys override.
        unified_pretrained = experiment_config.get("pre_trained", None)
        self.pre_trained_tokenizer = experiment_config.get(
            "pre_trained_tokenizer",
            unified_pretrained if unified_pretrained is not None else True,
        )
        self.pre_trained_predictor = experiment_config.get(
            "pre_trained_predictor",
            unified_pretrained if unified_pretrained is not None else True,
        )

        # ----------------------------- device ------------------------------
        device_config = self.loader.get_device_config()
        self.use_cuda = device_config.get("use_cuda", True)
        self.device_id = device_config.get("device_id", 0)

        # DDP/torchrun support was removed in the ZERO port (single device
        # only); the section is still parsed so upstream configs load.
        distributed_config = self.loader.get_distributed_config()
        self.use_ddp = False
        self.ddp_backend = distributed_config.get("backend", "nccl")

        self._compute_full_paths()

    def _compute_full_paths(self):
        self.tokenizer_save_path = os.path.join(self.base_save_path, self.tokenizer_save_name)
        self.tokenizer_best_model_path = os.path.join(self.tokenizer_save_path, "best_model")

        self.basemodel_save_path = os.path.join(self.base_save_path, self.basemodel_save_name)
        self.basemodel_best_model_path = os.path.join(self.basemodel_save_path, "best_model")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self, require_data_file: bool = True):
        """Sanity-check the configuration before training.

        Args:
            require_data_file: When True (default) the CSV file must exist.

        Raises:
            ValueError: listing every problem found, with hints on fixes.
        """
        problems = []

        if not self.data_path:
            problems.append(
                "data.data_path is not set. Point it at a CSV with columns "
                "['timestamps','open','high','low','close','volume','amount'], "
                f"e.g. a file under {DEFAULT_DATA_DIR}"
            )
        elif require_data_file and not os.path.exists(self.data_path):
            problems.append(
                f"data.data_path does not exist: {self.data_path}. "
                f"Place your CSV there (or under {DEFAULT_DATA_DIR}) and retry."
            )

        if self.lookback_window <= 0:
            problems.append("data.lookback_window must be a positive integer")
        if self.predict_window <= 0:
            problems.append("data.predict_window must be a positive integer")
        if self.max_context < self.lookback_window:
            problems.append(
                f"data.max_context ({self.max_context}) should be >= "
                f"data.lookback_window ({self.lookback_window})"
            )
        if self.clip <= 0:
            problems.append("data.clip must be positive (upstream default: 5.0)")

        for name, ratio in (
            ("train_ratio", self.train_ratio),
            ("val_ratio", self.val_ratio),
            ("test_ratio", self.test_ratio),
        ):
            if not (0.0 <= float(ratio) <= 1.0):
                problems.append(f"data.{name} must be in [0, 1], got {ratio}")
        if self.train_ratio + self.val_ratio + self.test_ratio > 1.0 + 1e-9:
            problems.append(
                "data.train_ratio + val_ratio + test_ratio must not exceed 1.0"
            )
        if self.val_ratio <= 0:
            problems.append(
                "data.val_ratio must be > 0: best checkpoints are selected by "
                "validation loss"
            )

        if self.batch_size < 1:
            problems.append("training.batch_size must be >= 1")
        if self.accumulation_steps < 1:
            problems.append("training.accumulation_steps must be >= 1")
        if self.train_tokenizer and self.tokenizer_epochs < 1:
            problems.append("training.tokenizer_epochs must be >= 1 when training the tokenizer")
        if self.train_basemodel and self.basemodel_epochs < 1:
            problems.append("training.basemodel_epochs must be >= 1 when training the base model")
        if self.tokenizer_learning_rate <= 0 or self.predictor_learning_rate <= 0:
            problems.append("learning rates must be positive")

        if problems:
            raise ValueError(
                "Invalid kronos_finetune configuration:\n  - " + "\n  - ".join(problems)
            )

        if self.batch_size % self.accumulation_steps != 0:
            # Upstream silently drops the remainder samples of each batch;
            # keep the behaviour but tell the user about it.
            print(
                f"Warning: batch_size ({self.batch_size}) is not divisible by "
                f"accumulation_steps ({self.accumulation_steps}); the remainder "
                "of each batch is dropped (upstream behaviour)."
            )

    # ------------------------------------------------------------------
    # Convenience dict views (upstream API, kept for compatibility)
    # ------------------------------------------------------------------
    def get_tokenizer_config(self):
        return {
            "data_path": self.data_path,
            "lookback_window": self.lookback_window,
            "predict_window": self.predict_window,
            "max_context": self.max_context,
            "clip": self.clip,
            "train_ratio": self.train_ratio,
            "val_ratio": self.val_ratio,
            "test_ratio": self.test_ratio,
            "epochs": self.tokenizer_epochs,
            "batch_size": self.batch_size,
            "log_interval": self.log_interval,
            "num_workers": self.num_workers,
            "seed": self.seed,
            "learning_rate": self.tokenizer_learning_rate,
            "adam_beta1": self.adam_beta1,
            "adam_beta2": self.adam_beta2,
            "adam_weight_decay": self.adam_weight_decay,
            "accumulation_steps": self.accumulation_steps,
            "pretrained_model_path": self.pretrained_tokenizer_path,
            "save_path": self.tokenizer_save_path,
        }

    def get_basemodel_config(self):
        return {
            "data_path": self.data_path,
            "lookback_window": self.lookback_window,
            "predict_window": self.predict_window,
            "max_context": self.max_context,
            "clip": self.clip,
            "train_ratio": self.train_ratio,
            "val_ratio": self.val_ratio,
            "test_ratio": self.test_ratio,
            "epochs": self.basemodel_epochs,
            "batch_size": self.batch_size,
            "log_interval": self.log_interval,
            "num_workers": self.num_workers,
            "seed": self.seed,
            "predictor_learning_rate": self.predictor_learning_rate,
            "tokenizer_learning_rate": self.tokenizer_learning_rate,
            "adam_beta1": self.adam_beta1,
            "adam_beta2": self.adam_beta2,
            "adam_weight_decay": self.adam_weight_decay,
            "pretrained_tokenizer_path": self.finetuned_tokenizer_path,
            "pretrained_predictor_path": self.pretrained_predictor_path,
            "save_path": self.basemodel_save_path,
        }

    def print_config_summary(self):
        print("=" * 60)
        print("Kronos finetuning configuration summary")
        print("=" * 60)
        print(f"Experiment name: {self.exp_name}")
        print(f"Data path: {self.data_path}")
        print(f"Lookback window: {self.lookback_window}")
        print(f"Predict window: {self.predict_window}")
        print(f"Tokenizer training epochs: {self.tokenizer_epochs}")
        print(f"Basemodel training epochs: {self.basemodel_epochs}")
        print(f"Batch size: {self.batch_size}")
        print(f"Tokenizer learning rate: {self.tokenizer_learning_rate}")
        print(f"Predictor learning rate: {self.predictor_learning_rate}")
        print(f"Train tokenizer: {self.train_tokenizer}")
        print(f"Train basemodel: {self.train_basemodel}")
        print(f"Skip existing: {self.skip_existing}")
        print(f"Use pre-trained tokenizer: {self.pre_trained_tokenizer}")
        print(f"Use pre-trained predictor: {self.pre_trained_predictor}")
        print(f"Pretrained tokenizer id/path: {self.pretrained_tokenizer_path}")
        print(f"Pretrained predictor id/path: {self.pretrained_predictor_path}")
        print(f"Base save path: {self.base_save_path}")
        print(f"Tokenizer save path: {self.tokenizer_save_path}")
        print(f"Basemodel save path: {self.basemodel_save_path}")
        print(f"Log directory: {self.log_dir}")
        print("=" * 60)


#: Friendly alias used by ZERO code.
FinetuneConfig = CustomFinetuneConfig
