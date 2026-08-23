# Export STEP et FreeCAD

Le fichier STEP utilise :

- **X** = largeur ;
- **Y** = hauteur ;
- **Z** = épaisseur et relief.

La face arrière du mur est à `Z = 0`.

## Corps de référence

L'option **Ajouter Base_reference dans le même STEP** produit un seul fichier STEP contenant :

- `Mur_complet`
- `Base_reference`

Les deux corps utilisent exactement le même repère.

Dans FreeCAD :

```text
Relief_seul = Cut(Mur_complet, Base_reference)
```

Il n'y a donc **aucun recalage manuel** à effectuer.

## Booléens

Une fois importé dans FreeCAD, le STEP peut être utilisé avec :

- Cut ;
- Fuse ;
- Common ;
- autres opérations Part.
