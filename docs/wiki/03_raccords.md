# Raccords entre textures

Une photo classique n'est pas forcément répétable.

## + Raccordé

La méthode la plus fiable pour prolonger une texture classique est **+ Raccordé**.

La copie est placée contre l'original puis retournée :

- miroir X pour gauche/droite ;
- miroir Y pour haut/bas.

Le bord commun est donc pixel-identique.

## Raccord doux

Un raccord doux mélange progressivement deux zones qui se chevauchent.

Une valeur de **4 à 10 %** est généralement suffisante.

## Raccord auto

Le raccord automatique analyse la **height-map réellement traitée** et donne davantage de poids aux contours des joints.

Il est surtout utile lorsque deux textures possèdent une vraie zone de chevauchement.
