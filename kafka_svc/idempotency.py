import sqlite3
import time
from pathlib import Path


class ProcessedStore:
    """Correlation ids whose side effect already happened; lives on disk so it survives a Writer restart."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self._con.execute("CREATE TABLE IF NOT EXISTS processed (correlation_id TEXT PRIMARY KEY, writer TEXT, processed_at TEXT)")

    def seen(self, correlation_id: str) -> bool:
        return self._con.execute("SELECT 1 FROM processed WHERE correlation_id = ?", (correlation_id,)).fetchone() is not None

    def mark(self, correlation_id: str, writer: str) -> bool:
        """True when this call recorded the id, False when another delivery already had."""
        cur = self._con.execute("INSERT OR IGNORE INTO processed VALUES (?, ?, ?)",
                                (correlation_id, writer, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        return cur.rowcount == 1

    def close(self) -> None:
        self._con.close()
