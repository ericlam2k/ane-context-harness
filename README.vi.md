# ⚡ ane-context-harness

[Tiếng Anh](README.md) · [Tiếng Việt](README.vi.md) · [Tiếng Trung](README.zh.md) · [Tiếng Pháp](README.fr.md) · [Tiếng Tây Ban Nha](README.es.md) · [Tiếng Nhật](README.ja.md) · [Tiếng Hàn](README.ko.md)

> **Cắt hơn 60% ngữ cảnh mà agent đọc, giữ mọi dòng bắt buộc, và chọn ngữ cảnh dưới 4ms — chạy hoàn toàn offline trên máy local của bạn.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## Đây là gì?

Khi bạn vibe-code hoặc chạy AI agent (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), đưa cả codebase vào cửa sổ ngữ cảnh LLM thì **chậm, lãng phí và nguy hiểm**:
- **Ngữ cảnh phình to:** Nhét nguyên file vào mọi lượt chat chôn model dưới boilerplate không liên quan — và nhà cung cấp tính mọi token, dù có tái sử dụng hay không.
- **Phản hồi chậm hơn:** Thời gian tới token đầu của LLM lê thê khi prefill hàng nghìn dòng không cần thiết.
- **Lạc giữa đoạn giữa:** Model ảo giác hoặc bỏ sót bug khi bị chôn dưới boilerplate không liên quan.
- **Rò rỉ bí mật:** Vô tình gửi secret `.env` hoặc AWS credentials tới nhà cung cấp model bên thứ ba.

**ane-context-harness** là một context engine nhẹ, local-first, nằm giữa codebase và coding agent của bạn. Trong **~3 mili giây**, nó lập chỉ mục repo, trích xuất hệ thống symbol (hàm, interface, type), loại nhiễu, redacted secret, và đóng gói chỉ bằng chứng mã nguồn có giá trị cao mà agent thực sự cần để hoàn thành nhiệm vụ.

> Tên `ane` mang tính lịch sử; nó **không** phải một dependency. Đường dẫn được ship là thuần CPU và chạy trên macOS Apple Silicon, macOS Intel và Linux. Tăng tốc phần cứng nằm trong một bản phân phối riêng, không công khai.

Không có lời gọi mạng ngoài. 100% riêng tư và offline.

---

## Kết quả benchmark thực tế

Đánh giá trên **30 nhiệm vụ benchmark** (10 nhỏ, 10 điển hình, 10 khó) trên các codebase Python và TypeScript tổng hợp, theo split đánh giá đóng băng của chúng tôi (`benchmarks/splits.json`):

| Metric | Without Harness (Full Repo Dump) | With Harness (Deterministic) | Ý nghĩa với bạn |
|---|---|---|---|
| **Median Context Tokens** | **3,213 tokens** | **782 tokens** | **Gửi ít hơn 60.47% tới LLM** |
| **Required-Evidence Recall** | 1.0 (100%) | **1.0 (100%)** | **Không bỏ sót dù chỉ một mảnh mã nguồn then chốt** |
| **Context Selection Speed** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Phản hồi local dưới 4ms — nhanh hơn mạng 100 lần** |
| **Peak Token Savings** | 0% | **Up to 90.32%** | **Tiết kiệm tới ~90% trên các nhiệm vụ config & settings có mục tiêu** |
| **Ranking Accuracy (nDCG@10)**| n/a | **0.849** | **Đặt các hàm then chốt nhất ngay trên cùng** |
| **Secret Redaction** | 0% (leaks all secrets) | **100% local redaction** | **`.env`, AWS keys và certificate không bao giờ rời máy bạn** |
| **Derived Cost per Task** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **Gửi ít hơn ~75% mỗi nhiệm vụ ở mức giá nêu trên — hóa đơn thực tế phụ thuộc mức nhà cung cấp tái sử dụng thay vì đọc lại** |

*(Độ trễ và bộ nhớ đo local trên Apple Silicon / CPU; chi phí và số liệu TTFT được suy ra theo mức giá token đã nêu; phương pháp và log tái lập được nằm trong `benchmarks/reports/` và `benchmarks/logs/`).*

### Phân rã các nhiệm vụ mẫu

| Loại nhiệm vụ | Nhiệm vụ ví dụ | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **Settings & Config** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Rules & Logic** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Bug Fixes (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript Architecture**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Complex Multi-file Cart** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Tiết kiệm token, đo được (main hiện tại)

![Token baseline so với token gửi theo từng nhiệm vụ với min recall 1.0, cùng median định dạng gói giống nhau (JSON / markdown / compact)](docs/token-savings.png)

Đo bằng các hàm công khai (`scripts/measure_token_savings.py`, split đánh giá đóng băng, một bộ đếm được ghim — tái lập với `PYTHONPATH=src python3 scripts/measure_token_savings.py`, vẽ với `scripts/plot_token_savings.py`). Cùng bằng chứng, ba cách render; render không bao giờ đụng tới selection.

### Cùng bài tập đối chiếu công cụ thật (không key, không tài khoản)

![Median selection và median định dạng gói giống nhau: harness select vs headroom rewrite vs evidence-JSON / markdown / real TOON / compact](docs/same-exercise-comparison.png)

Bài passthrough mà đối thủ nào cũng chạy được: 18 nhiệm vụ eval, một bộ đếm. Headroom 0.39.1 và encoder TOON thật chạy local (`pip install headroom-ai toon-format`, rồi `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, vẽ với `scripts/plot_same_exercise.py`). Rewrite mù nhiệm vụ gửi nhiều hơn select và không có cổng sống sót; TOON thật fallback về mapping từng hàng trên mã nhiều dòng trong khi compact của chúng tôi giữ header CSV với hàng nguyên văn.

---

## Vì sao developer & vibecoder thích

- 💰 **Ít ngữ cảnh hơn mỗi nhiệm vụ, output ổn định:** Bỏ qua file chẳng liên quan tới prompt — và output ổn định giúp nhà cung cấp tái sử dụng những gì đã đọc thay vì tính phí lại. Cut% đo mức giảm ngữ cảnh local, không phải hóa đơn của bạn.
- ⚡ **Độ trễ tức thì (~3ms):** Chạy hoàn toàn bằng Python native và C extension local trên Mac hoặc máy Linux của bạn.
- 🎯 **Độ chính xác điểm trúng:** Kết hợp khai báo symbol AST (class, TypeScript interface, enum, hàm) với tìm kiếm lexical BM25 và packing theo điểm, theo ngân sách token.
- 🛡️ **Làm sạch secret không rò rỉ:** Tự động quét và redact AWS keys, khóa RSA/PEM riêng, file `.env` và secret entropy cao bằng placeholder ổn định theo phạm vi request trước khi render prompt.
- 🔌 **Hỗ trợ agent phổ quát:** Ship sẵn adapter cho **Anthropic Messages** (kèm breakpoint prompt-caching), **OpenAI Responses**, chat **OpenAI-Compatible**, và **Markdown** sạch.

---

## Cách hoạt động

![Tổng quan đóng gói ngữ cảnh: LLM nhận gì, nhiệm vụ rewrite thành term thế nào, quy tắc keep/drop, từ điển reason, giới hạn packing, lịch sử](docs/context-packing-overview.png)

Poster một trang sinh từ pipeline thật (`scripts/plot_packing_overview.py`): từ của nhiệm vụ được rewrite thành term có điểm, pin bắt buộc luôn được gửi, thẻ tùy ý được pack theo điểm trong ngân sách, mọi thẻ giữ lại mang reason bạn có thể tranh luận. Phần trăm nói ta gửi ít hơn bao nhiêu so với mọi thứ có thể gửi — hóa đơn thực tế phụ thuộc mức nhà cung cấp tái sử dụng thay vì đọc lại.

---

## Bắt đầu nhanh (60 giây)

### 1. Cài đặt

Cần Python 3.13 hoặc 3.14 trên macOS hoặc Linux:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

Kiểm tra cài đặt:

```bash
ane-harness health
```

### 1b. Thiết lập một lệnh + prove-it (cổng adoption)

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` không gắn nhãn: nó báo median reduction + p50 latency và
`recall: not_applicable`. Chứng minh recall cần nhiệm vụ gắn nhãn thủ công (cơ chế
`benchmarks/splits.json` đóng băng); lần chạy không nhãn không bao giờ khẳng định
recall.

### 2. Lập chỉ mục codebase

Lập chỉ mục bất kỳ thư mục hoặc repository local nào vào kho SQLite local (tăng dần và cực nhanh):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. Chọn ngữ cảnh liên quan cho một prompt

Lấy gói Markdown gọn, theo ngân sách token, khớp nhiệm vụ coding của bạn:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. Ghi log cắt ngữ cảnh trước/sau trên nhiều prompt (`update`)

Chạy selection trên một lô nhiệm vụ (file JSONL hoặc stdin) rồi in + ghi log
ngân sách token trước/sau. Local, không mạng:

```bash
# from a JSONL file (one {"task": "..."} or bare task per line)
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

Output mẫu:

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

Mỗi hàng theo nhiệm vụ cũng được append dạng JSONL vào `--log` (gitignored).
**Lưu ý trung thực** in ra stderr mỗi lần chạy: *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

Mỗi lần chạy cũng in một dòng footer cut ra stderr (và cùng
dòng đó là khóa `summary` trong stdout JSON), ví dụ
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Chỉ lời thường —
không jargon, không markup heading `#`. Tổng cộng dồn local (chỉ đếm, không
có nội dung nhiệm vụ) — xem bất cứ lúc nào bằng
`ane-harness daily`, hoặc mỗi khi thoát shell với
`eval "$(ane-harness shell-init)"` trong `.zshrc`/`.bashrc`.

Agent có cùng hành vi, không phụ thuộc, qua skill đi kèm:
`skills/ane-harness/SKILL.md` — copy vào thư mục skills của agent
và tổng cut tự hiện sau mỗi nhiệm vụ, không cần setup khác. Với
host tương thích OpenCode/Claude/agent nó cũng chạy global, không cần cài theo project:
`~/.config/opencode/skills/`, `~/.claude/skills/`, hoặc
`~/.agents/skills/` (session mới sẽ nhận).

### 3c. Chế độ proxy cho agent không có tích hợp native (`proxy`)

Đưa nhiệm vụ vào stdin (mỗi dòng một `{"task": "..."}` hoặc nhiệm vụ trần),
nhận evidence Markdown ra stdout — không cần skill, MCP hay HTTP:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout là Markdown thuần (một doc mỗi nhiệm vụ, phân tách bằng `---`, với
ranh giới `<!-- ane-harness task N/M ... -->`); footer cut
theo nhiệm vụ ra stderr. Bỏ `--repo` khi repo-id đã được lập chỉ mục.

### 4. Hoặc chạy như server nền local

> **Agents: do NOT run this inside an agent turn.** `serve` (like `mcp`)
> never exits — a tool call that launches it blocks forever, so the turn
> never completes and every later prompt queues behind it. Bare
> `update`/`proxy` with no `--tasks-file` on an interactive terminal exit
> 2 with a hint instead of waiting on stdin. Inside agent turns use only
> one-shot commands (`index`, `select`, `prove`, `daily`, `health`). Run
> the server detached from a real terminal
> (`nohup ane-harness serve --port 8765 &`) or not at all.

Khởi động HTTP API local (sẵn để móc vào agent hoặc công cụ của bạn):

```bash
ane-harness serve --port 8765
```

Các endpoint có sẵn:
- `GET  /v1/health` — Trạng thái hệ thống, chế độ compute và profile
- `POST /v1/repositories/index` — Lập chỉ mục hoặc cập nhật repository
- `POST /v1/context/select` — Lấy ngữ cảnh đã tối ưu cho một nhiệm vụ
- `POST /v1/context/compress-output` — Nén log test/build dài thành digest lỗi gọn

---

## Dùng trong Python

Bạn cũng có thể dùng harness trực tiếp trong workflow AI agent của mình:

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

## Cách nó hoạt động

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

1. **Chunking AST theo symbol:** Thay vì cắt dòng ngây thơ, file được parse theo cấu trúc mã thật (class, method, TypeScript type/interface/enum).
2. **Truy xuất xác định:** Truy xuất lexical BM25 nhanh, lọc bằng symbol term guard, tách subtoken và gấp số nhiều.
3. **Packing ngân sách theo điểm:** Ngữ cảnh được pack tham lam để vừa khít ngân sách token bạn chỉ định (ví dụ 1,200 token), bảo đảm bằng chứng bắt buộc không bao giờ bị cắt.
4. **Phát hiện secret & hàng rào riêng tư:** Pattern loại trừ chuẩn (`.env*`, `.aws/**`, `*.pem`, v.v.) không bao giờ được đọc, và bộ phân loại regex + entropy thay token nhạy cảm bằng placeholder ổn định.
5. **Nén nhiễu:** Output công cụ dài (trace test, log terminal) được thu gọn thành digest giữ tín hiệu.

### Tăng tốc phần cứng: bản phân phối riêng, không công khai

Tên có `ane`, nhưng **không yêu cầu hay khẳng định silicon chuyên dụng** để
chạy harness. Engine được ship là CPU xác định thuần (Python +
SQLite) và chạy giống nhau trên macOS Apple Silicon, macOS Intel và Linux.
Tăng tốc phần cứng neural được duy trì riêng và không thuộc
repository này.

---

## Thông số kỹ thuật & độ chặt

Dành cho researcher, architect và technical lead quan tâm tới độ chặt số liệu:

- **Split benchmark đóng băng:** Mọi số liệu phát hành chạy trên split đánh giá 18 nhiệm vụ đóng băng (`benchmarks/splits.json`, seed `20261002`). Tuning bị cách ly nghiêm ngặt sang split dev.
- **Bộ ước lượng token xác định:** Đếm token dùng estimator được ghim (`TOKEN_ESTIMATOR_VERSION="2"`) nên số liệu tái lập 100% giữa các máy và phiên bản Python, không trôi tokenizer ngoài.
- **Chính sách embedding:** Embedding cố ý bị loại ở v0.1 dựa trên đánh đổi chi phí/độ trễ local. Xem [ADR-002](docs/adr-002-embedding-go-no-go.md).
- **Gói bằng chứng phát hành:** Bằng chứng phát hành có checksum được xác minh mật mã qua `ane-harness evidence verify ane-context-harness-evidence-v0.1`.

---

## Chạy bộ test

```bash
# Run all 258 unit, integration, and security tests
python3 -m pytest -q

# Run concurrent A/B benchmark evaluation
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## Giấy phép

Giấy phép MIT. Thiết kế cho trí tuệ local, quyền riêng tư của developer, và ngân sách token hợp lý.