"""CSV K-line dataset and dataloader construction for Kronos finetuning.

Ported from the upstream Kronos project (``finetune_csv/finetune_base_model.py``,
class ``CustomKlineDataset``), https://github.com/shiyu-coder/Kronos
(MIT License). Credit to the original Kronos authors; adapted for the ZERO
trading terminal.

The CSV must contain the columns::

    ['timestamps', 'open', 'high', 'low', 'close', 'volume', 'amount']

(``volume``/``amount`` may be zero if unavailable). Rows are sorted by
timestamp, split chronologically into train/val/test by ratio, and served
as sliding windows of ``lookback_window + predict_window + 1`` rows.
Each window is z-score normalised over the *whole* window and clipped to
``[-clip, +clip]`` — exactly as the upstream CSV pipeline does. (Upstream's
alternative qlib pipeline, ``finetune/dataset.py``, instead normalises
using lookback-window statistics only and samples from pickled per-symbol
frames; that pipeline is reference-only and not ported.)

Adaptations relative to upstream:

* ``CustomKlineDataset`` is a plain map-style dataset (implements
  ``__len__``/``__getitem__``) rather than subclassing
  ``torch.utils.data.Dataset``, so the module imports without torch.
  ``torch.utils.data.DataLoader`` accepts it unchanged.
* pandas/numpy/torch are imported lazily inside methods.
* ``fillna(method='ffill')`` (removed in pandas >= 2.x deprecation path)
  was replaced by the equivalent ``DataFrame.ffill()``.
* Missing columns and too-short datasets raise immediately with actionable
  messages instead of failing deep inside the training loop.
* ``create_dataloaders`` lives here (upstream duplicated it in both
  training scripts) and is single-process only — the DDP samplers were
  removed in the ZERO port.
"""

import os
import random

#: Column names expected in the input CSV.
REQUIRED_COLUMNS = ["timestamps", "open", "high", "low", "close", "volume", "amount"]

#: Price/volume features fed to the model (order matters).
FEATURE_LIST = ["open", "high", "low", "close", "volume", "amount"]

#: Calendar features derived from ``timestamps`` (order matters).
TIME_FEATURE_LIST = ["minute", "hour", "weekday", "day", "month"]


class CustomKlineDataset:
    """Sliding-window K-line dataset over a single CSV file.

    Map-style dataset compatible with ``torch.utils.data.DataLoader``.
    Returns ``(x, x_stamp)`` float32 tensors of shapes
    ``(window, 6)`` and ``(window, 5)`` where
    ``window = lookback_window + predict_window + 1``.

    Args:
        data_path: Path to the CSV file (see module docstring for columns).
        data_type: One of ``'train' | 'val' | 'test'``.
        lookback_window: Number of historical steps in each sample.
        predict_window: Number of future steps in each sample.
        clip: Symmetric clip applied after z-score normalisation.
        seed: Seed for the per-dataset random generator.
        train_ratio / val_ratio / test_ratio: Chronological split ratios.
    """

    def __init__(self, data_path, data_type="train", lookback_window=90, predict_window=10,
                 clip=5.0, seed=100, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15):
        if data_type not in ("train", "val", "test"):
            raise ValueError(f"data_type must be 'train', 'val' or 'test', got {data_type!r}")

        self.data_path = data_path
        self.data_type = data_type
        self.lookback_window = lookback_window
        self.predict_window = predict_window
        self.window = lookback_window + predict_window + 1
        self.clip = clip
        self.seed = seed
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio

        self.feature_list = list(FEATURE_LIST)
        self.time_feature_list = list(TIME_FEATURE_LIST)

        # Dedicated RNG so sampling never interferes with model-init RNG state.
        self.py_rng = random.Random(seed)

        self._load_and_preprocess_data()
        self._split_data_by_time()

        self.n_samples = len(self.data) - self.window + 1
        if self.n_samples <= 0:
            raise ValueError(
                f"[{data_type.upper()}] split has {len(self.data)} rows but each sample "
                f"needs {self.window} (lookback {lookback_window} + predict "
                f"{predict_window} + 1). Provide more data, shrink the windows, "
                "or adjust the split ratios."
            )

        print(f"[{data_type.upper()}] Data length: {len(self.data)}, Available samples: {self.n_samples}")

    # ------------------------------------------------------------------
    # Loading / preprocessing
    # ------------------------------------------------------------------
    def _load_and_preprocess_data(self):
        import pandas as pd  # lazy heavy import

        if not os.path.exists(self.data_path):
            raise FileNotFoundError(
                f"CSV data file not found: {self.data_path}. Set data.data_path "
                "in your config to an existing file."
            )

        df = pd.read_csv(self.data_path)

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"CSV {self.data_path} is missing required columns {missing}. "
                f"Expected columns: {REQUIRED_COLUMNS} (volume/amount may be 0)."
            )

        df["timestamps"] = pd.to_datetime(df["timestamps"])
        df = df.sort_values("timestamps").reset_index(drop=True)

        self.timestamps = df["timestamps"].copy()

        # Calendar features consumed by the Kronos predictor.
        df["minute"] = df["timestamps"].dt.minute
        df["hour"] = df["timestamps"].dt.hour
        df["weekday"] = df["timestamps"].dt.weekday
        df["day"] = df["timestamps"].dt.day
        df["month"] = df["timestamps"].dt.month

        self.data = df[self.feature_list + self.time_feature_list].copy()

        if self.data.isnull().any().any():
            print("Warning: Missing values found in data, performing forward fill")
            self.data = self.data.ffill()

        print(f"Original data time range: {self.timestamps.min()} to {self.timestamps.max()}")
        print(f"Original data total length: {len(df)} records")

    def _split_data_by_time(self):
        """Chronological split: first train_ratio, then val_ratio, rest test."""
        total_length = len(self.data)

        train_end = int(total_length * self.train_ratio)
        val_end = int(total_length * (self.train_ratio + self.val_ratio))

        if self.data_type == "train":
            self.data = self.data.iloc[:train_end].copy()
            self.timestamps = self.timestamps.iloc[:train_end].copy()
            print(f"[{self.data_type.upper()}] Training set: first {train_end} time points ({self.train_ratio})")
        elif self.data_type == "val":
            self.data = self.data.iloc[train_end:val_end].copy()
            self.timestamps = self.timestamps.iloc[train_end:val_end].copy()
            print(f"[{self.data_type.upper()}] Validation set: time points {train_end + 1} to {val_end} ({self.val_ratio})")
        elif self.data_type == "test":
            self.data = self.data.iloc[val_end:].copy()
            self.timestamps = self.timestamps.iloc[val_end:].copy()
            print(f"[{self.data_type.upper()}] Test set: after time point {val_end + 1}")

        if len(self.data) > 0:
            print(f"[{self.data_type.upper()}] Split time range: {self.timestamps.min()} to {self.timestamps.max()}")
        print(f"[{self.data_type.upper()}] Data length after split: {len(self.data)} records")

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------
    def set_epoch_seed(self, epoch):
        """Reseed the sampler for an epoch (kept for upstream reproducibility).

        The training scripts call this with ``epoch * 10000`` for train and
        ``0`` for val, matching upstream exactly; ``current_epoch`` feeds the
        deterministic window-start formula in :meth:`__getitem__`.
        """
        epoch_seed = self.seed + epoch
        self.py_rng.seed(epoch_seed)
        self.current_epoch = epoch

    def __len__(self):
        return self.n_samples

    def __getitem__(self, idx):
        import numpy as np  # lazy heavy import
        import torch  # lazy heavy import

        max_start = len(self.data) - self.window
        if max_start < 0:
            raise ValueError("Data length insufficient to create samples")

        if self.data_type == "train":
            # Deterministic pseudo-random start index (upstream formula):
            # decorrelates consecutive idx values and varies across epochs.
            epoch = getattr(self, "current_epoch", 0)
            start_idx = (idx * 9973 + (epoch + 1) * 104729) % (max_start + 1)
        else:
            start_idx = idx % (max_start + 1)

        end_idx = start_idx + self.window

        window_data = self.data.iloc[start_idx:end_idx]

        x = window_data[self.feature_list].values.astype(np.float32)
        x_stamp = window_data[self.time_feature_list].values.astype(np.float32)

        # Whole-window z-score normalisation + clipping (upstream CSV pipeline).
        x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)
        x = (x - x_mean) / (x_std + 1e-5)
        x = np.clip(x, -self.clip, self.clip)

        x_tensor = torch.from_numpy(x)
        x_stamp_tensor = torch.from_numpy(x_stamp)

        return x_tensor, x_stamp_tensor


def create_dataloaders(config):
    """Build train/val datasets and single-process DataLoaders from a config.

    Args:
        config: A :class:`~engine.kronos_finetune.config_loader.CustomFinetuneConfig`
            (or any object with the same data/training attributes).

    Returns:
        tuple: ``(train_loader, val_loader, train_dataset, val_dataset)``.

    Upstream returned DDP samplers as well; the ZERO port is single-device,
    so the sampler slots were dropped.
    """
    import torch  # lazy heavy import
    from torch.utils.data import DataLoader  # lazy heavy import

    print("Creating data loaders...")

    train_dataset = CustomKlineDataset(
        data_path=config.data_path,
        data_type="train",
        lookback_window=config.lookback_window,
        predict_window=config.predict_window,
        clip=config.clip,
        seed=config.seed,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
    )

    val_dataset = CustomKlineDataset(
        data_path=config.data_path,
        data_type="val",
        lookback_window=config.lookback_window,
        predict_window=config.predict_window,
        clip=config.clip,
        seed=config.seed + 1,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
    )

    if len(train_dataset) < config.batch_size:
        raise ValueError(
            f"Training split yields only {len(train_dataset)} samples but "
            f"training.batch_size is {config.batch_size} and the train loader "
            "drops incomplete batches. Reduce batch_size or provide more data."
        )

    pin_memory = torch.cuda.is_available()

    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
        pin_memory=pin_memory,
        drop_last=True,
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=config.batch_size,
        shuffle=False,
        num_workers=config.num_workers,
        pin_memory=pin_memory,
        drop_last=False,
    )

    print(f"Training set size: {len(train_dataset)}, Validation set size: {len(val_dataset)}")

    return train_loader, val_loader, train_dataset, val_dataset
