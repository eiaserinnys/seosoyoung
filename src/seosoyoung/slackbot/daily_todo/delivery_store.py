"""Atomic, process-locked local delivery and numbering history."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar('T')


class DeliveryStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix('.lock')

    def read(self) -> dict[str, Any]:
        return self.update(lambda state: state, write=False)

    def update(self, operation: Callable[[dict[str, Any]], T], *, write: bool = True) -> T:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open('a+', encoding='utf-8') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists():
                with self.path.open(encoding='utf-8') as source:
                    state = json.load(source)
            else:
                state = {'format_version': 1, 'days': {}, 'deliveries': {}, 'preparation': {}, 'events': []}
            result = operation(state)
            if write:
                name = None
                try:
                    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent, delete=False) as target:
                        name = target.name
                        json.dump(state, target, ensure_ascii=False, indent=2)
                        target.flush()
                        os.fsync(target.fileno())
                    os.replace(name, self.path)
                finally:
                    if name and os.path.exists(name):
                        os.unlink(name)
            return result
