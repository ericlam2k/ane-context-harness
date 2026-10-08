# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **Réduisez de plus de 60% le contexte lu par votre agent, conservez chaque ligne de code essentielle et sélectionnez le contexte en moins de 4 ms — le tout 100% hors ligne sur votre machine locale.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-265%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## De quoi s'agit-il ?

Lorsque vous faites du vibe-coding ou utilisez des agents IA (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), injecter l'intégralité de votre codebase dans la fenêtre de contexte d'un LLM est **lent, coûteux et risqué** :
- **Surcharge de contexte :** Envoyer des fichiers entiers à chaque échange noie le modèle sous du code répétitif (boilerplate) — et le fournisseur facture chaque token, réutilisé ou non.
- **Réponses plus lentes :** Le temps de réaction initial du modèle (LLM time-to-first-token) augmente lors du pré-remplissage (prefill) de milliers de lignes inutiles.
- **Phénomène du "Lost in the Middle" :** Les modèles risquent d'halluciner ou de manquer des bugs lorsqu'ils sont submergés d'informations irrelevantes.
- **Fuites de secrets :** Envoi involontaire de variables d'environnement (`.env`) ou d'identifiants AWS à des fournisseurs tiers.

**ane-context-harness** est un moteur de contexte léger et *local-first* qui s'intercale entre votre codebase et votre agent de codage. En **~3 millisecondes**, il indexe votre dépôt, extrait les hiérarchies de symboles (fonctions, interfaces, types), élimine le bruit, masquez les secrets (redaction) et ne conserve que les preuves de code indispensables à l'accomplissement de la tâche.

> Le nom `ane` est historique ; ce n'est **pas** une dépendance. Le moteur fourni fonctionne exclusivement sur CPU sous macOS (Apple Silicon & Intel) et Linux. L'accélération matérielle est réservée à une distribution privée distincte.

Zéro appel réseau externe. 100% privé et exécuté hors ligne.

![Illustration conceptuelle : la troncature brute casse les AST, les imports et les références — le harness garde les signatures, la structure AST et les dépendances essentielles](docs/ane-concept-generic.jpg)

*Illustration conceptuelle — le code dans l'image est un visuel, pas une vraie trace.*


---

## Résultats de Benchmark Réels

Évalué sur **30 tâches de benchmark** (10 simples, 10 standard, 10 complexes) sur des codebases Python et TypeScript issues de notre jeu d'évaluation fixe (`benchmarks/splits.json`) :

| Métrique | Sans Harness (Dump complet du repo) | Avec Harness (Déterministe) | Ce que cela change pour vous |
|---|---|---|---|
| **Tokens de contexte (Médiane)** | **3 213 tokens** | **782 tokens** | **Envoie 60,47% de tokens en moins au LLM** |
| **Rappel des preuves requises (Recall)** | 1,0 (100%) | **1,0 (100%)** | **Aucun élément de code critique n'a été omis** |
| **Vitesse de sélection du contexte** | ~0,01 ms (raw dump) | **3,05 ms – 3,83 ms** | **Réponse locale sous 4 ms — 100x plus rapide que le réseau** |
| **Économie maximale de tokens** | 0% | **Jusqu'à 90,32%** | **Économise jusqu'à ~90% sur les tâches de configuration** |
| **Précision de classement (nDCG@10)**| n/a | **0,849** | **Place les fonctions les plus critiques en tête de contexte** |
| **Masquage des secrets (Redaction)** | 0% (fuite intégrale) | **Masquage local à 100%** | **Les fichiers `.env`, clés AWS et certificats ne quittent jamais votre machine** |
| **Coût dérivé par tâche** *(à 3$/M)* | ~$0,0096 / tâche | **~$0,0023 / tâche** | **Envoie ~75% de données en moins par tâche — votre facture varie selon la réutilisation du contexte par le fournisseur** |

*(Latence et mémoire mesurées localement sur Apple Silicon / CPU ; coûts et TTFT calculés sur la base des tarifs au token indiqués ; méthodologie et logs disponibles dans `benchmarks/reports/` et `benchmarks/logs/`).*

![Illustration conceptuelle : comparer les approches de récupération de contexte sur une même échelle](docs/ane-benchmark-concept.jpg)

*Illustration conceptuelle, pas un résultat mesuré — l'échelle des tokens et les chiffres de l'image sont illustratifs. Toutes les vraies mesures sont dans le tableau ci-dessus.*


---

## Démarrage Rapide (60 secondes)

### 1. Cài đặt

Nécessite Python 3.13 ou 3.14 sous macOS ou Linux :

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

Vérifier l'installation :
```bash
ane-harness health
```

### 1b. Configuration automatique et vérification

```bash
# Indexation, installation du skill agent et test rapide
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# Vérification des réductions et de la latence sur VOTRE dépôt
ane-harness prove --repo /path/to/your/project --repo-id my-project
```

### 2. Indexer votre Codebase

Indexez n'importe quel dossier local dans une base SQLite locale (incrémentiel et ultra-rapide) :

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. Sélectionner le Contexte Pertinent

Générez un payload Markdown compact adapté à votre budget de tokens :

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

### 4. Lancer le Serveur HTTP Local

Démarrer l'API HTTP locale pour la connecter à vos agents ou outils :

```bash
ane-harness serve --port 8765
```

![Illustration conceptuelle : prompt système et payload à travers le filtre vers un payload propre — le pipeline de filtrage du harness](docs/ane-proxy-tracker-concept.jpg)

*Illustration conceptuelle — le tableau de bord dans l'image est un visuel, pas une capture d'un vrai outil.*


---

## Utilisation dans SDK Python

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. Initialiser le pipeline
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. Enregistrer le dépôt
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. Sélectionner le contexte selon le budget
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. Sérialiser pour votre fournisseur de LLM
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Packed {package.metrics['selected_tokens']} tokens (cut {package.metrics['tokens_removed']} tokens)")
```

---


![Illustration conceptuelle : baseline lourde contre harness léger — moins de tokens, précision intacte](docs/ane-concept-dashboard.jpg)

*Figure récapitulative mesurée — médianes issues de `benchmarks/reports/phase5-ab-evaluation.json` (frozen eval split, 18 tâches, Arm B deterministic) : 3 213 → 782 tokens (réduction de 60,47 %), min required recall 1,0.*

## Licence

Licence MIT. Conçu pour l'intelligence locale, la confidentialité des développeurs et le contrôle rigoureux des budgets de tokens.
