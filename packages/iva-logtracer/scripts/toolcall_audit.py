#!/usr/bin/env python3

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from logtracer_extractors.scripts import toolcall_audit as _impl

globals().update({name: value for name, value in _impl.__dict__.items() if not name.startswith("__")})
main = _impl.main


if __name__ == "__main__":
    raise SystemExit(main())
