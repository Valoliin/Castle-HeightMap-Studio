# Impression bicolore

Le workflow bicolore reste compatible avec FreeCAD.

Une stratégie simple consiste à utiliser :

- un fond sombre ;
- un relief clair.

Avec le STEP multi-corps, `Base_reference` et le relief peuvent être séparés dans FreeCAD tout en restant parfaitement alignés.

## Exemple de construction

```text
Fond : 1,0 mm
Relief : 1,25 mm
```

La pièce complète s'étend donc de 1,0 à 2,25 mm.

L'objectif est de conserver la conception mécanique dans FreeCAD avant le passage dans le slicer.
