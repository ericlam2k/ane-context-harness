# ⚡ ane-context-harness

[英語](README.md) · [ベトナム語](README.vi.md) · [中国語](README.zh.md) · [フランス語](README.fr.md) · [スペイン語](README.es.md) · [日本語](README.ja.md) · [韓国語](README.ko.md)

> **エージェントが読むコンテキストを 60%+ 削減し、必要な行はすべて残し、コンテキスト選定は 4ms 未満 — ローカルマシン上で完全オフラインで動作します。**

[![Python](https://img.shields.io/badge/Python-3.13%20%7C%203.14-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Linux-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-258%20passed-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

---

## これは何ですか？

バイブコーディングや AI エージェント（Cursor、Claude Code、OpenCode、Cline、Windsurf、Aider）を動かすとき、コードベース全体を LLM のコンテキストウィンドウに流し込むのは **遅く、無駄が多く、危険** です:
- **肥大化したコンテキスト:** 毎回ファイル丸ごとを突っ込むと、無関係なボイラープレートにモデルが埋もれます — プロバイダは再利用の有無にかかわらず、すべてのトークンをカウントします。
- **応答の遅延:** 不要な数千行をプリフィルすると、LLM の time-to-first-token が遅くなります。
- **Lost in the middle:** 無関係なボイラープレートに埋もれると、モデルは幻覚を起こしたりバグを見逃したりします。
- **シークレット漏洩:** `.env` の秘密情報や AWS 認証情報を、知らずにサードパーティのモデルプロバイダへ送ってしまうことがあります。

**ane-context-harness** は、コードベースとコーディングエージェントの間に座る、軽量でローカルファーストなコンテキストエンジンです。**約 3 ミリ秒** でリポジトリをインデックスし、シンボル階層（関数、インターフェース、型）を抽出し、ノイズを取り除き、シークレットをマスキングし、タスク完了にエージェントが本当に必要な高価値なコード証拠だけをパックします。

> 名前の `ane` は歴史的なものです。**依存関係ではありません。** 出荷パスは純粋な CPU で、macOS Apple Silicon、macOS Intel、Linux で動作します。ハードウェアアクセラレーションは別のプライベートディストリビューションにあります。

外部ネットワーク呼び出しはゼロ。100% プライベートかつオフラインです。

---

## 実測ベンチマーク結果

合成 Python / TypeScript コードベース上の **30 件のベンチマークタスク**（小規模 10、典型 10、難易度高 10）を、凍結評価スプリット（`benchmarks/splits.json`）で評価しました:

| 指標 | ハーネスなし（リポジトリ全体のダンプ） | ハーネスあり（決定論的） | あなたにとっての意味 |
|---|---|---|---|
| **コンテキストトークン中央値** | **3,213 トークン** | **782 トークン** | **LLM へ送る量が 60.47% 少ない** |
| **必須エビデンスのリコール** | 1.0 (100%) | **1.0 (100%)** | **重要なコードを一度も見逃していない** |
| **コンテキスト選択速度** | ~0.01 ms（生のダンプ） | **3.05 ms – 3.83 ms** | **サブ 4ms のローカル応答 — ネットワークより 100x 高速** |
| **トークン削減率のピーク** | 0% | **最大 90.32%** | **設定・コンフィグ向けタスクで最大約 90% 削減** |
| **ランキング精度 (nDCG@10)**| n/a | **0.849** | **最も重要な関数を先頭に配置** |
| **シークレットの秘匿化** | 0%（すべてのシークレットを漏洩） | **100% ローカルで秘匿化** | **`.env`、AWS キー、証明書はマシンから出ない** |
| **タスクあたりの実質コスト** *($3/M 換算)* | ~$0.0096 / task | **~$0.0023 / task** | **記載レートでタスクあたり約 75% 減 — 請求自体は、プロバイダが再読せず再利用する量に応じて動く** |

*(レイテンシとメモリは Apple Silicon / CPU 上でローカル測定。コストと TTFT の数値は記載トークンレートからの導出。方法論と再現可能なログは `benchmarks/reports/` と `benchmarks/logs/`。)*

### サンプルタスク内訳

| タスク種別 | 例となるタスク | 生トークン数 | ハーネストークン数 | 削減率 | リコール | 選択レイテンシ |
|---|---|---|---|---|---|---|
| **設定・コンフィグ** | `hard-settings-001` | 3,213 | **311** | **90.32%** | **100%** | 3.88 ms |
| **ルール・ロジック** | `hard-rules-vs-readme-001` | 3,213 | **445** | **86.15%** | **100%** | 4.22 ms |
| **バグ修正（Python）** | `py-discount-report-001` | 3,189 | **629** | **80.28%** | **100%** | 3.72 ms |
| **TypeScript アーキテクチャ**| `ts-discount-001` | 1,236 | **369** | **70.15%** | **100%** | 1.84 ms |
| **複雑なマルチファイルのカート** | `hard-cart-apply-001` | 3,213 | **2,146** | **33.21%** | **100%** | 4.38 ms |

### トークン削減、実測（現行 main）

このチャートの読み方: どのジョブもツールに「このタスクで AI が読むべきものは何か？」と聞いています。左パネルはジョブサイズ別に、コードベース全体を送った場合のテキスト量（グレー）と、ハーネスが選んだ量（グリーン）を比較します — 各グリーンバーの上の数字は、いま送る量とその小ささです。難しいジョブほど必要なファイルが増えるのでグリーンバーは伸びます — ただし必要なファイルは **毎回すべて残しました**。それが要点です。小さいこと自体が良いのではなく、重要なものが欠けないことが条件です。右パネルは同じ選定結果を 3 通りの送り方で示します — フル詳細、読みやすい中間、最短ラッピング — 短いほど安く、ラッピングは *何を* 選ぶかは変えません。

![ジョブサイズごとの読み取り量の削減と、同じ回答の 3 通りのラッピング](docs/token-savings.png)

測定は `PYTHONPATH=src python3 scripts/measure_token_savings.py`、描画は `scripts/plot_token_savings.py`（凍結評価スプリット、ピン留めしたトークンカウンタ 1 つ）。

### 同じ演習を実在ツールと比較（キーなし、アカウントなし）

このチャートの読み方: 同じ 18 件のジョブを同じ物差しで競わせます — 「中央のジョブは何トークンで、必要なものは失われたか？」。最初のチャートが見出しです。全部送るのがコストの高いデフォルト、外部のリライトツールは実際には必要以上に送り、グレーダが要求したコンフィグファイルを一度失いました（FAIL と標記）。一方、こちらの 2 モードは最短で、必要なファイルを毎回残しました（PASS）。2 番目のチャートはその内訳 — 選定だけでの削減と、同じ選定が短いラッピングを選ぶだけでさらに縮む様子。ここでの PASS/FAIL の意味はただ 1 つ: ベンチマークグレーダが必須とする断片がパックに戻ってきたかどうかです。

![同じ 18 件のジョブ: 全送信 vs 外部リライトツール vs 本ツール](docs/head-to-head.png)

![選定の中央値と、同じパックの 4 通りのラッピング、ジョブごとの例付き](docs/same-exercise-comparison.png)

再現: `pip install headroom-ai toon-format`、続けて `PYTHONPATH=src python3 scripts/bench_same_exercise.py`、描画は `scripts/plot_same_exercise.py`。タスクを見ないリライトは選定より多く送り、生存ゲートもありません。本物の TOON エンコーダは複数行コードで行ごとのマッピングにフォールバックしますが、こちらの compact は CSV ヘッダと逐語の行を保ちます。

### 会話での削減、実測

読み方: 1 ジョブは 1 質問ではありません — エージェントは尋ね、フォローアップし、検証します。このベンチはジョブごとに同じ 3 ターン会話を 3 通りで再生します: 毎ターンコードベース全体を送る（149,490 tokens）、トリムしたパック 1 つ（17,094）、先行ターンが見つけたものをフォローアップがすべて保持する 3 つの持ち越しパック（51,940）。持ち越し会話はノーハーネスコストの **約 3 分の 1** — 97,550 トークン減、65.3% 減 — 必要なファイルは 72 ターンすべてで生き残りました（毎ターン recall 1.0。必要なファイルを失うターンは会話を脱線させるので、そのゲートは飾りではなく荷重部材です）。

再現: `PYTHONPATH=src python3 scripts/bench_conversation.py`（凍結評価スプリット、ピン留めしたトークンカウンタ 1 つ。`benchmarks/reports/conversation-bench-eval.json` を書き出します）。境界をはっきり書きます: これらのパックを読むモデルはなく、フォローアップは本物のエージェント反応ではなく固定文字列、課金なし、ジョブは実際には完了しません。測っているのはループそのものではなく、渡す側 — 選定と持ち越し — です。

### 各ファイルに何が起きるか

文書化された 4 つのルール、モデルは関与せず、例外なし: ピンした（またはグレーダが要求する）ファイルは **常にバイト正確** に運ばれます。コード、コンフィグ、diff は構造を保ちます — ピッカーはシンボル単位で選び、書き換えません。折りたたまれるのは **ログと騒がしいツール出力だけ** です（繰り返す進捗行、重複トレースバック、インストールスパムは、何が除かれたかを示す要約行に折ります）。散文は選ばれたまま運ばれ、言い換えられません — ニューラルリライタがないので、ドキュメントを書いていない内容にパラフレーズできません。すべてのパックはファイルごとにどのルールが適用されたかを列挙します — 任意のレポートの `diagnostics.routing` を見て議論してください。

![概念イラスト: 同じ尺度でコンテキスト取得手法を比較](docs/ane-benchmark-concept.jpg)

*概念イラストであり、実測結果ではありません——図中のトークン規模や数値はイメージです。実際の測定値は上記の表と実測グラフをご覧ください。*


---

## 開発者とバイブコーダに支持される理由

- 💰 **タスクあたりのコンテキストを減らし、出力は安定:** プロンプトと無関係なファイルをスキップ — 安定した出力なら、プロバイダは既に読んだものを再利用でき、再課金を避けられます。Cut% はローカルのコンテキスト削減であり、請求額の主張ではありません。
- ⚡ **瞬時（約 3ms）のレイテンシ:** Mac または Linux 上で、ネイティブ Python と C 拡張として完全にローカル実行します。
- 🎯 **ピンポイント精度:** AST シンボル宣言（クラス、TypeScript インターフェース、enum、関数）と BM25 語彙検索、トークン予算つきスコア優先パッキングを組み合わせます。
- 🛡️ **ゼロリークのシークレットサニタイズ:** AWS キー、RSA/PEM 秘密鍵、`.env` ファイル、高エントロピー秘密を自動スキャンし、プロンプト描画前に安定したリクエストスコープのプレースホルダへ置き換えます。
- 🔌 **ユニバーサルなエージェント対応:** **Anthropic Messages**（プロンプトキャッシュブレークポイント付き）、**OpenAI Responses**、**OpenAI 互換 chat**、クリーンな **Markdown** 用アダプタをすぐ使える状態で同梱します。

![概念イラスト: 重いベースラインと軽量ハーネス——トークンは少なく、精度はそのまま](docs/ane-concept-dashboard.jpg)

*概念イラスト——図中の規模や表の数値はイメージです。実測値: 中央値 782 対 3,213 トークン（60.47% 削減）、recall 1.0、詳しくは上記のベンチマーク表をご覧ください。*


---

## 仕組み

![あなたの言葉が AI が読むものになる仕組み: 実際のベンチマーク課題を最初から最後まで追跡——平易な言葉が入り、全チャンクに点数が付き、各カードが選ばれた理由、1,236 中の 369 トークン](docs/context-packing-overview.png)

実パイプラインから生成した 1 ページの解説図（`scripts/plot_packing_overview.py`）: 実際のベンチマーク課題を最初から最後まで追跡します。あなたの言葉が入り、短い語は落ち、リポジトリの全チャンクに点数がつき、勝者が理由を付けて飛び、AI は全体 1,236 ではなく 369 トークンだけを読みます（70% 減、答えに必要なものは何も欠けていません）。図中の数字はすべて実測値で、絵ではありません。

![概念イラスト: 素朴な切り詰めは AST・import・参照を壊す——ハーネスはコード署名・AST 構造・必須依存を保持する](docs/ane-concept-generic.jpg)

*上記アイデアの概念イラスト——図中のコードはグラフィックであり、実際のトレースではありません。実測のトレースは直上のグラフです。*


---

## クイックスタート（60 秒）

### 1. インストール

macOS または Linux 上の Python 3.13 または 3.14 が必要です:

```bash
git clone https://github.com/ericlam2k/ane-context-harness.git
cd ane-context-harness
pip install -e .[test]
```

インストールの確認:
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

`prove` はラベルなしです: 中央値の削減と p50 レイテンシ、および
`recall: not_applicable` を報告します。リコールの証明には人手ラベル付きタスク（凍結した
`benchmarks/splits.json` 機構）が必要です。ラベルなし実行はリコールを主張しません。

### 2. コードベースをインデックス

任意のローカルフォルダまたはリポジトリを、ローカル SQLite ストアへインデックスします（増分で非常に高速）:

```bash
ane-harness index --repo /path/to/your/project --repo-id my-project
```

### 3. プロンプト向けに関連コンテキストを選定

コーディングタスクに合わせた、コンパクトでトークン予算つきの Markdown パッケージを取得します:

```bash
ane-harness select \
  --repo-id my-project \
  --task "Fix the discount calculation bug in checkout" \
  --budget 1200
```

  ### 3b. 多数のプロンプトにわたる before/after のコンテキスト削減を記録（`update`）

タスク一式（JSONL ファイルまたは stdin）に対して選定を実行し、before/after のトークン予算を表示・記録します。
ローカル、ネットワークなし:

```bash
# from a JSONL file (one {"task": "..."} or bare task per line)
ane-harness update \
  --repo-id my-project \
  --budget 2000 \
  --tasks-file prompts.jsonl \
  --log benchmarks/logs/update_session.jsonl
```

出力例:

```
repo_id: my-project | tasks: 3 | budget: 2000

  task                              before  after   removed  reduction
  Fix the discount calculation      3189    1952    1237     38.79%
  debug the inventory loader        3189    1758    1431     44.87%
  review reporting stats output     3189    1261    1928     60.46%

  TOTAL: before 9567 → after 4971 tokens (4596 removed, median reduction 44.87%)
```

タスクごとの行は `--log` にも JSONL として追記されます（gitignore 済み）。
**正直な但し書き** が毎回 stderr に出ます: *"local measurements over the
given repo; redaction does not guarantee all secrets are caught."*

毎回、1 行のカットフッタも stderr に出ます（同じ
行が stdout JSON の `summary` キーにも入ります）。例:
`ane-harness: sent 7.1k instead of 211.2k · cut 96.6% in 165 ms`。平易な言葉だけ —
専門用語なし、`#` 見出しマークアップなし。合計はローカルに累積します（カウントのみ、
タスク本文なし） — いつでも
`ane-harness daily` で確認でき、シェル終了のたびに出すなら
`.zshrc` / `.bashrc` に `eval "$(ane-harness shell-init)"` です。

エージェントは同梱スキル経由で同じ挙動を依存なしで得られます:
`skills/ane-harness/SKILL.md` — エージェントの skills ディレクトリへコピーすれば、
各タスク後にカット合計が自動で出ます。追加セットアップは不要です。OpenCode / Claude /
エージェント互換ホストではグローバルにも動き、プロジェクトごとの
インストールは不要です: `~/.config/opencode/skills/`、`~/.claude/skills/`、または
`~/.agents/skills/`（新しいセッションが拾います）。

### 3c. ネイティブ統合のないエージェント向けプロキシモード（`proxy`）

stdin にタスクを流し込み（1 行あたり `{"task": "..."}` または素のタスク）、
stdout に証拠 Markdown を返します — スキル、MCP、HTTP は不要です:

```bash
printf '%s\n' '{"task": "Fix the discount bug"}' 'review inventory loader' \
  | ane-harness proxy --repo /path/to/your/project --repo-id my-project --budget 2000 \
  > context.md
```

Stdout は純粋な Markdown（タスクごとに 1 ドキュメント、`---` 区切り、
`<!-- ane-harness task N/M ... -->` 境界付き）。タスクごとのカット
フッタは stderr へ。repo-id が既にインデックス済みなら `--repo` は省略できます。

### 4. またはローカルのバックグラウンドサーバとして実行

> **エージェント: エージェントターン内でこれを実行しないでください。** `serve`（`mcp` と同様）は
> 終了しません — 起動するツール呼び出しは永久にブロックするので、ターンは
> 完了せず、以降のプロンプトはすべてその後ろに並びます。対話端末で
> `--tasks-file` なしの素の `update` / `proxy` は stdin 待ちせず
> ヒント付きで exit 2 します。エージェントターン内ではワンショット
> コマンド（`index`、`select`、`prove`、`daily`、`health`）だけを使ってください。サーバは実際の端末からデタッチして実行するか
> （`nohup ane-harness serve --port 8765 &`）、そもそも実行しないでください。

ローカル HTTP API を起動します（エージェントやツールへの接続準備完了）:

```bash
ane-harness serve --port 8765
```

利用可能なエンドポイント:
- `GET  /v1/health` — システム状態、コンピュートモード、プロファイル
- `POST /v1/repositories/index` — リポジトリのインデックスまたは更新
- `POST /v1/context/select` — タスク向け最適化コンテキストの取得
- `POST /v1/context/compress-output` — 冗長なテスト/ビルドログをきれいな失敗ダイジェストへ圧縮

---

## Python での利用

独自の AI エージェントワークフロー内で、ハーネスを直接使うこともできます:

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

1. **シンボル認識 AST チャンキング:** 愚直な行分割ではなく、実際のコード構成（クラス、メソッド、TypeScript の型/インターフェース/enum）をパースします。
2. **決定的検索:** シンボルタームガード、サブトークン分割、複数形フォールディングでフィルタした高速な語彙 BM25 検索です。
3. **スコア優先の予算パッキング:** 指定トークン予算（例: 1,200 tokens）内に厳密に収まるよう貪欲にパックし、必須証拠が切り詰められないことを保証します。
4. **シークレット検出とプライバシーフェンス:** 正規の除外パターン（`.env*`、`.aws/**`、`*.pem` など）は読まず、正規表現 + エントロピー分類器が機微トークンを安定プレースホルダへ置き換えます。
5. **ノイズ圧縮:** 冗長なツール出力（テストトレース、端末ログ）を、信号を保ったコンパクトなダイジェストへ折りたたみます。

![概念イラスト: システムプロンプトとペイロードがフィルタを通ってクリーンなペイロードに——ハーネスのフィルタパイプライン](docs/ane-proxy-tracker-concept.jpg)

*上記パイプラインの概念イラスト——図中のダッシュボードはグラフィックであり、実際のツールのスクリーンショットではありません。*


### ハードウェアアクセラレーション: 別のプライベートディストリビューション

名前に `ane` が含まれますが、ハーネスの実行に **専用シリコンは不要であり、主張もしていません**。
出荷エンジンは純粋に決定的な CPU（Python +
SQLite）で、macOS Apple Silicon、macOS Intel、Linux で同一に動作します。
ニューラルハードウェアアクセラレーションは別管理であり、このリポジトリの一部ではありません。

---

## 技術仕様と厳密さ

数値の厳密さを気にする研究者、アーキテクト、技術リード向け:

- **凍結ベンチマークスプリット:** リリース数値はすべて凍結した 18 タスク評価スプリット（`benchmarks/splits.json`、シード `20261002`）で走ります。チューニングは厳密に dev スプリットへ隔離します。
- **決定的トークン推定器:** トークンカウントはピン留め推定器（`TOKEN_ESTIMATOR_VERSION="2"`）を使うので、外部トークナイザのドリフトなしにマシンと Python バージョンをまたいで 100% 再現できます。
- **埋め込みポリシー:** ローカルのコスト/レイテンシトレードオフに基づき、v0.1 では埋め込みを意図的に除外しています。[ADR-002](docs/adr-002-embedding-go-no-go.md) を参照。
- **リリース証拠バンドル:** チェックサム付きリリース証拠は `ane-harness evidence verify ane-context-harness-evidence-v0.1` で暗号的に検証されます。

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
