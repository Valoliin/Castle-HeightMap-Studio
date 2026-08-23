# Résolution et performances

Le **Pas STEP** influence fortement la quantité de géométrie.

Pour un mur de 200 × 60 mm :

| Pas | Grille approximative |
| --- | --- |
| 1,0 mm | 201 × 61 |
| 0,5 mm | 401 × 121 |

Passer de 1 mm à 0,5 mm quadruple environ le nombre d'échantillons.

## Adaptatif sécurisé

Le mode adaptatif réduit les points X tout en protégeant la géométrie :

- aucune ligne Y supprimée ;
- ancres régulières ;
- points renforcés près des transitions ;
- contrôle anti-overshoot ;
- redensification automatique si nécessaire.

Pour une façade FDM, un pas de **0,5 à 1,0 mm** est généralement largement suffisant.
