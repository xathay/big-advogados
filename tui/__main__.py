"""Entry-point: `python -m tui`.

Garante que a raiz do projeto esteja em sys.path para que tanto
`import tui...` quanto `import src...` funcionem, independente de onde
o comando for invocado.
"""

import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tui.app import BigAdvogadosTUI  # noqa: E402


def main() -> int:
    return BigAdvogadosTUI().run() or 0


if __name__ == "__main__":
    sys.exit(main())
