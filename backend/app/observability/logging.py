"""Structured (JSON) logging setup with secret redaction.

Call setup_logging() once at startup. Logs become single-line JSON (timestamp,
level, logger, message) with secret patterns redacted, suitable for ingestion by
any log pipeline. Falls back silently if anything goes wrong.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.security.prompt_injection import redact_secrets


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_secrets(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", *, json_format: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    # Replace existing handlers so we don't double-log.
    root.handlers = [handler]
