#!/usr/bin/env python3
"""BigCertificados — Digital certificate manager for Brazilian lawyers."""

import logging
import sys

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
