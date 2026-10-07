# ⚡ ane-context-harness

[영어](README.md) · [베트남어](README.vi.md) · [중국어](README.zh.md) · [프랑스어](README.fr.md) · [스페인어](README.es.md) · [일본어](README.ja.md) · [한국어](README.ko.md)

> **에이전트가 읽는 컨텍스트를 60%+ 줄이고, 필요한 줄은 모두 유지하며, 4ms 이내에 컨텍스트를 선택하세요 — 로컬 머신에서 완전히 오프라인으로 동작합니다.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## 이것은 무엇인가요?

바이브 코딩을 하거나 AI 에이전트(Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider)를 실행할 때, 코드베이스 전체를 LLM 컨텍스트 창에 넣는 것은 **느리고, 낭비이며, 위험합니다**:
- **비대한 컨텍스트:** 매 턴마다 파일 전체를 밀어 넣으면 모델이 관련 없는 보일러플레이트에 묻히고 — 제공자는 재사용 여부와 관계없이 모든 토큰을 셉니다.
- **느린 응답:** 불필요한 수천 줄을 프리필하면 LLM의 time-to-first-token이 기어갑니다.
- **중간에 묻힘:** 관련 없는 보일러플레이트에 파묻히면 모델이 환각하거나 버그를 놓칩니다.
- **시크릿 유출:** `.env` 시크릿이나 AWS 자격 증명을 제3자 모델 제공자에게 나도 모르게 보냅니다.

**ane-context-harness**는 코드베이스와 코딩 에이전트 사이에 앉는 가볍고 로컬 우선인 컨텍스트 엔진입니다. **~3 milliseconds** 만에 리포를 인덱싱하고, 심볼 계층(함수, 인터페이스, 타입)을 추출하고, 노이즈를 걷어내고, 시크릿을 마스킹하며, 작업을 완료하는 데 에이전트가 실제로 필요한 고가치 코드 증거만 패킹합니다.

> 이름 `ane`는 역사적인 것이며 **의존성이 아닙니다**. 배포 경로는 순수 CPU이며 macOS Apple Silicon, macOS Intel, Linux에서 동작합니다. 하드웨어 가속은 별도의 비공개 배포에 있습니다.

외부 네트워크 호출 없음. 100% 비공개 및 오프라인.

---

## 실제 벤치마크 결과

고정 평가 분할(`benchmarks/splits.json`)에서 합성 Python 및 TypeScript 코드베이스에 걸쳐 **30**개의 벤치마크 작업(10 small, 10 typical, 10 difficult)으로 평가했습니다:

| 지표 | 하네스 없음 (전체 리포 덤프) | 하네스 사용 (결정적) | 이것이 여러분에게 의미하는 것 |
|---|---|---|---|
| **중앙값 컨텍스트 토큰** | **3,213 토큰** | **782 토큰** | **LLM에 60.47% 덜 보냅니다** |
| **필수 근거 Recall** | 1.0 (100%) | **1.0 (100%)** | **중요한 코드를 하나도 놓치지 않았습니다** |
| **컨텍스트 선택 속도** | ~0.01 ms (원시 덤프) | **3.05 ms – 3.83 ms** | **4ms 미만 로컬 응답 — 네트워크보다 100x 빠름** |
| **최대 토큰 절감** | 0% | **최대 90.32%** | **타겟팅된 구성 및 설정 작업에서 최대 ~90% 절감** |
| **랭킹 정확도 (nDCG@10)**| n/a | **0.849** | **가장 중요한 함수를 맨 위에 배치합니다** |
| **시크릿 마스킹** | 0% (모든 시크릿 유출) | **100% 로컬 마스킹** | **`.env`, AWS 키, 인증서가 머신을 떠나지 않습니다** |
| **작업당 파생 비용** *($3/M 기준)* | ~$0.0096 / task | **~$0.0023 / task** | **명시된 요율에서 작업당 ~75% 덜 보냅니다 — 실제 청구는 제공자가 다시 읽는 대신 얼마나 재사용하느냐에 따라 달라집니다** |

*(지연 시간과 메모리는 Apple Silicon / CPU에서 로컬 측정; 비용과 TTFT 수치는 명시된 토큰 요율로 도출; 방법론과 재현 가능한 로그는 `benchmarks/reports/` 및 `benchmarks/logs/`).*

### 샘플 작업 분석

| 작업 유형 | 예제 작업 | 원본 토큰 | Harness 토큰 | 절감률 | 재현율 | 선택 지연 |
|---|---|---|---|---|---|---|
| **설정 & 구성** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **규칙 & 로직** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **버그 수정 (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript 아키텍처**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **복잡한 멀티 파일 장바구니** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### 토큰 절감, 측정값 (현재 main)

이 차트를 읽는 법: 모든 작업은 도구에 "이 작업을 위해 AI가 무엇을 읽어야 하는가?"를 물었습니다. 왼쪽 패널은 작업 크기별로 코드베이스 전체를 보냈을 때(회색)와 하네스가 고른 것(녹색)을 비교합니다 — 각 녹색 막대 위의 숫자는 지금 보내는 양과 그것이 얼마나 더 작은지입니다. 더 어려운 작업은 파일이 더 필요하므로 녹색 막대가 커집니다 — 하지만 필요한 파일은 **매번** 유지되었습니다. 이것이 핵심입니다: 중요한 것이 빠지지 않을 때만 더 작은 것이 좋습니다. 오른쪽 패널은 같은 선택을 세 가지 방식으로 보낸 것입니다 — 전체 상세, 읽기 쉬운 중간, 가장 짧은 래핑 — 짧을수록 저렴하고, 래핑은 *무엇을* 고르는지는 바꾸지 않습니다.

![작업 크기별 읽을 양 감소, 그리고 같은 답의 세 가지 래핑](docs/token-savings.png)

측정은 `PYTHONPATH=src python3 scripts/measure_token_savings.py`, 그림은 `scripts/plot_token_savings.py` (고정 eval split, 핀된 토큰 카운터 하나).

### 실제 도구 대비 동일 실험 (키 없음, 계정 없음)

이 차트를 읽는 법: 같은 18개 작업을 같은 자로 잰 경주입니다 — "중간 작업이 몇 토큰을 들고, 필요한 것이 빠졌는가?". 첫 차트는 헤드라인입니다: 전부 보내는 것이 비용이 큰 기본값이고, 외부 재작성 도구는 실제로는 필요한 것보다 *더* 보내며 한 번은 채점기가 요구한 config 파일을 놓쳤습니다(FAIL로 표시). 우리의 두 모드는 가장 짧고 필요한 파일을 매번 유지했습니다(PASS). 두 번째 차트는 그 뒤의 세부입니다 — 선택만으로 절감되는 것, 그리고 같은 선택이 더 짧은 래핑을 고르는 것만으로 다시 줄어드는 방식. 여기서 PASS/FAIL은 딱 한 가지입니다: 벤치마크 채점기가 필수라고 한 조각이 팩에 들어왔는가.

![같은 18개 작업: 전부 보내기 vs 외부 재작성 도구 vs 우리](docs/head-to-head.png)

![선택 중앙값과 네 가지 래핑의 같은 팩, 작업별 예제 포함](docs/same-exercise-comparison.png)

재현: `pip install headroom-ai toon-format`, 그다음 `PYTHONPATH=src python3 scripts/bench_same_exercise.py`, 그림은 `scripts/plot_same_exercise.py`. 작업에 맹목적인 재작성은 선택보다 더 보내고 생존 게이트가 없습니다; 실제 TOON 인코더는 여러 줄 코드에서 per-row 매핑으로 폴백하는 반면, 우리의 compact는 CSV 헤더와 원문 행을 유지합니다.

### 대화 절감, 측정값

이렇게 읽으세요: 한 작업은 질문이 하나가 아닙니다 — 에이전트가 묻고, 후속하고, 검증합니다. 이 벤치는 작업당 같은 3-turn 대화를 세 가지 방식으로 재생합니다: 매 턴 코드베이스 전체 보내기 (149,490 tokens), 트림된 팩 하나 (17,094), 그리고 각 후속이 이전 턴이 찾은 모든 것을 유지하는 세 개의 운반 팩 (51,940). 운반된 대화는 하네스 없는 비용의 **약 3분의 1**을 보냅니다 — 97,550 fewer tokens, 65.3% less — 그리고 필요한 파일은 72 turns 모두에서 살아남았습니다 (매 턴 recall 1.0; 필요한 파일을 잃는 턴은 대화를 탈선시키므로, 그 게이트는 장식이 아니라 부하를 받습니다).

재현: `PYTHONPATH=src python3 scripts/bench_conversation.py` (고정 eval split, 핀된 토큰 카운터 하나; `benchmarks/reports/conversation-bench-eval.json`을 씁니다). 경계를 분명히 합니다: 어떤 모델도 이 팩을 읽지 않고, 후속은 실제 에이전트 반응이 아니라 고정 문자열이며, 청구되지 않고, 어떤 작업도 실제로 완료되지 않습니다. 측정하는 것은 우리가 먹이는 절반 — 고르기와 운반 — 이지 루프 자체가 아닙니다.

### 각 파일에 일어나는 일

문서화된 규칙 네 가지, 모델 개입 없음, 예외 없음: 핀한(또는 채점기가 요구하는) 파일은 **항상 바이트 그대로** 갑니다. 코드, config, diffs는 구조를 유지합니다 — 피커는 심볼 전체를 고르며, 절대 다시 쓰지 않습니다. **로그와 noisy한 도구 출력만** 접힙니다 (반복되는 진행 줄, 중복 트레이스백, 설치 스팸은 무엇이 제거되었는지 말하는 요약 줄로 접힙니다). 산문은 고른 그대로 가며, 절대 다시 쓰지 않습니다 — 신경망 재작성기가 없으므로, 문서가 말하지 않은 것으로 패러프레이즈할 수 없습니다. 모든 팩은 파일마다 어떤 규칙이 적용되었는지 나열합니다 — 어떤 리포트에서든 `diagnostics.routing`을 확인하고 이의를 제기하십시오.

![개념 일러스트: 동일한 기준으로 컨텍스트 검색 방식 비교](docs/ane-benchmark-concept.jpg)

*개념 일러스트이며 측정 결과가 아닙니다 — 그림 속 토큰 규모와 수치는 예시입니다. 실제 측정값은 위의 표와 측정 차트를 참조하십시오.*


---

## 개발자와 바이브코더가 사랑하는 이유

- 💰 **작업당 더 적은 컨텍스트, 안정적인 출력:** 프롬프트와 무관한 파일은 건너뛰세요 — 안정적인 출력은 제공자가 이미 읽은 것을 재사용해 다시 청구하지 않게 합니다. Cut%는 로컬 컨텍스트 감소를 측정하며, 청구서가 아닙니다.
- ⚡ **즉시 (~3ms) 지연:** Mac 또는 Linux 박스에서 네이티브 Python과 C 확장으로 완전히 로컬 실행됩니다.
- 🎯 **정확한 조준:** AST 심볼 선언(클래스, TypeScript 인터페이스, 열거형, 함수)을 BM25 어휘 검색 및 토큰 예산 기반 score-first 패킹과 결합합니다.
- 🛡️ **제로 리크 시크릿 살균:** AWS 키, 비공개 RSA/PEM 키, `.env` 파일, 고엔트로피 시크릿을 프롬프트가 렌더되기 전에 안정적인 요청 범위 플레이스홀더로 자동 스캔하고 마스킹합니다.
- 🔌 **범용 에이전트 지원:** **Anthropic Messages** (프롬프트 캐싱 브레이크포인트 포함), **OpenAI Responses**, **OpenAI-Compatible chat**, 깨끗한 **Markdown**용 어댑터를 바로 쓸 수 있게 제공합니다.

![개념 일러스트: 무거운 베이스라인과 가벼운 하네스 — 토큰은 적게, 정확도는 그대로](docs/ane-concept-dashboard.jpg)

*개념 일러스트 — 그림 속 규모와 표 수치는 예시입니다. 실제 측정값: 중앙값 782 대 3,213 토큰(60.47% 감소), recall 1.0, 위의 벤치마크 표를 참조하십시오.*


---

## 작동 방식

![당신의 말이 AI가 읽는 것이 되는 과정: 실제 벤치마크 작업을 처음부터 끝까지 추적 — 평범한 말이 들어오고 모든 청크에 점수가 매겨지고, 각 카드가 떠난 이유, 1,236개 중 369개 토큰](docs/context-packing-overview.png)

실제 파이프라인에서 생성한 한 페이지 설명 그림(`scripts/plot_packing_overview.py`): 실제 벤치마크 작업을 처음부터 끝까지 추적합니다. 당신의 말이 들어오고 짧은 단어는 떨어지고, 저장소의 모든 청크에 점수가 매겨지며, 이긴 카드가 이유를 달아 날아가고, AI는 전체 1,236 대신 369 토큰만 읽습니다 (70% 적게, 정답에 필요한 것은 하나도 빠지지 않음). 그림의 모든 숫자는 실제 측정값이지 그림이 아닙니다.

![개념 일러스트: 무자비한 잘라내기는 AST·import·참조를 깨뜨린다 — 하네스는 코드 서명·AST 구조·필수 의존성을 유지한다](docs/ane-concept-generic.jpg)

*위 아이디어의 개념 일러스트 — 그림 속 코드는 그래픽이며 실제 트레이스가 아닙니다. 측정된 실제 트레이스는 바로 위의 차트입니다.*


---

## 빠른 시작 (60초)

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

`prove`는 라벨이 없습니다: 중앙값 감소 + p50 지연과
`recall: not_applicable`을 보고합니다. Recall 증명은 손으로 라벨한 작업이 필요합니다 (고정 `benchmarks/splits.json` 기계); 라벨 없는 실행은 recall을 주장하지 않습니다.

### 2. 코드베이스 인덱싱

로컬 폴더나 리포지토리를 로컬 SQLite 저장소로 인덱싱하세요 (증분이며 매우 빠릅니다):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. 프롬프트에 맞는 관련 컨텍스트 선택

코딩 작업에 맞춘 압축되고 토큰 예산이 적용된 Markdown 패키지를 가져오세요:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. 여러 프롬프트에 대한 전/후 컨텍스트 삭감 기록 (`update`)

작업 배치(JSONL 파일 또는 stdin)에 대해 선택을 실행하고 전/후 토큰 예산을 출력 + 기록합니다.
로컬, 네트워크 없음:

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

작업별 행은 JSONL로 `--log`에도 추가됩니다 (gitignored).
**정직한 주의**가 매 실행마다 stderr에 출력됩니다: *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

모든 실행은 또한 한 줄 cut footer를 stderr에 출력합니다 (그리고 stdout JSON의
`summary` 키로 같은 줄), 예:
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. 평범한 단어만 —
전문 용어 없음, `#` 제목 마크업 없음. 합계는 로컬에 누적됩니다 (카운트만, 작업
텍스트 없음) — 언제든
`ane-harness daily`로 보거나, 매 셸 종료 시
`.zshrc`/`.bashrc`에 `eval "$(ane-harness shell-init)"`로 보세요.

에이전트는 번들 스킬을 통해 의존성 없이 같은 동작을 얻습니다:
`skills/ane-harness/SKILL.md` — 에이전트의 skills 디렉터리에 복사하면
각 작업 후 cut 합계가 자동으로 나타납니다, 다른 설정 없음. OpenCode/Claude/에이전트 호환
호스트에서는 프로젝트별 설치 없이 전역으로도 동작합니다: `~/.config/opencode/skills/`, `~/.claude/skills/`, 또는
`~/.agents/skills/` (새 세션이 가져갑니다).

### 3c. 네이티브 통합이 없는 에이전트를 위한 프록시 모드 (`proxy`)

stdin으로 작업을 파이프하고 (한 줄에 `{"task": "..."}` 또는 맨 작업),
stdout으로 증거 Markdown을 받습니다 — 스킬, MCP, HTTP 불필요:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout은 순수 Markdown입니다 (작업당 문서 하나, `---`-구분, 
`<!-- ane-harness task N/M ... -->` 경계 포함); 작업별 cut
footer는 stderr로 갑니다. repo-id가 이미 인덱싱되어 있으면 `--repo`를 생략하세요.

### 4. 또는 로컬 백그라운드 서버로 실행

> **에이전트: 에이전트 턴 안에서 이것을 실행하지 마세요.** `serve` (`mcp`와 같이)
> 절대 종료하지 않습니다 — 이를  запуска하는 도구 호출은 영원히 막히므로, 턴이
> 완료되지 않고 이후의 모든 프롬프트가 뒤에 대기합니다. 대화형 터미널에서
> `--tasks-file` 없는 맨 `update`/`proxy`는 stdin을 기다리지 않고
> 힌트와 함께 exit 2 합니다. 에이전트 턴 안에서는 원샷 명령만 사용하세요
> (`index`, `select`, `prove`, `daily`, `health`). 서버는 실제 터미널에서
> detach해서 실행하세요
> (`nohup ane-harness serve --port 8765 &`) 또는 아예 실행하지 마세요.

로컬 HTTP API를 시작하세요 (에이전트나 도구에 연결할 준비가 됩니다):

```bash
ane-harness serve --port 8765
```

사용 가능한 엔드포인트:
- `GET  /v1/health` — 시스템 상태, 컴퓨트 모드, 프로파일
- `POST /v1/repositories/index` — 리포지토리 인덱싱 또는 업데이트
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

## 작동 방식

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

1. **심볼 인식 AST 청킹:** dumb한 줄 분할 대신, 파일을 실제 코드 구성(클래스, 메서드, TypeScript 타입/인터페이스/열거형)으로 파싱합니다.
2. **결정적 검색:** 심볼 용어 가드, 서브토큰 분할, 복수형 접기로 필터링된 빠른 어휘 BM25 검색.
3. **Score-First 예산 패킹:** 지정한 토큰 예산(예: 1,200 tokens) 안에 엄격히 맞도록 컨텍스트를 greedy하게 패킹하며, 필수 증거가 잘리지 않음을 보장합니다.
4. **시크릿 탐지 및 프라이버시 펜스:** 정규 제외 패턴(`.env*`, `.aws/**`, `*.pem` 등)은 절대 읽지 않으며, regex + 엔트로피 분류기가 민감 토큰을 안정적인 플레이스홀더로 바꿉니다.
5. **노이즈 압축:** 장황한 도구 출력(테스트 트레이스, 터미널 로그)을 신호를 보존하는 압축 다이제스트로 접습니다.

![개념 일러스트: 시스템 프롬프트와 페이로드가 필터를 거쳐 클린 페이로드로 — 하네스 필터 파이프라인](docs/ane-proxy-tracker-concept.jpg)

*위 파이프라인의 개념 일러스트 — 그림 속 대시보드는 그래픽이며 실제 도구의 스크린샷이 아닙니다.*


### 하드웨어 가속: 별도의 비공개 배포

이름에 `ane`가 들어 있지만, 하네스를 실행하는 데 **특수 실리콘은 요구되거나 주장되지 않습니다**.
배포된 엔진은 순수 결정적 CPU(Python +
SQLite)이며 macOS Apple Silicon, macOS Intel, Linux에서 동일하게 동작합니다.
신경망 하드웨어 가속은 별도로 유지되며 이 리포지토리의 일부가
아닙니다.

---

## 기술 사양 및 엄밀성

수치적 엄밀성을 중시하는 연구자, 아키텍트, 기술 리더를 위해:

- **고정 벤치마크 분할:** 모든 릴리스 숫자는 고정 18-task 평가 분할(`benchmarks/splits.json`, seed `20261002`)에서 실행됩니다. 튜닝은 엄격히 dev split에 격리됩니다.
- **결정적 토큰 추정기:** 토큰 카운팅은 핀된 추정기(`TOKEN_ESTIMATOR_VERSION="2"`)를 사용해 외부 토크나이저 드리프트 없이 머신과 Python 버전 간에 숫자가 100% 재현됩니다.
- **임베딩 정책:** 로컬 비용/지연 트레이드오프에 따라 v0.1에서 임베딩은 의도적으로 제외됩니다. [ADR-002](docs/adr-002-embedding-go-no-go.md)를 보세요.
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
