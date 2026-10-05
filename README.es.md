# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **Reduce el contexto que lee tu agente en más de un 60%, mantén cada línea necesaria y selecciona el contexto en menos de 4 ms, ejecutándose completamente sin conexión en tu máquina local.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## ¿Qué es esto?

Cuando haces *vibe-coding* o ejecutas agentes de IA (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), enviar toda tu base de código a la ventana de contexto de un LLM es **lento, un desperdicio y peligroso**:
- **Contexto inflado:** Introducir archivos completos en cada turno entierra al modelo en código repetitivo irrelevante, y el proveedor cobra por cada token, sea reutilizado o no.
- **Respuestas más lentas:** El tiempo hasta el primer token (TTFT) de los LLM se ralentiza al precargar miles de líneas innecesarias.
- **Perdido en el medio:** Los modelos alucinan o pasan por alto errores cuando están enterrados bajo código innecesario.
- **Fugas de secretos:** Enviar involuntariamente secretos en `.env` o credenciales de AWS a proveedores de modelos de terceros.

**ane-context-harness** es un motor de contexto ligero y enfocado en el entorno local que se sitúa entre tu base de código y tu agente de programación. En **~3 milisegundos**, indexa tu repositorio, extrae jerarquías de símbolos (funciones, interfaces, tipos), elimina el ruido, redacta secretos y empaqueta solo la evidencia de código de alto valor que tu agente realmente necesita para completar la tarea.

> El nombre `ane` es histórico; **no** es una dependencia. La versión distribuida es de CPU pura y funciona en macOS Apple Silicon, macOS Intel y Linux. La aceleración por hardware reside en una distribución privada separada.

Cero llamadas de red externas. 100% privado y sin conexión.

---

## Resultados de evaluaciones reales

Evaluado en **30 tareas de referencia** (10 pequeñas, 10 típicas, 10 difíciles) en bases de código sintéticas de Python y TypeScript en nuestra división de evaluación congelada (`benchmarks/splits.json`):

| Métrica | Sin Harness (Volcado completo) | Con Harness (Determinista) | Qué significa esto para ti |
|---|---|---|---|
| **Mediana de Tokens de contexto** | **3,213 tokens** | **782 tokens** | **Envía un 60.47% menos al LLM** |
| **Recuperación de Evidencia Necesaria**| 1.0 (100%) | **1.0 (100%)** | **Nunca omitió ni un solo fragmento de código crítico** |
| **Velocidad de selección de contexto**| ~0.01 ms (volcado crudo) | **3.05 ms – 3.83 ms** | **Respuesta local sub-4ms — 100x más rápido que la red** |
| **Ahorro máximo de tokens** | 0% | **Hasta 90.32%** | **Ahorra hasta un ~90% en tareas específicas de configuración** |
| **Precisión de ranking (nDCG@10)**| n/a | **0.849** | **Coloca las funciones más críticas en la parte superior** |
| **Redacción de secretos** | 0% (filtra todos los secretos) | **100% redacción local** | **Los `.env`, llaves AWS y certificados nunca abandonan tu máquina** |
| **Costo derivado por tarea** *(a $3/M)* | ~$0.0096 / tarea | **~$0.0023 / tarea** | **Envía ~75% menos por tarea — tu factura se reduce a medida que el proveedor reutiliza en lugar de volver a leer** |

*(Latencia y memoria medidas localmente en Apple Silicon / CPU; las cifras de costo y TTFT se derivan bajo tasas de tokens establecidas; metodología y registros reproducibles en `benchmarks/reports/` y `benchmarks/logs/`).*

### Desglose de tareas de muestra

| Tipo de tarea | Ejemplo de tarea | Tokens crudos | Tokens Harness | Reducción | Recuperación | Latencia selección |
|---|---|---|---|---|---|---|
| **Configuración** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Reglas y lógica** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Corrección de errores (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **Arquitectura TypeScript**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Carrito multi-archivo complejo** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Ahorro de tokens, medido (rama principal actual)

![Comparación de tokens base vs tokens enviados con recuperación mínima 1.0, más medianas de formato de empaquetado idéntico (JSON / markdown / compacto)](docs/token-savings.png)

Medido solo con funciones públicas (`scripts/measure_token_savings.py`, división de evaluación congelada, un contador anclado — reprodúcelo con `PYTHONPATH=src python3 scripts/measure_token_savings.py`, grafica con `scripts/plot_token_savings.py`). Misma evidencia, tres renderizaciones; la renderización nunca toca la selección.

### Mismo ejercicio contra herramientas reales (sin llaves, sin cuentas)

![Medianas de selección y medianas de formato de empaquetado idéntico: selección de harness vs reescritura de headroom vs evidencia-JSON / markdown / TOON real / compacto](docs/same-exercise-comparison.png)

La prueba de paso a través que cualquier rival puede ejecutar: 18 tareas de evaluación, un contador. Headroom 0.39.1 y el codificador TOON real se ejecutan localmente (`pip install headroom-ai toon-format`, luego `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, grafica con `scripts/plot_same_exercise.py`). La reescritura ciega a la tarea envía más que seleccionar y no mantiene una puerta de supervivencia; TOON real vuelve a los mapeos por fila en código multilínea, mientras que nuestro formato compacto mantiene encabezados CSV con filas literales.

---

## Por qué lo aman los desarrolladores y usuarios de IA

- 💰 **Menos contexto por tarea, salida estable:** Omite archivos que no tienen nada que ver con el prompt; una salida estable permite al proveedor reutilizar lo que ya leyó en lugar de cobrar de nuevo. El porcentaje de corte mide la reducción de contexto local, nunca tu factura.
- ⚡ **Latencia instantánea (~3ms):** Se ejecuta completamente en Python nativo y extensiones en C localmente en tu Mac o máquina Linux.
- 🎯 **Precisión milimétrica:** Combina declaraciones de símbolos AST (clases, interfaces de TypeScript, enums, funciones) con búsqueda léxica BM25 y empaquetado por puntuación con presupuesto de tokens.
- 🛡️ **Sanitización de secretos sin fugas:** Escanea y redacta automáticamente llaves de AWS, llaves privadas RSA/PEM, archivos `.env` y secretos de alta entropía con marcadores de posición estables antes de renderizar los prompts.
- 🔌 **Soporte universal para agentes:** Incluye adaptadores listos para usar para **Anthropic Messages** (con puntos de interrupción de caché de prompt), **OpenAI Responses**, **OpenAI-Compatible chat** y **Markdown** limpio.

---

## Cómo funciona

![Resumen de empaquetado de contexto: qué recibe el LLM, cómo las tareas reescriben a términos, reglas de mantener/descartar, diccionario de razones, límites de empaquetado, historial](docs/context-packing-overview.png)

Póster de una página generado desde la canalización real (`scripts/plot_packing_overview.py`): las palabras de la tarea se reescriben a términos puntuados, los elementos obligatorios siempre vuelan, las tarjetas discrecionales se empaquetan por puntuación bajo presupuesto, cada tarjeta mantenida lleva las razones que puedes discutir. El porcentaje dice cuánto menos enviamos que todo lo que podríamos enviar: tu factura se mueve con cuánto reutiliza el proveedor en lugar de volver a leer.

---

## Inicio rápido (60 segundos)

### 1. Instalación

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

### 1b. Configuración con un comando + prueba (puertas de adopción)

```bash
# indexar, instalar la habilidad del agente, prueba de humo (imprime una línea de resumen)
ane-harness setup --repo /ruta/a/tu/proyecto --repo-id mi-proyecto --yes

# probar: prueba de reducción/latencia en TU repositorio (5 tareas enlatadas, sin etiquetas necesarias)
ane-harness prove --repo /ruta/a/tu/proyecto --repo-id mi-proyecto
# con tus propias tareas: --tasks-file prompts.jsonl
# con un directorio de informe: --out /tmp/prove-report
```

`prove` no tiene etiquetas: informa la reducción mediana + latencia p50 y `recall: not_applicable`. Las pruebas de recuperación necesitan tareas etiquetadas a mano (la maquinaria congelada en `benchmarks/splits.json`); las ejecuciones sin etiquetas nunca reclaman recuperación.

### 2. Indexa tu base de código

Indexa cualquier carpeta o repositorio local en el almacén SQLite local (incremental y súper rápido):

```bash
ane-harness index --repo /ruta/a/tu/proyecto --repo-id mi-proyecto
```

### 3. Selecciona contexto relevante para un prompt

Obtén un paquete Markdown compacto, con presupuesto de tokens y adaptado a tu tarea de programación:

```bash
ane-harness select \
  --repo-id mi-proyecto \
  --task "Arregla el error de cálculo de descuento en el checkout" \
  --budget 1200
```

### 3b. Registro de cortes de contexto antes/después en múltiples prompts (`update`)

Ejecuta la selección sobre un lote de tareas (un archivo JSONL o stdin) e imprime + registra presupuestos de tokens antes/después. Local, sin red:

```bash
# desde un archivo JSONL (uno {"task": "..."} o tarea simple por línea)
ane-harness update \
  --repo-id mi-proyecto \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

Salida de muestra:

```
repo_id: mi-proyecto | tareas: 3 | presupuesto: 2000

  tarea                             antes   después eliminado reducción
  Arreglar cálculo de descuento     3189    1952    1237      38.79%
  depurar cargador de inventario    3189    1758    1431      44.87%
  revisar estadísticas reporte    3189    1261    1928      60.46%

  TOTAL: antes 9567 → después 4971 tokens (4596 eliminados, reducción mediana 44.87%)
```

Las filas por tarea también se añaden como JSONL a `--log` (ignorado por git).
**Advertencia honesta** impresa en stderr en cada ejecución: *"mediciones locales sobre el repositorio dado; la redacción no garantiza que se detecten todos los secretos."*

Cada ejecución también imprime un pie de página de corte de una línea en stderr (y la misma línea como la clave `summary` en JSON de stdout), ej. `ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Solo palabras planas, sin jerga, sin marcas de encabezado `#`. Los totales se acumulan localmente (solo conteos, sin texto de tareas): míralos en cualquier momento con `ane-harness daily`, o en cada salida de shell con `eval "$(ane-harness shell-init)"` en tu `.zshrc`/`.bashrc`.

Los agentes obtienen el mismo comportamiento sin dependencias a través de la habilidad incluida: `skills/ane-harness/SKILL.md`: cópialo en el directorio de habilidades de tu agente y los totales cortados aparecerán automáticamente después de cada tarea, sin otra configuración. Para hosts compatibles con OpenCode/Claude/agentes, también funciona globalmente, sin instalación por proyecto: `~/.config/opencode/skills/`, `~/.claude/skills/`, o `~/.agents/skills/` (las nuevas sesiones lo detectan).

### 3c. Modo proxy para agentes sin integración nativa (`proxy`)

Envía tareas por stdin (un `{"task": "..."}` o tarea simple por línea), recibe evidencia en Markdown por stdout: no se necesita habilidad, MCP o HTTP:

```bash
printf '%s\n' '{"task": "Arregla el error de descuento"}' 'revisar cargador de inventario' \
  | ane-harness proxy --repo /ruta/a/tu/proyecto --repo-id mi-proyecto --budget 2000 \
  > context.md
```

Stdout es Markdown puro (un documento por tarea, separado por `---`, con límites `<!-- ane-harness task N/M ... -->`); los pies de página de corte por tarea van a stderr. Omite `--repo` cuando el repo-id ya esté indexado.

### 4. O ejecuta como servidor de fondo local

> **Agentes: NO ejecutes esto dentro de un turno de agente.** `serve` (como `mcp`) nunca termina: una llamada a herramienta que lo inicia se bloquea para siempre, por lo que el turno nunca se completa y cada prompt posterior se pone en cola detrás de él. El comando `update`/`proxy` sin `--tasks-file` en una terminal interactiva sale con código 2 y una pista en lugar de esperar por stdin. Dentro de los turnos de agente usa solo comandos de un solo disparo (`index`, `select`, `prove`, `daily`, `health`). Ejecuta el servidor desvinculado de una terminal real (`nohup ane-harness serve --port 8765 &`) o no lo ejecutes en absoluto.

Inicia la API HTTP local (lista para ser conectada a tu agente o herramientas):

```bash
ane-harness serve --port 8765
```

Endpoints disponibles:
- `GET  /v1/health` — Estado del sistema, modo de cómputo y perfiles
- `POST /v1/repositories/index` — Indexar o actualizar un repositorio
- `POST /v1/context/select` — Recuperar contexto optimizado para una tarea
- `POST /v1/context/compress-output` — Comprimir registros detallados de pruebas/construcción en resúmenes de fallos limpios

---

## Uso en Python

También puedes usar el harness directamente dentro de tus propios flujos de trabajo de agentes de IA:

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. Inicializar canalización
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. Indexar repositorio
pipeline.register_repository("/ruta/a/mi-repo", repo_id="mi-repo")

# 3. Seleccionar contexto presupuestado
request = SelectRequest(
    repository_id="mi-repo",
    task="Actualizar lógica de redondeo de puntos de lealtad en servicio de pago",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. Serializar directamente para tu proveedor de LLM favorito
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Empaquetados {package.metrics['selected_tokens']} tokens (cortados {package.metrics['tokens_removed']} tokens)")
```

---

## Cómo funciona

```
                        Tu base de código
                             │
                     Analizador AST y Símbolos
               (Funciones Python, interfaces TS)
                             │
                      Fragmentador nivel de línea
                             │
                      Almacén SQLite local
                             │
Prompt de usuario  ──────►   Búsqueda léxica BM25
                             │
                   Empaquetado por presupuesto y puntuación
                  (Retención obligatoria + MMR)
                             │
                  Sanitizador de secretos local
              (Redacta .env, llaves AWS, certs)
                             │
               Adaptador de proveedor (Anthropic/OpenAI)
                             │
                   Contexto ajustado y preciso
```

1. **Fragmentación AST consciente de símbolos:** En lugar de dividir líneas de forma tonta, los archivos se analizan para obtener construcciones de código reales (clases, métodos, tipos/interfaces/enums de TypeScript).
2. **Recuperación determinista:** Búsqueda léxica rápida BM25 filtrada por guardas de términos de símbolos, división de sub-tokens y plegado de plurales.
3. **Empaquetado por presupuesto:** El contexto se empaqueta de forma voraz para ajustarse estrictamente dentro de tu presupuesto de tokens especificado (ej. 1,200 tokens), garantizando que la evidencia obligatoria nunca se trunque.
4. **Detección de secretos y barrera de privacidad:** Los patrones de exclusión canónicos (`.env*`, `.aws/**`, `*.pem`, etc.) nunca se leen, y los clasificadores de regex + entropía reemplazan tokens sensibles con marcadores de posición estables.
5. **Compresión de ruido:** Las salidas de herramientas detalladas (rastros de pruebas, registros de terminal) se colapsan en resúmenes compactos que preservan la señal.

### Aceleración por hardware: distribución privada separada

El nombre contiene `ane`, pero **no se requiere ni se reclama silicio especializado** para ejecutar el harness. El motor distribuido es de CPU determinista pura (Python + SQLite) y funciona de forma idéntica en macOS Apple Silicon, macOS Intel y Linux. La aceleración por hardware neuronal se mantiene por separado y no es parte de este repositorio.

---

## Especificaciones técnicas y rigor

Para investigadores, arquitectos y líderes técnicos que se preocupan por el rigor numérico:

- **División de referencia congelada:** Todos los números de lanzamiento se ejecutan en una división de evaluación congelada de 18 tareas (`benchmarks/splits.json`, semilla `20261002`). El ajuste está estrictamente en cuarentena para la división de desarrollo.
- **Estimador de tokens determinista:** El conteo de tokens utiliza un estimador anclado (`TOKEN_ESTIMATOR_VERSION="2"`) para que los números sean 100% reproducibles entre máquinas y versiones de Python sin deriva del tokenizador externo.
- **Política de incrustaciones (embeddings):** Las incrustaciones se excluyen intencionalmente en la v0.1 basadas en compromisos locales de costo/latencia. Ver [ADR-002](docs/adr-002-embedding-go-no-go.md).
- **Paquete de evidencia de lanzamiento:** La evidencia de lanzamiento tiene checksum y se verifica criptográficamente mediante `ane-harness evidence verify ane-context-harness-evidence-v0.1`.

---

## Ejecución del conjunto de pruebas

```bash
# Ejecutar las 258 pruebas unitarias, de integración y seguridad
python3 -m pytest -q

# Ejecutar evaluación comparativa concurrente A/B
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## Licencia

Licencia MIT. Diseñado para inteligencia local, privacidad del desarrollador y presupuestos de tokens sensatos.