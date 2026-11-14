# ha-pellets

Suivi d'un stock de pellets de bois dans Home Assistant.

| Dossier | Contenu |
|---|---|
| `pellets/` | App Home Assistant (FastAPI + SQLite, interface web par Ingress) |
| `custom_components/pellets/` | Intégration Home Assistant (installable par HACS) |

## Installation

1. **App** : Paramètres → Apps → Boutique → ⋮ → Dépôts, ajouter `https://github.com/cabatech/ha-pellets`, installer « HA - Pellets », démarrer.
2. **Intégration** : HACS → ⋮ → Dépôts personnalisés, ajouter le même dépôt en type « Intégration », installer « Pellets », redémarrer HA.
3. Paramètres → Appareils et services → Ajouter → Pellets. URL : `http://<nom d'hôte de l'app>:8234` (affiché sur la page de l'app).

## Entités

| Entité | Contenu |
|---|---|
| Stock, Stock en sacs | stock actuel |
| Autonomie, Conso moyenne | jours restants, kg/jour (moyenne 30 j, sinon 7 j) |
| Prix moyen | €/kg sur tous les achats |
| Conso hier | kg déstockés la veille |
| Stock bas | vrai si stock < 30 kg ou autonomie < 7 jours |
| Déstocker un sac | enregistre la sortie d'un sac (poids réglé à la configuration) |

Les achats se saisissent dans l'interface web de l'app.
