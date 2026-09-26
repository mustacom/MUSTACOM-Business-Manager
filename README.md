# MUSTACOM BUSINESS MANAGER — v1.0.0

Application de gestion commerciale **100 % hors-ligne** pour poste Windows,
développée pour **MUSTACOM** — *002 Cité Minière (Tawzakt), 45800 Tinghir,
Maroc — 07 08 78 51 53 — mustacom.services@gmail.com — www.mustacom.com*.

Activités couvertes : fourniture informatique & bureautique, services
d'impression et publicitaire, négoce. Ventes/POS, caisse, devis & factures,
stock & achats, clients/fournisseurs (ICE/IF/RC), prestations, réparations
informatiques, codes-barres, 18 rapports, sauvegardes automatiques, licences
par machine et contrôle d'accès par rôle.

- **Stack** : Python 3.10+ / PySide6 (Qt 6) / SQLite — aucune dépendance cloud.
- **Langues** : Français (défaut), العربية (RTL complet), English.
- **Localisation** : devise MAD (DH), fuseau `Africa/Casablanca`,
  dates `jj/mm/aaaa`, TVA configurable (20 / 10 / 0 % par défaut).

> **Documentation complète** : le pas-à-pas destiné aux utilisateurs se trouve
> dans [`docs/manuel-utilisateur.md`](docs/manuel-utilisateur.md) ; la
> procédure de mise en release dans [`docs/RELEASE.md`](docs/RELEASE.md).

---

## ⚠ Provenance des exécutables Windows (important)

Les binaires Windows **ne sont pas conservés dans ce dépôt** (ils ne peuvent
pas être construits depuis Linux/macOS) :

- `MUSTACOM-Business-Manager.exe` (application figée PyInstaller) et
- `MUSTACOM-Business-Manager-Setup.exe` (installateur Inno Setup)

sont **produits par le workflow GitHub Actions**
`.github/workflows/windows-installer.yml` (runner `windows-latest`, à chaque
push sur `main`, tag `v*`, ou déclenchement manuel), ou localement sur une
machine Windows via `build\build_windows.ps1`. Le workflow téléverse
l'installateur en **artefact de build** (`MUSTACOM-Business-Manager-Setup`) ;
les releases taguées `v*` le publient donc automatiquement.

Sur Linux/macOS, `build/build_linux_check.sh` **valide uniquement le spec
PyInstaller** (freeze + démarrage headless) — il ne produit aucun exécutable
Windows.

---

## 1. Prérequis

| Pour | Il faut |
|---|---|
| Exécuter (poste client) | Windows 10/11 64 bits — rien d'autre (tout est embarqué) |
| Construire l'installateur | Windows + Python 3.10+ + [Inno Setup 6](https://jrsoftware.org/isinfo.php) |
| CI | Aucun prérequis manuel (Python et Inno Setup installés par le workflow) |
| Développer / tester | Python 3.10+, `pip install -r requirements.txt pytest` |

## 2. Installation (poste client)

1. Récupérez **`MUSTACOM-Business-Manager-Setup.exe`** :
   - artefact du workflow GitHub Actions (onglet *Actions → windows-installer
     → dernier run → Artifacts*), ou
   - `installer\Output\` après un build local (§ 6).
2. Double-cliquez : assistant FR/EN, installation **par utilisateur** (sans
   droits administrateur), raccourcis **Bureau + menu Démarrer**,
   désinstallateur intégré (*Paramètres Windows → Applications*).
3. **Premier lancement** :
   1. écran **ACTIVATION DU LOGICIEL** : *Démarrer la période d'essai (30 j)*,
      ou saisie d'une clé `MUST-XXXX-XXXX-XXXX-XXXX`, ou activation hors-ligne
      par fichier `.mlic` (§ 7) ;
   2. création du compte **administrateur** (mot de passe fort exigé) ;
   3. éventuellement `--demo-data` pour charger le jeu de démonstration
      (11 produits nommés, 6 services, 4 types de clients, ~30 j de ventes).

Toutes les données (base SQLite, sauvegardes, exports, journaux, images)
vivent dans **`%APPDATA%\MUSTACOM\BusinessManager`** — jamais dans le dossier
d'installation ; la désinstallation ne touche pas aux données.

## 3. Exécution de l'application

```text
MUSTACOM-Business-Manager.exe [--data-dir DIR] [--database FICHIER] [--dark]
                              [--lang fr|ar|en] [--demo-data]
                              [--skip-license] [--reset] [--version]
```

| Option | Effet |
|---|---|
| `--data-dir` | autre répertoire de données (multi-sociétés/tests) |
| `--database` | fichier SQLite précis |
| `--dark` | démarre en thème sombre |
| `--lang` | force la langue (fr / ar / en) |
| `--demo-data` | seed de démonstration si la base est vide |
| `--skip-license` | développement uniquement |
| `--reset` | **destructif** : recrée la base locale |
| `--version` | affiche `MUSTACOM BUSINESS MANAGER 1.0.0` |

Interface : barre latérale par domaines, bandeau supérieur (utilisateur,
rôle, état de licence), barre d'état (session de caisse ouverte + solde).
Changement de langue et de thème à chaud dans *Paramètres*.

## 4. Configuration (*Paramètres*)

| Onglet | Contenu |
|---|---|
| **Entreprise** | raison sociale, forme juridique, activité, adresse, ICE/IF/RC/CNSS/patente/capital, banque + RIB + SWIFT, logo/cachet/signature (repris sur tous les documents A4), pied de ticket |
| **Taxes et numérotation** | TVA par défaut / normale / réduite / nulle ; **préfixes de numérotation** par type de document (DEV, FAC, BL, ACH…) |
| **Langue et devise** | fr/ar/en, code & symbole devise (MAD/DH), fuseau, format de date |
| **Impression** | imprimante par défaut + imprimante tickets (sinon export PDF), papiers facture (A4/A5) et ticket (80/58 mm), nombre de copies, logo oui/non |
| **POS et sécurité** | vente en stock négatif, session de caisse obligatoire au POS, tiroir-caisse, expiration de session (minutes) |
| **Apparence** | thème clair / sombre appliqué immédiatement |
| **Base de données** | emplacement, taille, `PRAGMA integrity_check`, compactage (VACUUM) |

## 5. Modules

| Domaine | Écrans & capacités |
|---|---|
| **Ventes** | Tableau de bord : 13 indicateurs, graphiques ventes/bénéfice, top produits, dernières factures, alertes stock, filtres de période. **POS** : scan/recherche, remises % et montant (globales et par ligne), 6 modes de paiement (espaces, carte, virement, chèque, crédit, mixte), rendu monnaie, ventes en attente, retours partiels avec avoir + restock, raccourcis F2/F4/F8/F9/F12/Échap, ticket 80/58 mm ou facture A4. **Caisse** : sessions (fond, compté, écart), dépôts/retraits, rapport Z imprimable |
| **Documents** | Devis `DEV-2026-0001` (→ BC, → facture, duplication), BC client/fournisseur, BL (quantités commandées/livrées → facture), bons de route (chauffeur/véhicule/km), factures `FAC-…` / proforma `PRO-…`, avoirs `AVR-…` ; encaissements partiels, annulation avec correction stock & soldes ; impression A4/A5/80/58 mm + export PDF ; en-tête société personnalisé |
| **Stock & Achats** | Produits (23 champs, EAN-13 généré, prix par marge, import/export Excel & CSV), journal des mouvements, transferts, casse/perte, inventaires physiques avec écarts, valorisation achat/vente, alertes faible/rupture ; achats : commande `ACH-…` → réception (stock) → facture fournisseur `FAF-…` → paiement ; retours fournisseur `BRF-…` |
| **Tiers** | Clients (particulier/société/association/école/administration) & fournisseurs avec ICE/IF/RC, plafond de crédit, soldes temps réel, relevés de compte A4 ; paiements avec imputation sur factures ; **dépenses** `DEP-…` par catégories paramétrables (loyer, électricité, internet, transport, publicité…) |
| **Services** | Catalogue de prestations vendables au POS ; **Réparations** : ticket `REP-…` (appareil, série, accessoires, diagnostic, pièces + main-d'œuvre, acompte, ETA), 7 statuts, ticket de dépôt imprimable, facturation en un clic |
| **Outils** | Codes-barres EAN-13/EAN-8/Code 128/QR + planches d'étiquettes 3 formats ; **18 rapports** exportables PDF/Excel/CSV ; journal d'audit |
| **Système** | Utilisateurs + 6 rôles (admin, gérant, caissier, magasinier, technicien, comptable) avec matrice de permissions module × action ; sauvegardes (§ 6) ; écran Licence (§ 7) |

## 6. Sauvegardes & restauration

- **Automatique** : quotidienne à l'heure configurée (défaut 20:00),
  rétention paramétrable (défaut 30 archives) ; planificateur interne.
- **Manuelle** : *Sauvegarde → Créer* ; chaque archive zip contient la base +
  métadonnées + **somme de contrôle SHA-256**.
- **Emplacement** : local par défaut ; miroir configurable vers dossier,
  **clé USB ou partage réseau** (*Sauvegarde → emplacement*).
- **Vérifier** : test zip + `integrity_check` de la base embarquée.
- **Restaurer** : remplace la base courante après confirmation (redémarrage
  requis) ; **Purger** applique la rétention.
- Intégrité globale : *Paramètres → Base de données → Vérifier*.

## 7. Licences & clés de série

- Écran d'activation au premier lancement : essai **30 j**, clé de série, ou
  fichier d'activation hors-ligne `.mlic` ; bouton *Demander une licence*
  affiche l'**ID machine** à communiquer.
- Clés `MUST-XXXX-XXXX-XXXX-XXXX` **uniques par client**, signées HMAC-SHA256,
  liées à l'ID machine — **aucune clé universelle**.
- Types : `trial` / `standard` / `professional` / `enterprise` ; durée et
  nombre de postes paramétrables ; avertissement 15 j avant expiration ;
  renouvellement et désactivation depuis l'écran *Licence*.
- Génération des clés :
  - **dans l'application** : *Licence → Générateur de clés* (rôle admin) ;
  - **côté éditeur** : `python tools/keygen.py --company "Client SARL"
    --machine <ID> --type professional --days 365 --devices 2
    [--export client.mlic]`.
- Secret maître surchargé à la compilation : variable d'environnement
  `MUSTACOM_LICENSE_SECRET` (le défaut public ne sert qu'au développement).

## 8. Empaquetage Windows & releases

```powershell
# sur une machine Windows (Python 3.10+ et Inno Setup 6 installés) :
powershell -ExecutionPolicy Bypass -File build\build_windows.ps1 [-Version 1.0.0]
```

1. `pip install -r requirements.txt pyinstaller` ;
2. `python -m PyInstaller build\mustacom.spec` → bundle **onedir**
   `dist\mustacom\` (migrations SQL, police code-barres et données qrcode
   embarquées) ;
3. `ISCC /DAppVersion=… installer\mustacom.iss` →
   **`installer\Output\MUSTACOM-Business-Manager-Setup.exe`** (LZMA2,
   raccourcis Bureau + Démarrer, désinstallateur, langues FR/EN).

**CI** — `.github/workflows/windows-installer.yml` :

| Job | Runner | Rôle |
|---|---|---|
| `freeze-check` | ubuntu-latest | sanity-check du spec : freeze + `--version` du binaire figé |
| `build-installer` | windows-latest | freeze → vérification de l'exe → `choco install innosetup` → ISCC → **artefact `MUSTACOM-Business-Manager-Setup`** (+ bundle figé en second artefact) |

Déclencheurs : push `main`, tags `v*`, pull requests, `workflow_dispatch`.
Voir `docs/RELEASE.md` pour la checklist de mise en release.

**Validation Linux locale** (ne produit **pas** d'exécutable Windows) :

```bash
bash build/build_linux_check.sh   # freeze + --version + boot headless (exit 124 attendu)
```

## 9. Tests & développement

```bash
python -m pip install -r requirements.txt pytest
python -m pytest tests -q          # 58 tests : calculs, stock, ventes, licences, sécurité, UI headless
```

Le harnais `tests/ui_smoke.py` construit une base de démo et pilote
l'interface en `QT_QPA_PLATFORM=offscreen` (captures d'écran incluses).

## 10. Arborescence

```text
mustacom/            code source : core/ (métier), db/ (SQLite+migrations),
                     ui/ (écrans PySide6), reporting/ (documents, exports), i18n/
tests/               pytest + harnais UI headless
build/               mustacom.spec, entry.py, build_windows.ps1, build_linux_check.sh
installer/           mustacom.iss (Inno Setup 6) → installer\Output\MUSTACOM-Business-Manager-Setup.exe
tools/               keygen.py (générateur de clés éditeur)
assets/              logo.png, logo-256.png, mustacom.ico
.github/workflows/   windows-installer.yml (artefacts Windows)
docs/                manuel-utilisateur.md, RELEASE.md
CHANGELOG.md         historique des versions
```

## 11. Sécurité

Mots de passe hachés (argon2 si disponible, sinon PBKDF2-SHA256
200 000 itérations), verrouillage après tentatives échouées, sessions avec
expiration configurable, permissions par module/action, requêtes SQL 100 %
paramétrées, licence signée HMAC, sauvegardes zip avec somme de contrôle,
`PRAGMA integrity_check` et contrôle des clés étrangères.

## 12. Support

MUSTACOM — 002 Cité Minière (Tawzakt), 45800 Tinghir, Maroc —
07 08 78 51 53 — mustacom.services@gmail.com — www.mustacom.com
