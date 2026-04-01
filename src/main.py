#!/usr/bin/env python3
"""BigCertificados — Digital certificate manager for Brazilian lawyers."""

import logging
import os
import sys

# Ensure the project root is in sys.path so "from src.xxx" imports work
# regardless of how main.py is invoked (python src/main.py, python -m src.main, etc.)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from src.application import BigCertificadosApp  # noqa: E402


def main() -> int:
    app = BigCertificadosApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
