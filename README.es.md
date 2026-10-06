# ⚡ ane-context-harness

[Inglés](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **Reduce el contexto que lee tu agente en un 60%+, conserva cada línea necesaria y selecciona el contexto en menos de 4ms — ejecutándose completamente sin conexión en tu máquina local.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## ¿Qué es esto?

Cuando haces vibe-code o ejecutas agentes de IA (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), meter todo tu código en la ventana de contexto de un LLM es **lento, derrochador y peligroso**:
- **Contexto inflado:** Empujar archivos enteros en cada turno entierra al modelo en boilerplate irrelevante — y el proveedor cuenta cada token, se reutilice o no.
- **Respuestas más lentas:** El time-to-first-token del LLM se arrastra al prellenar miles de líneas innecesarias.
- **Perdido en el medio:** Los modelos alucinan o se saltan bugs cuando quedan enterrados bajo boilerplate irrelevante.
- **Fugas de secretos:** Enviar sin querer secretos de `.env` o credenciales de AWS a proveedores de modelos de terceros.

**ane-context-harness** es un motor de contexto ligero y local-first que se sitúa entre tu código y tu agente de programación. En **~3 milliseconds**, indexa tu repositorio, extrae jerarquías de símbolos (funciones, interfaces, tipos), elimina el ruido, redacta secretos y empaqueta solo la evidencia de código de alto valor que tu agente realmente necesita para completar la tarea.

> El nombre `ane` es histórico; **no** es una dependencia. La ruta publicada es CPU pura y funciona en macOS Apple Silicon, macOS Intel y Linux. La aceleración por hardware vive en una distribución privada aparte.

Cero llamadas de red externas. 100% privado y sin conexión.

---

## Resultados reales del benchmark

Evaluado en **30 benchmark tasks** (10 small, 10 typical, 10 difficult) sobre codebases sintéticos de Python y TypeScript en nuestro split de evaluación congelado (`benchmarks/splits.json`):

| Métrica | Sin Harness (volcado completo del repo) | Con Harness (determinista) | Qué significa esto para ti |
|---|---|---|---|
| **Median Context Tokens** | **3,213 tokens** | **782 tokens** | **Envía 60.47% menos al LLM** |
| **Required-Evidence Recall** | 1.0 (100%) | **1.0 (100%)** | **No se perdió ni una sola pieza de código crítico** |
| **Context Selection Speed** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Respuesta local sub-4ms — 100x más rápida que la red** |
| **Peak Token Savings** | 0% | **Up to 90.32%** | **Ahorra hasta ~90% en tareas de config y settings** |
| **Ranking Accuracy (nDCG@10)**| n/a | **0.849** | **Coloca las funciones más críticas justo arriba** |
| **Secret Redaction** | 0% (leaks all secrets) | **100% local redaction** | **`.env`, claves AWS y certificados nunca salen de tu máquina** |
| **Derived Cost per Task** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **Envía ~75% menos por tarea a la tarifa indicada — tu factura se mueve según cuánto reutilice el proveedor en lugar de volver a leer** |

*(Latencia y memoria medidas localmente en Apple Silicon / CPU; las cifras de coste y TTFT se derivan con las tarifas de tokens indicadas; metodología y logs reproducibles en `benchmarks/reports/` y `benchmarks/logs/`).*

### Desglose de tareas de ejemplo

| Tipo de tarea | Tarea de ejemplo | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **Settings & Config** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Rules & Logic** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Bug Fixes (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript Architecture**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Complex Multi-file Cart** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Ahorro de tokens, medido (current main)

Cómo leer este gráfico: cada job le preguntó a la herramienta "¿qué debería leer la IA para esta tarea?". El panel izquierdo compara, por tamaño de job, cuánto texto enviarías si enviaras todo el código (gris) frente a lo que eligió el harness (verde) — el número encima de cada barra verde es lo que envías ahora y cuánto más pequeño es. Los jobs más difíciles necesitan más archivos, así que la barra verde crece — pero los archivos necesarios se conservaron **todas las veces**, que es el punto: más pequeño solo es bueno si no falta nada importante. El panel derecho muestra la misma elección enviada de tres formas — detalle completo, un punto medio legible y el wrapping más corto — más corto es más barato, y el wrapping nunca cambia *qué* se elige.

![Menos que leer por tamaño de job, más tres wrappings de la misma respuesta](docs/token-savings.png)

Mide con `PYTHONPATH=src python3 scripts/measure_token_savings.py`, dibuja con `scripts/plot_token_savings.py` (frozen eval split, un contador de tokens fijado).

### El mismo ejercicio contra herramientas reales (sin claves, sin cuentas)

Cómo leer este gráfico: es una carrera en los mismos 18 jobs con la misma regla — "¿cuántos tokens tiene el job del medio, y se perdió algo necesario?". El primer gráfico es el titular: enviar todo es el valor por defecto costoso, la herramienta de reescritura externa en realidad envía *más* de lo necesario y una vez perdió un archivo de config que el grader exigía (marcado FAIL), mientras que nuestros dos modos son los más cortos y conservaron los archivos necesarios todas las veces (PASS). El segundo gráfico muestra los detalles detrás — lo que ahorra la selección sola, y cómo la misma selección se encoge otra vez solo eligiendo un wrapping más corto. PASS/FAIL aquí significa exactamente una cosa: las piezas que el grader del benchmark dice que son requeridas volvieron en el pack.

![Los mismos 18 jobs: enviar-todo vs una herramienta de reescritura externa vs nosotros](docs/head-to-head.png)

![Medianas de selección y el mismo pack en cuatro wrappings, con ejemplos por job](docs/same-exercise-comparison.png)

Reproduce: `pip install headroom-ai toon-format`, then `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, draw with `scripts/plot_same_exercise.py`. La reescritura a ciegas de la tarea envía más que seleccionar y no tiene puerta de supervivencia; el encoder TOON real cae a mappings por fila en código multilínea mientras que nuestro compact mantiene cabeceras CSV con filas verbatim.

### Ahorro en conversación, medido

Cómo leer esto: un job nunca es una sola pregunta — el agente pregunta, luego hace follow-up, luego verifica. Este bench reproduce la misma conversación de 3 turnos por job de tres formas: enviando todo el código en cada turno (149,490 tokens), un pack recortado (17,094), y tres packs acumulados donde cada follow-up conserva todo lo que encontraron los turnos anteriores (51,940). La conversación acumulada envía **alrededor de un tercio** del coste sin harness — 97,550 tokens menos, 65.3% menos — y los archivos necesarios sobrevivieron los 72 turnos (recall 1.0 en cada turno; un turno que pierde un archivo necesario descarrila la conversación, así que esa puerta es estructural, no decorativa).

Reproduce: `PYTHONPATH=src python3 scripts/bench_conversation.py` (frozen eval split, un contador de tokens fijado; writes `benchmarks/reports/conversation-bench-eval.json`). Límite, dicho claro: ningún modelo lee estos packs, los follow-ups son cadenas fijas en lugar de reacciones reales del agente, no se factura nada, ningún job se completa de verdad. Mide la mitad que alimentamos — la selección y el acarreo — no el bucle en sí.

### Qué le ocurre a cada archivo

Cuatro reglas documentadas, sin modelo de por medio, sin excepciones: los archivos que fijas (o que el grader exige) viajan **byte a byte, siempre**. El código, la config y los diffs conservan su estructura — el picker selecciona símbolos enteros, nunca los reescribe. Solo **logs y salida ruidosa de herramientas** se colapsan (líneas de progreso repetidas, tracebacks duplicados, spam de install se pliegan en una línea de resumen que dice qué se eliminó). La prosa viaja tal como se eligió, nunca reescrita — no hay rewriter neuronal, así que nada puede parafrasear tus docs en algo que no dijeran. Cada pack lista, por archivo, qué regla se aplicó — comprueba `diagnostics.routing` en cualquier informe y discútelo.

---

## Por qué lo quieren los desarrolladores y vibecoders

- 💰 **Menos contexto por tarea, salida estable:** Omite archivos que no tienen nada que ver con el prompt — y una salida estable deja que el proveedor reutilice lo que ya leyó en lugar de cobrar otra vez. Cut% mide la reducción local de contexto, nunca tu factura.
- ⚡ **Latencia instantánea (~3ms):** Corre por completo en Python nativo y extensiones C localmente en tu Mac o caja Linux.
- 🎯 **Precisión milimétrica:** Combina declaraciones de símbolos AST (clases, interfaces TypeScript, enums, funciones) con búsqueda léxica BM25 y empaquetado score-first con presupuesto de tokens.
- 🛡️ **Sanitización de secretos Zero-Leak:** Escanea y redacta automáticamente claves AWS, claves privadas RSA/PEM, archivos `.env` y secretos de alta entropía con placeholders estables acotados a la petición antes de renderizar los prompts.
- 🔌 **Soporte universal de agentes:** Incluye adaptadores listos para usar para **Anthropic Messages** (con breakpoints de prompt-caching), **OpenAI Responses**, chat **OpenAI-Compatible** y **Markdown** limpio.

---

## Cómo funciona

![Cómo tus palabras se convierten en lo que la IA lee: una tarea real del benchmark rastreada de principio a fin — palabras simples, cada bloque puntuado, por qué vuela cada tarjeta, 369 de 1.236 tokens](docs/context-packing-overview.png)

Explicación de una página generada desde el pipeline real (`scripts/plot_packing_overview.py`): una tarea real del benchmark rastreada de principio a fin. Entran tus palabras, caen las palabras cortas, cada bloque del repo se puntúa, los ganadores vuelan con sus razones — y la IA lee 369 tokens en vez de los 1.236 completos (70 % menos, y no falta nada de lo que la corrección necesita). Cada número está medido, no ilustrado.

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

### 1b. Setup en un comando + prove-it (adoption gates)

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` no está etiquetado: reporta median reduction + p50 latency y
`recall: not_applicable`. Las pruebas de recall necesitan tareas etiquetadas a mano (la
maquinaria congelada de `benchmarks/splits.json`); las ejecuciones sin etiquetar nunca reivindican
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
presupuestos de tokens before/after. Local, sin red:

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
**Caveat honesto** impreso en stderr en cada ejecución: *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

Cada ejecución también imprime un pie de recorte de una línea en stderr (y la misma
línea como la clave `summary` en el JSON de stdout), p. ej.
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Solo palabras claras —
sin jerga, sin markup de encabezado `#`. Los totales se acumulan localmente (solo conteos, sin
texto de tarea) — consúltalos
cuando quieras con `ane-harness daily`, o en cada salida del shell con
`eval "$(ane-harness shell-init)"` en tu `.zshrc`/`.bashrc`.

Los agentes obtienen el mismo comportamiento sin dependencias vía el skill incluido:
`skills/ane-harness/SKILL.md` — cópialo al directorio de skills de tu agente
y los totales de recorte aparecen automáticamente después de cada tarea, sin más setup. Para
hosts compatibles con OpenCode/Claude/agent también funciona de forma global, sin instalación por proyecto:
`~/.config/opencode/skills/`, `~/.claude/skills/`, o
`~/.agents/skills/` (las sesiones nuevas lo recogen).

### 3c. Modo proxy para agentes sin integración nativa (`proxy`)

Envía tareas por stdin (una `{"task": "..."}` o tarea suelta por línea),
recibe el Markdown de evidencia por stdout — sin skill, MCP ni HTTP:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout es Markdown puro (un doc por tarea, separados por `---`, con
límites `<!-- ane-harness task N/M ... -->`); los pies de recorte
por tarea van a stderr. Omite `--repo` cuando el repo-id ya está indexado.

### 4. O ejecútalo como servidor local en segundo plano

> **Agentes: NO ejecuten esto dentro de un turno de agente.** `serve` (como `mcp`)
> nunca termina — una llamada de herramienta que lo lanza se bloquea para siempre, así que el turno
> nunca completa y cada prompt posterior se encola detrás. Un `update`/`proxy`
> desnudo sin `--tasks-file` en un terminal interactivo sale
> 2 con una pista en lugar de esperar en stdin. Dentro de turnos de agente usen solo
> comandos de un disparo (`index`, `select`, `prove`, `daily`, `health`). Ejecuten
> el servidor desacoplado desde un terminal real
> (`nohup ane-harness serve --port 8765 &`) o no lo ejecuten.

Arranca la API HTTP local (lista para engancharse a tu agente o herramientas):

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

También puedes usar el harness directamente dentro de tus propios flujos de agente de IA:

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

1. **Chunking AST consciente de símbolos:** En lugar de partir por líneas a lo bruto, los archivos se parsean buscando construcciones reales de código (clases, métodos, tipos/interfaces/enums de TypeScript).
2. **Recuperación determinista:** Recuperación léxica BM25 rápida filtrada por guards de términos de símbolo, splitting de subtokens y plegado de plurales.
3. **Empaquetado score-first con presupuesto:** El contexto se empaqueta de forma greedy para caber estrictamente en tu presupuesto de tokens (p. ej., 1,200 tokens), garantizando que la evidencia obligatoria nunca se trunque.
4. **Detección de secretos y valla de privacidad:** Los patrones canónicos de exclusión (`.env*`, `.aws/**`, `*.pem`, etc.) nunca se leen, y clasificadores de regex + entropía reemplazan tokens sensibles con placeholders estables.
5. **Compresión de ruido:** Salidas verbosas de herramientas (trazas de test, logs de terminal) se colapsan en digestos compactos que conservan la señal.

### Aceleración por hardware: distribución privada aparte

El nombre contiene `ane`, pero **no se requiere ni se reivindica silicio especializado** para
ejecutar el harness. El motor publicado es CPU determinista pura (Python +
SQLite) y corre igual en macOS Apple Silicon, macOS Intel y Linux.
La aceleración por hardware neuronal se mantiene aparte y no forma parte de
este repositorio.

---

## Especificaciones técnicas y rigor

Para investigadores, arquitectos y líderes técnicos a quienes importa el rigor numérico:

- **Frozen Benchmark Split:** Todos los números de release corren sobre un split de evaluación congelado de 18 tareas (`benchmarks/splits.json`, seed `20261002`). El ajuste queda estrictamente en cuarentena en el split de dev.
- **Estimador de tokens determinista:** El conteo de tokens usa un estimador fijado (`TOKEN_ESTIMATOR_VERSION="2"`) para que los números sean 100% reproducibles entre máquinas y versiones de Python sin deriva de tokenizer externo.
- **Política de embeddings:** Los embeddings se excluyen a propósito en v0.1 por el trade-off local de coste/latencia. Véase [ADR-002](docs/adr-002-embedding-go-no-go.md).
- **Paquete de evidencia de release:** La evidencia de release con checksum se verifica criptográficamente vía `ane-harness evidence verify ane-context-harness-evidence-v0.1`.

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

MIT License. Diseñado para inteligencia local, privacidad del desarrollador y presupuestos de tokens sanos.
