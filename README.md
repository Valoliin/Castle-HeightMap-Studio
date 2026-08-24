# Castle HeightMap Studio v4.4.0

**Auteur : Valentin Bonali**

Castle HeightMap Studio transforme des images et textures en reliefs 3D exportables en STEP, avec un workflow pensé pour FreeCAD et l'impression 3D.

## Installation rapide

### Windows — mode Python

Double-cliquer sur :

```text
install_windows.bat
```

Puis :

```text
run_windows.bat
```

### Linux / Zorin / Ubuntu — mode Python

```bash
chmod +x install_linux.sh run.sh
./install_linux.sh
./run.sh
```

## Version « logiciel » : EXE et AppImage

Le dépôt contient maintenant des scripts de build et un workflow GitHub Actions.

### Construire l'EXE sous Windows

```text
build_windows.bat
```

Le résultat est placé dans :

```text
dist/CastleHeightMapStudio.exe
```

### Construire l'AppImage sous Linux

```bash
chmod +x build_appimage.sh
./build_appimage.sh
```

Le résultat attendu est :

```text
dist/CastleHeightMapStudio-x86_64.AppImage
```

### GitHub Actions

Le fichier :

```text
.github/workflows/build-release.yml
```

construit automatiquement :
- le `.exe` Windows ;
- l'`.AppImage` Linux ;
- une archive source.

Sur un tag Git tel que `v4.2`, le workflow peut également publier les fichiers dans **GitHub Releases**.

## Mise à jour

Le menu :

```text
Aide → Rechercher les mises à jour
```

utilise l'API publique GitHub Releases.

Le dépôt est détecté automatiquement depuis :
1. `update_config.json` ;
2. la variable `GITHUB_REPOSITORY` ;
3. le remote `origin` Git.

Lors d'un build GitHub Actions, `update_config.json` est automatiquement renseigné avec le vrai dépôt.

Le logiciel télécharge la nouvelle version mais ne remplace pas silencieusement l'exécutable en cours : il laisse l'utilisateur lancer le nouveau fichier.

## Menus

### Fichier
- Nouveau
- Ouvrir
- Enregistrer
- Enregistrer sous
- Export PNG
- Export STEP
- Quitter

### Édition
- Annuler / Rétablir
- Ajouter une texture
- Dupliquer
- Supprimer

### Aide
- Aide
- Changelog
- Rechercher les mises à jour
- À propos

## À propos

La fenêtre À propos affiche notamment :
- version ;
- auteur ;
- système ;
- architecture ;
- Python ;
- Tk ;
- NumPy ;
- Pillow ;
- Matplotlib ;
- CadQuery ;
- dépôt GitHub détecté.

## Documentation

L'aide intégrée est maintenant organisée comme un mini-wiki :

- `docs/wiki_index.json`
- `docs/wiki/*.md`
- `docs/CHANGELOG.md`

Le logiciel possède son propre rendu Markdown pour les titres, listes, gras,
italique, blocs de code et liens cliquables.

## Exemple

L'image demandée est fournie :
- `smoke_test_heightmap.png`
- `examples/stone_wall_heightmap.png`

## STEP FreeCAD multi-corps

L'option **Ajouter Base_reference dans le même STEP** conserve les deux solides dans **un seul fichier STEP et le même repère** :

- `Mur_complet`
- `Base_reference`

Dans FreeCAD, `Cut(Mur_complet, Base_reference)` donne le relief seul sans recalage manuel.


## Logs

Les builds packagés n'écrivent jamais dans leur propre dossier.

- Linux : `~/.local/state/CastleHeightMapStudio/castle_heightmap.log`
- Windows : `%LOCALAPPDATA%\CastleHeightMapStudio\castle_heightmap.log`

## Self-test des builds

```bash
CastleHeightMapStudio --self-test
```

GitHub Actions exécute ce test sur les artefacts finaux avant de les publier.


## Packaging CadQuery / CasADi

CadQuery dépend notamment de CasADi. Sous Windows, CasADi contient un module
SWIG natif (`casadi._casadi`) et de nombreuses DLL.

Le build inclut donc :
- `--collect-all casadi`
- `--hidden-import casadi._casadi`
- un hook PyInstaller dédié ;
- un runtime hook Windows qui ajoute le dossier CasADi au chemin de recherche
  des DLL.

Le self-test de release effectue ensuite une vraie création de solide CadQuery
pour vérifier que la pile CadQuery/OpenCascade/CasADi est fonctionnelle.


## Origine du projet

Castle HeightMap Studio a été créé pour un projet **CDR — Coupe de France de Robotique**.

L'idée est de produire rapidement des textures de murs, des height-maps et des fichiers STEP
pour habiller un robot sur un thème **château fort / Camelot**, tout en gardant un workflow
simple avec **FreeCAD** et l'impression 3D.

En clair : éviter la punition médiévale qui consiste à modéliser chaque pierre à la main.

## Premier démarrage

Au premier lancement, l'application :

- affiche un **écran de bienvenue** ;
- explique l'origine et l'objectif du projet ;
- charge automatiquement un **exemple CDR** ;
- permet ensuite de partir sur un projet vide ou d'ouvrir son propre fichier.
