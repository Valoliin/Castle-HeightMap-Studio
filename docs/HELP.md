# Aide — Castle HeightMap Studio

## Origine du projet

Castle HeightMap Studio a été créé pour un projet **CDR — Coupe de France de Robotique**.

L'objectif est de générer rapidement des murs texturés, des height-maps et des STEP pour FreeCAD.

# Aide — Castle HeightMap Studio

Castle HeightMap Studio transforme une image ou une composition de textures en relief 3D exportable en STEP pour FreeCAD.

## Workflow rapide

1. **Fichier → Nouveau** pour repartir d'un projet vide.
2. Clique sur **+ Image** pour ajouter une texture.
3. Déplace et redimensionne la texture dans le cadre rouge représentant le mur.
4. Utilise les réglages de conversion pour obtenir une height-map exploitable.
5. Ajoute des masques si certaines zones doivent rester parfaitement lisses.
6. Vérifie le résultat dans les onglets **Height-map** et **3D**.
7. Règle les dimensions du mur, le fond, le relief et le pas STEP.
8. Exporte en STEP.

## Height-map

- **Noir** = niveau du fond, donc aucun relief.
- **Blanc** = relief maximal.
- Les gris donnent les hauteurs intermédiaires.

## Masques

- **Pinceau** : nettoie une forme libre.
- **Rectangle** : idéal autour d'une trappe, d'un capteur ou d'une fixation.
- **Cercle** : idéal pour une ouverture ou un capteur circulaire.

Les masques imposent un relief nul.

## Plusieurs textures

Une image sélectionnée possède huit poignées de redimensionnement.

`+ Raccordé` est recommandé pour prolonger une image classique sans couture brutale :
la copie est placée au bord et retournée en miroir.

`Raccord auto` sert surtout lorsque deux textures possèdent une vraie zone de chevauchement.

## Export FreeCAD bicolore

L'option **Ajouter Base_reference dans le même STEP** crée un seul fichier STEP contenant :
- `Mur_complet`
- `Base_reference`

Les deux corps partagent exactement le même repère.

Dans FreeCAD :
1. importe le STEP ;
2. garde `Mur_complet` pour la géométrie complète ;
3. effectue `Cut(Mur_complet, Base_reference)` pour obtenir uniquement le relief.

Tu peux ensuite conserver les deux corps pour ton workflow de fabrication sans aucun recalage manuel.

## Résolution STEP

Un pas plus petit augmente fortement le temps de calcul.

Exemple pour 200 × 60 mm :
- 1,0 mm : environ 201 × 61 échantillons ;
- 0,5 mm : environ 401 × 121 échantillons.

Le mode adaptatif sécurisé réduit les points X tout en contrôlant les splines pour éviter les oscillations.

## Projets

Le format `.castlehm` conserve les textures directement dans le projet ainsi que :
- dimensions ;
- calques ;
- masques ;
- réglages ;
- paramètres STEP.

## Mise à jour

Le menu **Aide → Rechercher les mises à jour** interroge la dernière GitHub Release.

Le programme ne remplace jamais silencieusement l'exécutable en cours d'utilisation :
il propose de télécharger la nouvelle release adaptée à la plateforme.

## Diagnostic

En cas de blocage pendant l'export STEP, ouvre l'onglet **Logs**.

Le fichier `castle_heightmap.log` contient également un journal détaillé.
