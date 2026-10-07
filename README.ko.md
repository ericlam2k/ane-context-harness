# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **AI 에이전트가 읽는 컨텍스트를 60% 이상 절감하고, 필요한 필수 코드는 100% 유지하며, 4ms 이내에 컨텍스트를 추출합니다 — 로컬 머신에서 완전한 오프라인으로 작동.**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-265%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## 어떤 도구인가요?

Cursor, Claude Code, OpenCode, Cline, Windsurf, Aider와 같은 AI 에이전트를 활용해 바이브 코딩(vibe-coding)을 진행할 때, 전체 코드베이스를 LLM 컨텍스트 윈도우에 그대로 전달하는 것은 **느리고, 비효율적이며, 보안상 위험**합니다:
- **컨텍스트 비대화 (Bloated Context):** 매 턴(turn)마다 전체 파일을 주입하면 모델이 불필요한 보일러플레이트 코드에 파묻히게 되며, 공급업체는 재사용 여부와 상관없이 모든 토큰에 비용을 청구합니다.
- **응답 속도 지연:** 불필요한 수천 줄의 코드를 프리필(prefill)하느라 첫 번째 토큰 생성 시간(TTFT)이 크게 지연됩니다.
- **"Lost in the Middle" 현상:** 모델이 불필요한 정보에 묻히면 할루시네이션(환각)을 일으키거나 중요한 버그를 놓치기 쉽습니다.
- **시크릿 유출 위험:** `.env` 환경 변수나 AWS 자격 증명 등이 의도치 않게 외부 LLM 공급업체로 전송될 수 있습니다.

**ane-context-harness**는 코드베이스와 코딩 에이전트 사이에서 동작하는 경량 로컬 퍼스트(Local-First) 컨텍스트 엔진입니다. 단 **~3밀리초** 만에 리포지토리를 인덱싱하고, 심볼 계층 구조(함수, 인터페이스, 타입)를 추출하며, 노이즈를 제거하고, 시크릿을 마스킹(Redaction)하여 에이전트가 작업에 실제 필요한 고가치 코드 증거만을 패킹합니다.

> `ane`라는 이름은 과거 프로젝트의 유산이며 필수 종속성이 아닙니다. 배포 버전은 순수 CPU 기반으로 작동하며 macOS Apple Silicon, macOS Intel 및 Linux를 완벽히 지원합니다. 하드웨어 가속 기능은 별도의 프라이빗 배포판으로 관리됩니다.

외부 네트워크 호출 0건. 100% 개인정보 보호 및 오프라인 동작.

![개념 일러스트: 무자비한 잘라내기는 AST·import·참조를 깨뜨린다 — 하네스는 코드 서명·AST 구조·필수 의존성을 유지한다](docs/ane-concept-generic.jpg)

*개념 일러스트 — 그림 속 코드는 그래픽이며 실제 트레이스가 아닙니다.*


---

## 실제 벤치마크 결과

고정된 평가 분할 데이터셋(`benchmarks/splits.json`) 기준 Python 및 TypeScript 코드베이스의 **30개 벤치마크 태스크**(소형 10개, 일반 10개, 고난도 10개) 평가 결과:

| 지표 | Harness 미사용 (전체 덤프) | Harness 사용 (결정론적 추출) | 실제 사용자 이점 |
|---|---|---|---|
| **중앙값 컨텍스트 토큰** | **3,213 tokens** | **782 tokens** | **LLM 전송 토큰량 60.47% 절감** |
| **필수 코드 재현율 (Recall)** | 1.0 (100%) | **1.0 (100%)** | **핵심 코드 단 한 줄도 누락 없음** |
| **컨텍스트 추출 속도** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **4ms 미만 로컬 응답 — 네트워크 대비 100배 빠른 속도** |
| **최대 토큰 절감율** | 0% | **최대 90.32%** | **설정 파일 관련 작업에서 최대 ~90% 절감** |
| **랭킹 정확도 (nDCG@10)**| n/a | **0.849** | **가장 중요한 함수를 컨텍스트 최상단에 배치** |
| **시크릿 마스킹 (Redaction)** | 0% (전체 유출) | **100% 로컬 마스킹** | **`.env`, AWS 키, 인증서가 로컬 머신을 벗어나지 않음** |
| **태스크당 추정 비용** *($3/M 토큰 기준)* | ~$0.0096 / task | **~$0.0023 / task** | **기본 요율 기준 전송량 ~75% 절감 — 실제 청구액은 공급업체의 프롬프트 캐시 재사용률에 따라 결정됨** |

*(레이턴시 및 메모리는 Apple Silicon / CPU 로컬 환경에서 측정; 비용 및 TTFT 수치는 표준 토큰 요율 기준 추정치; 상세 방법론 및 로그는 `benchmarks/reports/` 및 `benchmarks/logs/` 참조)*

![개념 일러스트: 동일한 기준으로 컨텍스트 검색 방식 비교](docs/ane-benchmark-concept.jpg)

*개념 일러스트이며 측정 결과가 아닙니다 — 그림 속 토큰 규모와 수치는 예시입니다. 실제 측정값은 위의 표를 참조하십시오.*


---

## 빠른 시작 (60초)

### 1. 설치

macOS 또는 Linux 환경의 Python 3.13 또는 3.14가 필요합니다:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

설치 확인:
```bash
ane-harness health
```

### 1b. 원클릭 설정 및 검증

```bash
# 인덱싱, 에이전트 스킬 설치 및 스모크 테스트 수행
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# 사용자의 리포지토리에서 토큰 절감률 및 레이턴시 검증
ane-harness prove --repo /path/to/your/project --repo-id my-project
```

### 2. 리포지토리 인덱싱

로컬 프로젝트를 로컬 SQLite 데이터베이스에 인덱싱합니다 (증분 업데이트 지원, 초고속):

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. 최적화된 컨텍스트 추출

지정된 토큰 예산(Token Budget)에 최적화된 Markdown 형식의 컨텍스트 패키지를 가져옵니다:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

### 4. 로컬 백그라운드 서버로 실행

에이전트나 외부 도구와 연동할 수 있는 로컬 HTTP API 서버를 실행합니다:

```bash
ane-harness serve --port 8765
```

![개념 일러스트: 시스템 프롬프트와 페이로드가 필터를 거쳐 클린 페이로드로 — 하네스 필터 파이프라인](docs/ane-proxy-tracker-concept.jpg)

*개념 일러스트 — 그림 속 대시보드는 그래픽이며 실제 도구의 스크린샷이 아닙니다.*


---

## Python SDK 사용 예시

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. 파이프라인 초기화
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. 리포지토리 등록 및 인덱싱
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. 토큰 예산 내 컨텍스트 추출
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. 대상 LLM 공급업체 형식으로 직렬화
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Packed {package.metrics['selected_tokens']} tokens (cut {package.metrics['tokens_removed']} tokens)")
```

---


![개념 일러스트: 무거운 베이스라인과 가벼운 하네스 — 토큰은 적게, 정확도는 그대로](docs/ane-concept-dashboard.jpg)

*개념 일러스트 — 그림 속 규모와 표 수치는 예시입니다. 실제 측정값: 중앙값 782 대 3,213 토큰(60.47% 감소), recall 1.0, 위의 표를 참조하십시오.*

## 라이선스

MIT License. 로컬 인텔리전스, 개발자의 개인정보 보호, 그리고 효율적인 토큰 예산 관리를 위해 설계되었습니다.
