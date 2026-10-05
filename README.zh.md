# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **将你的 AI Agent 读取的上下文内容减少 60% 以上，同时保留所有必要的代码行，并在 4 毫秒内完成上下文选择——完全在你的本地机器上离线运行。**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## 这是什么？

当你进行“氛围编程”（vibe-coding）或运行 AI Agent（如 Cursor、Claude Code、OpenCode、Cline、Windsurf、Aider）时，将整个代码库塞进 LLM 上下文窗口不仅**缓慢、浪费，而且存在安全隐患**：
- **上下文臃肿：** 每次对话都灌入整个文件，会让模型淹没在无关的样板代码中，而且模型供应商会对每一个 Token（无论是否被重复利用）进行计费。
- **响应变慢：** 当需要预填充数千行无关代码时，LLM 的首字延迟（TTFT）会大幅增加。
- **迷失在上下文中：** 当被无关代码淹没时，模型会出现幻觉或漏掉关键 Bug。
- **密钥泄露：** 可能在无意中将 `.env` 里的私钥或 AWS 凭证发送给第三方模型提供商。

**ane-context-harness** 是一个轻量级、优先考虑本地的上下文引擎，位于你的代码库和编码 Agent 之间。它只需 **3 毫秒左右** 即可索引你的仓库，提取符号层级（函数、接口、类型），剔除噪音，屏蔽敏感信息，并仅封装 Agent 完成任务所需的“高价值证据”。

> `ane` 这个名字具有历史原因，它**不是**项目依赖项。该工具纯粹使用 CPU 运行，支持 macOS Apple Silicon、macOS Intel 和 Linux。硬件加速功能存在于单独的私有发行版中。

零外部网络调用。100% 隐私保护，完全离线。

---

## 真实基准测试结果

在我们的固定评估集 (`benchmarks/splits.json`) 上，对 30 个基准测试任务（10 个简单、10 个典型、10 个困难）进行了评估：

| 指标 | 不使用 Harness（全量转储） | 使用 Harness（确定性） | 对你的意义 |
|---|---|---|---|
| **中位数上下文 Token** | **3,213 tokens** | **782 tokens** | **向 LLM 发送的内容减少了 60.47%** |
| **关键证据召回率** | 1.0 (100%) | **1.0 (100%)** | **绝不错过任何一段关键代码** |
| **上下文选择速度** | ~0.01 ms (原始转储) | **3.05 ms – 3.83 ms** | **亚 4 毫秒的本地响应——比网络快 100 倍** |
| **峰值 Token 节省** | 0% | **高达 90.32%** | **在配置和设置类任务中节省高达 90%** |
| **排序准确度 (nDCG@10)**| n/a | **0.849** | **将最关键的函数放在最显眼的位置** |
| **敏感信息屏蔽** | 0% (泄露所有私钥) | **100% 本地屏蔽** | **`.env`、AWS 密钥和证书永远不会离开你的机器** |
| **单任务派生费用** *(按 $3/M 计算)* | ~$0.0096 / 任务 | **~$0.0023 / 任务** | **在相同定价下单任务费用减少约 75%——你的账单费用直接取决于供应商对已读内容的复用程度，而非重复读取** |

*(延迟和内存数据在 Apple Silicon / CPU 上进行本地测量；成本和 TTFT 数据根据指定的 Token 费率推算得出；方法论和可复现日志位于 `benchmarks/reports/` 和 `benchmarks/logs/` 中)。*

### 示例任务细分

| 任务类型 | 示例任务 | 原始 Token | Harness Token | 缩减率 | 召回率 | 选择延迟 |
|---|---|---|---|---|---|---|
| **设置与配置** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **规则与逻辑** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Bug 修复 (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript 架构** | `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **复杂多文件购物车** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Token 节省实测 (当前主分支)

![基准测试对比图](docs/token-savings.png)

使用仅限公共函数进行测量（使用 `scripts/measure_token_savings.py`，固定评估集，单点计数器——通过 `PYTHONPATH=src python3 scripts/measure_token_savings.py` 复现，通过 `scripts/plot_token_savings.py` 绘图）。证据相同，渲染方式有三种；渲染过程不涉及选择逻辑。

### 与真实工具的对比测试 (无密钥，无账号)

![选择对比图](docs/same-exercise-comparison.png)

所有竞争对手都可以运行的直通测试：18 个评估任务，单计数器。Headroom 0.39.1 和 real TOON 编码器运行在本地（运行 `pip install headroom-ai toon-format`，然后执行 `PYTHONPATH=src python3 scripts/bench_same_exercise.py`，通过 `scripts/plot_same_exercise.py` 绘图）。任务盲区重写发送的内容比选择后的内容多，且没有保留筛选逻辑；real TOON 在处理多行代码时会回退到逐行映射，而我们的紧凑格式保留了带逐字行的 CSV 标题。

---

## 开发者与“氛围编程者”为何喜爱它

- 💰 **更少的单任务上下文，更稳定的输出：** 跳过与提示词无关的文件——稳定的输出使模型提供商能够复用已读内容，而不是反复计费。缩减百分比衡量的是本地上下文的减少，而非仅仅是你的账单。
- ⚡ **毫秒级 (~3ms) 延迟：** 完全在 Mac 或 Linux 上以原生 Python 和 C 扩展运行。
- 🎯 **精准定位：** 将 AST 符号声明（类、TypeScript 接口、枚举、函数）与 BM25 词汇搜索以及基于 Token 预算的评分优先打包相结合。
- 🛡️ **零泄露敏感信息清理：** 在提示词渲染前，自动扫描并使用稳定的请求级占位符屏蔽 AWS 密钥、私有 RSA/PEM 密钥、`.env` 文件等高熵敏感信息。
- 🔌 **通用 Agent 支持：** 提供内置适配器，支持 **Anthropic Messages**（带有提示词缓存断点）、**OpenAI Responses**、**OpenAI 兼容聊天**以及纯净的 **Markdown**。

---

## 工作原理

![上下文打包流程图](docs/context-packing-overview.png)

由真实流水线生成的单页图表（`scripts/plot_packing_overview.py`）：任务词被重写为带分值的术语，强制固定的内容始终包含在内，可选的卡片按评分优先级打包，且每张卡片都带有你可查阅的保留理由。百分比表示我们比可能发送的完整内容减少了多少——你的账单费用直接取决于供应商对已读内容的复用程度。

---

## 快速入门 (60 秒)

### 1. 安装

需要 macOS 或 Linux 上的 Python 3.13 或 3.14：

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

验证安装：
```bash
ane-harness health
```

### 1b. 一键安装 + 验证（采用准入）

```bash
# 索引、安装 Agent 技能、冒烟测试（打印一行摘要）
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# 验证：在你自己的仓库上进行缩减/延迟测试（5 个预置任务，无需标签）
ane-harness prove --repo /path/to/your/project --repo-id my-project
# 使用自定义任务：--tasks-file prompts.jsonl
# 指定报告目录：--out /tmp/prove-report
```

`prove` 是无标签的：它报告中位缩减率 + p50 延迟，但 `recall: not_applicable`。召回率证明需要手动标注的任务（使用固定的 `benchmarks/splits.json` 机制）；无标签运行不声明召回率。

### 2. 索引你的代码库

将任何本地文件夹或仓库索引到本地 SQLite 存储中（增量且速度极快）：

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. 为提示词选择相关上下文

获取专为你当前编码任务定制的、符合 Token 预算的紧凑 Markdown 包：

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

### 3b. 记录多次提示词前后的上下文缩减情况 (`update`)

对一批任务（JSONL 文件或标准输入）运行选择操作，并打印/记录 Token 预算的前后对比。本地运行，无需网络：

```bash
# 从 JSONL 文件读取（每行一个 {"task": "..."} 或单纯的任务文本）
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

输出示例：

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

每个任务的行也会以 JSONL 格式追加到 `--log` 文件（已在 gitignore 中）。
**诚信免责声明**：每次运行都会打印到标准错误 stderr —— *"local measurements over the given repo; redaction does not guarantee all secrets are caught."*

每次运行还会打印一行缩减总结到底部，例如：
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`。仅纯文本，无术语，无 `#` 标题。总量在本地累积（仅计数，不保存任务文本）——可通过 `ane-harness daily` 随时查看，或在 `.zshrc`/`.bashrc` 中通过 `eval "$(ane-harness shell-init)"` 在每次 Shell 退出时显示。

Agent 可通过捆绑的技能包获取相同行为：`skills/ane-harness/SKILL.md` —— 将其复制到 Agent 的技能目录中，每次任务完成后缩减数据会自动显示，无需额外配置。对于 OpenCode/Claude/兼容代理的主机，它也全局生效：`~/.config/opencode/skills/`、`~/.claude/skills/` 或 `~/.agents/skills/` (新会话会自动加载)。

### 3c. 针对无原生集成 Agent 的代理模式 (`proxy`)

通过标准输入传入任务（每行一个 `{"task": "..."}` 或任务文本），在标准输出中获取 Markdown 证据 —— 无需技能包、MCP 或 HTTP：

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

标准输出为纯 Markdown（每个任务一份文档，以 `---` 分隔，带有 `<!-- ane-harness task N/M ... -->` 边界）；每个任务的缩减总结输出到标准错误 stderr。当 repo-id 已索引时，可省略 `--repo` 参数。

### 4. 作为本地后台服务运行

> **Agent 提示：不要在 Agent 运行过程中启动此服务。** `serve`（类似 `mcp`）永远不会退出 —— 发起此工具调用的进程会永久阻塞，导致任务无法完成，后续提示词都会排队等待。在交互式终端中，不带 `--tasks-file` 的 `update`/`proxy` 命令在退出时会返回状态码 2 并给出提示，而不是等待输入。在 Agent 任务内部，请仅使用一次性命令（`index`, `select`, `prove`, `daily`, `health`）。若要运行服务，请将其从终端分离运行 (`nohup ane-harness serve --port 8765 &`)。

启动本地 HTTP API（可连接到你的 Agent 或工具）：

```bash
ane-harness serve --port 8765
```

可用接口：
- `GET  /v1/health` — 系统状态、计算模式和配置
- `POST /v1/repositories/index` — 索引或更新仓库
- `POST /v1/context/select` — 为任务检索优化后的上下文
- `POST /v1/context/compress-output` — 将冗长的测试/构建日志压缩为精简的错误摘要

---

## 在 Python 中使用

你也可以直接在自己的 AI Agent 工作流中使用本工具：

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. 初始化流水线
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. 索引仓库
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. 按预算选择上下文
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. 直接序列化为你使用的 LLM 提供商格式
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Packed {package.metrics['selected_tokens']} tokens (cut {package.metrics['tokens_removed']} tokens)")
```

---

## 工作原理

```
                        你的代码库
                             │
                     AST & 符号解析器
               (Python 函数, TS 接口)
                             │
                      行级分块器
                             │
                      本地 SQLite 存储
                             │
用户提示词 ──────►   BM25 词汇搜索
                             │
                   评分优先预算打包器
                  (强制保留 + MMR)
                             │
                  本地敏感信息清理器
              (屏蔽 .env, AWS 密钥, 证书)
                             │
               提供商适配器 (Anthropic/OpenAI)
                             │
                   紧凑、精准的上下文
```

1. **感知符号的 AST 分块：** 不进行死板的行切分，而是解析代码的实际结构（类、方法、TypeScript 类型/接口/枚举）。
2. **确定性检索：** 基于符号项保护、子词拆分和词形还原的快速 BM25 词汇检索。
3. **评分优先预算打包：** 上下文以贪婪方式打包以严格适应指定的 Token 预算（例如 1,200 tokens），确保强制证据永不被截断。
4. **敏感信息检测与隐私墙：** 规范的排除模式（`.env*`, `.aws/**`, `*.pem` 等）绝不会被读取，Regex + 熵分类器将敏感 Token 替换为稳定的占位符。
5. **噪音压缩：** 将冗长的工具输出（测试追踪、终端日志）折叠为精简的信号保留摘要。

### 硬件加速：单独的私有发行版

虽然名称包含 `ane`，但运行本工具**不需要、也不声称需要专门的硅片硬件**。随附引擎是纯粹的确定性 CPU 运行环境（Python + SQLite），在 macOS Apple Silicon、macOS Intel 和 Linux 上运行效果完全相同。神经网络硬件加速功能另行维护，不属于本仓库的一部分。

---

## 技术规格与严谨性

针对关注数值严谨性的研究人员、架构师和技术主管：

- **固定基准测试集：** 所有发布指标均在固定的 18 任务评估集上运行（`benchmarks/splits.json`，种子 `20261002`）。调优过程仅限开发集。
- **确定性 Token 估算器：** 使用锁定的估算器 (`TOKEN_ESTIMATOR_VERSION="2"`)，确保数据在不同机器和 Python 版本间 100% 可复现，不受外部 Tokenizer 漂移影响。
- **Embedding 策略：** 基于本地成本/延迟权衡，v0.1 版本有意排除了 Embedding。详见 [ADR-002](docs/adr-002-embedding-go-no-go.md)。
- **发布证据包：** 校验和发布证据通过 `ane-harness evidence verify ane-context-harness-evidence-v0.1` 进行加密验证。

---

## 运行测试套件

```bash
# 运行全部 258 个单元测试、集成测试和安全测试
python3 -m pytest -q

# 运行并发 A/B 基准评估
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## 许可协议

MIT 协议。专为本地智能、开发者隐私和合理的 Token 预算而设计。