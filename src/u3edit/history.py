"""Version history of a save directory, one bzip2 tarball per version.

Versions live in ``<savedir>/.u3edit-history/NNNN-YYYYmmdd-HHMMSS.tar.bz2``.
Each tarball holds the save files plus ``meta.json`` (label, change list).
"""

from __future__ import annotations

import io
import json
import re
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

HISTORY_DIR = ".u3edit-history"
META = "meta.json"
NAME_RE = re.compile(r"^(\d{4,})-(\d{8}-\d{6})\.tar\.bz2$")


@dataclass
class Version:
    number: int
    path: Path
    time: datetime
    label: str
    changes: list[str] = field(default_factory=list)


class History:
    def __init__(self, savedir: str | Path):
        self.dir = Path(savedir) / HISTORY_DIR

    def versions(self) -> list[Version]:
        """All versions, newest first."""
        if not self.dir.is_dir():
            return []
        out = []
        for path in self.dir.iterdir():
            m = NAME_RE.match(path.name)
            if not m:
                continue
            try:
                with tarfile.open(path, "r:bz2") as tar:
                    meta = json.load(tar.extractfile(META))
            except (OSError, tarfile.TarError, KeyError, ValueError):
                meta = {"label": "(unreadable)", "changes": []}
            out.append(Version(
                number=int(m.group(1)),
                path=path,
                time=datetime.strptime(m.group(2), "%Y%m%d-%H%M%S"),
                label=meta.get("label", ""),
                changes=meta.get("changes", []),
            ))
        return sorted(out, key=lambda v: v.number, reverse=True)

    def files(self, version: Version) -> dict[str, bytes]:
        with tarfile.open(version.path, "r:bz2") as tar:
            return {
                m.name: tar.extractfile(m).read()
                for m in tar.getmembers()
                if m.isfile() and m.name != META
            }

    def latest(self) -> Version | None:
        versions = self.versions()
        return versions[0] if versions else None

    def record(self, files: dict[str, bytes], label: str, changes: list[str] | None = None) -> Version:
        self.dir.mkdir(exist_ok=True)
        latest = self.latest()
        number = latest.number + 1 if latest else 1
        now = datetime.now().replace(microsecond=0)
        path = self.dir / f"{number:04d}-{now:%Y%m%d-%H%M%S}.tar.bz2"
        meta = json.dumps({"label": label, "changes": changes or []}, ensure_ascii=False).encode()
        tmp = path.with_suffix(".tmp")
        with tarfile.open(tmp, "w:bz2") as tar:
            for name, data in sorted(files.items()) + [(META, meta)]:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mtime = int(now.timestamp())
                tar.addfile(info, io.BytesIO(data))
        tmp.rename(path)
        return Version(number, path, now, label, changes or [])
