# AGENTS.md

> Instructions pour les agents IA qui travaillent sur ce dépôt (Claude Code, opencode, Cursor…).
> Le socle commun (sections 1 à 8) est copié depuis le second brain de Christophe, aire Vibecoding. Les sections « Spécifique au projet » sont propres à ce dépôt.

## 1. Contexte

- Lire `.contexte.md` en début de session : mission, décisions, statut et tâches. C'est la note du second brain (lien symbolique non versionné). Sans elle, demander à Christophe.
- Décisions, statut et tâches s'écrivent dans `.contexte.md`, jamais dans le dépôt. Tâches Operon : ne jamais écrire d'`operonId` à la main.
- Design : lire `DESIGN.md` (lien symbolique non versionné) avant toute interface. Il est commun à toutes les apps.
- Christophe est francophone, technicien vidéo événementiel et homelab. Il pilote, l'agent code. Échanges en français. Code, commentaires et commits en anglais si l'écosystème l'impose.

## 2. Méthode de travail

- **Réfléchir avant de coder.** Énoncer les hypothèses. Si la demande est ambiguë ou si plusieurs lectures existent, demander. Si une approche plus simple existe, la proposer.
- **Le plus petit changement qui résout tout le problème.** Réutiliser l'existant, la bibliothèque standard, les dépendances déjà installées, avant d'écrire du code. Pas de fonctionnalité, d'abstraction ni d'option non demandée.
- **Changements chirurgicaux.** Chaque ligne modifiée se rattache à la demande. Pas de refactor ni de reformatage voisin. Code mort ou suppression hors périmètre : proposer, ne pas appliquer. En cas de conflit entre « simplifier » et « rester dans le périmètre », le périmètre prime.
- **Objectif vérifiable.** Transformer la tâche en critère de succès (test qui échoue puis passe, commande qui répond). Pour plusieurs étapes, annoncer un plan court avec la vérification de chacune.
- **Zéro hallucination.** Pas de version, d'API ni d'option de bibliothèque sans l'avoir lue dans la doc ou le code installé. Sans réponse sûre, le dire.
- Skills de référence : [Ponytail](https://github.com/dietrichgebert/ponytail) en mode `full` ou `lite` (jamais `ultra`) ; [Karpathy guidelines](https://github.com/multica-ai/andrej-karpathy-skills). `ponytail-audit` et `ponytail-debt` seulement sur demande, en session dédiée.
- **Orchestrer par défaut.** Découper la demande ; dès qu'il y a au moins deux tâches indépendantes, une par agent en parallèle (worktree, modèle et effort adaptés, skills nommés dans le brief : Ponytail pour le code, Impeccable pour l'interface). Une tâche seule se fait en direct. L'orchestrateur relit, intègre, versionne et coche la demande dans la note du projet. Détail : skill `orchestrer-developpement-vibecoding` (second brain, `98-SYSTEM-TOOLS/SKILLS/`, à lire en début de session).

## 3. Stack par défaut

Choix de départ quand rien n'impose autre chose. Tout écart est justifié dans `.contexte.md` et validé par Christophe.

- **Langage et application** : Rust, avec Tauri pour le bureau et le mobile.
- **Interface** : Vue.js. Vue Flow pour les vues en graphe (nœuds et relations).
- **Style** : variables CSS et composants maison selon `DESIGN.md` (pas de bibliothèque de composants).
- Langage moderne et maintenu. Pas de dépendance ajoutée « pour quelques lignes ».

## 4. Internationalisation

- L'app existe en **français et en anglais dès la première version**.
- Aucune chaîne visible en dur dans le code : tout passe par des clés de traduction, un fichier par langue.
- Ajouter une langue = ajouter un fichier, sans toucher au code.
- Dates, nombres et unités suivent la langue choisie.

## 5. Design

- Toutes les apps partagent `DESIGN.md` : thème sombre par défaut, thème clair toujours disponible, tout tient à l'écran sans scroll, tactile dès le départ, couleur porteuse de sens.
- Avant de proposer une interface terminée, passer la checklist de revue de `DESIGN.md`.
- Textes d'interface et documentation : écrits comme un humain. Pas de vocabulaire marketing creux ni d'emoji décoratif (voir les anti-patterns de `DESIGN.md`).

## 6. Sobriété de consommation

- Lire uniquement les fichiers utiles à la tâche. Chercher (`grep`, recherche de symboles) avant de lire un fichier en entier.
- Borner les sorties de commandes (`head`, `tail`, `--quiet`). Ne pas recoller des logs entiers.
- Ne pas refaire une exploration déjà faite dans la session. Garder les réponses courtes : statut, ce qui marche, ce qui ne marche pas, suite.
- Découper les gros chantiers : une session par étape, état noté dans `.contexte.md` avant d'arrêter.

## 7. Qualité et Git

- Toute logique non triviale (branche, boucle, parseur, calcul, sécurité) a au moins un test. Lancer les tests avant de proposer un commit.
- **Avant de rendre la main** : l'agent compile, lance les tests et le linter, démarre l'app, lit les erreurs et les corrige lui-même. Christophe ne reçoit que du code qui compile et démarre. Commandes : partie « Spécifique au projet ». Si Christophe a déjà l'app ouverte, ne pas en lancer une deuxième instance ni la laisser tourner en arrière-plan : elle bloquerait la sienne.
- Commits petits et clairs, une branche par chantier.
- **Versions** : numérotation `MAJEUR.MINEUR.CORRECTIF` (SemVer), identique dans tous les fichiers qui la portent (`package.json`, `Cargo.toml`, `tauri.conf.json`, `manifest.json`…). À chaque lot stabilisé, fusionné et poussé : version incrémentée (avant 1.0.0, une nouvelle fonction incrémente le mineur, une correction le correctif), entrée dans `CHANGELOG.md` (ce qui change pour l'utilisateur, en français), tag Git annoté poussé `vX.Y.Z` (plugin Obsidian : `X.Y.Z` sans `v`, exigé par Obsidian). La version en cours figure dans la passation de `.contexte.md`.
- Dépôt GitHub **privé**. Jamais de visibilité publique sans demande explicite de Christophe.
- Aucun secret versionné (jeton, mot de passe, clé API, `.env`). Vérifier `git status` avant le premier push et avant chaque push suspect. En cas de fuite : alerter, ne pas réécrire l'historique sans accord.
- Valider aux frontières du système (entrées utilisateur, réseau, fichiers). Ne pas détruire de données sans confirmation.

## 8. Fin de session

- Mettre à jour `.contexte.md` : ce qui est fait, décisions prises, prochaine étape. Cocher les tâches Operon terminées via le skill `operon-tasks`.
- Dire ce qui a été sauté ou non vérifié, et tout risque connu.
- Livraison d'une version : skill `livrer-version-vibecoding` du second brain.

---

## Spécifique au projet

### Vue d'ensemble

Suivi d'un stock de pellets de bois dans Home Assistant. `pellets/` est une app HA (FastAPI + SQLite, interface web par Ingress, API REST sur le port 8234). `custom_components/pellets/` est l'intégration HA (HACS) qui lit l'API et expose capteurs, alerte stock bas et bouton de déstockage. Dépôt public sur demande explicite de Christophe (2026-11-14).

### Conventions

| Élément | Convention |
|---|---|
| Langage | Python 3.12 (app), Python de HA (intégration). Écart à la stack par défaut : reprise de l'app FastAPI existante |
| Style | ruff (`pellets/pyproject.toml`) |
| Tests | pytest : `pellets/tests/` pour l'app, `tests/` pour l'intégration |
| Commits | anglais, préfixe conventionnel (`feat:`, `fix:`, `chore:`) |
| Version | identique dans `pellets/config.yaml`, `pellets/pyproject.toml`, `pellets/app/__init__.py`, `custom_components/pellets/manifest.json` |

### Commandes

```bash
# App
cd pellets && uv sync --extra dev && uv run pytest && uv run ruff check .
uv run uvicorn app.main:app --port 8234          # lancer en local
docker build -t ha-pellets pellets               # image de l'app

# Intégration (venv à part avec pytest-homeassistant-custom-component)
python -m pytest                                 # depuis la racine du dépôt
```
