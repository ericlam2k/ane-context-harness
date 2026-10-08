# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **Reduce más del 60% del contexto que lee tu agente de IA, conserva cada línea de código requerida y selecciona contexto en menos de 4 ms — ejecutándose 100% offline en tu máquina local.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-265%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## ¿Qué es esto?

Cuando haces vibe-coding o ejecutas agentes de IA (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), enviar todo tu repositorio al contexto del LLM es **lento, ineficiente y riesgoso**:
- **Contexto sobrecargado:** Enviar archivos completos en cada interacción sepulta al modelo en código irrelevante (boilerplate), y el proveedor cobra por cada token, reutilizado o no.
- **Respuestas más lentas:** El tiempo hasta el primer token (LLM time-to-first-token) se degrada al procesar miles de líneas innecesarias.
- **Efecto "Lost in the Middle":** Los modelos alucinan o pasan por alto errores cuando hay exceso de ruido.
- **Fuga de credenciales:** Envío accidental de archivos `.env` o llaves de AWS a proveedores externos.

**ane-context-harness** es un motor de contexto *local-first* y ligero situado entre tu código y tu agente de desarrollo. En **~3 milisegundos**, indiza tu repositorio, extrae la jerarquía de símbolos (funciones, interfaces, tipos), elimina el ruido, oculta credenciales (redaction) y empaqueta solo el código relevante que el agente necesita.

> El nombre `ane` es por razones históricas; **no** es una dependencia. La versión pública corre únicamente en CPU sobre macOS (Apple Silicon e Intel) y Linux. La aceleración por hardware pertenece a una distribución privada independiente.

Sin llamadas a redes externas. 100% privado y ejecutable fuera de línea.

![Ilustración conceptual: el truncado bruto rompe AST, imports y referencias — el harness conserva firmas, estructura AST y dependencias esenciales](docs/ane-concept-generic.jpg)

*Ilustración conceptual — el código de la imagen es arte gráfico, no una traza real.*


---

## Resultados de Benchmark

Evaluado en **30 tareas de benchmark** (10 pequeñas, 10 típicas, 10 complejas) con repositorios sintéticos en Python y TypeScript utilizando nuestro dataset de evaluación fijo (`benchmarks/splits.json`):

| Métrica | Sin Harness (Dump completo del Repo) | Con Harness (Deterministico) | Qué significa para ti |
|---|---|---|---|
| **Tokens de Contexto (Mediana)** | **3,213 tokens** | **782 tokens** | **Envía un 60.47% menos de tokens al LLM** |
| **Cobertura de Código Requerido (Recall)** | 1.0 (100%) | **1.0 (100%)** | **Nunca omitió código crítico para la solución** |
| **Velocidad de Selección de Contexto** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Respuesta local en menos de 4 ms — 100x más rápido que la red** |
| **Ahorro Máximo de Tokens** | 0% | **Hasta 90.32%** | **Ahorra hasta ~90% en tareas de configuración** |
| **Precisión de Ranking (nDCG@10)**| n/a | **0.849** | **Coloca las funciones más críticas al inicio del contexto** |
| **Sanitización de Secretos** | 0% (fuga total) | **100% sanitización local** | **Variables `.env`, llaves AWS y certificados nunca salen de tu máquina** |
| **Costo Derivado por Tarea** *(a $3/M)* | ~$0.0096 / tarea | **~$0.0023 / tarea** | **Envía ~75% menos datos por tarea según tarifas estándar — la factura final depende del reuso de caché del proveedor** |

*(Latencia y memoria medidas localmente en Apple Silicon / CPU; costos y TTFT derivados bajo tarifas oficiales de tokens; detalles de metodología en `benchmarks/reports/` y `benchmarks/logs/`).*

![Ilustración conceptual: comparar enfoques de recuperación de contexto con la misma vara](docs/ane-benchmark-concept.jpg)

*Ilustración conceptual, no un resultado medido — la escala de tokens y las cifras de la imagen son ilustrativas. Todas las mediciones reales están en la tabla de arriba.*


---

## Inicio Rápido (60 Segundos)

### 1. Instalación

Requiere Python 3.13 o 3.14 en macOS o Linux:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

Verificar la instalación:
```bash
ane-harness health
```

### 1b. Configuración y prueba inicial

```bash
# Indizar, instalar el skill para el agente y ejecutar smoke test
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# Probar la reducción de tokens en TU repositorio
ane-harness prove --repo /path/to/your/project --repo-id my-project
```

### 2. Indizar tu Repositorio

Indiza cualquier proyecto local en SQLite (actualización incremental y ultrarrápida):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. Seleccionar Contexto Optimizado

Obtén un payload en Markdown empaquetado según tu presupuesto de tokens:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

### 4. Ejecutar como Servidor Local en Segundo Plano

Inicia la API HTTP local para integrarla con tus agentes o herramientas:

```bash
ane-harness serve --port 8765
```

![Ilustración conceptual: system prompt y payload a través del filtro hacia un payload limpio — el pipeline de filtrado del harness](docs/ane-proxy-tracker-concept.jpg)

*Ilustración conceptual — el panel de la imagen es arte gráfico, no una captura de una herramienta real.*


---

## Uso desde SDK de Python

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. Inicializar pipeline
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. Registrar e indizar repositorio
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. Seleccionar contexto con límite de tokens
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. Serializar para el proveedor de LLM deseado
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Packed {package.metrics['selected_tokens']} tokens (cut {package.metrics['tokens_removed']} tokens)")
```

---


![Ilustración conceptual: baseline pesado frente a harness ligero — menos tokens, precisión intacta](docs/ane-concept-dashboard.jpg)

*Figura resumen medida — medianas de `benchmarks/reports/phase5-ab-evaluation.json` (frozen eval split, 18 tareas, Arm B deterministic): 3.213 → 782 tokens (recorte del 60,47 %), min required recall 1,0.*

## Licencia

Licencia MIT. Diseñado para inteligencia local, privacidad del desarrollador y control eficiente del consumo de tokens.
