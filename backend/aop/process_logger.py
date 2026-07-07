"""Structured process logger that streams pipeline events."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict, Any


class ProcessLogger:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def _stamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%H:%M:%S")

    def log(self, level: str, stage: str, message: str, **data) -> Dict[str, Any]:
        entry = {
            "ts": self._stamp(),
            "level": level,
            "stage": stage,
            "message": message,
            "data": data,
        }
        self.events.append(entry)
        return entry

    def info(self, stage: str, msg: str, **data):
        return self.log("INFO", stage, msg, **data)

    def warn(self, stage: str, msg: str, **data):
        return self.log("WARN", stage, msg, **data)

    def error(self, stage: str, msg: str, **data):
        return self.log("ERROR", stage, msg, **data)

    def ok(self, stage: str, msg: str, **data):
        return self.log("OK", stage, msg, **data)

    def to_text(self) -> str:
        lines = []
        for e in self.events:
            lines.append(f"[{e['ts']}] {e['level']:5s} {e['stage']:24s} :: {e['message']}")
        return "\n".join(lines)
