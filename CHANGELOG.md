# Historique des versions — MUSTACOM BUSINESS MANAGER

## 1.0.0 — 2026-09-26

Première version de production.

### Application
- Tableau de bord : 13 indicateurs, graphiques ventes/bénéfice, top produits,
  alertes de stock, filtres de période.
- POS complet : scan/recherche, remises % et montant (globales et par ligne),
  6 modes de paiement dont mixte, rendu monnaie, ventes en attente, retours
  partiels avec avoir et restock, raccourcis F2/F4/F8/F9/F12/Échap, ticket
  80/58 mm ou facture A4/A5.
- Caisse : sessions (fond, compté, écart), dépôts/retraits, rapport Z.
- Documents : devis, BC client/fournisseur, BL, bons de route, factures,
  proforma, avoirs, retours client/fournisseur — conversions en chaîne,
  encaissements partiels, annulations avec correction stock & soldes,
  impression A4/A5/80/58 mm + PDF.
- Produits (23 champs, EAN-13 généré, import/export Excel & CSV), stock
  (mouvements, transferts, casse/perte, inventaires, valorisation, alertes),
  cycle d'achat complet (commande → réception → facture → paiement).
- Clients & fournisseurs (ICE/IF/RC, plafond de crédit, relevés de compte),
  paiements avec imputation, dépenses par catégories paramétrables.
- Services vendables au POS ; réparations 7 statuts avec ticket de dépôt et
  facturation.
- Codes-barres EAN-13/EAN-8/Code 128/QR + planches d'étiquettes 3 formats.
- 18 rapports exportables PDF/Excel/CSV ; journal d'audit.
- 6 rôles + matrice de permissions module × action (7 actions).
- Licence : essai 30 j, clés `MUST-XXXX-XXXX-XXXX-XXXX` signées HMAC liées à
  l'ID machine, 4 types, activation hors-ligne `.mlic`, renouvellement,
  désactivation, générateur de clés intégré (admin) + `tools/keygen.py`.
- Sauvegardes automatiques quotidiennes + manuelles, miroir USB/réseau,
  vérification (zip + SHA-256 + integrity_check), restauration, purge.
- Paramètres : entreprise (ICE/IF/RC, logo/cachet/signature), TVA,
  numérotation, langue FR/AR (RTL)/EN, devise MAD, fuseau Africa/Casablanca,
  imprimantes, papiers, POS, thème clair/sombre, base de données.
- Sécurité : mots de passe hachés (argon2/PBKDF2), sessions expirantes,
  requêtes paramétrées, permissions par module/action.

### Infrastructure
- PySide6 (Qt 6) + SQLite, application hors-ligne ; données dans
  `%APPDATA%\MUSTACOM\BusinessManager`.
- Empaquetage PyInstaller (onedir) + Inno Setup 6 →
  `MUSTACOM-Business-Manager-Setup.exe` (raccourcis, désinstallateur, FR/EN).
- Workflow GitHub Actions `windows-installer` (freeze-check Linux +
  build-installer Windows) produisant l'installateur en artefact.
- Script de validation Linux `build/build_linux_check.sh`.
- 58 tests automatisés (métier + interface headless).
- Documentation : README, manuel utilisateur, procédure de release.
