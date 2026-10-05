# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **에이전트가 읽는 컨텍스트를 60% 이상 절감하고, 필수 라인을 모두 유지하며, 4ms 이내에 컨텍스트를 선택하세요. 로컬 머신에서 완전히 오프라인으로 실행됩니다.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## 이게 무엇인가요?

Vibe-coding을 하거나 AI 에이전트(Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider)를 실행할 때, 전체 코드베이스를 LLM 컨텍스트 윈도우에 넣는 것은 **느리고, 낭비가 심하며, 위험합니다**:
- **비대한 컨텍스트:** 매번 전체 파일을 밀어 넣으면 모델이 불필요한 보일러플레이트에 파묻히게 됩니다. 또한 제공업체는 재사용 여부와 관계없이 모든 토큰에 대해 비용을 청구합니다.
- **느려진 응답:** 수천 줄의 불필요한 코드를 미리 채우느라 LLM의 첫 토큰 생성 시간(TTFT)이 지연됩니다.
- **중간 유실(Lost in the middle):** 불필요한 보일러플레이트에 묻히면 모델이 환각을 일으키거나 버그를 놓치게 됩니다.
- **비밀 정보 유출:** 자신도 모르게 `.env` 비밀 값이나 AWS 자격 증명을 타사 모델 제공업체로 전송할 수 있습니다.

**ane-context-harness**는 코드베이스와 코딩 에이전트 사이에 위치하는 가볍고 로컬 중심적인 컨텍스트 엔진입니다. **약 3밀리초** 내에 저장소를 인덱싱하고, 심볼 계층 구조(함수, 인터페이스, 타입)를 추출하며, 노이즈를 제거하고, 비밀 정보를 마스킹한 뒤, 에이전트가 작업을 완료하는 데 실제로 필요한 고가치 코드 증거만을 압축하여 제공합니다.

> `ane`라는 이름은 역사적인 명칭일 뿐이며, **의존성이 아닙니다.** 제공되는 경로는 순수 CPU이며 macOS Apple Silicon, macOS Intel, Linux에서 실행됩니다. 하드웨어 가속은 별도의 비공개 배포판에서 관리됩니다.

외부 네트워크 호출 제로. 100% 비공개 및 오프라인.

---

## 실제 벤치마크 결과

고정된 평가 데이터셋(`benchmarks/splits.json`)을 사용하여 Python 및 TypeScript 코드베이스의 **30개 벤치마크 작업**(소규모 10개, 일반 10개, 복잡 10개)을 평가했습니다:

| 지표 | Harness 미사용 (전체 저장소 덤프) | Harness 사용 (결정론적) | 이것이 의미하는 바 |
|---|---|---|---|
| **중간 컨텍스트 토큰** | **3,213 토큰** | **782 토큰** | **LLM으로 전송되는 데이터 60.47% 감소** |
| **필수 증거 회수율** | 1.0 (100%) | **1.0 (100%)** | **핵심 코드를 단 하나도 놓치지 않음** |
| **컨텍스트 선택 속도** | ~0.01 ms (원시 덤프) | **3.05 ms – 3.83 ms** | **4ms 이하 로컬 응답 — 네트워크 대비 100배 빠름** |
| **최대 토큰 절감** | 0% | **최대 90.32%** | **설정 및 구성 작업에서 최대 약 90% 비용 절감** |
| **순위 정확도 (nDCG@10)**| n/a | **0.849** | **가장 중요한 함수를 최상단에 배치** |
| **비밀 정보 마스킹** | 0% (모든 비밀 노출) | **100% 로컬 마스킹** | **`.env`, AWS 키, 인증서가 머신을 절대 떠나지 않음** |
| **작업당 파생 비용** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **명시된 요금 대비 작업당 전송량 약 75% 감소 — 공급자가 다시 읽는 대신 재사용하는 양만큼 청구 금액도 함께 감소** |

*(지연 시간 및 메모리는 Apple Silicon / CPU에서 로컬로 측정됨; 비용 및 TTFT 수치는 명시된 토큰 요금을 기준으로 도출됨; 방법론 및 재현 가능한 로그는 `benchmarks/reports/` 및 `benchmarks/logs/`에 위치).*

### 샘플 작업 분석

| 작업 유형 | 예시 작업 | 원시 토큰 | Harness 토큰 | 절감률 | 회수율 | 선택 지연 시간 |
|---|---|---|---|---|---|---|
| **설정 및 구성** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **규칙 및 로직** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **버그 수정 (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript 아키텍처**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **복잡한 다중 파일 카트** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### 측정된 토큰 절감액 (현재 메인 브랜치 기준)

![작업별 기준 대비 전송 토큰량 및 최소 회수율 1.0, 동일 팩 형식 중앙값(JSON / 마크다운 / 압축)](docs/token-savings.png)

공개 함수만 사용하여 측정(`scripts/measure_token_savings.py`, 고정된 평가 데이터셋, 단일 고정 카운터 — `PYTHONPATH=src python3 scripts/measure_token_savings.py`로 재현하고 `scripts/plot_token_savings.py`로 시각화). 동일한 증거, 세 가지 렌더링 방식; 렌더링은 선택 과정에 영향을 주지 않음.

### 실제 도구 대비 테스트 (키, 계정 불필요)

![선택 중앙값 및 동일 팩 형식 중앙값: harness select vs headroom rewrite vs evidence-JSON / markdown / real TOON / compact](docs/same-exercise-comparison.png)

경쟁 도구들이 수행할 수 있는 패스스루 테스트: 18개 평가 작업, 단일 카운터. Headroom 0.39.1 및 실제 TOON 인코더를 로컬에서 실행(`pip install headroom-ai toon-format` 후 `PYTHONPATH=src python3 scripts/bench_same_exercise.py` 및 `scripts/plot_same_exercise.py`로 시각화). 작업 내용을 모른 채 재작성하는 방식은 선택 방식보다 더 많은 데이터를 전송하며 생존 게이트를 유지하지 못함; 실제 TOON은 다중 라인 코드에서 행 단위 매핑으로 되돌아가는 반면, 당사의 압축 방식은 CSV 헤더와 함께 원문 행을 유지함.

---

## 개발자 및 Vibecoder들이 이 도구를 사랑하는 이유

- 💰 **작업당 컨텍스트 감소, 안정적인 출력:** 프롬프트와 무관한 파일은 제외 — 안정적인 출력은 공급자가 이미 읽은 내용을 재사용하게 하여 다시 비용을 지불하지 않게 합니다. Cut%는 로컬 컨텍스트 절감율을 나타내며, 귀하의 청구 금액이 아닙니다.
- ⚡ **즉각적인 (~3ms) 지연 시간:** Mac 또는 Linux 박스에서 네이티브 Python 및 C 확장으로 로컬에서 완전히 실행됩니다.
- 🎯 **정밀한 정확도:** AST 심볼 선언(클래스, TypeScript 인터페이스, 열거형, 함수)과 BM25 어휘 검색 및 토큰 예산 기반 스코어 우선 패킹을 결합합니다.
- 🛡️ **비밀 정보 유출 제로 마스킹:** AWS 키, 개인 RSA/PEM 키, `.env` 파일 및 고엔트로피 비밀 정보를 자동으로 스캔하고 마스킹하여 프롬프트가 렌더링되기 전에 안정적인 요청 범위의 자리 표시자로 대체합니다.
- 🔌 **범용 에이전트 지원:** **Anthropic Messages**(프롬프트 캐싱 브레이크포인트 포함), **OpenAI Responses**, **OpenAI 호환 챗**, 깔끔한 **Markdown**을 위한 즉시 사용 가능한 어댑터를 제공합니다.

---

## 작동 원리

![컨텍스트 패킹 개요: LLM이 받는 내용, 작업이 용어로 재작성되는 방식, 유지/삭제 규칙, 이유 사전, 패킹 제한, 이력](docs/context-packing-overview.png)

실제 파이프라인에서 생성된 한 페이지 포스터(`scripts/plot_packing_overview.py`): 작업 단어가 점수화된 용어로 재작성되고, 필수 고정 항목은 항상 포함되며, 재량 카드는 예산 내에서 점수 우선으로 패킹되고, 유지된 모든 카드에는 논의 가능한 근거가 포함됩니다. 퍼센트 수치는 전체 전송 가능량 대비 전송량을 나타냅니다. 공급자가 재사용하는 만큼 청구 금액이 절감됩니다.

---

## 퀵 스타트 (60초)

### 1. 설치

macOS 또는 Linux에서 Python 3.13 또는 3.14가 필요합니다:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

설치 확인:
```bash
ane-harness health
```

### 1b. 원커맨드 설정 + 증명 (채택 게이트)

```bash
# 인덱싱, 에이전트 스킬 설치, 스모크 테스트 (요약 한 줄 출력)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# 증명: 귀하의 저장소에서 절감률/지연 시간 증명 (5개 사전 정의 작업, 레이블 불필요)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# 직접 만든 작업 사용 시: --tasks-file prompts.jsonl
# 보고서 디렉토리 사용 시: --out /tmp/prove-report
```

`prove`는 레이블이 지정되지 않습니다: 중앙값 절감률 + p50 지연 시간을 보고하며 `recall: not_applicable`을 표시합니다. 회수율 증명은 수동 레이블링 작업(고정된 `benchmarks/splits.json` 메커니즘)이 필요합니다. 레이블이 없는 실행은 회수율을 주장하지 않습니다.

### 2. 코드베이스 인덱싱

로컬 폴더나 저장소를 로컬 SQLite 저장소로 인덱싱합니다 (점진적이며 매우 빠름):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. 프롬프트를 위한 관련 컨텍스트 선택

코딩 작업에 맞춘 토큰 예산이 적용된 압축 마크다운 패키지를 가져옵니다:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. 여러 프롬프트에 걸친 컨텍스트 절감 전/후 로그 확인 (`update`)

여러 작업(JSONL 파일 또는 stdin)에 대해 선택 과정을 실행하고 토큰 예산 전/후를 출력 및 기록합니다. 로컬 실행, 네트워크 없음:

```bash
# JSONL 파일로부터 (라인당 {"task": "..."} 하나 또는 단순 작업)
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

작업별 행은 `--log`(gitignored)에도 JSONL로 추가됩니다.
**솔직한 주의사항**이 모든 실행 시 stderr로 출력됩니다: *"주어진 저장소에 대한 로컬 측정값; 마스킹이 모든 비밀 정보를 잡아낸다고 보장하지는 않습니다."*

모든 실행은 stderr로 한 줄짜리 절감 요약(stdout JSON의 `summary` 키와 동일)을 출력합니다. 예:
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`. 순수 텍스트만 출력 — 전문 용어 없음, `#` 헤딩 마크업 없음. 합계는 로컬에 누적됩니다(개수만, 작업 텍스트 제외). 언제든지 `ane-harness daily`로 확인하거나, `.zshrc`/`.bashrc`에서 `eval "$(ane-harness shell-init)"`를 통해 쉘 종료 시마다 확인하세요.

에이전트는 번들된 스킬(`skills/ane-harness/SKILL.md`)을 통해 의존성 없이 동일한 동작을 수행합니다. 스킬 디렉토리에 복사하면 작업 완료 후 자동으로 절감 총합이 표시됩니다. OpenCode/Claude/에이전트 호환 호스트의 경우 전역적으로도 작동합니다: `~/.config/opencode/skills/`, `~/.claude/skills/`, 또는 `~/.agents/skills/`에 넣으면 새로운 세션에서 즉시 반영됩니다.

### 3c. 네이티브 통합이 없는 에이전트를 위한 프록시 모드 (`proxy`)

stdin을 통해 작업을 파이프하고 (라인당 `{"task": "..."}` 하나 또는 단순 작업), stdout으로 증거 마크다운을 돌려받습니다 — 스킬, MCP, HTTP 불필요:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout은 순수 마크다운(작업당 문서 하나, `---`로 구분, `<!-- ane-harness task N/M ... -->` 경계 포함); 작업별 절감 요약은 stderr로 출력됩니다. repo-id가 이미 인덱싱되어 있다면 `--repo`는 생략 가능합니다.

### 4. 로컬 백그라운드 서버로 실행

> **에이전트 주의:** 에이전트 작업 중에는 이 명령을 실행하지 마십시오. `serve`(MCP와 유사)는 절대 종료되지 않습니다. 이를 실행하는 도구 호출은 영원히 차단되어, 작업이 완료되지 않고 이후의 모든 프롬프트가 대기열에 쌓이게 됩니다. 대화형 터미널에서 `--tasks-file` 없이 `update`/`proxy`를 실행하면 stdin 대기 대신 2를 반환하며 힌트를 출력합니다. 에이전트 내에서는 단발성 명령(`index`, `select`, `prove`, `daily`, `health`)만 사용하십시오. 서버를 실행할 때는 실제 터미널과 분리하여(`nohup ane-harness serve --port 8765 &`) 실행하거나, 실행하지 마십시오.

로컬 HTTP API 시작 (에이전트 또는 도구와 연동 준비):

```bash
ane-harness serve --port 8765
```

사용 가능한 엔드포인트:
- `GET  /v1/health` — 시스템 상태, 컴퓨팅 모드 및 프로필
- `POST /v1/repositories/index` — 저장소 인덱싱 또는 업데이트
- `POST /v1/context/select` — 작업에 최적화된 컨텍스트 검색
- `POST /v1/context/compress-output` — 장황한 테스트/빌드 로그를 깔끔한 실패 다이제스트로 압축

---

## Python에서 사용하기

에이전트 워크플로우 내에서 직접 harness를 사용할 수 있습니다:

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. 파이프라인 초기화
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. 저장소 인덱싱
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. 예산 범위 내 컨텍스트 선택
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. 선호하는 LLM 공급자를 위해 직접 직렬화
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

1. **심볼 인식 AST 청킹:** 단순한 라인 분할 대신, 실제 코드 구조(클래스, 메서드, TypeScript 타입/인터페이스/열거형)를 파싱합니다.
2. **결정론적 검색:** 심볼 용어 가드, 서브토큰 분할, 복수형 폴딩으로 필터링되는 고속 어휘 BM25 검색.
3. **점수 우선 예산 패킹:** 지정된 토큰 예산(예: 1,200 토큰) 내에 컨텍스트가 탐욕적으로 패킹되어, 필수 증거가 절대 잘리지 않도록 보장합니다.
4. **비밀 정보 탐지 및 개인 정보 보호:** 표준 제외 패턴(`.env*`, `.aws/**`, `*.pem` 등)은 절대 읽지 않으며, 정규식 + 엔트로피 분류기가 민감한 토큰을 안정적인 자리 표시자로 대체합니다.
5. **노이즈 압축:** 장황한 도구 출력(테스트 추적, 터미널 로그)은 신호를 보존하는 압축된 다이제스트로 축소됩니다.

### 하드웨어 가속: 별도의 비공개 배포판

이름에 `ane`가 포함되어 있지만, harness를 실행하기 위해 **특수 실리콘이 필요하거나 주장하지 않습니다.** 제공된 엔진은 순수 결정론적 CPU(Python + SQLite)이며 macOS Apple Silicon, macOS Intel, Linux에서 동일하게 실행됩니다. 신경망 하드웨어 가속은 별도로 유지 관리되며 이 저장소에 포함되지 않습니다.

---

## 기술 사양 및 엄격함

수치적 엄격함을 중요시하는 연구자, 설계자 및 기술 리더를 위한 정보:

- **고정 벤치마크 데이터셋:** 모든 릴리스 수치는 고정된 18개 작업 평가 데이터셋(`benchmarks/splits.json`, 시드 `20261002`)에서 실행됩니다. 튜닝은 개발 데이터셋으로 엄격히 격리됩니다.
- **결정론적 토큰 추정기:** 토큰 계수는 고정된 추정기(`TOKEN_ESTIMATOR_VERSION="2"`)를 사용하여 외부 토크나이저 드리프트 없이 머신 및 Python 버전 간에 100% 재현 가능합니다.
- **임베딩 정책:** 임베딩은 로컬 비용/지연 시간 트레이드오프에 따라 v0.1에서 의도적으로 제외되었습니다. [ADR-002](docs/adr-002-embedding-go-no-go.md)를 참조하세요.
- **릴리스 증거 번들:** 체크섬이 포함된 릴리스 증거는 `ane-harness evidence verify ane-context-harness-evidence-v0.1`을 통해 암호학적으로 검증됩니다.

---

## 테스트 제품군 실행

```bash
# 258개의 모든 단위, 통합 및 보안 테스트 실행
python3 -m pytest -q

# 동시 A/B 벤치마크 평가 실행
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## 라이선스

MIT 라이선스. 로컬 지능, 개발자 개인 정보 보호 및 합리적인 토큰 예산을 위해 설계되었습니다.