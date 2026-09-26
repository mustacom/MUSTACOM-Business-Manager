# Manuel utilisateur — MUSTACOM BUSINESS MANAGER v1.0.0

> **MUSTACOM** — 002 Cité Minière (Tawzakt), 45800 Tinghir, Maroc —
> 07 08 78 51 53 — mustacom.services@gmail.com — www.mustacom.com

Ce manuel couvre l'installation, la configuration, l'utilisation quotidienne,
les sauvegardes et la licence de l'application.

---

## 1. Installation

### 1.1 Installer l'application (poste Windows)

1. Récupérez le fichier **`MUSTACOM-Business-Manager-Setup.exe`**
   (release GitHub ou artefact du workflow *windows-installer* ; il peut aussi
   être compilé localement sur Windows — voir le README, § 8).
2. Double-cliquez dessus. L'assistant est disponible en **français** et en
   **anglais** (choix automatique selon la langue de Windows).
3. Choisissez le dossier d'installation (défaut proposé) — aucun droit
   administrateur n'est requis.
4. Terminez : l'installateur crée un raccourci sur le **Bureau** et dans le
   **menu Démarrer**, puis lance l'application.

### 1.2 Désinstaller

*Paramètres Windows → Applications → MUSTACOM Business Manager →
Désinstaller* (ou raccourci « Désinstaller » du menu Démarrer).
**Les données commerciales ne sont pas supprimées** : elles se trouvent dans
`%APPDATA%\MUSTACOM\BusinessManager` — exportez-les ou conservez ce dossier
avant de changer de machine.

### 1.3 Premier lancement

1. **Écran d'activation** : trois options (§ 15) —
   *Démarrer la période d'essai (30 jours)*, saisir une **clé de série**
   `MUST-XXXX-XXXX-XXXX-XXXX`, ou activer hors-ligne avec un fichier `.mlic`.
2. **Création du compte administrateur** : identifiant + mot de passe fort
   (longueur et complexité contrôlées). Ce compte donne accès à tout :
   utilisateurs, permissions, paramètres, sauvegardes, licence.
3. Le tableau de bord s'affiche. Une base vide est normale : créez d'abord
   les produits, clients et fournisseurs, ou lancez l'option `--demo-data`
   (§ 3.3) pour explorer l'application avec un jeu de démonstration.

## 2. Emplacement des données

| Contenu | Emplacement |
|---|---|
| Base de données SQLite | `%APPDATA%\MUSTACOM\BusinessManager\mustacom.db` |
| Sauvegardes | `%APPDATA%\MUSTACOM\BusinessManager\backups\` (+ miroir USB/réseau configuré) |
| Exports & rapports | `%APPDATA%\MUSTACOM\BusinessManager\exports\` |
| Journaux d'application | `%APPDATA%\MUSTACOM\BusinessManager\logs\` |
| Images (logo, cachet…) | `%APPDATA%\MUSTACOM\BusinessManager\` |

## 3. Exécution de l'application

### 3.1 Interface

- **Barre latérale** : modules regroupés par domaines (Ventes, Documents,
  Stock & Achats, Tiers, Services, Outils, Système).
- **Bandeau supérieur** : utilisateur connecté, rôle, état de la licence.
- **Barre d'état** : session de caisse ouverte et son solde.
- Les boutons absents de l'interface correspondent aux **permissions**
  refusées pour le rôle (§ 13).

### 3.2 Langue et thème

- *Paramètres → Langue et devise* : **Français**, **العربية (RTL complet)**,
  **English** — appliqués immédiatement, sans redémarrage.
- *Paramètres → Apparence* : thème **clair** ou **sombre**.

### 3.3 Ligne de commande

```text
MUSTACOM-Business-Manager.exe [--data-dir RÉP] [--database FICHIER] [--dark]
                              [--lang fr|ar|en] [--demo-data]
                              [--skip-license] [--reset] [--version]
```

- `--data-dir` : autre répertoire de données (tests, multi-sociétés).
- `--demo-data` : charge le jeu de démonstration si la base est vide
  (11 produits, 6 services, 4 types de clients, ~30 jours de ventes).
- `--reset` : **destructif** — recrée une base vierge.
- `--version` : affiche la version.

## 4. Configuration (*Paramètres*)

### 4.1 Entreprise

Raison sociale, forme juridique, activité, adresse, ville, téléphone, e-mail,
site web, **ICE / IF / RC / CNSS / patente / capital**, coordonnées bancaires
(banque, RIB, SWIFT). Images : **logo**, **cachet**, **signature** — repris
automatiquement sur tous les documents A4 ; pied de page des tickets.

### 4.2 Taxes et numérotation

- **TVA** : taux par défaut, taux normal (20 %), réduit (10 %) et nul (0 %) —
  modifiables, appliqués aux produits et aux lignes de documents.
- **Numérotation** : préfixe de chaque type de document (voir annexe B),
  incrément automatique `PRÉFIXE-AAAA-NNNN`.

### 4.3 Langue et devise

Langue de l'interface, code devise (MAD) et symbole (DH), fuseau horaire
(`Africa/Casablanca`), format de date (`jj/mm/aaaa`).

### 4.4 Impression

Imprimante par défaut (documents) et **imprimante tickets** (POS) — si aucune
imprimante n'est disponible, l'export PDF prend le relais. Papiers : facture
**A4/A5**, ticket **80 mm / 58 mm**. Nombre de copies, affichage du logo.

### 4.5 POS et sécurité

Vente en stock négatif (oui/non), session de caisse obligatoire au POS,
ouverture du tiroir-caisse, **expiration de session** en minutes.

### 4.6 Base de données

Emplacement et taille du fichier, **vérification d'intégrité**
(`PRAGMA integrity_check`) et **compactage** (VACUUM).

## 5. Tableau de bord

13 indicateurs (CA jour, CA mois, bénéfice, ventes, achats, dépenses, valeur
du stock, stock faible, rupture, créances clients, dettes fournisseurs,
nb clients, nb fournisseurs), graphique des ventes et du bénéfice, top
produits, dernières factures, alertes de stock. Filtres de période :
aujourd'hui / 7 jours / 30 jours / mois / année / période personnalisée.

## 6. Caisse (POS)

| Touche | Action |
|---|---|
| `F2` | champ recherche produit |
| `F4` | choix du client |
| `F8` / `F12` | encaisser / valider la vente |
| `F9` | mettre la vente en attente |
| `Entrée` (champ scan) | ajout par code-barres |
| `Échap` | vider le panier |

- Recherche par nom, SKU ou code-barres ; scan direct à la douchette.
- Remise globale en **%** ou en **montant**, remise par ligne.
- Paiement : espèces (rendu monnaie), carte, virement, chèque, crédit
  (client obligatoire, plafond vérifié), **mixte** (répartition des montants).
- **Mettre en attente / Reprendre** : paniers suspendus par session.
- **Mode retour/avoir** : choisir la vente d'origine, quantités retournées →
  restock automatique et avoir `AVR-…` généré.
- Après validation : impression du **ticket 80/58 mm** ou de la **facture
  A4/A5** (+ PDF).

**Session de caisse** : *Caisse → Ouvrir* (fond de caisse) ; la fermeture
saisit le compté et calcule l'**écart** ; le **rapport Z** récapitule
espèces/ventes/dépôts/retraits et s'imprime. Dépôts et retraits d'espèces
tracés.

## 7. Documents de vente

- **Devis** (`DEV-2026-0001`) : client, lignes, remise, validité ;
  impression/PDF, *Dupliquer*, conversions **→ BC** et **→ Facture**.
- **Bons de commande** client/fournisseur ; conversion client → facture.
- **Bons de livraison** : quantités commandées/livrées par ligne, conversion
  → facture.
- **Bons de route** : chauffeur, véhicule, départ/destination, km, colis.
- **Factures** (`FAC-…`) : encaissement total/partiel, annulation (stock &
  soldes corrigés), avoir, impression/PDF ; proforma `PRO-…`.
- **Avoirs** (`AVR-…`) : consultation et impression.

Tous les documents portent l'en-tête société (logo, ICE/IF/RC, pied de page
définis dans *Paramètres → Entreprise*) et respectent les papiers configurés.

## 8. Produits & Stock

- **Produits** : fiche à 23 champs (SKU, code-barres, catégorie, marque,
  fournisseur, prix achat/vente HT, TVA, stock min/max, emplacement…),
  génération EAN-13, calcul de prix par marge, import/export **Excel & CSV**,
  historique des mouvements, ajustement manuel.
- **Stock** : journal des mouvements (achat, vente, retours, ajustement,
  transfert, casse, perte, inventaire), transferts entre emplacements,
  casse/perte motivées, **inventaire physique** (comptage puis validation des
  écarts), valorisation (achat/vente), alertes faible/rupture.
- **Codes-barres** : EAN-13 / EAN-8 / Code 128 / QR, planches d'étiquettes
  38×25 / 50×30 / 70×40 mm avec prix et nom, impression A4.

## 9. Achats & fournisseurs

Cycle complet : **commande** (`ACH-…`) → **réception** (`REC-…`, stock
augmenté) → **facture fournisseur** (`FAF-…`) → **payer** (virement/chèque/
espèces). **Retours fournisseur** (`BRF-…`) avec sortie de stock. Liste des
factures fournisseur et soldes.

## 10. Tiers, paiements & dépenses

- **Clients / Fournisseurs** : fiches avec ICE/IF/RC, type de client
  (particulier, société, association, école, administration), plafond de
  crédit, **relevé de compte** imprimable A4, solde en temps réel.
- **Paiements** : encaissements `ENC-…` (avec imputation cochée sur
  factures) et décaissements `DEB-…` ; mise à jour automatique des statuts
  et des soldes.
- **Dépenses** (`DEP-…`) : charges classées par **catégories paramétrables**
  (loyer, électricité, internet, transport, publicité…) avec montant, TVA et
  justificatif ; rapport « dépenses par catégorie ».

## 11. Services & réparations

- **Services** : catalogue de prestations (impression, publicité,
  maintenance…) **vendables directement au POS**.
- **Réparations** : ticket (`REP-…`) avec appareil, série, accessoires,
  problème/diagnostic, pièces + main-d'œuvre, acompte, ETA ; **7 statuts**
  (reçu → diagnostic → attente pièces → en réparation → test → prêt → livré) ;
  impression du ticket de dépôt ; **Facturer** génère la facture.

## 12. Rapports & exports

18 rapports (ventes par jour/produit/catégorie/mode de paiement, marge &
résultat, meilleurs clients, balances clients/fournisseurs, déclaration TVA,
achats, factures fournisseur, dépenses par catégorie, valorisation &
mouvements & alertes de stock, caisse journalière, activité réparations,
journal d'audit) — chacun exportable en **PDF, Excel, CSV**.

## 13. Utilisateurs & permissions

Six rôles prédéfinis : **administrateur, gérant, caissier, magasinier,
technicien, comptable**. La **matrice de permissions** (module × action :
voir/créer/modifier/supprimer/imprimer/exporter/valider) se règle par rôle ;
chaque bouton de l'interface respecte ces droits. Réinitialisation de mot de
passe par l'administrateur.

## 14. Sauvegardes & restauration

1. **Automatique** : *Paramètres* — sauvegarde quotidienne activée par défaut
   à 20:00, rétention 30 archives ; l'horaire et le nombre sont réglables.
2. **Manuelle** : *Sauvegardes → Créer* avec libellé libre.
3. **Emplacement** : dossier local par défaut ; *Sauvegardes → emplacement*
   ajoute un miroir sur **clé USB ou partage réseau**.
4. **Vérifier** : test du zip + somme de contrôle SHA-256 + intégrité SQLite
   de la base embarquée.
5. **Restaurer** : sélection de l'archive → confirmation → remplacement de la
   base courante → **redémarrage de l'application**.
6. **Purger** : applique la politique de rétention.

> Conseil : branchez la clé USB de sauvegarde chaque jour ; l'archive du jour
> est la garantie contre toute panne du poste.

## 15. Licence

- **Essai** : 30 jours complets, démarrés au premier lancement ; avertissement
  15 jours avant l'expiration.
- **Acheter une licence** : bouton *Demander une licence* → communiquer
  l'**ID machine** affiché et la raison sociale à MUSTACOM → recevoir une clé
  `MUST-XXXX-XXXX-XXXX-XXXX` **propre à ce poste** (les clés sont uniques par
  client : aucune clé ne fonctionne sur une autre machine).
- **Activation** : saisir la clé, ou utiliser le **fichier `.mlic`** reçu
  (activation hors-ligne, sans saisie).
- **Types** : trial / standard / professional / enterprise, avec durée et
  nombre de postes paramétrables.
- **Écran Licence** : type, machine, expiration, jours restants, postes
  autorisés ; **Renouveler**, **Désactiver**, export du fichier de licence ;
  **Générateur de clés** (admin) pour émettre des clés.
- Changer de matériel : *Désactiver* puis réactiver avec la nouvelle clé.

---

## Annexe A — Raccourcis clavier (POS)

`F2` recherche · `F4` client · `F8`/`F12` encaisser · `F9` attente ·
`Entrée` scan · `Échap` vider.

## Annexe B — Numérotation des documents

| Document | Préfixe | Document | Préfixe |
|---|---|---|---|
| Devis | `DEV` | Achat | `ACH` |
| BC client | `BCC` | Réception achat | `REC` |
| BC fournisseur | `BCF` | Facture fournisseur | `FAF` |
| Bon de livraison | `BL` | Encaissement | `ENC` |
| Bon de route | `BR` | Décaissement | `DEB` |
| Vente POS | `VTE` | Dépense | `DEP` |
| Facture | `FAC` | Réparation | `REP` |
| Proforma | `PRO` | Entrée de stock | `ENT` |
| Avoir | `AVR` | Sortie de stock | `SOR` |
| Retour client | `BRC` | Ajustement stock | `AJU` |
| Retour fournisseur | `BRF` | Inventaire | `INV` |
| Session caisse | `CS` | Livraison | `LIV` |

Format : `PRÉFIXE-AAAA-NNNN` (ex. `FAC-2026-0001`), année glissante.

## Annexe C — Dépannage rapide

| Symptôme | Solution |
|---|---|
| « Stock insuffisant » au POS | *Paramètres → POS et sécurité* (stock négatif) ou réapprovisionner |
| Impression absente | *Paramètres → Impression* : choisir l'imprimante ou exporter en PDF |
| Licence expirée | Écran *Licence* → Renouveler, nouvelle clé ou fichier `.mlic` |
| Perte de données | *Sauvegardes* → Vérifier puis Restaurer l'archive du jour |
| Base suspecte | *Paramètres → Base de données → Vérifier* (integrity_check) |
| Mot de passe oublié | Un administrateur réinitialise le mot de passe (*Utilisateurs*) |
