# ⚡ ane-context-harness

[English](README.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md) · [Français](README.fr.md) · [Español](README.es.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

> **エージェントが読み込むコンテキストを60%以上削減し、必要な行はすべて維持。4ミリ秒以内でコンテキストを選択し、ローカルマシン上で完全にオフラインで動作します。**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## これは何か？

Cursor、Claude Code、OpenCode、Cline、Windsurf、AiderなどのAIエージェントでコードを書いたり実行したりする際、コードベース全体をLLMのコンテキストウィンドウに流し込むのは、**低速かつ無駄が多く、危険**です。

- **肥大化したコンテキスト：** すべてのファイルを毎回入力すると、モデルは無関係なボイラープレート（定型コード）に埋もれてしまいます。また、プロバイダーは再利用の有無にかかわらずすべてのトークンをカウントします。
- **応答の遅延：** 何千行もの不要なコードを先行入力することで、LLMの最初のトークン生成までの時間（TTFT）が大幅に遅延します。
- **情報の埋没（Lost in the middle）：** 関連性のないボイラープレートに埋もれることで、モデルがハルシネーション（幻覚）を起こしたり、バグを見逃したりします。
- **機密情報の漏洩：** `.env`内の秘密鍵やAWSクレデンシャルを、意図せずサードパーティのモデルプロバイダーに送信してしまうリスクがあります。

**ane-context-harness** は、コードベースとコーディングエージェントの間に位置する軽量でローカルファーストなコンテキストエンジンです。わずか **3ミリ秒程度** でリポジトリをインデックス化し、シンボル階層（関数、インターフェース、型）を抽出してノイズを除去、機密情報をマスキングし、タスクの完了に本当に必要な高価値のコード情報のみをエージェントに提供します。

> `ane` という名前は歴史的な経緯によるものであり、依存関係ではありません。出荷されるコードは純粋なCPUベースで、macOS Apple Silicon、macOS Intel、およびLinux上で動作します。ハードウェアアクセラレーションは別の非公開ディストリビューションに存在します。

外部ネットワーク呼び出しはゼロ。100%プライベートかつオフラインです。

---

## ベンチマーク結果

固定された評価用データセット（`benchmarks/splits.json`）を使用し、合成されたPythonおよびTypeScriptコードベースの **30のベンチマークタスク**（小規模10、標準10、困難10）で評価しました。

| 指標 | ハーネスなし（全リポジトリダンプ） | ハーネスあり（決定論的） | ユーザーにとっての意味 |
|---|---|---|---|
| **中央値コンテキストトークン** | **3,213 トークン** | **782 トークン** | **LLMへの送信量を60.47%削減** |
| **必要な情報の再現率** | 1.0 (100%) | **1.0 (100%)** | **重要なコードを一つも見逃さない** |
| **コンテキスト選択速度** | ~0.01 ms (未加工) | **3.05 ms – 3.83 ms** | **4ms未満の高速応答 — ネットワークより100倍高速** |
| **最大トークン削減率** | 0% | **最大90.32%** | **対象設定タスク等で最大約90%の節約** |
| **ランキング精度 (nDCG@10)** | n/a | **0.849** | **最も重要な関数を最優先に配置** |
| **機密情報のマスキング** | 0% (全て漏洩) | **100% ローカルマスキング** | **`.env`、AWSキー等はマシンから出ない** |
| **タスクあたりの派生コスト** *(3ドル/Mトークン換算)* | ~$0.0096 / タスク | **~$0.0023 / タスク** | **送信量を約75%削減。プロバイダーの再利用率向上によりコスト抑制** |

*(レイテンシとメモリはApple Silicon / CPU上でローカルに測定。コストとTTFTの数値は指定されたトークン単価に基づく。手法および再現可能なログは `benchmarks/reports/` および `benchmarks/logs/` を参照。)*

### タスク例の内訳

| タスクタイプ | タスク例 | 未加工トークン | ハーネス利用トークン | 削減率 | 再現率 | 選択レイテンシ |
|---|---|---|---|---|---|---|
| **設定・構成** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **ルールとロジック** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **バグ修正 (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScriptアーキテクチャ** | `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **複雑なマルチファイルカート** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### トークン削減量の計測（現在のメインブランチ）

![Per-task baseline vs sent tokens with min recall 1.0, plus identical-pack format medians (JSON / markdown / compact)](docs/token-savings.png)

公開関数のみを対象として測定（`scripts/measure_token_savings.py`、凍結評価分割、固定カウンター — 再現には `PYTHONPATH=src python3 scripts/measure_token_savings.py`、描画には `scripts/plot_token_savings.py` を使用）。同じ証拠データに対し3つのレンダリングを使用。レンダリングは選択には影響しません。

### 他のツールとの比較（キーやアカウントは不要）

![Selection medians and identical-pack format medians: harness select vs headroom rewrite vs evidence-JSON / markdown / real TOON / compact](docs/same-exercise-comparison.png)

比較テスト: 18の評価タスク、1つのカウンター。Headroom 0.39.1 および実用的なTOONエンコーダーをローカルで実行（`pip install headroom-ai toon-format` の後、`PYTHONPATH=src python3 scripts/bench_same_exercise.py`、描画には `scripts/plot_same_exercise.py` を使用）。タスクを考慮しない書き換えは選択するよりも多くのトークンを送信し、生存ゲートを維持しません。実用的なTOONは複数行のコードに対して行単位のマッピングにフォールバックしますが、我々のコンパクトフォーマットはCSVヘッダーと逐語的な行を維持します。

---

## 開発者から愛される理由

- 💰 **タスクごとのコンテキスト削減と安定した出力：** プロンプトに関係のないファイルをスキップ。安定した出力により、プロバイダーは読み取り済みの内容を再利用できるため、再課金を防げます。削減率（Cut%）はローカルのコンテキスト削減量を測るもので、請求額そのものではありません。
- ⚡ **即時（~3ms）レイテンシ：** ネイティブPythonおよびC拡張機能で、MacやLinux上で完全にローカル動作。
- 🎯 **ピンポイントの精度：** ASTシンボル宣言（クラス、TypeScriptインターフェース、列挙型、関数）とBM25語彙検索、トークン予算ベースのスコア優先パッキングを組み合わせ。
- 🛡️ **機密情報の漏洩ゼロ：** AWSキー、秘密のRSA/PEMキー、`.env`ファイル、高エントロピーの秘密情報を自動的にスキャンし、プロンプト生成前に要求スコープごとの安定したプレースホルダーに置換。
- 🔌 **汎用的なエージェントサポート：** **Anthropic Messages**（プロンプトキャッシングブレークポイント付き）、**OpenAI Responses**、**OpenAI互換チャット**、およびクリーンな**Markdown**用のすぐ使えるアダプターを同梱。

---

## 仕組み

![Context packing overview: what the LLM receives, how tasks rewrite to terms, keep/drop rules, reason dictionary, packing limits, history](docs/context-packing-overview.png)

実際のパイプラインから生成されたワンページポスター（`scripts/plot_packing_overview.py`）：タスク単語はスコア付けされた用語に書き換えられ、必須のピン留めは常に保持されます。任意のカードは予算内でスコア順にパックされ、保持された各カードには議論可能な理由が付随します。パーセンテージは、送信可能なすべてに対してどれだけ削減したかを示しています。

---

## クイックスタート (60秒)

### 1. インストール

macOSまたはLinuxでPython 3.13または3.14が必要です。

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

インストールを検証：
```bash
ane-harness health
```

### 1b. ワンコマンドセットアップ + 証明（検証）

```bash
# インデックス化、エージェントスキルのインストール、スモークテスト（要約を1行表示）
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# 証明: あなたのリポジトリ上での削減率/レイテンシの検証（5つの標準タスク、ラベル不要）
ane-harness prove --repo /path/to/your/project --repo-id my-project
# 独自のタスクを使用する場合: --tasks-file prompts.jsonl
# レポートディレクトリを指定する場合: --out /tmp/prove-report
```

`prove`はラベルなしです。中央値の削減率とp50レイテンシを報告し、`recall: not_applicable`となります。再現率の証明には手動ラベル付きタスク（凍結された `benchmarks/splits.json` 機構）が必要です。

### 2. コードベースのインデックス化

ローカルのフォルダやリポジトリをローカルのSQLiteストアにインデックス化します（増分更新可能で非常に高速）：

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. プロンプトに関連するコンテキストの選択

コーディングタスクに合わせた、トークン予算内でコンパクトなMarkdownパッケージを取得します：

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

### 3b. 多くのプロンプトにわたるコンテキスト削減の前後ログ記録 (`update`)

タスクのバッチに対して選択を実行し、トークン予算の前後を印刷・ログ記録します。ローカルで動作し、ネットワークは使いません：

```bash
# JSONLファイルから（1行につき {"task": "..."} 1つ、またはタスク文字列のみ）
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

出力例：

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

タスクごとの行は `--log` にもJSONL形式で追記されます（gitignored）。
すべての実行でstderrに警告を表示： *"local measurements over the given repo; redaction does not guarantee all secrets are caught."*

すべての実行は、stderrに1行の削減フッターを表示します（stdoutのJSONの `summary` キーも同様）。例: `ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`。合計はローカルに蓄積されます（カウントのみ、タスクテキストは保持されません）。いつでも `ane-harness daily` で確認可能。また、`.zshrc`/`.bashrc` で `eval "$(ane-harness shell-init)"` を設定すれば、シェル終了時に毎回表示されます。

エージェントも同梱のスキルで依存関係なしに同じ動作を得られます：`skills/ane-harness/SKILL.md` をエージェントのスキルディレクトリにコピーすれば、タスク終了後に自動的に削減合計が表示されます。OpenCode/Claude/エージェント互換ホストではグローバルにも動作します。

### 3c. ネイティブ統合がないエージェント用のプロキシモード (`proxy`)

stdinにタスクを流し込み（`{"task": "..."}` または単純なタスク文字列を1行ずつ）、stdoutに証拠Markdownを返します。スキル、MCP、HTTPは不要です：

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdoutは純粋なMarkdownです。repo-idがすでにインデックス化されている場合は `--repo` を省略可能です。

### 4. ローカルバックグラウンドサーバーとして実行

> **エージェントへ:** エージェントのタスク実行中にこれを実行しないでください。`serve`（`mcp`のようなもの）は決して終了しないため、ツール呼び出しが実行されると永遠にブロックされ、後続のプロンプトがすべてキューに並んでしまいます。インタラクティブな端末での `update`/`proxy`（`--tasks-file` なし）は stdin を待つのではなく終了コード2を返します。エージェント内ではワンショットコマンド（`index`、`select`、`prove`、`daily`、`health`）のみを使用してください。サーバーを実行する場合は、端末から切り離して実行（`nohup ane-harness serve --port 8765 &`）してください。

ローカルHTTP APIを起動します：

```bash
ane-harness serve --port 8765
```

利用可能なエンドポイント：
- `GET  /v1/health` — システム状態、計算モード、プロファイル
- `POST /v1/repositories/index` — リポジトリのインデックス化または更新
- `POST /v1/context/select` — タスク用の最適化されたコンテキストの取得
- `POST /v1/context/compress-output` — 詳細なテスト/ビルドログを簡潔なエラーダイジェストに圧縮

---

## Pythonでの使用

自身のAIエージェントワークフロー内で直接使用することも可能です：

```python
from ane_context_harness.config import build_config
from ane_context_harness.pipeline import Pipeline
from ane_context_harness.schemas import SelectRequest
from ane_context_harness.providers import serialize

# 1. パイプラインの初期化
cfg = build_config()
pipeline = Pipeline(cfg)

# 2. リポジトリの登録
pipeline.register_repository("/path/to/my-repo", repo_id="my-repo")

# 3. 予算内でのコンテキスト選択
request = SelectRequest(
    repository_id="my-repo",
    task="Update loyalty point rounding logic in payment service",
    token_budget=1500,
)
package = pipeline.select_context(request)

# 4. お好みのLLMプロバイダー用にシリアライズ
anthropic_payload = serialize("anthropic", package)
openai_payload    = serialize("openai", package)
markdown_text     = serialize("markdown", package)

print(f"Packed {package.metrics['selected_tokens']} tokens (cut {package.metrics['tokens_removed']} tokens)")
```

---

## 仕組み

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

1. **シンボル認識ASTチャンク:** 単純な行分割ではなく、実際のコード構造（クラス、メソッド、TSインターフェース等）を解析します。
2. **決定論的検索:** シンボルガード、サブトークン分割、複数形折りたたみによってフィルタリングされた高速なBM25語彙検索。
3. **スコア優先予算パッキング:** コンテキストは指定されたトークン予算内に収まるように貪欲に詰め込まれ、必須の証拠が削除されることはありません。
4. **機密情報の検知とプライバシーフェンス:** 標準的な除外パターン（`.env*`等）は読み取られず、Regexとエントロピー分類器が機密情報を安定したプレースホルダーに置換します。
5. **ノイズ圧縮:** 詳細なツール出力（トレース、端末ログ）は、シグナルを保持するコンパクトなダイジェストに折りたたまれます。

### ハードウェアアクセラレーション: 別個の非公開ディストリビューション

名前に `ane` が含まれていますが、実行に**特別なシリコンは不要**であり、主張もしていません。出荷されるエンジンは決定論的なCPU（Python + SQLite）のみで構成され、macOS Apple Silicon、macOS Intel、Linuxで同一に動作します。ニューラルハードウェアアクセラレーションは別々に保守されており、本リポジトリには含まれていません。

---

## 技術仕様と厳密さ

数値的な厳密さを求める研究者、アーキテクト、技術リード向け：

- **凍結されたベンチマーク:** 全てのリリース数値は、凍結された18タスクの評価データセット（`benchmarks/splits.json`、シード `20261002`）で実行されます。チューニングは開発用データセットに厳密に限定されています。
- **決定論的トークン見積もり:** トークンカウントには固定された見積もり器（`TOKEN_ESTIMATOR_VERSION="2"`）を使用し、外部のトークナイザーの変動なしに、マシンやPythonのバージョン間で数値を100%再現可能にしています。
- **埋め込みポリシー:** ローカルのコスト/レイテンシのトレードオフに基づき、v0.1では埋め込み（Embedding）を意図的に除外しています。[ADR-002](docs/adr-002-embedding-go-no-go.md) を参照。
- **リリース証拠バンドル:** チェックサム付きのリリース証拠は、`ane-harness evidence verify ane-context-harness-evidence-v0.1` を通じて暗号学的に検証されます。

---

## テストスイートの実行

```bash
# 258のユニット、統合、セキュリティテストをすべて実行
python3 -m pytest -q

# 同時A/Bベンチマーク評価を実行
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## ライセンス

MITライセンス。ローカルインテリジェンス、開発者のプライバシー、健全なトークン予算のために設計されています。