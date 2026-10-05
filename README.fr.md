# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **Réduisez le contexte lu par votre agent de plus de 60 %, conservez chaque ligne requise et sélectionnez le contexte en moins de 4 ms — le tout exécuté entièrement hors-ligne sur votre machine locale.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## Qu'est-ce que c'est ?

Lorsque vous faites du "vibe-coding" ou utilisez des agents IA (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), injecter l'intégralité de votre base de code dans la fenêtre de contexte d'un LLM est **lent, inefficace et dangereux** :
- **Contexte surchargé :** Envoyer des fichiers entiers à chaque requête noie le modèle sous du code répétitif (boilerplate) inutile — et le fournisseur facture chaque jeton, qu'il soit réutilisé ou non.
- **Réponses plus lentes :** Le temps d'obtention du premier jeton (TTFT) du LLM devient interminable lorsqu'il doit traiter des milliers de lignes inutiles.
- **Perdu au milieu :** Les modèles peuvent halluciner ou manquer des bugs lorsqu'ils sont submergés par du code superflu.
- **Fuites de secrets :** Envoyer involontairement des secrets `.env` ou des identifiants AWS à des fournisseurs de modèles tiers.

**ane-context-harness** est un moteur de contexte léger et local qui se place entre votre base de code et votre agent de codage. En **~3 millisecondes**, il indexe votre dépôt, extrait les hiérarchies de symboles (fonctions, interfaces, types), élimine le bruit, caviarde les secrets et ne transmet que les preuves de code essentielles dont votre agent a réellement besoin pour accomplir la tâche.

> Le nom `ane` est historique ; ce n'est **pas** une dépendance. La version fournie est purement CPU et fonctionne sur macOS Apple Silicon, macOS Intel et Linux. L'accélération matérielle fait l'objet d'une distribution privée séparée.

Aucun appel réseau externe. 100 % privé et hors-ligne.

---

## Résultats des benchmarks réels

Évalué sur **30 tâches de référence** (10 petites, 10 typiques, 10 difficiles) à travers des bases de code synthétiques Python et TypeScript sur notre jeu d'évaluation figé (`benchmarks/splits.json`) :

| Métrique | Sans Harness (Vidage complet du repo) | Avec Harness (Déterministe) | Ce que cela signifie pour vous |
|---|---|---|---|
| **Jetons de contexte médians** | **3 213 jetons** | **782 jetons** | **Envoie 60,47 % de moins au LLM** |
| **Rappel des preuves requises** | 1,0 (100 %) | **1,0 (100 %)** | **N'a jamais manqué une seule ligne de code critique** |
| **Vitesse de sélection du contexte** | ~0,01 ms (vidage brut) | **3,05 ms – 3,83 ms** | **Réponse locale sous les 4ms — 100x plus rapide que le réseau** |
| **Économies de jetons maximales** | 0 % | **Jusqu'à 90,32 %** | **Économise jusqu'à ~90 % sur les tâches de configuration** |
| **Précision du classement (nDCG@10)**| n/a | **0,849** | **Place les fonctions critiques tout en haut** |
| **Caviardage de secrets** | 0 % (fuit tous les secrets) | **100 % caviardage local** | **Les `.env`, clés AWS et certificats ne quittent jamais votre machine** |
| **Coût dérivé par tâche** *(à 3 $/M)* | ~0,0096 $ / tâche | **~0,0023 $ / tâche** | **Envoie ~75 % de moins par tâche au tarif indiqué — votre facture varie selon la réutilisation du modèle plutôt que sa relecture** |

*(Latence et mémoire mesurées localement sur Apple Silicon / CPU ; les chiffres de coût et de TTFT sont dérivés selon des tarifs de jetons spécifiques ; méthodologie et journaux reproductibles dans `benchmarks/reports/` et `benchmarks/logs/`).*

### Analyse des tâches d'exemple

| Type de tâche | Tâche exemple | Jetons bruts | Jetons Harness | Réduction | Rappel | Latence sélect. |
|---|---|---|---|---|---|---|
| **Réglages & Config** | `hard-settings-001` | 3 213 | **311** | **90,32 %** | **100 %** | 3,88 ms |
| **Règles & Logique** | `hard-rules-vs-readme-001` | 3 213 | **445** | **86,15 %** | **100 %** | 4,22 ms |
| **Correction de bugs (Python)** | `py-discount-report-001` | 3 189 | **629** | **80,28 %** | **100 %** | 3,72 ms |
| **Architecture TypeScript**| `ts-discount-001` | 1 236 | **369** | **70,15 %** | **100 %** | 1,84 ms |
| **Panier multi-fichiers complexe** | `hard-cart-apply-001` | 3 213 | **2 146** | **33,21 %** | **100 %** | 4,38 ms |

### Économies de jetons mesurées (main actuel)

![Baseline par tâche vs jetons envoyés avec rappel min 1.0, plus médianes des formats identiques (JSON / markdown / compact)](docs/token-savings.png)

Mesuré avec les fonctions publiques uniquement (`scripts/measure_token_savings.py`, jeu d'évaluation figé, un compteur épinglé — reproduire avec `PYTHONPATH=src python3 scripts/measure_token_savings.py`, tracer avec `scripts/plot_token_savings.py`). Même preuve, trois rendus ; le rendu ne touche jamais à la sélection.

### Comparaison avec des outils réels (sans clés, sans comptes)

![Médianes de sélection et médianes des formats identiques : sélection harness vs réécriture headroom vs preuve JSON / markdown / vrai TOON / compact](docs/same-exercise-comparison.png)

Le test de passage que tout rival peut exécuter : 18 tâches d'évaluation, un compteur. Headroom 0.39.1 et l'encodeur TOON réel fonctionnent localement (`pip install headroom-ai toon-format`, puis `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, tracer avec `scripts/plot_same_exercise.py`). La réécriture aveugle aux tâches envoie plus que la sélection et n'a pas de porte de survie ; le TOON réel revient à des mappages par ligne sur du code multiligne, tandis que notre format compact conserve les en-têtes CSV avec les lignes textuelles.

---

## Pourquoi les développeurs l'adorent

- 💰 **Moins de contexte par tâche, sortie stable :** Ignorez les fichiers qui n'ont aucun rapport avec le prompt — une sortie stable permet au fournisseur de réutiliser ce qu'il a déjà lu au lieu de facturer à nouveau. La réduction de contexte locale ne dépend jamais de votre facture.
- ⚡ **Latence instantanée (~3ms) :** S'exécute entièrement en Python natif et extensions C localement sur votre Mac ou machine Linux.
- 🎯 **Précision extrême :** Combine les déclarations de symboles AST (classes, interfaces TypeScript, énumérations, fonctions) avec une recherche lexicale BM25 et un empaquetage basé sur un score selon un budget de jetons.
- 🛡️ **Assainissement des secrets sans fuite :** Analyse et caviarde automatiquement les clés AWS, clés privées RSA/PEM, fichiers `.env` et secrets à haute entropie avec des espaces réservés stables avant le rendu des prompts.
- 🔌 **Support universel des agents :** Fournit des adaptateurs prêts à l'emploi pour **Anthropic Messages** (avec points d'arrêt de mise en cache), **OpenAI Responses**, **OpenAI-Compatible chat** et **Markdown** propre.

---

## Comment ça marche

![Vue d'ensemble de l'empaquetage de contexte : ce que le LLM reçoit, comment les tâches réécrivent en termes, règles de conservation/suppression, dictionnaire de raisons, limites d'empaquetage, historique](docs/context-packing-overview.png)

Affiche générée à partir du pipeline réel (`scripts/plot_packing_overview.py`) : les mots de la tâche sont réécrits en termes pondérés, les éléments obligatoires sont toujours inclus, les éléments discrétionnaires sont empilés par score sous le budget, et chaque élément conservé comporte les raisons justifiant sa présence. Le pourcentage indique combien nous envoyons de moins par rapport à tout ce que nous pourrions envoyer — votre facture varie selon la réutilisation du modèle plutôt que sa relecture.

---

## Démarrage rapide (60 secondes)

### 1. Installation

Nécessite Python 3.13 ou 3.14 sur macOS ou Linux :

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

Vérifiez votre installation :
```bash
ane-harness health
```

### 1b. Configuration en une commande + preuve (portes d'adoption)

```bash
# indexer, installer la compétence agent, test rapide (imprime une ligne de résumé)
ane-harness setup --repo /chemin/vers/votre/projet --repo-id mon-projet --yes

# preuve : preuve de réduction/latence sur VOTRE repo (5 tâches, sans étiquettes)
ane-harness prove --repo /chemin/vers/votre/projet --repo-id mon-projet
# avec vos propres tâches : --tasks-file prompts.jsonl
# avec un répertoire de rapport : --out /tmp/prove-report
```

`prove` est sans étiquette : il rapporte la réduction médiane + la latence p50 et
`recall: not_applicable`. Les preuves de rappel nécessitent des tâches étiquetées manuellement (le mécanisme figé `benchmarks/splits.json`) ; les exécutions non étiquetées ne prétendent jamais au rappel.

### 2. Indexez votre base de code

Indexez n'importe quel dossier ou dépôt local dans le magasin SQLite local (incrémental et ultra-rapide) :

```bash
ane-harness index --repo /chemin/vers/votre/projet --repo-id mon-projet
```

### 3. Sélectionnez le contexte pertinent pour un prompt

Récupérez un paquet Markdown compact, budgétisé en jetons et adapté à votre tâche de codage :

```bash
ane-harness select \
  --repo-id mon-projet \
  --task "Corriger le bug de calcul de remise dans le checkout" \
  --budget 1200
```

### 3b. Journalisez les réductions de contexte avant/après sur plusieurs prompts (`update`)

Exécutez la sélection sur un lot de tâches (fichier JSONL ou stdin) et imprimez + journalisez
les budgets de jetons avant/après. Local, sans réseau :

```bash
# depuis un fichier JSONL (un {"task": "..."} ou une tâche brute par ligne)
ane-harness update \
  --repo-id mon-projet \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

Sortie exemple :

```
repo_id: mon-projet | tasks: 3 | budget: 2000

  task                              avant   après   supprimé  réduction
  Fix the discount calculation      3189    1952    1237       38.79%
  debug the inventory loader        3189    1758    1431       44.87%
  review reporting stats output     3189    1261    1928       60.46%

  TOTAL: avant 9567 → après 4971 jetons (4596 supprimés, réduction médiane 44.87%)
```

Les lignes par tâche sont également ajoutées en JSONL dans `--log` (gitignored).
**Avertissement honnête** imprimé sur stderr à chaque exécution : *"mesures locales sur le dépôt donné ; le caviardage ne garantit pas que tous les secrets sont détectés."*

Chaque exécution imprime également un pied de page de coupe d'une ligne sur stderr (et la même
ligne que la clé `summary` dans le JSON de stdout), ex.
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Mots simples seulement —
pas de jargon, pas de balisage d'en-tête `#`. Les totaux s'accumulent localement (comptages uniquement, pas de texte de tâche) — consultez-les
à tout moment avec `ane-harness daily`, ou à chaque sortie de shell avec
`eval "$(ane-harness shell-init)"` dans votre `.zshrc`/`.bashrc`.

Les agents obtiennent le même comportement sans dépendance via la compétence fournie :
`skills/ane-harness/SKILL.md` — copiez-le dans le répertoire de compétences de votre agent
et les totaux de réduction apparaîtront automatiquement après chaque tâche, sans autre configuration. Pour
OpenCode/Claude/hôtes compatibles, cela fonctionne aussi globalement, sans installation par projet : `~/.config/opencode/skills/`, `~/.claude/skills/`, ou
`~/.agents/skills/` (les nouvelles sessions le détectent).

### 3c. Mode proxy pour agents sans intégration native (`proxy`)

Pipez les tâches dans stdin (un `{"task": "..."}` ou une tâche brute par ligne),
récupérez le Markdown des preuves sur stdout — sans compétence, MCP ou HTTP requis :

```bash
printf '%s\n' '{"task": "Corriger le bug de remise"}' 'revoir le chargeur d'inventaire' \
  | ane-harness proxy --repo /chemin/vers/votre/projet --repo-id mon-projet --budget 2000 \
  > context.md
```

Stdout est du Markdown pur (un doc par tâche, séparé par `---`, avec
des frontières `<!-- ane-harness task N/M ... -->`) ; les pieds de page de coupe
par tâche vont sur stderr. Omettez `--repo` lorsque le repo-id est déjà indexé.

### 4. Ou exécutez comme serveur d'arrière-plan local

> **Agents : n'exécutez PAS ceci à l'intérieur d'un tour d'agent.** `serve` (comme `mcp`)
> ne s'arrête jamais — un appel d'outil qui le lance bloquerait indéfiniment, donc le tour
> ne se terminerait jamais et chaque prompt suivant serait mis en file d'attente. `update`/`proxy` sans `--tasks-file` sur un terminal interactif se terminent avec un code 2 et un indice au lieu d'attendre sur stdin. À l'intérieur des tours d'agent, utilisez uniquement des commandes one-shot (`index`, `select`, `prove`, `daily`, `health`). Exécutez le serveur détaché d'un terminal réel
> (`nohup ane-harness serve --port 8765 &`) ou pas du tout.

Démarrez l'API HTTP locale (prête à être connectée à votre agent ou vos outils) :

```bash
ane-harness serve --port 8765
```

Endpoints disponibles :
- `GET  /v1/health` — État du système, mode de calcul et profils
- `POST /v1/repositories/index` — Indexer ou mettre à jour un dépôt
- `POST /v1/context/select` — Récupérer le contexte optimisé pour une tâche
- `POST /v1/context/compress-output` — Compresser des journaux verbeux de test/build en résumés d'échec propres

---

## Utilisation en Python

Vous pouvez également utiliser le harness directement dans vos propres flux de travail d'agent IA :

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. Initialiser le pipeline
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. Indexer le dépôt
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. Sélectionner le contexte budgétisé
request = SelectRequest(
    repository_id="my-repo",
    task="Mettre à jour la logique d'arrondi des points de fidélité dans le service de paiement",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. Sérialiser directement pour votre fournisseur LLM préféré
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Empaqueté {package.metrics['selected_tokens']} jetons (réduit de {package.metrics['tokens_removed']} jetons)")
```

---

## Comment ça marche

```
                        Votre base de code
                                │
                     Analyseur AST & Symboles
              (fonctions Python, interfaces TS)
                                │
                      Découpage par ligne
                                │
                      Magasin SQLite local
                                │
Prompt utilisateur ──────►  Recherche lexicale BM25
                                │
                Empaqueteur par score selon budget
                  (Rétention obligatoire + MMR)
                                │
                  Assainisseur de secrets local
              (Caviarde .env, clés AWS, certificats)
                                │
               Adaptateur fournisseur (Anthropic/OpenAI)
                                │
                   Contexte serré et précis
```

1. **Découpage AST conscient des symboles :** Au lieu d'un découpage bête par ligne, les fichiers sont analysés pour des constructions de code réelles (classes, méthodes, types/interfaces/enums TypeScript).
2. **Récupération déterministe :** Recherche lexicale BM25 rapide filtrée par garde de termes de symboles, découpage par sous-jetons et repliement du pluriel.
3. **Empaqueteur budgétaire par score :** Le contexte est empaqueté de manière gourmande pour s'insérer strictement dans votre budget de jetons spécifié (ex. 1 200 jetons), garantissant que les preuves obligatoires ne sont jamais tronquées.
4. **Détection de secrets et barrière de confidentialité :** Les modèles d'exclusion canoniques (`.env*`, `.aws/**`, `*.pem`, etc.) ne sont jamais lus, et les classificateurs regex + entropie remplacent les jetons sensibles par des espaces réservés stables.
5. **Compression du bruit :** Les sorties d'outils verbeuses (traces de test, journaux de terminal) sont réduites en résumés compacts préservant le signal.

### Accélération matérielle : distribution privée séparée

Le nom contient `ane`, mais **aucun silicium spécialisé n'est requis ou nécessaire** pour exécuter le harness. Le moteur fourni est purement déterministe sur CPU (Python + SQLite) et fonctionne identiquement sur macOS Apple Silicon, macOS Intel et Linux. L'accélération matérielle neuronale est maintenue séparément et ne fait pas partie de ce dépôt.

---

## Spécifications techniques et rigueur

Pour les chercheurs, architectes et responsables techniques attachés à la rigueur numérique :

- **Jeu de référence figé :** Tous les numéros de version sont exécutés sur un jeu d'évaluation figé de 18 tâches (`benchmarks/splits.json`, graine `20261002`). Le réglage est strictement mis en quarantaine sur le split de développement.
- **Estimateur de jetons déterministe :** Le comptage des jetons utilise un estimateur épinglé (`TOKEN_ESTIMATOR_VERSION="2"`) afin que les chiffres soient reproductibles à 100 % sur différentes machines et versions de Python sans dérive de tokeniseur externe.
- **Politique d'embeddings :** Les embeddings sont intentionnellement exclus dans la v0.1 en raison de compromis coût/latence locaux. Voir [ADR-002](docs/adr-002-embedding-go-no-go.md).
- **Bundle de preuves de version :** Les preuves de version avec checksum sont vérifiées cryptographiquement via `ane-harness evidence verify ane-context-harness-evidence-v0.1`.

---

## Exécution de la suite de tests

```bash
# Exécuter les 258 tests unitaires, d'intégration et de sécurité
python3 -m pytest -q

# Exécuter l'évaluation de benchmark A/B concurrente
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## Licence

Licence MIT. Conçu pour l'intelligence locale, la confidentialité des développeurs et des budgets de jetons sains.