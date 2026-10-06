# ⚡ ane-context-harness

[英语](README.md) · [越南语](README.vi.md) · [中文](README.zh.md) · [法语](README.fr.md) · [西班牙语](README.es.md) · [日语](README.ja.md) · [韩语](README.ko.md)

> **把智能体读取的上下文削减 60% 以上，保留每一行必需内容，并在 4ms 内完成上下文选择 —— 完全离线运行在你的本机上。**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## 这是什么？

当你在 vibe-code，或运行 AI 智能体（Cursor、Claude Code、OpenCode、Cline、Windsurf、Aider）时，把整个代码库塞进 LLM 上下文窗口既**慢、浪费，又危险**：
- **上下文膨胀：** 每一轮都把整份文件塞进去，会把模型埋进无关样板代码 —— 而且无论是否复用，提供商都会按 token 计费。
- **响应更慢：** 预填充成千上万行无用内容时，LLM 的首 token 时间会拖得很长。
- **迷失在中间：** 模型被无关样板淹没时会幻觉，或漏掉真正的 bug。
- **密钥泄漏：** 无意中把 `.env` 密钥或 AWS 凭证发给第三方模型提供商。

**ane-context-harness** 是一个轻量、本地优先的上下文引擎，位于你的代码库与编码智能体之间。在 **约 3 毫秒**内，它会索引仓库、提取符号层级（函数、接口、类型）、剥离噪声、脱敏密钥，并只打包智能体完成任务真正需要的高价值代码证据。

> 名称里的 `ane` 是历史遗留；它**不是**依赖。已发布路径是纯 CPU，可在 macOS Apple Silicon、macOS Intel 和 Linux 上运行。硬件加速位于单独的私有发行版中。

零外部网络请求。100% 私密且离线。

---

## 真实基准结果

在冻结评估划分（`benchmarks/splits.json`）上，跨合成 Python 与 TypeScript 代码库评估了 **30 个基准任务**（10 个小型、10 个典型、10 个困难）：

| 指标 | 无 Harness（完整仓库转储） | 有 Harness（确定性） | 对你意味着什么 |
|---|---|---|---|
| **Median Context Tokens** | **3,213 tokens** | **782 tokens** | **发给 LLM 的量少 60.47%** |
| **Required-Evidence Recall** | 1.0 (100%) | **1.0 (100%)** | **从未漏掉任何一段关键代码** |
| **Context Selection Speed** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **本地亚 4ms 响应 —— 比网络快 100 倍** |
| **Peak Token Savings** | 0% | **Up to 90.32%** | **在针对性的配置与设置任务上最多节省约 90%** |
| **Ranking Accuracy (nDCG@10)**| n/a | **0.849** | **把最关键的函数放在最前面** |
| **Secret Redaction** | 0% (leaks all secrets) | **100% local redaction** | **`.env`、AWS 密钥和证书永远不会离开你的机器** |
| **Derived Cost per Task** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **按所述费率每任务少发送约 75% —— 账单本身随提供商复用而非重读的程度而变化** |

*（延迟与内存在 Apple Silicon / CPU 上本地测得；成本与 TTFT 数字按所述 token 费率推导；方法与可复现日志见 `benchmarks/reports/` 和 `benchmarks/logs/`）。*

### 示例任务分解

| 任务类型 | 示例任务 | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **设置与配置** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **规则与逻辑** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Bug 修复（Python）** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript 架构**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **复杂多文件购物车** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Token 节省，实测（当前 main）

如何读这张图：每个任务都在问工具“这次任务 AI 该读什么？”。左图按任务规模对比：若发送整个代码库会发出多少文本（灰色），以及 harness 实际挑选了多少（绿色）—— 绿色柱上方的数字是你现在发送的量以及缩小了多少。更难的任务需要更多文件，所以绿色柱会变高 —— 但所需文件**每一次都被保留**，这才是关键：只有在不漏掉重要内容时，更小才是好事。右图展示同一次选择的三种发送方式 —— 完整细节、可读的中间档、最短包装 —— 更短更便宜，而且包装从不改变*挑选了什么*。

![按任务规模更少需要阅读的内容，以及同一答案的三种包装](docs/token-savings.png)

用 `PYTHONPATH=src python3 scripts/measure_token_savings.py` 测量，用 `scripts/plot_token_savings.py` 绘图（冻结评估划分，一个固定的 token 计数器）。

### 同一练习对真实工具（无密钥、无账号）

如何读这张图：这是同一把尺子上的 18 个任务赛跑 —— “中间那个任务占多少 token，有没有丢掉需要的东西？”。第一张图是头条：全部发送是昂贵的默认做法，外部改写工具实际发送的比需要的还多，并且曾经丢掉评分器要求的配置文件（标记为 FAIL），而我们的两种模式最短，并且每次都保留了所需文件（PASS）。第二张图展示背后的细节 —— 仅选择能省多少，以及同一选择再换更短包装还能再缩多少。这里的 PASS/FAIL 只表示一件事：基准评分器认定必需的片段是否出现在打包结果中。

![同样的 18 个任务：全部发送 vs 外部改写工具 vs 我们](docs/head-to-head.png)

![选择中位数以及同一打包的四种包装，附带逐任务示例](docs/same-exercise-comparison.png)

复现：`pip install headroom-ai toon-format`，然后 `PYTHONPATH=src python3 scripts/bench_same_exercise.py`，用 `scripts/plot_same_exercise.py` 绘图。任务盲改写发送的比选择更多，且没有存活门控；真正的 TOON 编码器在多行代码上会回退到按行映射，而我们的紧凑格式保留 CSV 表头与逐字行。

### 对话节省，实测

如何读：一个任务从来不是一个问题 —— 智能体会提问，然后跟进，然后验证。该基准按三种方式重放每个任务相同的 3 轮对话：每轮发送整个代码库（149,490 tokens）、一份裁剪后的打包（17,094），以及三份携带式打包，每次跟进都保留先前轮次找到的全部内容（51,940）。携带式对话大约只发送无 harness 成本的**三分之一** —— 少 97,550 tokens，少 65.3% —— 且所需文件在全部 72 轮中都存活（每轮 recall 1.0；丢掉所需文件的一轮会让对话脱轨，所以该门控是承重的，不是装饰）。

复现：`PYTHONPATH=src python3 scripts/bench_conversation.py`（冻结评估划分，一个固定的 token 计数器；写入 `benchmarks/reports/conversation-bench-eval.json`）。边界说清楚：没有模型阅读这些打包，跟进是固定字符串而非真实智能体反应，没有计费，也没有真正完成任何任务。它测量的是我们喂进去的那一半 —— 挑选与携带 —— 而不是循环本身。

### 每个文件会发生什么

四条已文档化的规则，不涉及模型，没有例外：你钉住的文件（或评分器要求的文件）**始终按字节精确**传输。代码、配置和 diff 保留结构 —— 选择器挑选整个符号，从不改写它们。只有**日志和嘈杂的工具输出**会被折叠（重复的进度行、重复的 traceback、安装垃圾会折成一行摘要，说明去掉了什么）。散文按挑选原样传输，从不改写 —— 没有神经改写器，所以没有什么能把你的文档改写成它没说过的话。每个打包都会按文件列出应用了哪条规则 —— 查看任意报告中的 `diagnostics.routing` 并与之争论。

---

## 开发者与 Vibecoder 为什么喜欢它

- 💰 **每任务更少上下文，输出稳定：** 跳过与提示无关的文件 —— 稳定输出让提供商复用已读内容，而不是再次收费。Cut% 衡量的是本地上下文削减，从来不是你的账单。
- ⚡ **即时（约 3ms）延迟：** 完全在你的 Mac 或 Linux 机器上以原生 Python 和 C 扩展运行。
- 🎯 **精确定位：** 将 AST 符号声明（类、TypeScript 接口、枚举、函数）与 BM25 词法搜索以及按 token 预算的分数优先打包相结合。
- 🛡️ **零泄漏密钥脱敏：** 在渲染提示之前，自动扫描并脱敏 AWS 密钥、RSA/PEM 私钥、`.env` 文件和高熵密钥，替换为稳定的请求作用域占位符。
- 🔌 **通用智能体支持：** 开箱即用适配器，支持 **Anthropic Messages**（带提示缓存断点）、**OpenAI Responses**、**OpenAI 兼容 chat**，以及干净的 **Markdown**。

---

## 工作原理

![上下文打包概览：LLM 收到什么、任务如何改写成词项、保留/丢弃规则、原因字典、打包限制、历史](docs/context-packing-overview.png)

一页海报由真实流水线生成（`scripts/plot_packing_overview.py`）：任务词改写成打分词项，强制钉住的内容始终放行，可自由卡片按分数优先在预算内打包，每张保留的卡片都带着你可以争论的原因。百分比表示我们比所能发送的全部内容少发了多少 —— 账单本身随提供商复用而非重读的程度而变化。

---

## 快速开始（60 秒）

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

### 1b. 一键安装 + 证明（采用门槛）

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` 是无标注的：它报告中位数削减 + p50 延迟以及
`recall: not_applicable`。召回证明需要人工标注任务（冻结的
`benchmarks/splits.json` 机制）；无标注运行从不声称
召回。

### 2. 索引你的代码库

将任意本地文件夹或仓库索引到本地 SQLite 存储（增量且极快）：

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. 为提示选择相关上下文

获取针对你的编码任务裁剪的、受 token 预算约束的紧凑 Markdown 包：

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. 跨多个提示记录前后上下文削减（`update`）

对一批任务（JSONL 文件或 stdin）运行选择，并打印 + 记录
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

逐任务行也会以 JSONL 追加到 `--log`（已 gitignore）。
每次运行都会向 stderr 打印**诚实免责声明**："*local measurements over the
given repo; redaction does not guarantee all secrets are caught.*"

每次运行还会向 stderr 打印一行削减页脚（stdout JSON 中的
`summary` 键是同一行），例如
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`。只用白话 ——
没有行话，没有 `#` 标题标记。总计在本地累积（仅计数，不含
任务文本）—— 随时可用
`ane-harness daily` 查看，或在每次 shell 退出时通过在 `.zshrc`/`.bashrc` 中加入
`eval "$(ane-harness shell-init)"` 查看。

智能体可通过捆绑的 skill 获得同样的无依赖行为：
`skills/ane-harness/SKILL.md` —— 把它复制到智能体的 skills 目录，
每次任务后削减总计会自动出现，无需其他设置。对
OpenCode/Claude/兼容智能体的宿主，它也可以全局使用，无需按项目
安装：`~/.config/opencode/skills/`、`~/.claude/skills/`，或
`~/.agents/skills/`（新会话会自动拾取）。

### 3c. 无原生集成的智能体的代理模式（`proxy`）

从 stdin 管道输入任务（每行一个 `{"task": "..."}` 或裸任务），
在 stdout 得到证据 Markdown —— 不需要 skill、MCP 或 HTTP：

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout 是纯 Markdown（每个任务一份文档，用 `---` 分隔，带
`<!-- ane-harness task N/M ... -->` 边界）；逐任务削减
页脚发到 stderr。当 repo-id 已经索引时，可省略 `--repo`。

### 4. 或作为本地后台服务器运行

> **智能体：不要在智能体回合内运行这个。** `serve`（和 `mcp` 一样）
> 永远不会退出 —— 启动它的工具调用会永久阻塞，因此该回合
> 永远完不成，之后的每个提示都会排队等在后面。在交互式终端上，裸的
> `update`/`proxy` 且没有 `--tasks-file` 会以退出码
> 2 结束并给出提示，而不是等待 stdin。在智能体回合内只使用
> 一次性命令（`index`、`select`、`prove`、`daily`、`health`）。从真实终端
> 分离运行服务器
> （`nohup ane-harness serve --port 8765 &`），或者干脆不要运行。

启动本地 HTTP API（可接到你的智能体或工具）：

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

## 它如何工作

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

1. **符号感知的 AST 分块：** 不是笨拙地按行切分，而是解析文件中的真实代码结构（类、方法、TypeScript 类型/接口/枚举）。
2. **确定性检索：** 快速词法 BM25 检索，经符号词项守卫、子 token 拆分和复数折叠过滤。
3. **分数优先的预算打包：** 上下文被贪心打包，严格落入你指定的 token 预算（例如 1,200 tokens），保证强制证据永不被截断。
4. **密钥检测与隐私围栏：** 规范排除模式（`.env*`、`.aws/**`、`*.pem` 等）从不被读取，正则 + 熵分类器用稳定占位符替换敏感 token。
5. **噪声压缩：** 冗长的工具输出（测试追踪、终端日志）被折叠成保留信号的紧凑摘要。

### 硬件加速：单独的私有发行版

名称包含 `ane`，但运行该 harness **不需要也不声称任何专用硅片**。
已发布引擎是纯确定性 CPU（Python +
SQLite），在 macOS Apple Silicon、macOS Intel 和 Linux 上运行方式相同。
神经硬件加速另行维护，不属于
本仓库。

---

## 技术规格与严谨性

面向关心数值严谨性的研究者、架构师和技术负责人：

- **冻结基准划分：** 所有发布数字都在冻结的 18 任务评估划分上运行（`benchmarks/splits.json`，种子 `20261002`）。调优严格隔离在 dev 划分。
- **确定性 Token 估计器：** Token 计数使用固定估计器（`TOKEN_ESTIMATOR_VERSION="2"`），因此数字在机器和 Python 版本之间 100% 可复现，没有外部分词器漂移。
- **嵌入策略：** 基于本地成本/延迟权衡，v0.1 有意排除嵌入。见 [ADR-002](docs/adr-002-embedding-go-no-go.md)。
- **发布证据包：** 经校验和的发布证据通过 `ane-harness evidence verify ane-context-harness-evidence-v0.1` 进行密码学验证。

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