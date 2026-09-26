#!/usr/bin/env python3
"""Contrôle de cohérence documentaire (release).

1. Tout chemin de fichier cité dans README.md / docs/*.md / CHANGELOG.md
   existe dans le dépôt (hors produits de compilation).
2. La version canonique (mustacom/config.py APP_VERSION) est cohérente avec
   README.md, docs/manuel-utilisateur.md et CHANGELOG.md.
Usage : python tools/check_docs.py   (exit 0 = OK)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "CHANGELOG.md",
        ROOT / "docs" / "manuel-utilisateur.md", ROOT / "docs" / "RELEASE.md"]

# Racines connues du dépôt : seuls les chemins qui en commencent un sont
# vérifiés (évite les fausses alertes type « ICE/IF/RC », « A4/A5 »…).
KNOWN_ROOTS = ("mustacom", "tests", "build", "installer", "tools", "assets",
               ".github", "docs", "dist")
PATH_RE = re.compile(
    rf"(?:^|[\s`(\[\"'→·])((?:{'|'.join(map(re.escape, KNOWN_ROOTS))})"
    r"(?:[/\\][A-Za-z0-9_.\-]+)+)(?=$|[\s`)\]\"'.,;:])"
)
# Produits de compilation : absents d'un dépôt vierge, donc non vérifiés.
BUILD_OUTPUTS = ("dist/mustacom", "installer/Output")


def app_version() -> str:
    src = (ROOT / "mustacom" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', src)
    if not match:
        sys.exit("APP_VERSION introuvable dans mustacom/config.py")
    return match.group(1)


def check_paths() -> list[str]:
    errors: list[str] = []
    for doc in DOCS:
        for lineno, line in enumerate(
                doc.read_text(encoding="utf-8").splitlines(), 1):
            for raw in PATH_RE.findall(line):
                rel = raw.replace("\\", "/").rstrip("/")
                if rel.startswith(("http", "%", "$")) or "://" in rel:
                    continue
                if any(rel == out or rel.startswith(out + "/")
                       for out in BUILD_OUTPUTS):
                    continue
                if not (ROOT / rel).exists():
                    errors.append(f"{doc.name}:{lineno}: « {raw} » introuvable")
    return errors


def check_version(version: str) -> list[str]:
    errors: list[str] = []
    expectations = {
        ROOT / "README.md":
            rf"# MUSTACOM BUSINESS MANAGER — v{re.escape(version)}",
        ROOT / "docs" / "manuel-utilisateur.md":
            rf"MUSTACOM BUSINESS MANAGER v{re.escape(version)}",
        ROOT / "CHANGELOG.md": rf"^## {re.escape(version)} ",
    }
    for doc, pattern in expectations.items():
        if not re.search(pattern, doc.read_text(encoding="utf-8"), re.M):
            errors.append(f"{doc.name}: version {version} introuvable")
    return errors


def main() -> int:
    version = app_version()
    errors = check_paths() + check_version(version)
    if errors:
        print("CHECK DOCS: ÉCHEC")
        for err in errors:
            print(" -", err)
        return 1
    print(f"CHECK DOCS OK (version {version}, {len(DOCS)} documents vérifiés)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
