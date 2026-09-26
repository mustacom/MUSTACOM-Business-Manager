# Procédure de release — MUSTACOM BUSINESS MANAGER

> Rappel : les exécutables Windows (`MUSTACOM-Business-Manager.exe` et
> `MUSTACOM-Business-Manager-Setup.exe`) sont **uniquement** produits par
> `build\build_windows.ps1` (machine Windows) ou par le workflow GitHub
> Actions `.github/workflows/windows-installer.yml` (runner `windows-latest`).
> Le dépôt ne contient aucun binaire ; `build/build_linux_check.sh` ne fait
> que **valider** le spec PyInstaller sous Linux.

## 1. Avant de taguer

- [ ] Faire passer la version dans **un seul endroit canonique** :
      `mustacom/config.py` → `APP_VERSION = "x.y.z"`.
      Le workflow CI relit cette valeur et la passe à Inno Setup via
      `/DAppVersion=` ; `build_windows.ps1` l'accepte aussi en `-Version`.
- [ ] Mettre à jour les mentions de version dans :
      - `README.md` (titre `v x.y.z`),
      - `docs/manuel-utilisateur.md` (titre),
      - `CHANGELOG.md` (nouvelle section, date du jour).
- [ ] `python -m pytest tests -q` → tous les tests au vert.
- [ ] `bash build/build_linux_check.sh` → exit 0 (freeze + `--version` du
      binaire figé + boot headless, exit 124 attendu pour le boot).
- [ ] Vérifier la cohérence documentaire (chemins cités, captures de
      numérotation, préfixes) — script de contrôle :
      `python tools/check_docs.py`.

## 2. Construire l'installateur

**Option A — CI (recommandée)** :

```bash
git tag v1.0.0
git push origin main --tags
```

Le workflow `windows-installer` s'exécute (jobs `freeze-check` puis
`build-installer`) et téléverse :

| Artefact | Contenu |
|---|---|
| `MUSTACOM-Business-Manager-Setup` | `installer/Output/MUSTACOM-Business-Manager-Setup.exe` |
| `mustacom-windows-frozen` | bundle figé `dist/mustacom/` (zip) |

Récupération : GitHub → *Actions → windows-installer → run du tag →
Artifacts*.

**Option B — machine Windows** :

```powershell
powershell -ExecutionPolicy Bypass -File build\build_windows.ps1 -Version 1.0.0
# → installer\Output\MUSTACOM-Business-Manager-Setup.exe
```

Prérequis : Python 3.10+ et [Inno Setup 6](https://jrsoftware.org/isinfo.php)
(`ISCC.exe` dans le PATH ou chemin par défaut).

## 3. Checklist de recette sur le poste de test (Windows)

- [ ] Installer `MUSTACOM-Business-Manager-Setup.exe` : raccourcis Bureau +
      menu Démarrer présents, aucun droit admin demandé.
- [ ] Premier lancement : écran d'activation, essai 30 j OK, création admin.
- [ ] `%APPDATA%\MUSTACOM\BusinessManager` créé avec `mustacom.db`.
- [ ] POS : vente complète + ticket ; session de caisse + rapport Z.
- [ ] Facture A4 PDF avec en-tête société.
- [ ] Sauvegarde manuelle → Vérifier → Restaurer.
- [ ] Licence : activer une clé de test (`tools/keygen.py`), renouveler.
- [ ] Désinstaller : données conservées dans `%APPDATA%`.

## 4. Publier

- [ ] Joindre l'installateur à la release GitHub du tag `v*`.
- [ ] Signatures SHA-256 (conseillé) :
      `certutil -hashfile MUSTACOM-Business-Manager-Setup.exe SHA256`.
- [ ] Diffusion interne : l'installateur + le manuel utilisateur
      (`docs/manuel-utilisateur.md` exporté en PDF) + la clé de licence par
      client (générée via *Licence → Générateur de clés* ou
      `tools/keygen.py`, **jamais** la même clé pour deux clients).
