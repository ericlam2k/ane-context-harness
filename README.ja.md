# ⚡ ane-context-harness

[英語](README.md) · [ベトナム語](README.vi.md) · [中国語](README.zh.md) · [フランス語](README.fr.md) · [スペイン語](README.es.md) · [日本語](README.ja.md) · [韓国語](README.ko.md)

> **エージェントが読むコンテキストを 60%+ 削減し、必要な行はすべて残し、4ms 未満でコンテキストを選定 — すべてローカルマシン上で完全オフライン動作。**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## これは何？

バイブコーディングや AI エージェント（Cursor、Claude Code、OpenCode、Cline、Windsurf、Aider）を使うとき、コードベース全体を LLM のコンテキストウィンドウに流し込むのは **遅く、無駄が多く、危険** です：
- **肥大化したコンテキスト:** 毎回ファイル全体を突っ込むと、無関係なボイラープレートにモデルが埋もれます — プロバイダは再利用の有無にかかわらず、すべてのトークンをカウントします。
- **応答の遅延:** 不要な何千行ものプリフィルで、LLM の time-to-first-token が遅くなります。
- **Lost in the middle:** 無関係なボイラープレートに埋もれると、モデルは幻覚を起こしたりバグを見逃したりします。
- **シークレットの漏洩:** `.env` のシークレットや AWS 認証情報を、意図せずサードパーティのモデルプロバイダに送ってしまう。

**ane-context-harness** は、コードベースとコーディングエージェントの間に立つ、軽量なローカルファーストのコンテキストエンジンです。**~3 milliseconds** でリポジトリをインデックスし、シンボル階層（関数、インターフェース、型）を抽出し、ノイズを除去し、シークレットをマスキングし、タスク完了にエージェントが実際に必要とする高価値なコード証拠だけをパックします。

> 名前の `ane` は歴史的なものです。**依存関係ではありません。** 出荷パスは純粋な CPU で、macOS Apple Silicon、macOS Intel、Linux 上で動作します。ハードウェアアクセラレーションは別のプライベート配布にあります。

外部ネットワーク呼び出しはゼロ。100% プライベートかつオフライン。

---

## 実際のベンチマーク結果

合成 Python および TypeScript コードベース上の凍結評価スプリット（`benchmarks/splits.json`）で、**30 件のベンチマークタスク**（小規模 10、標準 10、高難度 10）を評価：

| 指標 | ハーネスなし（リポジトリ全ダンプ） | ハーネスあり（決定的） | あなたにとっての意味 |
|---|---|---|---|
| **Median Context Tokens** | **3,213 tokens** | **782 tokens** | **LLM へ送る量が 60.47% 少ない** |
| **Required-Evidence Recall** | 1.0 (100%) | **1.0 (100%)** | **重要なコードを一度も見逃さない** |
| **Context Selection Speed** | ~0.01 ms (raw dump) | **3.05 ms – 3.83 ms** | **4ms 未満のローカル応答 — ネットワークより 100x 高速** |
| **Peak Token Savings** | 0% | **Up to 90.32%** | **設定・コンフィグ系のターゲットタスクで最大 ~90% 削減** |
| **Ranking Accuracy (nDCG@10)**| n/a | **0.849** | **最も重要な関数を先頭に配置** |
| **Secret Redaction** | 0% (leaks all secrets) | **100% local redaction** | **`.env`、AWS キー、証明書がマシンから出ない** |
| **Derived Cost per Task** *(at $3/M)* | ~$0.0096 / task | **~$0.0023 / task** | **記載レートでタスクあたり ~75% 少ない送信 — 請求額自体は、プロバイダが再読込ではなく再利用する量に応じて動く** |

*(レイテンシとメモリは Apple Silicon / CPU 上でローカル計測。コストと TTFT の数値は記載のトークンレートから算出。手法と再現可能なログは `benchmarks/reports/` および `benchmarks/logs/`)。*

### サンプルタスク内訳

| タスク種別 | 例タスク | Raw Tokens | Harness Tokens | Reduction | Recall | Select Latency |
|---|---|---|---|---|---|---|
| **設定とコンフィグ** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **ルールとロジック** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **バグ修正 (Python)** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript アーキテクチャ**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **複雑な複数ファイルのカート** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### トークン削減（実測、現行 main）

![タスクごとのベースライン対送信トークン（最小 recall 1.0）、および同一パック形式の中央値（JSON / markdown / compact）](docs/token-savings.png)

公開関数のみで計測（`scripts/measure_token_savings.py`、凍結評価スプリット、ピン留めしたカウンタ 1 つ — 再現は `PYTHONPATH=src python3 scripts/measure_token_savings.py`、描画は `scripts/plot_token_savings.py`）。同じ証拠、3 通りのレンダリング。レンダリングは選定に一切触れません。

### 実在ツールとの同一演習（キーなし、アカウントなし）

![選定の中央値と同一パック形式の中央値: harness select 対 headroom rewrite 対 evidence-JSON / markdown / real TOON / compact](docs/same-exercise-comparison.png)

どの対抗手段でも実行できるパススルーテスト: 評価タスク 18 件、カウンタ 1 つ。Headroom 0.39.1 と本物の TOON エンコーダをローカルで実行（`pip install headroom-ai toon-format`、続いて `PYTHONPATH=src python3 scripts/bench_same_exercise.py`、描画は `scripts/plot_same_exercise.py`）。タスクを見ない書き換えは選定より多く送り、生存ゲートを持ちません。本物の TOON は複数行コードで行ごとのマッピングにフォールバックしますが、私たちの compact は CSV ヘッダと逐語的な行を維持します。

---

## 開発者とバイブコーダーに支持される理由

- 💰 **タスクあたりのコンテキストを減らし、出力を安定:** プロンプトと無関係なファイルをスキップ — 安定した出力なら、プロバイダは再課金せず既に読んだ内容を再利用できます。Cut% はローカルのコンテキスト削減であり、請求額の主張ではありません。
- ⚡ **瞬時（~3ms）のレイテンシ:** Mac または Linux 上で、ネイティブ Python と C 拡張として完全にローカル実行。
- 🎯 **ピンポイントの精度:** AST シンボル宣言（クラス、TypeScript インターフェース、enum、関数）と BM25 語彙検索、トークン予算つきスコア優先パッキングを組み合わせます。
- 🛡️ **ゼロリークのシークレットサニタイズ:** AWS キー、RSA/PEM 秘密鍵、`.env` ファイル、高エントロピーシークレットを自動スキャンし、プロンプト描画前にリクエストスコープの安定したプレースホルダへ置換します。
- 🔌 **ユニバーサルなエージェント対応:** **Anthropic Messages**（プロンプトキャッシュのブレークポイント付き）、**OpenAI Responses**、**OpenAI 互換 chat**、クリーンな **Markdown** 向けアダプタを同梱。

---

## 仕組み

![コンテキストパッキングの概要: LLM が受け取るもの、タスクから用語への書き換え、keep/drop ルール、理由辞書、パッキング上限、履歴](docs/context-packing-overview.png)

実際のパイプラインから生成した 1 ページのポスター（`scripts/plot_packing_overview.py`）: タスクの語がスコア付き用語へ書き換わり、必須ピンは必ず飛び、裁量カードは予算内でスコア優先にパックされ、残したカードには議論できる理由が付きます。パーセントは、送り得たすべてよりどれだけ少なく送ったかを示します — 請求額自体は、プロバイダが再読込ではなく再利用する量に応じて動きます。

---

## クイックスタート（60 Seconds）

### 1. インストール

macOS または Linux 上の Python 3.13 または 3.14 が必要です：

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

インストールを確認：
```bash
ane-harness health
```

### 1b. ワンコマンドセットアップ + prove-it（導入ゲート）

```bash
# index, install the agent skill, smoke-test (prints one summary line)
ane-harness setup --repo /path/to/your/project --repo-id my-project --yes

# prove-it: reduction/latency proof on YOUR repo (5 canned tasks, no labels needed)
ane-harness prove --repo /path/to/your/project --repo-id my-project
# with your own tasks: --tasks-file prompts.jsonl
# with a report dir: --out /tmp/prove-report
```

`prove` はラベルなしです。削減率の中央値 + p50 レイテンシと
`recall: not_applicable` を報告します。再現率の証明には人手ラベル付きタスク（凍結した `benchmarks/splits.json` の仕組み）が必要です。ラベルなし実行は再現率を主張しません。

### 2. コードベースのインデックス

任意のローカルフォルダまたはリポジトリを、ローカル SQLite ストアへインデックス（増分で非常に高速）：

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. プロンプト向けの関連コンテキストを選定

コーディングタスクに合わせた、コンパクトでトークン予算つきの Markdown パッケージを取得：

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. 多数のプロンプトにわたる前後のコンテキスト削減を記録（`update`）

タスク一式（JSONL ファイルまたは stdin）に対して選定を実行し、前後のトークン予算を表示 + 記録します。ローカル、ネットワークなし：

```bash
# from a JSONL file (one {"task": "..."} or bare task per line)
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

タスクごとの行は JSONL として `--log` にも追記されます（gitignore 済み）。
**正直な但し書き** が毎回 stderr に出力されます：*"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

毎回の実行は、stderr に 1 行の cut フッタも出します（同じ
行が stdout JSON の `summary` キーにも入ります）。例：
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`。平易な言葉のみ —
jargon なし、`#` 見出しマークアップなし。合計はローカルに蓄積します（カウントのみ、
タスク本文なし） — いつでも
`ane-harness daily` で確認でき、`.zshrc`/`.bashrc` に
`eval "$(ane-harness shell-init)"` を入れればシェル終了のたびに表示されます。

エージェントは同梱スキル経由で、依存関係なしに同じ動作を得られます：
`skills/ane-harness/SKILL.md` — エージェントの skills ディレクトリへコピーすれば、
他のセットアップなしで、各タスク後に削減合計が自動表示されます。OpenCode/Claude/エージェント互換ホストではグローバルにも動き、プロジェクトごとの
インストールは不要です：`~/.config/opencode/skills/`、`~/.claude/skills/`、または
`~/.agents/skills/`（新しいセッションが取り込みます）。

### 3c. ネイティブ連携のないエージェント向けプロキシモード（`proxy`）

stdin にタスクを流し込み（1 行あたり `{"task": "..."}` または素のタスク）、
stdout に証拠 Markdown を返す — skill、MCP、HTTP は不要：

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout は純粋な Markdown（タスクごとに 1 ドキュメント、`---` 区切り、
`<!-- ane-harness task N/M ... -->` 境界付き）。タスクごとの cut
フッタは stderr へ。repo-id が既にインデックス済みなら `--repo` は省略できます。

### 4. またはローカルのバックグラウンドサーバーとして実行

> **エージェント: エージェントターン内でこれを実行しないでください。** `serve`（`mcp` と同様）は
> 終了しません — 起動するツール呼び出しは永久にブロックし、ターンが
> 完了せず、以降のプロンプトすべてがその後ろに並びます。対話端末で `--tasks-file` なしの素の
> `update`/`proxy` は stdin 待ちではなく、ヒント付きで
> exit 2 します。エージェントターン内ではワンショットコマンド
> （`index`、`select`、`prove`、`daily`、`health`）だけを使ってください。サーバーは実端末からデタッチして実行
> （`nohup ane-harness serve --port 8765 &`）するか、そもそも起動しないでください。

ローカル HTTP API を起動（エージェントやツールへ接続する準備ができます）：

```bash
ane-harness serve --port 8765
```

利用可能なエンドポイント：
- `GET  /v1/health` — システム状態、コンピュートモード、プロファイル
- `POST /v1/repositories/index` — リポジトリのインデックスまたは更新
- `POST /v1/context/select` — タスク向けに最適化したコンテキストを取得
- `POST /v1/context/compress-output` — 冗長なテスト/ビルドログをクリーンな失敗ダイジェストへ圧縮

---

## Python での使い方

独自の AI エージェントワークフロー内から、ハーネスを直接使うこともできます：

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

## 動作の仕組み

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

1. **シンボル認識 AST チャンク:** 愚直な行分割ではなく、実際のコード構造（クラス、メソッド、TypeScript の型/インターフェース/enum）をパースします。
2. **決定的検索:** シンボル用語ガード、サブトークン分割、複数形フォールディングでフィルタした高速な語彙 BM25 検索。
3. **スコア優先の予算パッキング:** 指定トークン予算（例: 1,200 tokens）内に厳密に収まるよう貪欲にパックし、必須証拠が切り捨てられないことを保証します。
4. **シークレット検出とプライバシーフェンス:** 正規の除外パターン（`.env*`、`.aws/**`、`*.pem` など）は読まず、正規表現 + エントロピー分類器が機微トークンを安定プレースホルダへ置換します。
5. **ノイズ圧縮:** 冗長なツール出力（テストトレース、端末ログ）を、信号を残したコンパクトなダイジェストへ畳みます。

### ハードウェアアクセラレーション：別のプライベート配布

名前に `ane` が含まれますが、ハーネスの実行に **専用シリコンは不要であり、主張もしていません**。出荷エンジンは純粋に決定的な CPU（Python +
SQLite）で、macOS Apple Silicon、macOS Intel、Linux 上で同一に動作します。
ニューラルハードウェアアクセラレーションは別に保守しており、このリポジトリの一部ではありません。

---

## 技術仕様と厳密さ

数値の厳密さを気にする研究者、アーキテクト、テクニカルリード向け：

- **凍結ベンチマークスプリット:** リリース数値はすべて凍結した 18-task 評価スプリット（`benchmarks/splits.json`、seed `20261002`）で実行。チューニングは dev スプリットに厳密に隔離。
- **決定的トークン推定器:** トークンカウントはピン留めした推定器（`TOKEN_ESTIMATOR_VERSION="2"`）を使うため、外部トークナイザのドリフトなしに、マシンと Python バージョンを超えて数値が 100% 再現可能。
- **埋め込みポリシー:** ローカルのコスト/レイテンシトレードオフに基づき、v0.1 では埋め込みを意図的に除外。 [ADR-002](docs/adr-002-embedding-go-no-go.md) を参照。
- **リリース証拠バンドル:** チェックサム付きリリース証拠は `ane-harness evidence verify ane-context-harness-evidence-v0.1` で暗号学的に検証。

---

## テストスイートの実行

```bash
# Run all 258 unit, integration, and security tests
python3 -m pytest -q

# Run concurrent A/B benchmark evaluation
python3 scripts/run_concurrent_ab.py 1 /tmp/eval-run
```

---

## ライセンス

MIT License。ローカル知能、開発者のプライバシー、健全なトークン予算のために設計されています。