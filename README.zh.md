# ⚡ ane-context-harness

[英语](README.md) · [越南语](README.vi.md) · [中文](README.zh.md) · [法语](README.fr.md) · [西班牙语](README.es.md) · [日语](README.ja.md) · [韩语](README.ko.md)

> **将智能体读取的上下文削减 60% 以上，保留每一行必要代码，并在 4ms 内完成上下文选取 — 完全离线运行于本机。**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## 这是什么？

当你 vibe coding 或运行 AI 智能体（Cursor、Claude Code、OpenCode、Cline、Windsurf、Aider）时，把整个代码库塞进 LLM 上下文窗口既**慢、浪费，又危险**：
- **臃肿的上下文：** 每一轮都把整份文件铲进去，会把模型埋在无关样板代码里 — 而且无论是否复用，提供商都会按 token 计费。
- **更慢的响应：** 预填充成千上万行无用内容时，LLM 的首 token 时间会爬行般变慢。
- **迷失在中间：** 模型被无关样板代码淹没时会幻觉，或漏掉缺陷。
- **密钥泄漏：** 无意中把 `.env` 密钥或 AWS 凭证发给第三方模型提供商。

**ane-context-harness** 是一个轻量、本地优先的上下文引擎，夹在你的代码库和编程智能体之间。在 **~3 milliseconds** 内，它索引仓库、提取符号层级（函数、接口、类型）、剔除噪声、脱敏密钥，并只打包智能体完成任务真正需要的高价值代码证据。

> 名称中的 `ane` 是历史遗留；它**不是**依赖。已发布路径是纯 CPU，可运行于 macOS Apple Silicon、macOS Intel 和 Linux。硬件加速位于单独的私有发行版中。

零外部网络调用。100% 私密且离线。

---

## 真实基准测试结果

在冻结评测划分（`benchmarks/splits.json`）上，跨越 **30 benchmark tasks**（10 个 small、10 个 typical、10 个 difficult），覆盖合成 Python 和 TypeScript 代码库进行评估：

| 指标 | 不使用 Harness（完整仓库转储） | 使用 Harness（确定性） | 对你意味着什么 |
|---|---|---|---|
| **上下文 Token 中位数** | **3,213 tokens** | **782 tokens** | **向 LLM 少发送 60.47%** |
| **必要证据召回率** | 1.0 (100%) | **1.0 (100%)** | **从未遗漏任何一段关键代码** |
| **上下文选取速度** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **亚 4ms 的本地响应 — 比网络快 100x** |
| **峰值 Token 节省** | 0% | **Up to 90.32%** | **在针对性的配置与设置任务上最多节省 ~90%** |
| **排序准确率 (nDCG@10)**| n/a | **0.849** | **把最关键的函数排在最前面** |
| **密钥脱敏** | 0% (leaks all secrets) | **100% local redaction** | **`.env`、AWS 密钥和证书永远不会离开你的机器** |
| **每任务派生成本** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **按所述费率每任务少发送 ~75% — 账单本身随提供商复用而非重读的程度而变化** |

*(延迟与内存在 Apple Silicon / CPU 上本地测得；成本和 TTFT 数字按所述 token 费率派生；方法论与可复现日志见 `benchmarks/reports/` 和 `benchmarks/logs/`)。*

### 示例任务明细

| 任务类型 | 示例任务 | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **设置与配置** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **规则与逻辑** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **缺陷修复（Python）** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript 架构**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **复杂多文件购物车** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Token 节省，实测（当前 main）

![逐任务基线 vs 发送 token（最低召回率 1.0），外加相同打包格式的中位数（JSON / markdown / compact）](docs/token-savings.png)

仅用公开函数测得（`scripts/measure_token_savings.py`，冻结评测划分，一个钉死的计数器 — 用 `PYTHONPATH=src python3 scripts/measure_token_savings.py` 复现，用 `scripts/plot_token_savings.py` 绘图）。同一份证据，三种渲染；渲染从不触及选取。

### 同一练习对照真实工具（无密钥、无账号）

![选取中位数与相同打包格式中位数：harness select vs headroom rewrite vs evidence-JSON / markdown / real TOON / compact](docs/same-exercise-comparison.png)

任何对手都能跑的透传测试：18 个评测任务，一个计数器。Headroom 0.39.1 和真正的 TOON 编码器在本地运行（`pip install headroom-ai toon-format`，然后 `PYTHONPATH=src python3 scripts/bench_same_exercise.py`，用 `scripts/plot_same_exercise.py` 绘图）。任务盲目改写比选取发送得更多，且没有存活门控；真正的 TOON 在多行代码上退回逐行映射，而我们的 compact 用 CSV 表头加逐字行。

---

## 开发者和 Vibecoder 为何喜欢它

- 💰 **每任务更少上下文，输出稳定：** 跳过与提示无关的文件 — 稳定输出让提供商复用已读内容，而不是再次计费。Cut% 衡量的是本地上下文削减，绝不是你的账单。
- ⚡ **即时（~3ms）延迟：** 完全以原生 Python 和 C 扩展在你的 Mac 或 Linux 机器上本地运行。
- 🎯 **精准定位：** 将 AST 符号声明（类、TypeScript 接口、枚举、函数）与 BM25 词法搜索以及按 token 预算的分数优先打包相结合。
- 🛡️ **零泄漏密钥消毒：** 在渲染提示之前，自动扫描并脱敏 AWS 密钥、私有 RSA/PEM 密钥、`.env` 文件以及高熵密钥，替换为稳定的请求作用域占位符。
- 🔌 **通用智能体支持：** 开箱即用适配器，支持 **Anthropic Messages**（带提示缓存断点）、**OpenAI Responses**、**OpenAI-Compatible chat**，以及干净的 **Markdown**。

---

## 工作原理

![上下文打包总览：LLM 收到什么、任务如何改写成词项、保留/丢弃规则、原因字典、打包上限、历史](docs/context-packing-overview.png)

一页海报由真实流水线生成（`scripts/plot_packing_overview.py`）：任务词改写成打分词项，强制钉住的内容始终放行，酌情卡片在预算下按分数优先打包，每张留下的卡片都带着你可以争辩的原因。这个百分比表示我们比本来能发送的全部内容少发了多少 — 账单本身随提供商复用而非重读的程度而变化。

---

## 快速开始（60 Seconds）

### 1. 安装

需要在 macOS 或 Linux 上使用 Python 3.13 或 3.14：

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

验证安装：
```bash
ane-harness health
```

### 1b. 一键安装 + 实证（采用门控）

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` 是无标注的：它报告中位数削减 + p50 延迟以及
`recall: not_applicable`。召回率证明需要人工标注任务（冻结的
`benchmarks/splits.json` 机制）；无标注运行从不声称
召回率。

### 2. 索引你的代码库

将任意本地文件夹或仓库索引到本地 SQLite 存储（增量且极快）：

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. 为提示选取相关上下文

获取为你的编程任务量身定制的、紧凑且受 token 预算约束的 Markdown 包：

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. 跨多个提示记录前后上下文削减（`update`）

对一批任务运行选取（JSONL 文件或 stdin），打印并记录
前后 token 预算。本地，无网络：

```bash
# from a JSONL file (one {"task": "..."} or bare task per line)
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

示例输出：

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

逐任务行也会以 JSONL 追加到 `--log`（已被 gitignore）。
每次运行都会向 stderr 打印 **诚实免责声明**：*"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

每次运行还会向 stderr 打印一行削减页脚（stdout JSON 中的
`summary` 键也是同一行），例如
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`。只用白话 —
没有行话，没有 `#` 标题标记。总计在本地累积（只计次数，不含
任务文本）— 随时用
`ane-harness daily` 查看，或在每次 shell 退出时用
`eval "$(ane-harness shell-init)"` 写入你的 `.zshrc`/`.bashrc`。

智能体可通过捆绑技能获得相同行为且无依赖：
`skills/ane-harness/SKILL.md` — 把它复制到智能体的 skills 目录
后，每个任务结束后会自动显示削减总计，无需其他设置。对于
OpenCode/Claude/兼容智能体的宿主，它也可以全局生效，无需按项目
安装：`~/.config/opencode/skills/`、`~/.claude/skills/`，或
`~/.agents/skills/`（新会话会自动拾取）。

### 3c. 无原生集成的智能体代理模式（`proxy`）

从 stdin 管道传入任务（每行一个 `{"task": "..."}` 或裸任务），
在 stdout 拿回证据 Markdown — 不需要 skill、MCP 或 HTTP：

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout 是纯 Markdown（每个任务一份文档，用 `---` 分隔，带
`<!-- ane-harness task N/M ... -->` 边界）；逐任务削减
页脚走 stderr。当 repo-id 已经索引过时，可省略 `--repo`。

### 4. 或作为本地后台服务器运行

> **智能体：不要在智能体回合内运行这个。** `serve`（和 `mcp` 一样）
> 永远不会退出 — 启动它的工具调用会永久阻塞，于是该回合
> 永远完不成，之后的每个提示都排队等在后面。裸
> `update`/`proxy` 且没有 `--tasks-file` 时，在交互式终端会以
> exit 2 退出并给出提示，而不是等待 stdin。在智能体回合内只使用
> 一次性命令（`index`、`select`、`prove`、`daily`、`health`）。从真正的终端
> 分离运行服务器
> （`nohup ane-harness serve --port 8765 &`），或者干脆不要运行。

启动本地 HTTP API（可挂到你的智能体或工具上）：

```bash
ane-harness serve --port 8765
```

可用端点：
- `GET  /v1/health` — 系统状态、计算模式和配置文件
- `POST /v1/repositories/index` — 索引或更新仓库
- `POST /v1/context/select` — 为任务检索优化后的上下文
- `POST /v1/context/compress-output` — 将冗长的测试/构建日志压缩成干净的失败摘要

---

## 在 Python 中使用

你也可以在自己的 AI 智能体工作流中直接使用该 harness：

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

## 工作原理

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

1. **符号感知的 AST 分块：** 不是笨拙地按行切割，而是解析文件中的真实代码构造（类、方法、TypeScript 类型/接口/枚举）。
2. **确定性检索：** 快速词法 BM25 检索，由符号词项守卫、子 token 拆分和复数折叠过滤。
3. **分数优先的预算打包：** 上下文被贪心打包，严格拟合你指定的 token 预算（例如 1,200 tokens），保证强制证据永不被截断。
4. **密钥检测与隐私围栏：** 规范排除模式（`.env*`、`.aws/**`、`*.pem` 等）永不被读取，正则 + 熵分类器用稳定占位符替换敏感 token。
5. **噪声压缩：** 冗长的工具输出（测试轨迹、终端日志）被折叠成紧凑且保留信号的摘要。

### 硬件加速：单独的私有发行版

名称里有 `ane`，但运行该 harness **不要求也不声称需要专用硅片**。
已发布引擎是纯确定性 CPU（Python +
SQLite），在 macOS Apple Silicon、macOS Intel 和 Linux 上运行方式相同。
神经硬件加速另行维护，不属于
本仓库。

---

## 技术规格与严谨性

面向关心数值严谨性的研究者、架构师和技术负责人：

- **冻结基准划分：** 所有发布数字都跑在冻结的 18 任务评测划分上（`benchmarks/splits.json`，种子 `20261002`）。调参严格隔离在 dev 划分。
- **确定性 Token 估计器：** Token 计数使用钉死的估计器（`TOKEN_ESTIMATOR_VERSION="2"`），因此数字在不同机器和 Python 版本间 100% 可复现，没有外部分词器漂移。
- **嵌入策略：** 基于本地成本/延迟权衡，v0.1 有意排除嵌入。见 [ADR-002](docs/adr-002-embedding-go-no-go.md)。
- **发布证据包：** 带校验和的发布证据通过 `ane-harness evidence verify ane-context-harness-evidence-v0.1` 进行密码学验证。

---

## 运行测试套件

```bash
# Run all 258 unit, integration, and security tests
python3 -m pytest -q

# Run concurrent A/B benchmark evaluation
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## 许可证

MIT License。为本地智能、开发者隐私和合理的 token 预算而设计。