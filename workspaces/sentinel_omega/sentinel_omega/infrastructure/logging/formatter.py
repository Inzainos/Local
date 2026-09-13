import json, logging, sys
from datetime import datetime, timezone
from pathlib import Path
from logging.handlers import RotatingFileHandler
class JSONFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        for k, v in record.__dict__.items():
            if k not in {"name","msg","args","created","filename","funcName","levelname","levelno","lineno","module","msecs","message","pathname","process","processName","relativeCreated","thread","threadName","exc_info","exc_text","stack_info"}:
                try:
                    json.dumps({k: v})
                    entry[k] = v
                except Exception:
                    entry[k] = str(v)
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)
def setup_logging(level="INFO", log_file="logs/sentinel_omega.log", fmt="json", max_bytes=10485760, backup_count=5):
    p = Path(log_file)
    if not p.is_absolute():
        p = Path(__file__).parent.parent.parent / p
    p.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    ch = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        ch.setFormatter(JSONFormatter())
    else:
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(ch)
    fh = RotatingFileHandler(str(p), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    if fmt == "json":
        fh.setFormatter(JSONFormatter())
    else:
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(fh)
    for noisy in ("urllib3","requests","httpx","PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return root
def get_logger(name):
    return logging.getLogger(name)
