#!/usr/bin/env python3
"""Named CPython copy so macOS TCC shows ``soliqo-mcp``, not ``python3.11``.

Copy, never hardlink: a shared inode makes every Python on this interpreter
report an arbitrary name via ``proc_pidpath``.
"""

from __future__ import annotations

import shutil
import stat
import sys
from pathlib import Path

NAME = "soliqo-mcp"


def main() -> int:
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        print("must run inside the soliqo-mcp venv", file=sys.stderr)
        return 2
    real = Path(sys.executable).resolve()
    sibling = real.with_name(NAME)
    if not (
        sibling.exists()
        and not sibling.is_symlink()
        and sibling.stat().st_ino != real.stat().st_ino
        and sibling.stat().st_size == real.stat().st_size
    ):
        tmp = sibling.with_name(NAME + ".tmp")
        tmp.unlink(missing_ok=True)
        shutil.copy2(real, tmp)
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        tmp.replace(sibling)
    shim = Path(sys.prefix) / "bin" / NAME
    if shim.exists() or shim.is_symlink():
        try:
            if shim.resolve() == sibling.resolve():
                print(shim)
                return 0
        except OSError:
            pass
        shim.unlink()
    shim.symlink_to(sibling.resolve())
    print(shim)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
