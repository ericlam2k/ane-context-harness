# ⚡ ane-context-harness

[영어](README.md) · [베트남어](README.vi.md) · [중국어](README.zh.md) · [프랑스어](README.fr.md) · [스페인어](README.es.md) · [일본어](README.ja.md) · [한국어](README.ko.md)

> **에이전트가 읽는 컨텍스트를 60%+ 줄이고, 필요한 줄은 전부 유지하며, 4ms 이내에 컨텍스트를 선택합니다 — 로컬 머신에서 완전히 오프라인으로 실행됩니다.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## 이것은 무엇인가요?

바이브 코딩을 하거나 AI 에이전트(Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider)를 실행할 때, 전체 코드베이스를 LLM 컨텍스트 윈도우에 넣는 것은 **느리고, 낭비이며, 위험합니다**:
- **비대한 컨텍스트:** 매 턴마다 파일 전체를 밀어 넣으면 관련 없는 보일러플레이트에 모델이 묻히고 — 제공자는 재사용 여부와 관계없이 모든 토큰을 셉니다.
- **느린 응답:** 불필요한 수천 줄을 프리필하면 LLM의 time-to-first-token이 기어갑니다.
- **중간에 길을 잃음:** 관련 없는 보일러플레이트에 묻히면 모델이 환각하거나 버그를 놓칩니다.
- **비밀 유출:** `.env` 시크릿이나 AWS 자격 증명을 모르고 서드파티 모델 제공자에게 보냅니다.

**ane-context-harness**는 코드베이스와 코딩 에이전트 사이에 앉는 가벼운 로컬 우선 컨텍스트 엔진입니다. **~3 milliseconds** 안에 저장소를 인덱싱하고, 심볼 계층(함수, 인터페이스, 타입)을 추출하고, 노이즈를 걷어내고, 시크릿을 레닥션한 뒤, 작업을 완료하는 데 에이전트가 실제로 필요한 고가치 코드 증거만 팩합니다.

> 이름 `ane`는 역사적인 것이며 **의존성이 아닙니다**. 배포 경로는 순수 CPU이며 macOS Apple Silicon, macOS Intel, Linux에서 실행됩니다. 하드웨어 가속은 별도의 비공개 배포에 있습니다.

외부 네트워크 호출 없음. 100% 비공개이며 오프라인입니다.

---

## 실제 벤치마크 결과

합성 Python 및 TypeScript 코드베이스에서 고정 평가 스플릿(`benchmarks/splits.json`)의 **30 benchmark tasks**(10 small, 10 typical, 10 difficult)에 대해 평가했습니다:

| 지표 | 하네스 없음 (전체 저장소 덤프) | 하네스 사용 (결정적) | 이것이 의미하는 바 |
|---|---|---|---|
| **중앙값 컨텍스트 토큰** | **3,213 tokens** | **782 tokens** | **LLM에 60.47% 덜 전송합니다** |
| **필수 증거 재현율** | 1.0 (100%) | **1.0 (100%)** | **중요한 코드를 하나도 놓치지 않았습니다** |
| **컨텍스트 선택 속도** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **4ms 미만 로컬 응답 — 네트워크보다 100x 빠름** |
| **최대 토큰 절감** | 0% | **Up to 90.32%** | **타깃 설정 및 구성 작업에서 최대 ~90% 절감** |
| **랭킹 정확도 (nDCG@10)**| n/a | **0.849** | **가장 중요한 함수를 맨 위에 둡니다** |
| **시크릿 레닥션** | 0% (leaks all secrets) | **100% local redaction** | **`.env`, AWS keys, certificates가 기기를 떠나지 않습니다** |
| **작업당 파생 비용** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **명시된 요율에서 작업당 ~75% 덜 전송 — 청구서 자체는 제공자가 다시 읽는 대신 얼마나 재사용하느냐에 따라 움직입니다** |

*(지연 시간과 메모리는 Apple Silicon / CPU에서 로컬로 측정했습니다. 비용과 TTFT 수치는 명시된 토큰 요율 아래 파생되었습니다. 방법론과 재현 가능한 로그는 `benchmarks/reports/` 및 `benchmarks/logs/`에 있습니다).*

### 샘플 작업 분석

| 작업 유형 | 예제 작업 | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **설정 및 구성** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **규칙 및 로직** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **버그 수정 (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript 아키텍처**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **복잡한 멀티파일 장바구니** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### 토큰 절감, 측정됨 (current main)

![작업별 베이스라인 대 전송 토큰(최소 재현율 1.0), 그리고 동일 팩 포맷 중앙값 (JSON / markdown / compact)](docs/token-savings.png)

공개 함수만으로 측정했습니다 (`scripts/measure_token_savings.py`, 고정 eval 스플릿, 핀된 카운터 하나 — `PYTHONPATH=src python3 scripts/measure_token_savings.py`로 재현, `scripts/plot_token_savings.py`로 그리기). 같은 증거, 세 가지 렌더링; 렌더링은 선택에 절대 손대지 않습니다.

### 실제 도구 대비 동일 실험 (키 없음, 계정 없음)

![선택 중앙값과 동일 팩 포맷 중앙값: harness select 대 headroom rewrite 대 evidence-JSON / markdown / real TOON / compact](docs/same-exercise-comparison.png)

어떤 경쟁자도 실행할 수 있는 패스스루 테스트: 18 eval tasks, 카운터 하나. Headroom 0.39.1과 실제 TOON 인코더는 로컬에서 실행됩니다 (`pip install headroom-ai toon-format`, 이어서 `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, `scripts/plot_same_exercise.py`로 그리기). 작업에 맹목적인 재작성은 선택보다 더 많이 보내고 생존 게이트가 없으며; 실제 TOON은 여러 줄 코드에서 per-row 매핑으로 폴백하는 반면 우리의 compact는 CSV 헤더와 원문 행을 유지합니다.

---

## 개발자와 바이브코더가 사랑하는 이유

- 💰 **작업당 더 적은 컨텍스트, 안정적인 출력:** 프롬프트와 무관한 파일은 건너뛰고 — 안정적인 출력이면 제공자가 이미 읽은 것을 재사용하여 다시 과금하지 않습니다. Cut%는 로컬 컨텍스트 감소를 측정하며, 청구서가 아닙니다.
- ⚡ **즉시 (~3ms) 지연 시간:** Mac 또는 Linux 박스에서 네이티브 Python과 C 확장으로 전적으로 로컬 실행됩니다.
- 🎯 **핀포인트 정확도:** AST 심볼 선언(클래스, TypeScript 인터페이스, enum, 함수)을 BM25 어휘 검색 및 토큰 예산 기반 score-first 패킹과 결합합니다.
- 🛡️ **제로 리크 시크릿 살균:** AWS 키, 비공개 RSA/PEM 키, `.env` 파일, 고엔트로피 시크릿을 프롬프트가 렌더되기 전에 안정적인 요청 범위 플레이스홀더로 자동 스캔하고 레닥션합니다.
- 🔌 **범용 에이전트 지원:** **Anthropic Messages**(프롬프트 캐싱 브레이크포인트 포함), **OpenAI Responses**, **OpenAI-Compatible chat**, 깨끗한 **Markdown**용 어댑터를 바로 쓸 수 있게 제공합니다.

---

## 작동 방식

![컨텍스트 패킹 개요: LLM이 받는 것, 작업이 용어로 다시 쓰이는 방식, keep/drop 규칙, reason 사전, 패킹 한도, 히스토리](docs/context-packing-overview.png)

실제 파이프라인에서 생성된 한 페이지 포스터(`scripts/plot_packing_overview.py`): 작업 단어가 점수 매겨진 용어로 다시 쓰이고, 필수 핀은 항상 탑승하며, 재량 카드는 예산 아래 score-first로 팩되고, 유지된 카드마다 반박할 수 있는 이유가 붙습니다. 퍼센트는 보낼 수 있는 전부보다 얼마나 덜 보내는지를 말합니다 — 청구서 자체는 제공자가 다시 읽는 대신 얼마나 재사용하느냐에 따라 움직입니다.

---

## 빠른 시작 (60 Seconds)

### 1. 설치

macOS 또는 Linux에서 Python 3.13 또는 3.14가 필요합니다:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

설치를 확인하세요:
```bash
ane-harness health
```

### 1b. 원커맨드 설정 + prove-it (도입 게이트)

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove`는 라벨이 없습니다: 중앙값 감소 + p50 지연 시간과
`recall: not_applicable`을 보고합니다. 재현율 증명은 손으로 라벨링한 작업이 필요합니다 (고정된
`benchmarks/splits.json` 장치). 라벨 없는 실행은 재현율을 주장하지 않습니다.

### 2. 코드베이스 인덱싱

로컬 폴더나 저장소를 로컬 SQLite 스토어에 인덱싱합니다 (증분이며 매우 빠릅니다):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. 프롬프트에 맞는 관련 컨텍스트 선택

코딩 작업에 맞춘 압축된 토큰 예산 Markdown 패키지를 가져옵니다:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. 여러 프롬프트에 걸쳐 전/후 컨텍스트 컷을 기록 (`update`)

작업 배치(JSONL 파일 또는 stdin)에 대해 선택을 실행하고 전/후
토큰 예산을 출력하고 기록합니다. 로컬, 네트워크 없음:

```bash
# from a JSONL file (one {"task": "..."} or bare task per line)
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

샘플 출력:

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

작업별 행은 JSONL로 `--log`에도 추가됩니다 (gitignore됨).
**정직한 주의**가 매 실행마다 stderr에 출력됩니다: *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

매 실행은 한 줄 컷 푸터를 stderr에 출력하고 (그리고 같은
줄을 stdout JSON의 `summary` 키로도 출력합니다). 예:
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. 평범한 단어만 —
전문 용어 없음, `#` 제목 마크업 없음. 합계는 로컬로 누적됩니다 (카운트만, 작업
텍스트 없음) — 언제든
`ane-harness daily`로 보거나, 매 셸 종료 시
`.zshrc`/`.bashrc`에 `eval "$(ane-harness shell-init)"`를 넣으면 됩니다.

에이전트는 번들 스킬을 통해 의존성 없이 같은 동작을 얻습니다:
`skills/ane-harness/SKILL.md` — 에이전트의 skills 디렉터리에 복사하면
다른 설정 없이 각 작업 후 컷 합계가 자동으로 나타납니다. OpenCode/Claude/에이전트 호환 호스트에서는
프로젝트별 설치 없이 전역으로도 동작합니다:
`~/.config/opencode/skills/`, `~/.claude/skills/`, 또는
`~/.agents/skills/` (새 세션이 가져갑니다).

### 3c. 네이티브 연동이 없는 에이전트를 위한 프록시 모드 (`proxy`)

stdin으로 작업을 넣고 (한 줄에 `{"task": "..."}` 또는 그냥 작업),
stdout으로 증거 Markdown을 받습니다 — 스킬, MCP, HTTP 불필요:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout은 순수 Markdown입니다 (작업당 문서 하나, `---`로 구분,
`<!-- ane-harness task N/M ... -->` 경계 포함). 작업별 컷
푸터는 stderr로 갑니다. repo-id가 이미 인덱싱되어 있으면 `--repo`를 생략하세요.

### 4. 또는 로컬 백그라운드 서버로 실행

> **에이전트: 에이전트 턴 안에서 이것을 실행하지 마세요.** `serve`(`mcp`와 같이)
> 절대 종료되지 않습니다 — 이를  запуска하는 툴 호출은 영원히 막혀서 턴이
> 완료되지 않고 이후 모든 프롬프트가 뒤에 대기합니다. 대화형 터미널에서
> `--tasks-file` 없는 Bare
> `update`/`proxy`는 stdin을 기다리지 않고 힌트와 함께
> 2로 종료합니다. 에이전트 턴 안에서는 원샷 명령만 사용하세요
> (`index`, `select`, `prove`, `daily`, `health`). 서버는 실제 터미널에서
> 분리해 실행하거나
> (`nohup ane-harness serve --port 8765 &`) 아예 실행하지 마세요.

로컬 HTTP API를 시작합니다 (에이전트나 도구에 연결할 준비가 됩니다):

```bash
ane-harness serve --port 8765
```

사용 가능한 엔드포인트:
- `GET  /v1/health` — 시스템 상태, 컴퓨트 모드, 프로파일
- `POST /v1/repositories/index` — 저장소 인덱싱 또는 업데이트
- `POST /v1/context/select` — 작업에 최적화된 컨텍스트 조회
- `POST /v1/context/compress-output` — 장황한 테스트/빌드 로그를 깨끗한 실패 다이제스트로 압축

---

## Python에서 사용하기

자체 AI 에이전트 워크플로 안에서 하네스를 직접 사용할 수도 있습니다:

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

## 작동 원리

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

1. **심볼 인식 AST 청킹:** 멍청한 줄 분할 대신, 파일을 실제 코드 구성(클래스, 메서드, TypeScript 타입/인터페이스/enum)으로 파싱합니다.
2. **결정적 검색:** 심볼 텀 가드, 서브토큰 분할, 복수형 폴딩으로 필터링된 빠른 어휘 BM25 검색.
3. **Score-First 예산 패킹:** 지정한 토큰 예산(예: 1,200 tokens) 안에 엄격히 맞도록 컨텍스트를 탐욕적으로 팩하며, 필수 증거가 잘리지 않음을 보장합니다.
4. **시크릿 탐지 및 프라이버시 펜스:** 정규 제외 패턴(`.env*`, `.aws/**`, `*.pem` 등)은 읽히지 않으며, 정규식 + 엔트로피 분류기가 민감 토큰을 안정적인 플레이스홀더로 바꿉니다.
5. **노이즈 압축:** 장황한 도구 출력(테스트 트레이스, 터미널 로그)을 신호를 보존하는 압축 다이제스트로 접습니다.

### 하드웨어 가속: 별도의 비공개 배포

이름에 `ane`가 들어 있지만, 하네스를 실행하는 데 **특수 실리콘은 필요하지도 주장하지도 않습니다**.
배포된 엔진은 순수 결정적 CPU(Python +
SQLite)이며 macOS Apple Silicon, macOS Intel, Linux에서 동일하게 실행됩니다.
뉴럴 하드웨어 가속은 별도로 유지되며 이 저장소의 일부가
아닙니다.

---

## 기술 사양 및 엄밀성

수치적 엄밀성을 중시하는 연구자, 아키텍트, 기술 리더를 위해:

- **고정 벤치마크 스플릿:** 모든 릴리스 수치는 고정된 18-task 평가 스플릿(`benchmarks/splits.json`, seed `20261002`)에서 실행됩니다. 튜닝은 엄격히 dev 스플릿에 격리됩니다.
- **결정적 토큰 추정기:** 토큰 카운팅은 핀된 추정기(`TOKEN_ESTIMATOR_VERSION="2"`)를 사용하므로 외부 토크나이저 드리프트 없이 머신과 Python 버전 전반에서 숫자가 100% 재현됩니다.
- **임베딩 정책:** 로컬 비용/지연 트레이드오프에 따라 v0.1에서는 임베딩을 의도적으로 제외합니다. [ADR-002](docs/adr-002-embedding-go-no-go.md)를 보세요.
- **릴리스 증거 번들:** 체크섬된 릴리스 증거는 `ane-harness evidence verify ane-context-harness-evidence-v0.1`로 암호학적으로 검증됩니다.

---

## 테스트 스위트 실행

```bash
# Run all 258 unit, integration, and security tests
python3 -m pytest -q

# Run concurrent A/B benchmark evaluation
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## 라이선스

MIT License. 로컬 지능, 개발자 프라이버시, 건전한 토큰 예산을 위해 설계되었습니다.