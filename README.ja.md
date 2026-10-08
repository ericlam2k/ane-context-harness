# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **AIエージェントが読み込むコンテキストを 60% 以上削減。必要なコード行を1行も漏らさず、4ms 未満でコンテキストを抽出 — ローカル環境で完全オフライン動作。**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-265%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## 概要

Cursor、Claude Code、OpenCode、Cline、Windsurf、Aider などの AI エージェントを利用してコーディングを行う際、リポジトリ全体をそのまま LLM のコンテキストウィンドウに投入することは**低速で無駄が多く、セキュリティリスクを伴います**：
- **コンテキストの肥大化（Bloated context）：** ターンごとにファイル全体を送信すると、モデルが無関係なボイラープレートコードに埋もれてしまいます。また、再利用の有無にかかわらず全トークンに対して課金が発生します。
- **レスポンスの低下：** 不要なコードを数千行単位で プリフィル（prefill）するため、最初のトークンが出力されるまでの時間（TTFT）が大幅に遅延します。
- **「Lost in the Middle」現象：** ノイズが多い環境下では、LLM のハルシネーション（幻覚）が発生しやすくなり、重要なバグを見落とす原因になります。
- **シークレットの流出リスク：** `.env` の環境変数や AWS の認証情報などを誤ってサードパーティの LLM プロバイダーへ送信してしまうリスクがあります。

**ane-context-harness** は、コードベースと AI エージェントの間に位置する軽量かつローカルファーストなコンテキストエンジンです。わずか **~3 ミリ秒** でリポジトリのインデックスを作成し、シンボル階層（関数、インターフェース、型定義）を抽出。ノイズの除去およびシークレットの伏字化（Redaction）を行い、エージェントがタスクを完了するために必要な「高価値なコード証拠」のみを抽出してパッキングします。

> `ane` という名称は歴史的な経緯によるものであり、依存関係ではありません。提供されているエンジンは純粋な CPU 処理であり、macOS Apple Silicon、macOS Intel、Linux 上で動作します。ハードウェアアクセラレーション機能は別途プライベート版として管理されています。

外部ネットワークへの通信はゼロ。100% プライベートかつオフラインで動作します。

![概念イラスト: 素朴な切り詰めは AST・import・参照を壊す——ハーネスはコード署名・AST 構造・必須依存を保持する](docs/ane-concept-generic.jpg)

*概念イラスト——図中のコードはグラフィックであり、実際のトレースではありません。*


---

## ベンチマーク実績

固定評価データセット（`benchmarks/splits.json`）を使用し、Python および TypeScript のコードベースにおける **30 件のベンチマークタスク**（小規模 10 件、標準 10 件、高難易度 10 件）で評価を実施：

| 指標 | Harness 未使用（リポジトリ全体のダンプ） | Harness 使用（決定論的抽出） | 導入によるメリット |
|---|---|---|---|
| **コンテキストトークン中央値** | **3,213 tokens** | **782 tokens** | **LLM への送信トークン量を 60.47% 削減** |
| **必須コードの再現率（Recall）** | 1.0 (100%) | **1.0 (100%)** | **重要なコードの欠落は一切なし** |
| **コンテキスト抽出速度** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **4ms 未満のローカル応答 — ネットワーク経由より 100 倍高速** |
| **最大トークン削減率** | 0% | **最大 90.32%** | **設定ファイル関連タスクで最大 ~90% 削減** |
| **ランキング精度 (nDCG@10)**| n/a | **0.849** | **最も重要な関数をコンテキストの最上部に配置** |
| **シークレットの伏字化** | 0%（全漏洩） | **100% ローカル伏字化** | **`.env`、AWS キー、証明書が外部に送信されるのを防止** |
| **タスクあたりの推定量（$3/M換算）** | ~$0.0096 / task | **~$0.0023 / task** | **送信データ量を約 75% 削減 — 実際の請求額はプロバイダーのキャッシュ再利用率に依存** |

*(レイテンシおよびメモリ計測は Apple Silicon / CPU 上のローカル環境で実施。コストおよび TTFT 算定根拠、再現可能なログは `benchmarks/reports/` および `benchmarks/logs/` に収録)*

![概念イラスト: 同じ尺度でコンテキスト取得手法を比較](docs/ane-benchmark-concept.jpg)

*概念イラストであり、実測結果ではありません——図中のトークン規模や数値はイメージです。実際の測定値は上記の表をご覧ください。*


---

## クイックスタート (60 秒)

### 1. インストール

macOS または Linux 上の Python 3.13 / 3.14 が必要です：

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

動作確認：
```bash
ane-harness health
```

### 1b. セットアップおよび検証

```bash
# インデックス作成、エージェント用 Skill のインストール、動作確認
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# 自身のリポジトリで削減率とレイテンシを測定
ane-harness prove --repo /path/to/your/project --repo-id my-project
```

### 2. リポジトリのインデックス作成

ローカルのプロジェクトを SQLite データベースにインデックス化します（差分更新・超高速）：

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. コンテキストの抽出

トークン予算（Token Budget）に最適化された Markdown 形式のコンテキストを取得します：

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

### 4. ローカルバックグラウンドサーバーとしての起動

ローカル HTTP API サーバーを起動し、エージェントや外部ツールと連携します：

```bash
ane-harness serve --port 8765
```

![概念イラスト: システムプロンプトとペイロードがフィルタを通ってクリーンなペイロードに——ハーネスのフィルタパイプライン](docs/ane-proxy-tracker-concept.jpg)

*概念イラスト——図中のダッシュボードはグラフィックであり、実際のツールのスクリーンショットではありません。*


---

## Python SDK での使用例

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. パイプラインの初期化
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. リポジトリの登録とインデックス化
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. トークン予算を指定してコンテキストを抽出
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. 指定の LLM プロバイダー向けにシリアライズ
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Packed {package.metrics['selected_tokens']} tokens (cut {package.metrics['tokens_removed']} tokens)")
```

---


![概念イラスト: 重いベースラインと軽量ハーネス——トークンは少なく、精度はそのまま](docs/ane-concept-dashboard.jpg)

*实測サマリー図——中央値は `benchmarks/reports/phase5-ab-evaluation.json` より（frozen eval split、18 タスク、Arm B deterministic）: 3,213 → 782 トークン（60.47% 削減）、min required recall 1.0。*

## ライセンス

MIT License。ローカルでのプライバシー保護と最適なトークン管理のために設計されています。
