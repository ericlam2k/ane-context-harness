# ⚡ ane-context-harness

[Inglés](README.md) · [Vietnamita](README.vi.md) · [Chino](README.zh.md) · [Francés](README.fr.md) · [Español](README.es.md) · [Japonés](README.ja.md) · [Coreano](README.ko.md)

> **Reduce el contexto que lee tu agente en un 60%+, conserva cada línea necesaria y selecciona el contexto en menos de 4ms — ejecutándose completamente offline en tu máquina local.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## ¿Qué es esto?

Cuando haces vibe-code o ejecutas agentes de IA (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), meter todo tu código en una ventana de contexto de un LLM es **lento, derrochador y peligroso**:
- **Contexto inflado:** Meter archivos enteros en cada turno entierra al modelo en boilerplate irrelevante — y el proveedor cuenta cada token, se reutilice o no.
- **Respuestas más lentas:** El time-to-first-token del LLM se arrastra al prellenar miles de líneas innecesarias.
- **Perdido en el medio:** Los modelos alucinan o se saltan bugs cuando quedan enterrados bajo boilerplate irrelevante.
- **Fugas de secretos:** Enviar sin querer secretos de `.env` o credenciales de AWS a proveedores de modelos de terceros.

**ane-context-harness** es un motor de contexto ligero y local-first que se sitúa entre tu código y tu agente de programación. En **~3 milliseconds**, indexa tu repositorio, extrae jerarquías de símbolos (funciones, interfaces, tipos), elimina el ruido, redacta secretos y empaqueta solo la evidencia de código de alto valor que tu agente realmente necesita para completar la tarea.

> El nombre `ane` es histórico; **no** es una dependencia. El camino publicado es CPU pura y funciona en macOS Apple Silicon, macOS Intel y Linux. La aceleración por hardware vive en una distribución privada aparte.

Cero llamadas de red externas. 100% privado y offline.

---

## Resultados reales del benchmark

Evaluado a lo largo de **30 tareas de benchmark** (10 small, 10 typical, 10 difficult) sobre codebases sintéticos de Python y TypeScript en nuestro split de evaluación congelado (`benchmarks/splits.json`):

| Métrica | Sin harness (volcado completo del repo) | Con harness (determinista) | Qué significa esto para ti |
|---|---|---|---|
| **Tokens de contexto (mediana)** | **3,213 tokens** | **782 tokens** | **Envía un 60.47% menos al LLM** |
| **Recall de evidencia requerida** | 1.0 (100%) | **1.0 (100%)** | **Nunca omitió ni una sola pieza de código crítico** |
| **Velocidad de selección de contexto** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Respuesta local sub-4ms — 100x más rápida que la red** |
| **Ahorro máximo de tokens** | 0% | **Up to 90.32%** | **Ahorra hasta ~90% en tareas específicas de config y settings** |
| **Precisión de ranking (nDCG@10)**| n/a | **0.849** | **Coloca las funciones más críticas justo al principio** |
| **Redacción de secretos** | 0% (leaks all secrets) | **100% local redaction** | **`.env`, las claves de AWS y los certificados nunca salen de tu máquina** |
| **Coste derivado por tarea** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **Envía ~75% menos por tarea a la tarifa indicada — tu factura en sí se mueve según cuánto reutilice el proveedor en lugar de volver a leer** |

*(Latencia y memoria medidas localmente en Apple Silicon / CPU; las cifras de coste y TTFT se derivan bajo las tarifas de tokens indicadas; metodología y logs reproducibles en `benchmarks/reports/` y `benchmarks/logs/`).*

### Desglose de tareas de ejemplo

| Tipo de tarea | Tarea de ejemplo | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **Ajustes y configuración** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Reglas y lógica** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Corrección de bugs (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **Arquitectura TypeScript**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Carrito complejo multiarchivo** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Ahorro de tokens, medido (current main)

![Tokens de baseline vs enviados por tarea con recall mínimo 1.0, más medianas de formato de paquete idéntico (JSON / markdown / compact)](docs/token-savings.png)

Medido solo con funciones públicas (`scripts/measure_token_savings.py`, frozen eval split, un contador fijado — reproduce with `PYTHONPATH=src python3 scripts/measure_token_savings.py`, draw with `scripts/plot_token_savings.py`). La misma evidencia, tres renderizados; el renderizado nunca toca la selección.

### El mismo ejercicio contra herramientas reales (sin claves, sin cuentas)

![Medianas de selección y medianas de formato de paquete idéntico: harness select vs headroom rewrite vs evidence-JSON / markdown / real TOON / compact](docs/same-exercise-comparison.png)

La prueba passthrough que cualquier rival puede ejecutar: 18 tareas de eval, un contador. Headroom 0.39.1 y el encoder TOON real se ejecutan en local (`pip install headroom-ai toon-format`, then `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, draw with `scripts/plot_same_exercise.py`). La reescritura ciega a la tarea envía más que seleccionar y no mantiene ninguna survival gate; el TOON real cae a mapeos por fila en código multilínea mientras que nuestro compact mantiene cabeceras CSV con filas verbatim.

---

## Por qué lo aman los desarrolladores y vibecoders

- 💰 **Menos contexto por tarea, salida estable:** Omite archivos que no tienen nada que ver con el prompt — y una salida estable permite al proveedor reutilizar lo que ya leyó en lugar de cobrar de nuevo. Cut% mide la reducción local de contexto, nunca tu factura.
- ⚡ **Latencia instantánea (~3ms):** Se ejecuta por completo en Python nativo y extensiones C en local, en tu Mac o caja Linux.
- 🎯 **Precisión milimétrica:** Combina declaraciones de símbolos AST (clases, interfaces TypeScript, enums, funciones) con búsqueda léxica BM25 y empaquetado score-first con presupuesto de tokens.
- 🛡️ **Sanitización de secretos sin fugas:** Escanea y redacta automáticamente claves AWS, claves privadas RSA/PEM, archivos `.env` y secretos de alta entropía con placeholders estables de ámbito de petición antes de renderizar los prompts.
- 🔌 **Soporte universal de agentes:** Incluye adaptadores listos para usar para **Anthropic Messages** (con breakpoints de prompt-caching), **OpenAI Responses**, **OpenAI-Compatible chat** y **Markdown** limpio.

---

## Cómo funciona

![Vista general del empaquetado de contexto: lo que recibe el LLM, cómo las tareas se reescriben en términos, reglas keep/drop, diccionario de reasons, límites de packing, historial](docs/context-packing-overview.png)

Póster de una página generado a partir del pipeline real (`scripts/plot_packing_overview.py`): las palabras de la tarea se reescriben en términos puntuados, los pins obligatorios siempre vuelan, las cards discrecionales se empaquetan score-first bajo presupuesto, cada card conservada lleva las reasons con las que puedes discutir. El porcentaje dice cuánto menos enviamos de todo lo que podríamos enviar — tu factura en sí se mueve según cuánto reutilice el proveedor en lugar de volver a leer.

---

## Inicio rápido (60 Seconds)

### 1. Instalar

Requiere Python 3.13 o 3.14 en macOS o Linux:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

Verifica tu instalación:
```bash
ane-harness health
```

### 1b. Setup de un comando + prove-it (adoption gates)

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` no está etiquetado: reporta la reducción mediana + latencia p50 y
`recall: not_applicable`. Las pruebas de recall necesitan tareas etiquetadas a mano (la
maquinaria congelada de `benchmarks/splits.json`); las ejecuciones sin etiquetar nunca reclaman
recall.

### 2. Indexa tu código

Indexa cualquier carpeta o repositorio local en el almacén SQLite local (incremental y súper rápido):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. Selecciona el contexto relevante para un prompt

Obtén un paquete Markdown compacto, con presupuesto de tokens, adaptado a tu tarea de programación:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. Registra recortes de contexto before/after en muchos prompts (`update`)

Ejecuta la selección sobre un lote de tareas (un archivo JSONL o stdin) e imprime + registra
los presupuestos de tokens before/after. Local, sin red:

```bash
# from a JSONL file (one {"task": "..."} or bare task per line)
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

Salida de ejemplo:

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

Las filas por tarea también se añaden como JSONL a `--log` (gitignored).
La **advertencia honesta** se imprime en stderr en cada ejecución: *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

Cada ejecución también imprime un pie de recorte de una línea en stderr (y la misma
línea como la clave `summary` en el JSON de stdout), p. ej.
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Solo palabras planas —
sin jerga, sin markup de encabezados `#`. Los totales se acumulan en local (solo recuentos, sin
texto de tarea) — consúltalos
cuando quieras con `ane-harness daily`, o en cada salida del shell con
`eval "$(ane-harness shell-init)"` en tu `.zshrc`/`.bashrc`.

Los agentes obtienen el mismo comportamiento sin dependencias mediante el skill incluido:
`skills/ane-harness/SKILL.md` — cópialo en el directorio de skills de tu agente
y los totales de recorte aparecen automáticamente después de cada tarea, sin más configuración. En
hosts compatibles con OpenCode/Claude/agentes también funciona de forma global, sin instalación
por proyecto: `~/.config/opencode/skills/`, `~/.claude/skills/` o
`~/.agents/skills/` (las sesiones nuevas lo recogen).

### 3c. Modo proxy para agentes sin integración nativa (`proxy`)

Envía tareas por stdin (un `{"task": "..."}` o una tarea suelta por línea),
recibe el Markdown de evidencia por stdout — no hace falta skill, MCP ni HTTP:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout es Markdown puro (un documento por tarea, separado por `---`, con
límites `<!-- ane-harness task N/M ... -->`); los pies de recorte
por tarea van a stderr. Omite `--repo` cuando el repo-id ya está indexado.

### 4. O ejecútalo como servidor local en segundo plano

> **Agentes: NO ejecutes esto dentro de un turno de agente.** `serve` (como `mcp`)
> nunca termina — una llamada de herramienta que lo lanza se bloquea para siempre, así que el turno
> nunca se completa y cada prompt posterior se encola detrás. `update`/`proxy`
> sin `--tasks-file` en un terminal interactivo salen
> con código 2 y una pista en lugar de esperar en stdin. Dentro de turnos de agente usa solo
> comandos de un disparo (`index`, `select`, `prove`, `daily`, `health`). Ejecuta
> el servidor desprendido desde un terminal real
> (`nohup ane-harness serve --port 8765 &`) o no lo ejecutes.

Arranca la API HTTP local (lista para conectar a tu agente o herramientas):

```bash
ane-harness serve --port 8765
```

Endpoints disponibles:
- `GET  /v1/health` — Estado del sistema, modo de cómputo y perfiles
- `POST /v1/repositories/index` — Indexar o actualizar un repositorio
- `POST /v1/context/select` — Recuperar contexto optimizado para una tarea
- `POST /v1/context/compress-output` — Comprimir logs verbosos de test/build en digestos limpios de fallos

---

## Uso en Python

También puedes usar el harness directamente dentro de tus propios flujos de agentes de IA:

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

## Cómo funciona

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

1. **Chunking AST consciente de símbolos:** En lugar de un troceado tonto por líneas, los archivos se parsean en busca de construcciones reales de código (clases, métodos, tipos/interfaces/enums de TypeScript).
2. **Recuperación determinista:** Recuperación léxica BM25 rápida filtrada por guards de términos de símbolos, splitting de subtokens y plegado de plurales.
3. **Empaquetado score-first con presupuesto:** El contexto se empaqueta de forma greedy para caber estrictamente en tu presupuesto de tokens (p. ej., 1,200 tokens), garantizando que la evidencia obligatoria nunca se trunque.
4. **Detección de secretos y valla de privacidad:** Los patrones de exclusión canónicos (`.env*`, `.aws/**`, `*.pem`, etc.) nunca se leen, y los clasificadores de regex + entropía sustituyen tokens sensibles por placeholders estables.
5. **Compresión de ruido:** Las salidas verbosas de herramientas (trazas de tests, logs de terminal) se colapsan en digestos compactos que preservan la señal.

### Aceleración por hardware: distribución privada aparte

El nombre contiene `ane`, pero **no se requiere ni se reclama silicio especializado** para
ejecutar el harness. El motor publicado es CPU determinista pura (Python +
SQLite) y funciona de forma idéntica en macOS Apple Silicon, macOS Intel y Linux.
La aceleración de hardware neuronal se mantiene aparte y no forma parte de
este repositorio.

---

## Especificaciones técnicas y rigor

Para investigadores, arquitectos y líderes técnicos a quienes importa el rigor numérico:

- **Split de benchmark congelado:** Todos los números de release se ejecutan sobre un split de evaluación congelado de 18 tareas (`benchmarks/splits.json`, seed `20261002`). El ajuste queda estrictamente en cuarentena en el split de dev.
- **Estimador de tokens determinista:** El recuento de tokens usa un estimador fijado (`TOKEN_ESTIMATOR_VERSION="2"`) para que los números sean 100% reproducibles entre máquinas y versiones de Python sin deriva de tokenizer externo.
- **Política de embeddings:** Los embeddings se excluyen deliberadamente en v0.1 por el equilibrio local de coste/latencia. Véase [ADR-002](docs/adr-002-embedding-go-no-go.md).
- **Paquete de evidencia de release:** La evidencia de release con checksum se verifica criptográficamente con `ane-harness evidence verify ane-context-harness-evidence-v0.1`.

---

## Ejecutar la suite de tests

```bash
# Run all 258 unit, integration, and security tests
python3 -m pytest -q

# Run concurrent A/B benchmark evaluation
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## Licencia

Licencia MIT. Diseñado para inteligencia local, privacidad del desarrollador y presupuestos de tokens sensatos.