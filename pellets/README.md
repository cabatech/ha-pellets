# HA - Pellets

App Home Assistant de suivi d'un stock de pellets de bois : achats, déstockage, consommation, prix moyen, autonomie.

- Interface web dans la barre latérale de HA (Ingress) : tableau de bord, saisie des achats, lots, mouvements, statistiques.
- API REST sur le port 8234 du réseau interne de HA, utilisée par l'intégration `pellets` du même dépôt.
- Base SQLite dans `/data/pellets.db`, incluse dans les sauvegardes de HA.

## Reprendre une base existante

Avant le premier démarrage, déposer le fichier dans `/share/pellets/pellets.db`. L'app le copie dans `/data` si aucune base n'existe encore.
