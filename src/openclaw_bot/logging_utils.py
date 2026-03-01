from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path



def setup_logging(log_path: str) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        file_handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)
