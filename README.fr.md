# ⚡ ane-context-harness

[Anglais](README.md) · [Vietnamien](README.vi.md) · [Chinois](README.zh.md) · [Français](README.fr.md) · [Espagnol](README.es.md) · [Japonais](README.ja.md) · [Coréen](README.ko.md)

> **Réduisez de 60%+ le contexte lu par votre agent, conservez chaque ligne requise et sélectionnez le contexte en moins de 4ms — entièrement hors ligne, sur votre machine locale.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## Qu'est-ce que c'est ?

Quand vous vibe-codez ou lancez des agents IA (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), injecter l'intégralité de votre codebase dans la fenêtre de contexte d'un LLM est **lent, gaspilleur et dangereux** :
- **Contexte gonflé :** Envoyer des fichiers entiers à chaque tour noie le modèle sous du boilerplate hors sujet — et le fournisseur compte chaque token, réutilisé ou non.
- **Réponses plus lentes :** Le time-to-first-token du LLM s'effondre quand il préremplit des milliers de lignes inutiles.
- **Perdu au milieu :** Les modèles hallucinent ou ratent des bugs quand ils sont ensevelis sous du boilerplate hors sujet.
- **Fuites de secrets :** Envoi involontaire de secrets `.env` ou d'identifiants AWS à des fournisseurs de modèles tiers.

**ane-context-harness** est un moteur de contexte léger, local-first, qui s'intercale entre votre codebase et votre agent de coding. En **~3 milliseconds**, il indexe votre dépôt, extrait les hiérarchies de symboles (fonctions, interfaces, types), élimine le bruit, masque les secrets et n'empile que les preuves de code à haute valeur dont votre agent a réellement besoin pour terminer la tâche.

> Le nom `ane` est historique ; ce n'est **pas** une dépendance. Le chemin livré est du CPU pur et tourne sur macOS Apple Silicon, macOS Intel et Linux. L'accélération matérielle vit dans une distribution privée séparée.

Zéro appel réseau externe. 100 % privé et hors ligne.

---

## Résultats réels du benchmark

Évalué sur **30 benchmark tasks** (10 small, 10 typical, 10 difficult) à travers des codebases Python et TypeScript synthétiques, sur notre split d'évaluation figé (`benchmarks/splits.json`) :

| Métrique | Sans harness (dump complet du dépôt) | Avec harness (déterministe) | Ce que cela signifie pour vous |
|---|---|---|---|
| **Median Context Tokens** | **3,213 tokens** | **782 tokens** | **Sends 60.47% less to the LLM** |
| **Required-Evidence Recall** | 1.0 (100%) | **1.0 (100%)** | **Never missed a single piece of critical code** |
| **Context Selection Speed** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Sub-4ms local response — 100x faster than network** |
| **Peak Token Savings** | 0% | **Up to 90.32%** | **Saves up to ~90% on targeted config & settings tasks** |
| **Ranking Accuracy (nDCG@10)**| n/a | **0.849** | **Places the most critical functions right at the top** |
| **Secret Redaction** | 0% (leaks all secrets) | **100% local redaction** | **`.env`, AWS keys, and certificates never leave your machine** |
| **Derived Cost per Task** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **Sends ~75% less per task at the stated rate — your bill itself moves with how much the provider reuses instead of re-reading** |

*(Latence et mémoire mesurées localement sur Apple Silicon / CPU ; les chiffres de coût et de TTFT sont dérivés aux tarifs de tokens indiqués ; méthodologie et journaux reproductibles dans `benchmarks/reports/` et `benchmarks/logs/`).*

### Détail d'un échantillon de tâches

| Type de tâche | Exemple de tâche | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **Settings & Config** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Rules & Logic** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Bug Fixes (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript Architecture**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Complex Multi-file Cart** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Économies de tokens, mesurées (main actuelle)

Comment lire ce graphique : chaque job a demandé à l'outil « que l'IA devrait-elle lire pour cette tâche ? ». Le panneau de gauche compare, par taille de job, combien de texte vous enverriez si vous envoyiez toute la codebase (gris) versus ce que le harness a choisi (vert) — le nombre au-dessus de chaque barre verte est ce que vous envoyez maintenant et de combien c'est plus petit. Les jobs plus difficiles ont besoin de plus de fichiers, donc la barre verte grandit — mais les fichiers nécessaires ont été conservés **à chaque fois**, et c'est tout l'enjeu : plus petit n'est bon que si rien d'important ne manque. Le panneau de droite montre le même choix envoyé de trois façons — détail complet, un milieu lisible, et l'emballage le plus court — plus court est moins cher, et l'emballage ne change jamais *ce qui* est choisi.

![Moins à lire par taille de job, plus trois emballages de la même réponse](docs/token-savings.png)

Mesurez avec `PYTHONPATH=src python3 scripts/measure_token_savings.py`, tracez avec `scripts/plot_token_savings.py` (split d'éval figé, un compteur de tokens épinglé).

### Le même exercice face à de vrais outils (pas de clés, pas de comptes)

Comment lire ce graphique : c'est une course sur les mêmes 18 jobs avec la même règle — « combien de tokens contient le job du milieu, et quelque chose de nécessaire a-t-il été perdu ? ». Le premier graphique est le titre : tout envoyer est le défaut coûteux, l'outil de réécriture externe envoie en fait *plus* que nécessaire et a une fois perdu un fichier de config que le grader exigeait (marqué FAIL), tandis que nos deux modes sont les plus courts et ont conservé les fichiers nécessaires à chaque fois (PASS). Le second graphique montre les détails derrière — ce que la sélection seule économise, et comment la même sélection rétrécit encore rien qu'en choisissant un emballage plus court. PASS/FAIL ici signifie exactement une chose : les morceaux que le grader du benchmark dit requis sont revenus dans le pack.

![Les mêmes 18 jobs : tout-envoyer vs un outil de réécriture externe vs les nôtres](docs/head-to-head.png)

![Médianes de sélection et le même pack en quatre emballages, avec des exemples par job](docs/same-exercise-comparison.png)

Reproduisez : `pip install headroom-ai toon-format`, puis `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, tracez avec `scripts/plot_same_exercise.py`. La réécriture aveugle à la tâche envoie plus que la sélection et n'a aucune porte de survie ; le vrai encodeur TOON retombe sur des mappings par ligne sur du code multiligne tandis que notre compact garde les en-têtes CSV avec des lignes verbatim.

### Économies de conversation, mesurées

Comment lire ceci : un job n'est jamais une seule question — l'agent demande, puis relance, puis vérifie. Ce bench rejoue la même conversation en 3 tours par job de trois façons : envoyer toute la codebase à chaque tour (149,490 tokens), un pack réduit (17,094), et trois packs reportés où chaque suivi conserve tout ce que les tours précédents ont trouvé (51,940). La conversation reportée envoie **environ un tiers** du coût sans harness — 97,550 tokens de moins, 65.3% de moins — et les fichiers nécessaires ont survécu aux 72 tours (recall 1.0 à chaque tour ; un tour qui perd un fichier nécessaire fait dérailler la conversation, donc cette porte est structurelle, pas décorative).

Reproduisez : `PYTHONPATH=src python3 scripts/bench_conversation.py` (split d'éval figé, un compteur de tokens épinglé ; écrit `benchmarks/reports/conversation-bench-eval.json`). Limite, dite clairement : aucun modèle ne lit ces packs, les suivis sont des chaînes fixes plutôt que de vraies réactions d'agent, rien n'est facturé, aucun job n'est réellement terminé. Cela mesure la moitié que nous alimentons — le choix et le report — pas la boucle elle-même.

### Ce qui arrive à chaque fichier

Quatre règles documentées, aucun modèle impliqué, aucune exception : les fichiers que vous épinglez (ou que le grader exige) voyagent **octet pour octet, toujours**. Le code, la config et les diffs gardent leur structure — le sélecteur choisit des symboles entiers, ne les réécrit jamais. Seuls **les logs et les sorties d'outils bruyantes** sont compactés (lignes de progression répétées, tracebacks dupliqués, spam d'install se plient en une ligne de résumé qui dit ce qui a été retiré). La prose voyage telle que choisie, jamais reformulée — il n'y a pas de réécrivain neuronal, donc rien ne peut paraphraser vos docs en quelque chose qu'elles n'ont pas dit. Chaque pack liste, par fichier, quelle règle s'est appliquée — consultez `diagnostics.routing` dans n'importe quel rapport et discutez-en.

---

## Pourquoi les développeurs et les vibecoders l'adorent

- 💰 **Moins de contexte par tâche, sortie stable :** Ignorez les fichiers qui n'ont rien à voir avec le prompt — et une sortie stable permet au fournisseur de réutiliser ce qu'il a déjà lu au lieu de facturer à nouveau. Cut% mesure la réduction de contexte locale, jamais votre facture.
- ⚡ **Latence instantanée (~3ms) :** Tourne entièrement en Python natif et extensions C, localement sur votre Mac ou votre machine Linux.
- 🎯 **Précision chirurgicale :** Combine les déclarations de symboles AST (classes, interfaces TypeScript, enums, fonctions) avec la recherche lexicale BM25 et un packing score-first budgété en tokens.
- 🛡️ **Sanitisation des secrets zéro fuite :** Scanne et masque automatiquement les clés AWS, les clés privées RSA/PEM, les fichiers `.env` et les secrets à haute entropie avec des placeholders stables scopés à la requête, avant le rendu des prompts.
- 🔌 **Support universel des agents :** Livré avec des adaptateurs prêts à l'emploi pour **Anthropic Messages** (avec breakpoints de prompt-caching), **OpenAI Responses**, le chat **OpenAI-Compatible**, et du **Markdown** propre.

---

## Comment ça marche

![Comment vos mots deviennent ce que l'IA lit : une vraie tâche du benchmark tracée de bout en bout — mots simples à l'entrée, chaque bloc scoré, pourquoi chaque carte vole, 369 des 1 236 tokens](docs/context-packing-overview.png)

Explication d'une page générée depuis le vrai pipeline (`scripts/plot_packing_overview.py`) : une vraie tâche du benchmark tracée de bout en bout. Vos mots entrent, les petits mots tombent, chaque bloc du dépôt est scoré, les gagnants volent avec leurs raisons — et l'IA lit 369 tokens au lieu des 1 236 entiers (70 % de moins, et rien de ce qu'exige la correction n'est absent). Chaque chiffre est mesuré, pas illustré.

---

## Démarrage rapide (60 Seconds)

### 1. Installer

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

### 1b. Setup en une commande + prove-it (portes d'adoption)

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` est non labellisé : il rapporte la réduction médiane + la latence p50 et
`recall: not_applicable`. Les preuves de recall exigent des tâches labellisées à la main (la
machinerie figée `benchmarks/splits.json`) ; les runs non labellisés ne revendiquent jamais
de recall.

### 2. Indexer votre codebase

Indexez n'importe quel dossier ou dépôt local dans le store SQLite local (incrémental et super rapide) :

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. Sélectionner le contexte pertinent pour un prompt

Récupérez un package Markdown compact, budgété en tokens, adapté à votre tâche de coding :

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. Journaliser les coupes de contexte avant/après sur de nombreux prompts (`update`)

Lancez la sélection sur un lot de tâches (un fichier JSONL ou stdin) et affichez + journalisez
les budgets de tokens avant/après. Local, pas de réseau :

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

Les lignes par tâche sont aussi ajoutées en JSONL dans `--log` (gitignoré).
**Mise en garde honnête** imprimée sur stderr à chaque run : *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

Chaque run imprime aussi un pied de coupe d'une ligne sur stderr (et la même
ligne comme clé `summary` du JSON stdout), p. ex.
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Des mots simples uniquement —
pas de jargon, pas de balisage de titre `#`. Les totaux s'accumulent localement (comptages uniquement, pas de
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

Envoyez les tâches sur stdin (une `{"task": "..."}` ou une tâche brute par ligne),
récupérez le Markdown de preuves sur stdout — pas besoin de skill, MCP, ni HTTP :

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout est du Markdown pur (un doc par tâche, séparé par `---`, avec
des frontières `<!-- ane-harness task N/M ... -->`) ; les pieds de coupe
par tâche vont sur stderr. Omettez `--repo` quand le repo-id est déjà indexé.

### 4. Ou lancer comme serveur local en arrière-plan

> **Agents : ne lancez PAS ceci dans un tour d'agent.** `serve` (comme `mcp`)
> ne se termine jamais — un appel d'outil qui le lance bloque pour toujours, donc le tour
> ne se termine jamais et chaque prompt suivant s'aligne derrière. Un `update`/`proxy`
> nu sans `--tasks-file` sur un terminal interactif sort
> 2 avec un indice au lieu d'attendre sur stdin. Dans les tours d'agent, n'utilisez que
> des commandes one-shot (`index`, `select`, `prove`, `daily`, `health`). Lancez
> le serveur détaché depuis un vrai terminal
> (`nohup ane-harness serve --port 8765 &`) ou pas du tout.

Démarrez l'API HTTP locale (prête à être branchée à votre agent ou vos outils) :

```bash
ane-harness serve --port 8765
```

Endpoints disponibles :
- `GET  /v1/health` — Statut système, mode de calcul et profils
- `POST /v1/repositories/index` — Indexer ou mettre à jour un dépôt
- `POST /v1/context/select` — Récupérer le contexte optimisé pour une tâche
- `POST /v1/context/compress-output` — Compresser des logs de test/build verbeux en digests d'échec propres

---

## Utilisation en Python

Vous pouvez aussi utiliser le harness directement dans vos propres workflows d'agent IA :

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

## Comment ça marche

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
2. **Retrieval déterministe :** Retrieval lexical BM25 rapide filtré par des gardes de termes de symboles, splitting en sous-tokens, et repli au pluriel.
3. **Packing budgétaire score-first :** Le contexte est packé goulûment pour tenir strictement dans votre budget de tokens spécifié (p. ex. 1,200 tokens), garantissant que les preuves obligatoires ne sont jamais tronquées.
4. **Détection de secrets et barrière de confidentialité :** Les motifs d'exclusion canoniques (`.env*`, `.aws/**`, `*.pem`, etc.) ne sont jamais lus, et des classifieurs regex + entropie remplacent les tokens sensibles par des placeholders stables.
5. **Compression du bruit :** Les sorties d'outils verbeuses (traces de tests, logs de terminal) sont compactées en digests compacts qui préservent le signal.

### Accélération matérielle : distribution privée séparée

Le nom contient `ane`, mais **aucun silicium spécialisé n'est requis ni revendiqué** pour
faire tourner le harness. Le moteur livré est du CPU déterministe pur (Python +
SQLite) et tourne de façon identique sur macOS Apple Silicon, macOS Intel et Linux.
L'accélération par matériel neuronal est maintenue séparément et ne fait pas partie de
ce dépôt.

---

## Spécifications techniques et rigueur

Pour les chercheurs, architectes et responsables techniques qui tiennent à la rigueur numérique :

- **Split de benchmark figé :** Tous les chiffres de release tournent sur un split d'évaluation figé de 18 tâches (`benchmarks/splits.json`, seed `20261002`). Le tuning est strictement quarantiné sur le split dev.
- **Estimateur de tokens déterministe :** Le comptage de tokens utilise un estimateur épinglé (`TOKEN_ESTIMATOR_VERSION="2"`) pour que les chiffres soient 100 % reproductibles d'une machine et d'une version Python à l'autre, sans dérive de tokenizer externe.
- **Politique d'embeddings :** Les embeddings sont volontairement exclus en v0.1 sur la base des compromis coût/latence locaux. Voir [ADR-002](docs/adr-002-embedding-go-no-go.md).
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

Licence MIT. Conçu pour l'intelligence locale, la confidentialité des développeurs, et des budgets de tokens sains.
