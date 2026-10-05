# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **Cắt giảm hơn 60% ngữ cảnh mà tác nhân (agent) của bạn đọc, giữ lại mọi dòng cần thiết và chọn lọc ngữ cảnh trong chưa đầy 4ms — chạy hoàn toàn ngoại tuyến (offline) trên máy cục bộ của bạn.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## Đây là gì?

Khi bạn thực hiện "vibe-code" hoặc chạy các tác nhân AI (Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider), việc nạp toàn bộ cơ sở mã nguồn vào cửa sổ ngữ cảnh LLM là **chậm chạp, lãng phí và nguy hiểm**:
- **Ngữ cảnh cồng kềnh:** Việc nhồi nhét toàn bộ tệp tin vào mỗi lượt hỏi sẽ làm mô hình bị ngộp trong các đoạn boilerplate không liên quan — và nhà cung cấp sẽ tính phí từng token, bất kể chúng có được dùng lại hay không.
- **Phản hồi chậm hơn:** Thời gian chờ token đầu tiên (TTFT) của LLM sẽ kéo dài khi phải nạp trước hàng ngàn dòng không cần thiết.
- **Mất phương hướng ở giữa (Lost in the middle):** Các mô hình thường bị "ảo giác" hoặc bỏ sót lỗi khi bị chôn vùi dưới những đoạn boilerplate vô nghĩa.
- **Rò rỉ bí mật:** Vô tình gửi các tệp bí mật `.env` hoặc thông tin đăng nhập AWS đến các nhà cung cấp mô hình bên thứ ba.

**ane-context-harness** là một công cụ ngữ cảnh gọn nhẹ, ưu tiên cục bộ (local-first), đóng vai trò trung gian giữa cơ sở mã nguồn và tác nhân lập trình của bạn. Trong khoảng **~3 mili giây**, nó lập chỉ mục kho lưu trữ, trích xuất cấu trúc phân cấp biểu tượng (hàm, giao diện, kiểu dữ liệu), loại bỏ các dữ liệu nhiễu, biên tập các thông tin bí mật và chỉ đóng gói những bằng chứng mã nguồn chất lượng cao mà tác nhân thực sự cần để hoàn thành nhiệm vụ.

> Tên gọi `ane` mang tính lịch sử; nó **không phải** là một phụ thuộc (dependency). Mã nguồn được vận chuyển hoàn toàn là CPU thuần túy và chạy trên macOS Apple Silicon, macOS Intel và Linux. Các tính năng tăng tốc phần cứng nằm trong một bản phân phối riêng tư khác.

Không có bất kỳ cuộc gọi mạng bên ngoài nào. 100% riêng tư và ngoại tuyến.

---

## Kết quả đánh giá thực tế

Được đánh giá trên **30 tác vụ benchmark** (10 dễ, 10 trung bình, 10 khó) trên các cơ sở mã nguồn Python và TypeScript tổng hợp dựa trên tập đánh giá cố định của chúng tôi (`benchmarks/splits.json`):

| Chỉ số | Không dùng Harness (Dump toàn bộ) | Có dùng Harness (Xác định) | Ý nghĩa đối với bạn |
|---|---|---|---|
| **Số Token Ngữ cảnh trung bình** | **3,213 tokens** | **782 tokens** | **Gửi ít hơn 60.47% đến LLM** |
| **Độ nhớ lại (Recall) bằng chứng cần thiết** | 1.0 (100%) | **1.0 (100%)** | **Không bao giờ bỏ sót bất kỳ đoạn mã quan trọng nào** |
| **Tốc độ chọn lọc ngữ cảnh** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **Phản hồi cục bộ dưới 4ms — nhanh gấp 100 lần mạng** |
| **Tiết kiệm token đỉnh điểm** | 0% | **Lên đến 90.32%** | **Tiết kiệm tới ~90% trên các tác vụ cấu hình & cài đặt** |
| **Độ chính xác xếp hạng (nDCG@10)** | n/a | **0.849** | **Đưa các hàm quan trọng nhất lên đầu** |
| **Biên tập bí mật** | 0% (rò rỉ toàn bộ) | **100% biên tập cục bộ** | **`.env`, khóa AWS và chứng chỉ không bao giờ rời khỏi máy** |
| **Chi phí suy diễn mỗi tác vụ** *(tại $3/M)* | ~$0.0096 / tác vụ | **~$0.0023 / tác vụ** | **Gửi ít hơn ~75% mỗi tác vụ theo mức giá đã nêu — hóa đơn của bạn thay đổi dựa trên lượng dữ liệu nhà cung cấp dùng lại thay vì đọc lại** |

*(Độ trễ và bộ nhớ được đo cục bộ trên Apple Silicon / CPU; chi phí và các con số TTFT được suy ra theo mức giá token đã nêu; phương pháp luận và nhật ký có thể tái lập trong `benchmarks/reports/` và `benchmarks/logs/`).*

### Phân tích các tác vụ mẫu

| Loại tác vụ | Tác vụ ví dụ | Token thô | Token Harness | Giảm thiểu | Nhớ lại | Độ trễ chọn lọc |
|---|---|---|---|---|---|---|
| **Cài đặt & Cấu hình** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **Quy tắc & Logic** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **Sửa lỗi (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **Kiến trúc TypeScript**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **Giỏ hàng đa tệp phức tạp** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### Mức tiết kiệm token, đã đo lường (nhánh main hiện tại)

![Cơ sở so sánh từng tác vụ với số token gửi đi với độ nhớ lại tối thiểu 1.0, cộng với các định dạng gói giống hệt nhau (JSON / markdown / nén)](docs/token-savings.png)

Đo lường chỉ với các hàm công khai (`scripts/measure_token_savings.py`, tập eval cố định, một bộ đếm được ghim — tái lập với `PYTHONPATH=src python3 scripts/measure_token_savings.py`, vẽ với `scripts/plot_token_savings.py`). Cùng một bằng chứng, ba cách hiển thị; việc hiển thị không bao giờ tác động đến việc lựa chọn.

### Cùng một bài kiểm tra so với các công cụ thực tế (không khóa, không tài khoản)

![Số trung vị lựa chọn và số trung vị định dạng gói giống hệt nhau: harness select so với headroom rewrite so với evidence-JSON / markdown / TOON thực tế / nén](docs/same-exercise-comparison.png)

Bài kiểm tra passthrough mà bất kỳ đối thủ nào cũng có thể chạy: 18 tác vụ đánh giá, một bộ đếm. Headroom 0.39.1 và bộ mã hóa TOON thực tế chạy cục bộ (`pip install headroom-ai toon-format`, sau đó `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, vẽ với `scripts/plot_same_exercise.py`). Việc viết lại mù quáng theo tác vụ gửi nhiều hơn việc chọn lọc và không có cổng kiểm soát sinh tồn; TOON thực tế quay về ánh xạ theo hàng trên mã đa dòng trong khi gói nén của chúng tôi giữ nguyên tiêu đề CSV với các hàng nguyên văn.

---

## Tại sao các nhà phát triển & người dùng "Vibecode" yêu thích nó

- 💰 **Ít ngữ cảnh hơn mỗi tác vụ, đầu ra ổn định:** Bỏ qua các tệp không liên quan đến yêu cầu — và đầu ra ổn định giúp nhà cung cấp dùng lại những gì đã đọc thay vì tính phí lần nữa. Cut% đo lường mức độ giảm ngữ cảnh cục bộ, không phải hóa đơn của bạn.
- ⚡ **Độ trễ tức thì (~3ms):** Chạy hoàn toàn bằng Python gốc và các tiện ích mở rộng C cục bộ trên máy Mac hoặc Linux của bạn.
- 🎯 **Độ chính xác từng điểm:** Kết hợp các khai báo biểu tượng AST (lớp, giao diện TypeScript, enums, hàm) với tìm kiếm từ vựng BM25 và đóng gói theo ngân sách token dựa trên điểm số.
- 🛡️ **Vệ sinh bí mật không rò rỉ:** Tự động quét và biên tập các khóa AWS, khóa RSA/PEM riêng tư, tệp `.env` và các bí mật có độ entropy cao bằng các trình giữ chỗ ổn định theo yêu cầu trước khi render prompt.
- 🔌 **Hỗ trợ tác nhân toàn cầu:** Đi kèm với các bộ điều hợp sẵn sàng sử dụng cho **Anthropic Messages** (với các điểm ngắt bộ nhớ đệm prompt), **OpenAI Responses**, **OpenAI-Compatible chat** và **Markdown** sạch sẽ.

---

## Cách thức hoạt động

![Tổng quan đóng gói ngữ cảnh: những gì LLM nhận được, cách tác vụ viết lại thành các thuật ngữ, quy tắc giữ/bỏ, từ điển lý do, giới hạn đóng gói, lịch sử](docs/context-packing-overview.png)

Poster một trang được tạo từ quy trình thực tế (`scripts/plot_packing_overview.py`): các từ tác vụ được viết lại thành các thuật ngữ có điểm số, các ghim bắt buộc luôn được giữ, các thẻ tùy chọn được đóng gói theo điểm số trước dưới ngân sách, mỗi thẻ được giữ đều mang theo lý do bạn có thể tranh luận. Phần trăm cho biết chúng ta gửi ít hơn bao nhiêu so với tất cả những gì có thể gửi — hóa đơn của bạn thay đổi dựa trên lượng dữ liệu nhà cung cấp dùng lại thay vì đọc lại.

---

## Bắt đầu nhanh (60 Giây)

### 1. Cài đặt

Yêu cầu Python 3.13 hoặc 3.14 trên macOS hoặc Linux:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

Xác minh cài đặt của bạn:
```bash
ane-harness health
```

### 1b. Thiết lập một lệnh + kiểm chứng (cổng chấp nhận)

```bash
# lập chỉ mục, cài đặt kỹ năng tác nhân, kiểm tra nhanh (in một dòng tóm tắt)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# kiểm chứng: bằng chứng về giảm thiểu/độ trễ trên repo CỦA BẠN (5 tác vụ có sẵn, không cần nhãn)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# với tác vụ của riêng bạn: --tasks-file prompts.jsonl
# với thư mục báo cáo: --out /tmp/prove-report
```

`prove` không có nhãn: nó báo cáo số trung vị giảm thiểu + độ trễ p50 và
`recall: not_applicable`. Các chứng minh về độ nhớ lại cần các tác vụ được gắn nhãn thủ công (cơ chế `benchmarks/splits.json` cố định); các lần chạy không nhãn không bao giờ khẳng định độ nhớ lại.

### 2. Lập chỉ mục cơ sở mã nguồn của bạn

Lập chỉ mục bất kỳ thư mục hoặc kho lưu trữ cục bộ nào vào kho lưu trữ SQLite cục bộ (tăng dần và siêu nhanh):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. Chọn ngữ cảnh liên quan cho một yêu cầu (Prompt)

Lấy một gói Markdown nhỏ gọn, theo ngân sách token phù hợp với tác vụ lập trình của bạn:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. Nhật ký trước/sau khi cắt ngữ cảnh trên nhiều yêu cầu (`update`)

Chạy chọn lọc trên một loạt các tác vụ (tệp JSONL hoặc stdin) và in + ghi lại ngân sách token trước/sau. Cục bộ, không mạng:

```bash
# từ một tệp JSONL (một {"task": "..."} hoặc tác vụ thuần mỗi dòng)
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

Đầu ra mẫu:

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

Các hàng cho từng tác vụ cũng được thêm dưới dạng JSONL vào `--log` (gitignored).
**Lưu ý trung thực** được in ra stderr trong mỗi lần chạy: *"các phép đo cục bộ trên repo đã cho; việc biên tập không đảm bảo tất cả bí mật đều bị bắt."*

Mỗi lần chạy cũng in một chân trang cắt ngắn ra stderr (và dòng tương tự dưới dạng khóa `summary` trong JSON stdout), ví dụ:
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. Chỉ dùng từ ngữ đơn giản — không thuật ngữ, không đánh dấu tiêu đề `#`. Tổng số tích lũy cục bộ (chỉ đếm, không có văn bản tác vụ) — xem chúng bất cứ lúc nào với `ane-harness daily`, hoặc mỗi khi thoát shell với `eval "$(ane-harness shell-init)"` trong `.zshrc`/`.bashrc` của bạn.

Các tác nhân nhận được hành vi tương tự không cần phụ thuộc thông qua kỹ năng đi kèm:
`skills/ane-harness/SKILL.md` — sao chép nó vào thư mục kỹ năng của tác nhân và tổng số cắt giảm sẽ tự động xuất hiện sau mỗi tác vụ, không cần thiết lập khác. Đối với các máy chủ tương thích OpenCode/Claude/tác nhân, nó cũng hoạt động toàn cục, không cần cài đặt mỗi dự án: `~/.config/opencode/skills/`, `~/.claude/skills/`, hoặc `~/.agents/skills/` (các phiên mới sẽ tự nhận diện).

### 3c. Chế độ proxy cho các tác nhân không tích hợp sẵn (`proxy`)

Đưa tác vụ vào stdin (một `{"task": "..."}` hoặc tác vụ thuần mỗi dòng),
nhận lại bằng chứng Markdown trên stdout — không cần kỹ năng, MCP hay HTTP:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout là Markdown thuần túy (một tài liệu mỗi tác vụ, phân tách bởi `---`, với các ranh giới `<!-- ane-harness task N/M ... -->`); chân trang cắt ngắn cho từng tác vụ đi đến stderr. Bỏ qua `--repo` khi repo-id đã được lập chỉ mục.

### 4. Hoặc Chạy như một Máy chủ chạy ngầm cục bộ

> **Các tác nhân: KHÔNG chạy lệnh này bên trong một lượt tác nhân.** `serve` (giống như `mcp`) không bao giờ thoát — một lệnh gọi công cụ khởi chạy nó sẽ bị chặn vĩnh viễn, vì vậy lượt tác nhân không bao giờ hoàn thành và mọi yêu cầu sau đó sẽ bị xếp hàng phía sau nó. Chỉ `update`/`proxy` không có `--tasks-file` trên thiết bị đầu cuối tương tác thoát 2 với gợi ý thay vì chờ trên stdin. Bên trong các lượt tác nhân chỉ sử dụng các lệnh một lần (`index`, `select`, `prove`, `daily`, `health`). Chạy máy chủ tách biệt khỏi thiết bị đầu cuối thực tế (`nohup ane-harness serve --port 8765 &`) hoặc không chạy gì cả.

Khởi động HTTP API cục bộ (sẵn sàng để kết nối với tác nhân hoặc công cụ của bạn):

```bash
ane-harness serve --port 8765
```

Các endpoint khả dụng:
- `GET  /v1/health` — Trạng thái hệ thống, chế độ tính toán và các cấu hình
- `POST /v1/repositories/index` — Lập chỉ mục hoặc cập nhật kho lưu trữ
- `POST /v1/context/select` — Truy xuất ngữ cảnh tối ưu cho một tác vụ
- `POST /v1/context/compress-output` — Nén nhật ký kiểm tra/xây dựng dài dòng thành các bản tóm tắt lỗi sạch sẽ

---

## Sử dụng trong Python

Bạn cũng có thể sử dụng harness trực tiếp trong quy trình làm việc của tác nhân AI của riêng bạn:

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. Khởi tạo đường ống
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. Lập chỉ mục kho lưu trữ
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. Chọn ngữ cảnh theo ngân sách
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. Serialize trực tiếp cho nhà cung cấp LLM yêu thích của bạn
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Đã đóng gói {package.metrics['selected_tokens']} tokens (đã cắt {package.metrics['tokens_removed']} tokens)")
```

---

## Cách thức hoạt động

```
                        Cơ sở mã nguồn của bạn
                             │
                     AST & Trình phân tích cú pháp biểu tượng
               (Các hàm Python, giao diện TS)
                             │
                      Chunker cấp dòng
                             │
                      Kho SQLite cục bộ
                             │
Prompt người dùng  ──────►   Tìm kiếm từ vựng BM25
                             │
                   Đóng gói ngân sách ưu tiên điểm số
                  (Giữ lại bắt buộc + MMR)
                             │
                  Trình biên tập bí mật cục bộ
              (Biên tập .env, khóa AWS, chứng chỉ)
                             │
               Bộ điều hợp nhà cung cấp (Anthropic/OpenAI)
                             │
                   Ngữ cảnh chặt chẽ, chính xác
```

1. **Phân đoạn AST nhận biết biểu tượng:** Thay vì phân tách dòng ngớ ngẩn, các tệp được phân tích cú pháp cho các cấu trúc mã thực (lớp, phương thức, kiểu dữ liệu/giao diện/enums TypeScript).
2. **Truy xuất xác định:** Truy xuất từ vựng BM25 nhanh được lọc bởi các rào cản thuật ngữ biểu tượng, phân tách subtoken và gộp số nhiều.
3. **Đóng gói ngân sách ưu tiên điểm số:** Ngữ cảnh được đóng gói tham lam để nằm gọn trong ngân sách token bạn đã chỉ định (ví dụ: 1.200 token), đảm bảo bằng chứng bắt buộc không bao giờ bị cắt bớt.
4. **Phát hiện bí mật & Hàng rào quyền riêng tư:** Các mẫu loại trừ chính tắc (`.env*`, `.aws/**`, `*.pem`, v.v.) không bao giờ được đọc, và các bộ phân loại regex + entropy thay thế các token nhạy cảm bằng các trình giữ chỗ ổn định.
5. **Nén nhiễu:** Các đầu ra công cụ dài dòng (vết kiểm tra, nhật ký đầu cuối) được thu gọn thành các bản tóm tắt bảo toàn tín hiệu nhỏ gọn.

### Tăng tốc phần cứng: bản phân phối riêng tư riêng biệt

Tên gọi chứa `ane`, nhưng **không yêu cầu hoặc khẳng định cần silicon chuyên dụng** để chạy harness. Công cụ được vận chuyển là CPU xác định thuần túy (Python + SQLite) và chạy giống hệt nhau trên macOS Apple Silicon, macOS Intel và Linux. Tăng tốc phần cứng thần kinh được duy trì riêng biệt và không phải là một phần của kho lưu trữ này.

---

## Thông số kỹ thuật & Độ nghiêm ngặt

Dành cho các nhà nghiên cứu, kiến trúc sư và trưởng nhóm kỹ thuật quan tâm đến độ nghiêm ngặt số học:

- **Tập Benchmark cố định:** Tất cả các số liệu phát hành chạy trên tập đánh giá cố định 18 tác vụ (`benchmarks/splits.json`, seed `20261002`). Việc điều chỉnh được cách ly nghiêm ngặt với tập dev.
- **Trình ước tính token xác định:** Việc đếm token sử dụng trình ước tính đã ghim (`TOKEN_ESTIMATOR_VERSION="2"`) nên các con số có thể tái lập 100% trên các máy và phiên bản Python mà không bị trôi tokenizer bên ngoài.
- **Chính sách nhúng (Embedding):** Các nhúng được cố tình loại trừ trong v0.1 dựa trên sự đánh đổi chi phí/độ trễ cục bộ. Xem [ADR-002](docs/adr-002-embedding-go-no-go.md).
- **Gói bằng chứng phát hành:** Bằng chứng phát hành đã kiểm tra tổng kiểm tra (checksum) được xác minh bằng mật mã thông qua `ane-harness evidence verify ane-context-harness-evidence-v0.1`.

---

## Chạy bộ kiểm tra (Test Suite)

```bash
# Chạy tất cả 258 bài kiểm tra đơn vị, tích hợp và bảo mật
python3 -m pytest -q

# Chạy đánh giá benchmark A/B đồng thời
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## Giấy phép

Giấy phép MIT. Được thiết kế cho trí thông minh cục bộ, quyền riêng tư của nhà phát triển và ngân sách token hợp lý.