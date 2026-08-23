# Diagnostic et logs

Le journal détaillé permet de diagnostiquer la génération STEP.

Exemple :

```text
[Section 066/121] makeSpline START
[Section 066/121] makeSpline END en 1.82 s
```

Si le programme reste longtemps sur `makeSpline START`, OpenCascade travaille sur cette spline.

Le fichier :

```text
castle_heightmap.log
```

contient également le journal complet.

Les étapes chronométrées comprennent :

- génération des points ;
- spline ;
- wire ;
- loft ;
- validation ;
- export STEP.
