import logging
import os
from datetime import datetime
from pathlib import Path

# Log directory is overridable via the LOG_DIR env var. This matters on AWS
# Lambda, where the project directory is read-only and only /tmp is writable
# (e.g. set LOG_DIR=/tmp/logs in the Lambda environment).
_LOG_DIR = Path(os.getenv("LOG_DIR", str(Path(__file__).resolve().parents[2] / "logs")))
_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def configure(job_id: str, level: str = "INFO") -> logging.Logger:
    """
    Set up root-level logging to both stdout and a timestamped log file.

    Each run writes to ``logs/<job_id>.log``.  Call this once from
    ``run.py`` or the Lambda handler before creating the Scrapy process.

    Parameters
    ----------
    job_id:
        Unique identifier for this run; used as the log filename.
    level:
        Logging level string, e.g. ``"INFO"``, ``"DEBUG"``.

    Returns
    -------
    logging.Logger
        The root logger with handlers attached.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = _LOG_DIR / f"{job_id}.log"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(console_handler)
    else:
        root.handlers.clear()
        root.addHandler(file_handler)
        root.addHandler(console_handler)

    root.info("Logging initialised — job_id=%s  log_file=%s", job_id, log_file)
    return root
