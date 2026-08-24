# Changelog — Castle HeightMap Studio

## 4.4.2
- Intégration de vraies captures d’écran du projet dans le README GitHub.
- Ajout de captures dans l’écran de bienvenue : vue de l’éditeur et vue FreeCAD.
- Reprise de la présentation du projet avec des visuels plus concrets.
- Correction du bug AppImage `No module named 'PIL._tkinter_finder'`.
- Ajout du packaging explicite de Pillow/Tk dans les builds Linux et Windows.
- Ajout de `--collect-submodules PIL`.
- Ajout des imports cachés `PIL.ImageTk` et `PIL._tkinter_finder`.
- Ajout d’un test `pillow/tk` dans le self-test du binaire final.
- Lancement via AppImage et lancement via `./run.sh` doivent maintenant se comporter pareil côté rendu.


## 4.4.1
- Refonte complète de l'écran de bienvenue.
- Nouvelle présentation en deux colonnes avec identité visuelle sombre et accent doré.
- Affichage de l'icône du logiciel, de la version et de l'auteur.
- Aperçu visuel de la texture CDR fournie.
- Présentation en trois étapes : Composer → Régler le relief → Exporter.
- Indicateur indiquant si l'exemple CDR est déjà chargé.
- Actions de démarrage plus visibles : continuer avec l'exemple, nouveau projet ou ouvrir un projet.
- Liens directs vers l'aide et le changelog.
- Correction du prototype v4.4.0 qui faisait référence à un widget `MarkdownText` inexistant.
- README GitHub entièrement remanié avec une vraie description du logiciel en tête de page.
- Ajout dans le README de l'origine CDR, du problème que le logiciel cherche à résoudre et du workflow complet vers FreeCAD.
- Ajout d'une liste détaillée des fonctionnalités et de la présentation de l'exemple CDR.


## 4.4.0
- Ajout d'un écran de bienvenue / premier démarrage.
- Ajout d'une description claire de l'origine du projet : **CDR — Coupe de France de Robotique**.
- Ajout d'un exemple CDR chargé automatiquement au premier lancement.
- Ajout d'une commande **Fichier → Ouvrir l'exemple CDR**.
- Ajout d'une commande **Aide → Écran de bienvenue**.
- Le README et l'aide embarquée rappellent désormais l'objectif du projet.
- Refactor de l'ouverture de projet avec une méthode réutilisable.
- Chargement plus robuste des images embarquées dans les projets (`load()`, `copy()`).
- Après ouverture d'un projet/exemple, rendu 2D et aperçu 3D sont forcés immédiatement.
- Le rendu 2D journalise maintenant proprement ses erreurs au lieu de juste tout faire disparaître comme un magicien fatigué.


## 4.3.3
- Correction du packaging Windows de CasADi utilisé indirectement par CadQuery.
- Ajout d'un hook PyInstaller `hook-casadi.py`.
- Collecte explicite de tous les sous-modules, données, DLL et plugins CasADi.
- Ajout des imports cachés `casadi._casadi` et `_casadi`.
- Ajout d'un runtime hook Windows pour le chemin de recherche des DLL.
- Le dossier CasADi extrait par PyInstaller est ajouté avec `os.add_dll_directory()`.
- Le même dossier est ajouté au `PATH` pour le chargeur de plugins CasADi.
- Vérification de `casadi._casadi` dans l'environnement Windows avant compilation.
- Le self-test final de l'EXE continue de réaliser une vraie opération CadQuery/OpenCascade.
- La stratégie CasADi est également appliquée au build AppImage pour garder les deux plateformes cohérentes.


## 4.3.2
- Correction du self-test de l'EXE Windows construit avec PyInstaller `--windowed`.
- Compatibilité avec `pythonw.exe` / absence de `stdout` et `stderr`.
- Le self-test peut désormais écrire son résultat dans `CHMS_SELF_TEST_REPORT`.
- GitHub Actions lance l'EXE Windows avec `Start-Process -Wait -PassThru`.
- Le code de retour du véritable EXE est vérifié de manière fiable.
- Le rapport du self-test Windows est affiché directement dans les logs GitHub Actions.
- Le self-test AppImage produit le même type de rapport pour faciliter le diagnostic.
- L'application reste une vraie application graphique Windows : aucune console n'apparaît au lancement normal.


## 4.3.1
- Correction du démarrage de l'AppImage sur système de fichiers en lecture seule.
- Les logs ne sont plus écrits à côté de l'exécutable.
- Linux : logs dans `~/.local/state/CastleHeightMapStudio/`.
- Windows : logs dans `%LOCALAPPDATA%/CastleHeightMapStudio/`.
- Ajout de chemins de secours si le dossier utilisateur principal n'est pas inscriptible.
- Une erreur de création du fichier log ne peut plus empêcher le logiciel de démarrer.
- Ajout de `--self-test` pour tester le vrai binaire packagé sans ouvrir l'interface.
- GitHub Actions teste désormais l'EXE Windows et l'AppImage Linux avant publication.
- Correction de l'arborescence interne AppImage.
- Correction du job de publication GitHub Release avec `GH_REPO`.


## 4.3
- Ajout d'un véritable rendu Markdown dans les fenêtres d'aide.
- Les titres, listes, gras, italique, code et liens sont maintenant affichés correctement.
- Remplacement de l'onglet Aide monolithique par un **mini-wiki intégré**.
- Navigation par sommaire.
- Recherche instantanée dans les pages du wiki.
- Boutons précédent/suivant.
- Le changelog bénéficie lui aussi du rendu Markdown.
- Les liens HTTP/HTTPS deviennent cliquables.
- L'aide est maintenant découpée en pages thématiques dans `docs/wiki/`.


## 4.2
- Interface plus proche d'un logiciel de bureau classique.
- Menu **Fichier** : Nouveau, Ouvrir, Enregistrer, Enregistrer sous, export PNG, export STEP et Quitter.
- Menu **Édition** : Annuler/Rétablir, ajout et duplication de texture.
- Menu **Aide** : Aide, Changelog, recherche de mise à jour et À propos.
- Nouvelle fenêtre **À propos** inspirée des logiciels CAO : version, auteur, système, Python et bibliothèques.
- Auteur affiché : **Valentin Bonali**.
- Aide et changelog consultables directement dans l'application.
- Vérification des nouvelles versions via **GitHub Releases**.
- Téléchargement assisté de la bonne release (`.exe`, `.AppImage` ou ZIP) quand elle existe.
- Détection automatique du dépôt GitHub depuis `update_config.json`, `GITHUB_REPOSITORY` ou `.git/config`.
- Ajout d'une icône d'application.
- Ajout d'un système de build GitHub Actions pour Windows et Linux.
- Build Windows `.exe` via PyInstaller.
- Build Linux `.AppImage` via PyInstaller + AppImageKit.
- L'image `smoke_test_heightmap.png` est de nouveau fournie dans l'archive.
- Ajout d'un dossier `examples/`.

## 4.1
- Réécriture de la résolution adaptative pour supprimer les grandes oscillations B-Spline.
- Aucune suppression de lignes Y en mode adaptatif sécurisé.
- Ancres X régulières et renforcement autour des transitions fond/relief.
- Contrôle anti-overshoot des splines.
- Redensification automatique lorsqu'une spline devient dangereuse.
- Repli possible sur le profil complet.

## 4.0
- Sauvegarde et ouverture des projets `.castlehm`.
- Historique Annuler/Rétablir.
- Panneau de calques avec visibilité, verrouillage, ordre et renommage.
- Position et dimensions des calques en millimètres.
- Rotation et verrouillage du ratio.
- Aimantation à une grille paramétrable.
- Masques de relief : pinceau, rectangle et cercle/ellipse.
- Presets de conversion : Neutre, Pierre douce, Pierre marquée et Gravure.
- Aperçu 3D intégré.
- Résolution STEP adaptative.
- Analyse estimative avant export.
- Export STEP multi-corps optionnel avec `Mur_complet` + `Base_reference` dans le même repère pour FreeCAD.

## 3.2
- Journal de diagnostic dans l'interface.
- Fichier `castle_heightmap.log`.
- Chronométrage détaillé de chaque section, spline, wire, loft, validation et export.
- Avertissement sur les splines anormalement lentes.

## 3.1
- Correction du raccord automatique : utilisation de la height-map réellement traitée après HSV/niveaux/gamma.
- Alignement davantage basé sur les contours des joints.
- Ajout de `+ Raccordé` par miroir horizontal/vertical pour créer une jonction de bord continue.

## 3.0
- Passage à un véritable éditeur multi-calques.
- 8 poignées de redimensionnement façon traitement de texte.
- Étirement X/Y libre.
- Duplication, suppression et changement d'ordre des textures.
- Chevauchement avec raccord doux.
- Premier algorithme de raccord automatique.
- Zones sans texture = relief nul.

## 2.2
- Correction du STEP « mille-feuille ».
- Loft lissé / surface continue par défaut.
- Ancien mode en bandes conservé comme secours.

## 2.1
- Dézoom sous 100 %, jusqu'à 5 %.
- Zones hors image converties en noir / relief nul.
- Possibilité de conserver des bandes parfaitement lisses autour d'une texture.

## 2.0
- Interface graphique complète.
- Image source + rectangle de cadrage au ratio du mur.
- Zoom et déplacement de l'image.
- Réglages HSV.
- Contraste, niveaux noir/blanc, gamma et lissage.
- Prévisualisation de la height-map.
- Aperçu 3D.
- Export PNG et STEP.

## 1.0
- Première version du convertisseur image → height-map → STEP.
- Dimensions physiques du mur en millimètres.
- Épaisseur de fond, relief maximal et pas d'échantillonnage.
- Génération d'un vrai solide STEP via CadQuery/OpenCascade.
