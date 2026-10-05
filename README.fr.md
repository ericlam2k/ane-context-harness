# ⚡ ane-context-harness

[Anglais](README.md) · [Vietnamien](README.vi.md) · [Chinois](README.zh.md) · [Français](README.fr.md) · [Espagnol](README.es.md) · [Japonais](README.ja.md) · [Coréen](README.ko.md)

> **Réduisez de 60%+ le contexte lu par votre agent, conservez chaque ligne indispensable, et sélectionnez le contexte en moins de 4ms — entièrement hors ligne sur votre machine locale.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## Qu'est-ce que c'est ?

Lorsque vous vibe-codez ou lancez des agents IA (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), envoyer l'intégralité de votre dépôt dans la fenêtre de contexte d'un LLM est **lent, gaspilleur et dangereux** :
- **Contexte gonflé :** Balancer des fichiers entiers à chaque tour noie le modèle sous du boilerplate hors sujet — et le fournisseur compte chaque jeton, réutilisé ou non.
- **Réponses plus lentes :** Le time-to-first-token du LLM s'effondre quand il préremplit des milliers de lignes inutiles.
- **Perdu au milieu :** Les modèles hallucinent ou ratent des bugs lorsqu'ils sont ensevelis sous du boilerplate hors sujet.
- **Fuites de secrets :** Envoyer sans le vouloir des secrets `.env` ou des identifiants AWS à des fournisseurs de modèles tiers.

**ane-context-harness** est un moteur de contexte léger, local-first, qui s'intercale entre votre dépôt et votre agent de code. En **~3 milliseconds**, il indexe votre dépôt, extrait les hiérarchies de symboles (fonctions, interfaces, types), élimine le bruit, masque les secrets, et packe uniquement les preuves de code à haute valeur dont votre agent a réellement besoin pour terminer la tâche.

> Le nom `ane` est historique ; ce n'est **pas** une dépendance. Le chemin livré est du CPU pur et fonctionne sur macOS Apple Silicon, macOS Intel et Linux. L'accélération matérielle vit dans une distribution privée séparée.

Zéro appel réseau externe. 100% privé et hors ligne.

---

## Résultats de benchmark réels

Évalué sur **30 tâches de benchmark** (10 petites, 10 typiques, 10 difficiles) à travers des dépôts Python et TypeScript synthétiques sur notre split d'évaluation figé (`benchmarks/splits.json`) :

| Métrique | Sans harness (dump complet du dépôt) | Avec harness (déterministe) | Ce que cela signifie pour vous |
|---|---|---|---|
| **Jetons de contexte médians** | **3,213 tokens** | **782 tokens** | **Envoie 60.47% de moins au LLM** |
| **Rappel des preuves requises** | 1.0 (100%) | **1.0 (100%)** | **N'a jamais manqué le moindre morceau de code critique** |
| **Vitesse de sélection du contexte** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Réponse locale sous 4ms — 100x plus rapide que le réseau** |
| **Économie maximale de jetons** | 0% | **Up to 90.32%** | **Économise jusqu'à ~90% sur les tâches ciblées de config et de paramètres** |
| **Précision du classement (nDCG@10)**| n/a | **0.849** | **Place les fonctions les plus critiques tout en haut** |
| **Masquage des secrets** | 0% (leaks all secrets) | **100% local redaction** | **Les `.env`, clés AWS et certificats ne quittent jamais votre machine** |
| **Coût dérivé par tâche** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **Envoie ~75% de moins par tâche au tarif indiqué — votre facture, elle, évolue selon ce que le fournisseur réutilise au lieu de relire** |

*(Latence et mémoire mesurées localement sur Apple Silicon / CPU ; les chiffres de coût et de TTFT sont dérivés aux tarifs de jetons indiqués ; méthodologie et journaux reproductibles dans `benchmarks/reports/` et `benchmarks/logs/`).*

### Détail des tâches d'exemple

| Type de tâche | Tâche d'exemple | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **Paramètres et config** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Règles et logique** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Corrections de bugs (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **Architecture TypeScript**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Panier complexe multi-fichiers** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Économies de jetons, mesurées (main actuel)

![Baseline par tâche vs jetons envoyés avec rappel min 1.0, plus médianes de format de pack identique (JSON / markdown / compact)](docs/token-savings.png)

Mesuré avec les fonctions publiques uniquement (`scripts/measure_token_savings.py`, split d'éval figé, un compteur épinglé — reproduisez avec `PYTHONPATH=src python3 scripts/measure_token_savings.py`, tracez avec `scripts/plot_token_savings.py`). Mêmes preuves, trois rendus ; le rendu ne touche jamais la sélection.

### Le même exercice face à de vrais outils (pas de clés, pas de comptes)

![Médianes de sélection et médianes de format de pack identique : harness select vs réécriture headroom vs evidence-JSON / markdown / vrai TOON / compact](docs/same-exercise-comparison.png)

Le test en passthrough que n'importe quel rival peut lancer : 18 tâches d'éval, un compteur. Headroom 0.39.1 et le vrai encodeur TOON s'exécutent en local (`pip install headroom-ai toon-format`, puis `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, tracez avec `scripts/plot_same_exercise.py`). La réécriture aveugle à la tâche envoie plus que la sélection et n'a aucune porte de survie ; le vrai TOON retombe sur des mappings par ligne pour le code multiligne, tandis que notre compact conserve les en-têtes CSV avec des lignes verbatim.

---

## Pourquoi les développeurs et vibecoders l'adorent

- 💰 **Moins de contexte par tâche, sortie stable :** Ignorez les fichiers sans rapport avec le prompt — et une sortie stable permet au fournisseur de réutiliser ce qu'il a déjà lu au lieu de facturer à nouveau. Cut% mesure la réduction locale de contexte, jamais votre facture.
- ⚡ **Latence instantanée (~3ms) :** S'exécute entièrement en Python natif et extensions C, en local sur votre Mac ou votre machine Linux.
- 🎯 **Précision chirurgicale :** Combine les déclarations de symboles AST (classes, interfaces TypeScript, enums, fonctions) avec une recherche lexicale BM25 et un packing score-first borné par un budget de jetons.
- 🛡️ **Sanitisation des secrets zéro fuite :** Scanne et masque automatiquement les clés AWS, clés privées RSA/PEM, fichiers `.env` et secrets à haute entropie avec des placeholders stables scoped à la requête, avant le rendu des prompts.
- 🔌 **Support universel des agents :** Livré avec des adaptateurs prêts à l'emploi pour **Anthropic Messages** (avec breakpoints de prompt-caching), **OpenAI Responses**, chat **OpenAI-Compatible**, et du **Markdown** propre.

---

## Comment ça marche

![Vue d'ensemble du packing de contexte : ce que le LLM reçoit, comment les tâches se réécrivent en termes, règles keep/drop, dictionnaire de raisons, limites de packing, historique](docs/context-packing-overview.png)

Poster d'une page généré depuis le vrai pipeline (`scripts/plot_packing_overview.py`) : les mots de la tâche se réécrivent en termes scorés, les pins obligatoires passent toujours, les cartes discrétionnaires packent score-first sous budget, chaque carte conservée porte les raisons que vous pouvez contester. Le pourcentage dit de combien nous envoyons moins que tout ce que nous pourrions envoyer — votre facture, elle, évolue selon ce que le fournisseur réutilise au lieu de relire.

---

## Démarrage rapide (60 Seconds)

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

### 1b. Setup en une commande + prove-it (gates d'adoption)

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` n'est pas labellisé : il rapporte la réduction médiane + la latence p50 et
`recall: not_applicable`. Les preuves de rappel exigent des tâches labellisées à la main (la
machinerie figée `benchmarks/splits.json`) ; les runs non labellisés ne revendiquent jamais
de rappel.

### 2. Indexez votre dépôt

Indexez n'importe quel dossier ou dépôt local dans le store SQLite local (incrémental et super rapide) :

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. Sélectionnez le contexte pertinent pour un prompt

Récupérez un package Markdown compact, borné en jetons, adapté à votre tâche de code :

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. Journalisez les coupes de contexte avant/après sur de nombreux prompts (`update`)

Lancez la sélection sur un lot de tâches (un fichier JSONL ou stdin) et affichez + journalisez
les budgets de jetons avant/après. Local, pas de réseau :

```bash
# from a JSONL file (one {"task": "..."} or bare task per line)
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

Exemple de sortie :

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

Les lignes par tâche sont aussi ajoutées en JSONL dans `--log` (gitignored).
**Caveat honnête** imprimé sur stderr à chaque run : *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

Chaque run imprime aussi un pied de coupe d'une ligne sur stderr (et la même
ligne comme clé `summary` du JSON stdout), p. ex.
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Des mots simples uniquement —
pas de jargon, pas de balisage de titre `#`. Les totaux s'accumulent en local (compteurs uniquement, pas de
texte de tâche) — consultez-les
à tout moment avec `ane-harness daily`, ou à chaque sortie de shell avec
`eval "$(ane-harness shell-init)"` dans votre `.zshrc`/`.bashrc`.

Les agents obtiennent le même comportement sans dépendance via le skill bundlé :
`skills/ane-harness/SKILL.md` — copiez-le dans le répertoire de skills de votre agent
et les totaux de coupe apparaissent automatiquement après chaque tâche, sans autre setup. Pour
les hôtes compatibles OpenCode/Claude/agent, cela fonctionne aussi globalement, sans install par projet :
`~/.config/opencode/skills/`, `~/.claude/skills/`, ou
`~/.agents/skills/` (les nouvelles sessions le prennent en compte).

### 3c. Mode proxy pour les agents sans intégration native (`proxy`)

Pipez les tâches sur stdin (une `{"task": "..."}` ou une tâche brute par ligne),
récupérez le Markdown de preuves sur stdout — pas de skill, MCP, ni HTTP nécessaire :

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout est du Markdown pur (un doc par tâche, séparé par `---`, avec
des bornes `<!-- ane-harness task N/M ... -->`) ; les pieds de coupe
par tâche vont sur stderr. Omettez `--repo` lorsque le repo-id est déjà indexé.

### 4. Ou lancez-le comme serveur local en arrière-plan

> **Agents : ne lancez PAS ceci dans un tour d'agent.** `serve` (comme `mcp`)
> ne se termine jamais — un appel d'outil qui le lance bloque indéfiniment, donc le tour
> ne se termine jamais et chaque prompt suivant s'empile derrière. Un `update`/`proxy`
> nu sans `--tasks-file` sur un terminal interactif quitte
> avec le code 2 et un indice, au lieu d'attendre sur stdin. Dans les tours d'agent, n'utilisez que
> des commandes one-shot (`index`, `select`, `prove`, `daily`, `health`). Lancez
> le serveur détaché depuis un vrai terminal
> (`nohup ane-harness serve --port 8765 &`) ou pas du tout.

Démarrez l'API HTTP locale (prête à être branchée sur votre agent ou vos outils) :

```bash
ane-harness serve --port 8765
```

Endpoints disponibles :
- `GET  /v1/health` — Statut système, mode de calcul et profils
- `POST /v1/repositories/index` — Indexer ou mettre à jour un dépôt
- `POST /v1/context/select` — Récupérer le contexte optimisé pour une tâche
- `POST /v1/context/compress-output` — Compresser les logs verbeux de tests/build en digests d'échec propres

---

## Utilisation en Python

Vous pouvez aussi utiliser le harness directement dans vos propres workflows d'agents IA :

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. Initialize pipeline
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. Index repository
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. Select budgeted context
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. Serialize directly for your favorite LLM provider
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Packed {package.metrics['selected_tokens']} tokens (cut {package.metrics['tokens_removed']} tokens)")
```

---

## Comment ça fonctionne

```
                        Your Codebase
                             │
                     AST & Symbol Parser
               (Python functions, TS interfaces)
                             │
                      Line-Level Chunker
                             │
                      Local SQLite Store
                             │
User Prompt  ──────►   BM25 Lexical Search
                             │
                   Score-First Budget Packer
                  (Mandatory Retention + MMR)
                             │
                  Local Secret Sanitizer
              (Redacts .env, AWS keys, certs)
                             │
               Provider Adapter (Anthropic/OpenAI)
                             │
                   Tight, Accurate Context
```

1. **Chunking AST conscient des symboles :** Au lieu d'un découpage bête par lignes, les fichiers sont parsés pour de vrais construits de code (classes, méthodes, types/interfaces/enums TypeScript).
2. **Récupération déterministe :** Récupération lexicale BM25 rapide, filtrée par des gardes de termes de symboles, un découpage en sous-tokens, et un repli des pluriels.
3. **Packing de budget score-first :** Le contexte est packé de façon gloutonne pour tenir strictement dans votre budget de jetons (p. ex. 1,200 jetons), en garantissant que les preuves obligatoires ne sont jamais tronquées.
4. **Détection de secrets et barrière de confidentialité :** Les motifs d'exclusion canoniques (`.env*`, `.aws/**`, `*.pem`, etc.) ne sont jamais lus, et des classifieurs regex + entropie remplacent les jetons sensibles par des placeholders stables.
5. **Compression du bruit :** Les sorties d'outils verbeuses (traces de tests, logs de terminal) sont repliées en digests compacts qui préservent le signal.

### Accélération matérielle : distribution privée séparée

Le nom contient `ane`, mais **aucun silicium spécialisé n'est requis ni revendiqué** pour
faire tourner le harness. Le moteur livré est du CPU déterministe pur (Python +
SQLite) et fonctionne à l'identique sur macOS Apple Silicon, macOS Intel et Linux.
L'accélération neural-hardware est maintenue séparément et ne fait pas partie de
ce dépôt.

---

## Spécifications techniques et rigueur

Pour les chercheurs, architectes et responsables techniques qui tiennent à la rigueur numérique :

- **Split de benchmark figé :** Tous les chiffres de release tournent sur un split d'évaluation figé de 18 tâches (`benchmarks/splits.json`, seed `20261002`). Le tuning est strictement quarantiné sur le split de dev.
- **Estimateur de jetons déterministe :** Le comptage de jetons utilise un estimateur épinglé (`TOKEN_ESTIMATOR_VERSION="2"`) afin que les chiffres soient 100% reproductibles d'une machine et d'une version de Python à l'autre, sans dérive de tokenizer externe.
- **Politique d'embeddings :** Les embeddings sont volontairement exclus en v0.1 d'après les compromis coût/latence locaux. Voir [ADR-002](docs/adr-002-embedding-go-no-go.md).
- **Bundle de preuves de release :** Les preuves de release checksummées sont vérifiées cryptographiquement via `ane-harness evidence verify ane-context-harness-evidence-v0.1`.

---

## Lancer la suite de tests

```bash
# Run all 258 unit, integration, and security tests
python3 -m pytest -q

# Run concurrent A/B benchmark evaluation
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## Licence

Licence MIT. Conçu pour l'intelligence locale, la vie privée des développeurs, et des budgets de jetons sains.