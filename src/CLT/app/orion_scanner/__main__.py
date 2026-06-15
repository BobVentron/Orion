"""
Entry point : python -m orion_scanner

Sans argument   → affiche l'aide (renvoie vers cli.py et collector_daemon.py)
"""

from __future__ import annotations

import sys


def main() -> None:
    print(
        "\n"
        "  Orion Scanner\n"
        "  ─────────────────────────────────────────────────────\n"
        "  Deux modes de lancement disponibles :\n"
        "\n"
        "  CLI (gestion des profils et des réseaux) :\n"
        "    python -m orion_scanner.cli --help\n"
        "\n"
        "  Daemon collecteur (scan permanent) :\n"
        "    python -m orion_scanner.collector_daemon\n"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
