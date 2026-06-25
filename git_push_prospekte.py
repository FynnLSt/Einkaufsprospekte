#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from datetime import datetime


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def ensure_git_repo() -> None:
    result = run(["git", "rev-parse", "--is-inside-work-tree"], check=False)
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise RuntimeError("Der aktuelle Ordner ist kein Git-Repository.")


def has_changes() -> bool:
    result = run(["git", "status", "--porcelain"], check=True)
    return bool(result.stdout.strip())


def main() -> int:
    try:
        ensure_git_repo()

        run(["git", "add", "-A"])

        if not has_changes():
            print("Keine Änderungen zum Committen.")
            return 0

        if len(sys.argv) > 1:
            commit_message = " ".join(sys.argv[1:])
        else:
            commit_message = "Automatisches Prospekt-Update " + datetime.now().strftime("%Y-%m-%d %H:%M")

        run(["git", "commit", "-m", commit_message])
        run(["git", "push"])

        print("Änderungen wurden committed und gepusht.")
        return 0

    except subprocess.CalledProcessError as exc:
        print("Git-Befehl fehlgeschlagen:")
        print(" ".join(exc.cmd))
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr)
        return 1

    except Exception as exc:
        print(f"Fehler: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
