# IBM Bob セットアップガイド（日本語）

`otel-hook` を IBM Bob に組み込み、エージェントの活動を OpenTelemetry の
トレース／ログとして任意の OTLP バックエンドへ送るための手順書です。

英語版は [README の IBM Bob セクション](README.md#ibm-bob) にあります。

- **個人で試す場合** → [1〜4章](#1-前提条件)
- **バックエンドを立てず PC のフォルダだけで試す場合** → [4-B](#4-b-ローカルのフォルダだけに出力するバックエンド不要)
- **組織全体に強制展開する場合** → [6章 EnforcedHooks](#6-組織全体への強制展開enforcedhooks)

> **先に知っておくべき Bob の性質**
> Bob は失敗した hook を**ログに記録するだけで無視**します。設定を誤っても
> エラーは表に出ず、テレメトリが静かに欠落します。導入後は必ず
> [5章の動作確認](#5-動作確認)を行ってください。

---

## 1. 前提条件

| 項目 | 要件 |
|---|---|
| Python | 3.12 以上 |
| IBM Bob | lifecycle hooks 対応版 |
| 送信先 | OTLP 対応バックエンド（OpenTelemetry Collector、Jaeger、Grafana Tempo など） |

```bash
python3 --version   # 3.12 以上であること
```

---

## 2. インストール

`pipx` を推奨します。独立した venv に入れつつ `otel-hook` を PATH に通せます。

```bash
# 推奨
pipx install opentelemetry-hooks

# または pip
pip install opentelemetry-hooks
```

このフォーク（Bob 対応版）から直接入れる場合:

```bash
pipx install git+https://github.com/r-nakayamasan/opentelemetry-hooks-bob.git@feat/bob-adapter
```

> 組織展開では、ビルド済み wheel を配布するほうが確実です
> （`python -m build` で生成できます）。

インストール先を確認します。**このパスは6章の強制展開で必要になります。**

```bash
command -v otel-hook
# 例: /Users/you/.local/bin/otel-hook
```

---

## 3. Bob への hook 登録

```bash
# 全プロジェクトに適用（~/.bob/settings/settings.json）
otel-hook setup --agent bob

# 特定プロジェクトのみ（.bob/settings.json）
otel-hook setup --agent bob --no-global
```

> グローバル設定のパスは `~/.bob/settings/settings.json` です。
> `settings` ディレクトリが1階層多い点に注意してください。

生成される設定は次の形です。Bob がサポートする5つの lifecycle hook が登録され、
`matcher` は Bob が受け付ける2つのツールコールバックにのみ付与されます。

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "/path/to/otel-hook --bob", "timeout": 30 }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "/path/to/otel-hook --bob", "timeout": 30 }] }
    ],
    "PreToolUse": [
      { "matcher": ".*",
        "hooks": [{ "type": "command", "command": "/path/to/otel-hook --bob", "timeout": 30 }] }
    ],
    "PostToolUse": [
      { "matcher": ".*",
        "hooks": [{ "type": "command", "command": "/path/to/otel-hook --bob", "timeout": 30 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "/path/to/otel-hook --bob", "timeout": 30 }] }
    ]
  }
}
```

コマンド末尾の `--bob` は必須です。これによりフックが Bob として動作し、
Bob 固有のフィールド変換と stdout 抑制（[7章](#7-bob-固有の挙動)）が有効になります。

`timeout` が Bob の既定 10 秒ではなく **30 秒**になっているのは意図的です。
Python のコールドスタートと OTLP フラッシュが 10 秒を超えることがあり、
Bob はタイムアウトを黙って無視するため、短すぎる値はテレメトリの欠落になります。

既存の hook がある設定ファイルに対しても安全にマージされ、他の hook は保持されます。

---

## 4. 送信先の設定

送信先は2通りから選べます。

| | 用途 | 送信先 | バックエンド |
|---|---|---|---|
| **4-A** | 本番・チーム共有 | OTLP コレクター | 必要 |
| **4-B** | ひとりでローカル検証 | **PC 上のフォルダ（JSONL ファイル）** | **不要** |

まずローカルだけで動作を確かめたい場合は [4-B](#4-b-ローカルのフォルダだけに出力するバックエンド不要) に進んでください。

### 4-A. OTLP コレクターに送る

hook 自身の設定ファイルを編集します。pip / pipx インストールの場合:

```
~/.local/share/opentelemetry-hooks/otel_config.json
```

ソースチェックアウトの場合は `otel_hook.py` と同じ場所の `otel_config.json` です。

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector.example.com:4317",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_SERVICE_NAME": "bob-agent",
  "IDE_OTEL_BATCH_ON_STOP": "true",
  "IDE_OTEL_STATE_TTL_SECONDS": "3600"
}
```

> **`http/protobuf` / `http/json` を使う場合はパスまで書いてください。**
> このフックはエンドポイントを**そのまま**エクスポーターに渡すため、
> OTel SDK による `/v1/traces` の自動補完が働きません。実測で確認しました。
>
> | 設定値 | 実際の POST 先 |
> |---|---|
> | `http://collector:4318` | `/` → 実コレクターでは **404** |
> | `http://collector:4318/v1/traces` | `/v1/traces` → 正常 |
>
> 既定の `grpc` ではこの問題は起きません。HTTP を使う場合、パスを忘れると
> Bob は hook の失敗を黙って無視するので**全損に気づけません**。

#### 主な設定項目

| 変数 | 説明 | 既定値 |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP コレクターのエンドポイント | `http://localhost:4317` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` / `http/protobuf` / `http/json` | `grpc` |
| `OTEL_EXPORTER_OTLP_HEADERS` | 認証ヘッダー（URL エンコードした `key=value`） | — |
| `OTEL_EXPORTER_OTLP_INSECURE` | **gRPC のみ**。TLS を使う場合は `false` | `true` |
| `OTEL_SERVICE_NAME` | トレース上のサービス名 | `ide-agent` |
| `IDE_OTEL_BATCH_ON_STOP` | セッション単位のバッチ送信（推奨） | `false` |
| `IDE_OTEL_STATE_TTL_SECONDS` | 状態ファイルの TTL。**Bob では短縮推奨**（[7章](#sessionend-が存在しない)） | `86400` |

#### プライバシー関連（既定はすべて無効＝本文を送らない）

既定ではプロンプトやツール入出力の**本文は送信されず**、文字数と SHA-256
ハッシュのみが記録されます。本文が必要な場合のみ明示的に有効化してください。

| 変数 | 説明 | 既定値 |
|---|---|---|
| `IDE_OTEL_CAPTURE_CONVERSATION_CONTENT` | プロンプト・応答・エラー本文を span に含める | `false` |
| `IDE_OTEL_CAPTURE_TOOL_INPUT_CONTENT` | ツール入力の本文をログに含める | `false` |
| `IDE_OTEL_CAPTURE_USER_IDENTITY` | `user.id` / `user.email` を含める | `false` |
| `IDE_OTEL_MASK_PROMPTS` | メールアドレス・トークン・ユーザー名をマスク | `false` |
| `IDE_OTEL_TEXT_MAX_CHARS` | 取得する本文の最大文字数 | `4000` |

設定後は Bob を再起動してください。

> **なぜ環境変数ではなく設定ファイルなのか**
> `otel-hook` は起動ごとに自身の `otel_config.json` を読み、次に MDM/レジストリ
> ポリシーを重ね、最後に未設定の変数だけを実行時環境から補完します。明示的な
> 環境変数は優先されますが、親プロセスからの `OTEL_*` 継承に依存しません。


### 4-B. ローカルのフォルダだけに出力する（バックエンド不要）

コレクターを立てずに、**PC 上のフォルダへ JSONL ファイルとして書き出す**構成です。
1人での動作確認、hook が本当に呼ばれているかの調査、属性の中身を目で見たいときに使います。

必要な設定は2つだけです。

| 設定 | 値 | 意味 |
|---|---|---|
| `IDE_OTEL_LOCAL_SPANS` | `"true"` | span をローカル JSONL に保存する |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | **設定しない** | リモート送信を行わない |

出力先は `<hook ホーム>/.state/local_spans/<session_id>.jsonl` です。
`<hook ホーム>` は既定で `~/.local/share/opentelemetry-hooks`、
`IDE_OTEL_HOOK_HOME` で変更できます。

#### 方法B-1: 既定の場所に出す（手軽・推奨）

`~/.local/share/opentelemetry-hooks/otel_config.json` を次の内容にします。
`OTEL_EXPORTER_OTLP_ENDPOINT` の行は**書きません**。

```json
{
  "IDE_OTEL_LOCAL_SPANS": "true",
  "IDE_OTEL_BATCH_ON_STOP": "true",
  "IDE_OTEL_STATE_TTL_SECONDS": "3600"
}
```

hook の登録は通常どおりで構いません。

```bash
otel-hook setup --agent bob
```

出力先:

```bash
ls ~/.local/share/opentelemetry-hooks/.state/local_spans/
# local1.jsonl  ...  セッションごとに1ファイル
```

#### 方法B-2: 出力先フォルダを自分で指定する

「このフォルダに出したい」という場合は `IDE_OTEL_HOOK_HOME` を指定します。
Bob の hook 設定に `env` ブロックはないため、**`command` を `env` でラップ**します。

```bash
# 例: ~/bob-telemetry に出す
mkdir -p ~/bob-telemetry
otel-hook setup --agent bob --no-global
```

生成された `.bob/settings.json` の `command` を、5イベントすべて次の形に書き換えます。

```json
{
  "type": "command",
  "command": "env IDE_OTEL_HOOK_HOME=/Users/you/bob-telemetry IDE_OTEL_LOCAL_SPANS=true otel-hook --bob",
  "timeout": 30
}
```

`command` はシェルで実行されるため `env VAR=値 コマンド` がそのまま使えます。
実機の Bob では `~` も展開されます（既存の Bob hook が
`sh ~/.bob/hooks/...` の形で動作していることを確認しました）。ただし配布物では
解釈の揺れを避けるため**絶対パス**を推奨します。

sed でまとめて置換する例:

```bash
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path(".bob/settings.json")
d = json.loads(p.read_text())
new = "env IDE_OTEL_HOOK_HOME=/Users/you/bob-telemetry IDE_OTEL_LOCAL_SPANS=true otel-hook --bob"
for entries in d["hooks"].values():
    for e in entries:
        for h in e["hooks"]:
            if "otel-hook" in h["command"] or "otel_hook" in h["command"]:
                h["command"] = new
p.write_text(json.dumps(d, indent=2) + "\n")
print("書き換えました")
EOF
```

> **注意: 指定したフォルダは「span の置き場」ではなく hook の作業ホーム全体になります。**
> `otel_config.json`・`.state/`・ログのほか、OpenTelemetry SDK 用の **`.venv/` が
> 自動生成され数百ファイルが作られます**。Git 管理下に置くなら `.gitignore` に
> 追加するか、リポジトリ外のフォルダを指定してください。
> 「span だけ見たい」なら方法B-1 のほうが副作用がありません。

#### 出力の確認

`Stop` まで到達した時点でフラッシュされます（[5-2章](#5-2-hook-を手動で叩いてみる)と同じ理由）。

```bash
OUT=~/.local/share/opentelemetry-hooks/.state/local_spans   # 方法B-2 なら指定したフォルダ配下
ls -la $OUT

# イベントとツール名の一覧（jq がある場合）
jq -r '[.attributes["gen_ai.client.hook.event"] // .name, .attributes["gen_ai.client.tool_name"] // "-"] | @tsv' \
  $OUT/*.jsonl

# jq が無い場合
python3 -c "
import json,glob,sys
for p in sorted(glob.glob(sys.argv[1])):
    for l in open(p):
        s=json.loads(l); a=s['attributes']
        print(a.get('gen_ai.client.hook.event') or s['name'], '|', a.get('gen_ai.client.tool_name','-'))
" "$OUT/*.jsonl"
```

出力例（1ターン分）:

```
UserPromptSubmit          -
PreToolUse                write_file
PostToolUse               write_file
Stop                      -
gen_ai.client.generation  -
```

最後の `gen_ai.client.generation` は1ターン全体をまとめた親 span です。
hook イベントではないので `hook.event` 属性を持たず、上のコマンドでは
span 名で表示されます。これが出ていれば正常です。

`SessionStart` の行が無いのも正常です（[7章](#sessionend-が存在しない)）。

1行が1 span の JSON です。主なキー:

| キー | 内容 |
|---|---|
| `name` | `gen_ai.client.hook.PreToolUse` など span 名 |
| `trace_id` / `span_id` / `parent_span_id` | トレース構造 |
| `start_time_ns` / `end_time_ns` | 開始・終了時刻 |
| `attributes` | 属性一覧（下記） |
| `resource` | サービス名などのリソース属性 |

`attributes` の主なもの:

```
gen_ai.client.name             = "bob"
gen_ai.client.hook.event       = "PreToolUse"
gen_ai.client.tool_name        = "write_file"     ← Bob の tool から変換された値
gen_ai.client.session_id       = "local1"
gen_ai.operation.name          = "execute_tool"
gen_ai.client.tool.input.length = 16              ← 本文ではなく長さとハッシュ
gen_ai.client.tool.input.sha256 = "dcd6d08c..."
```

#### ローカル検証時のログ

送信しないので、動きを追うには hook のログを使います。

```bash
# ログレベルを上げ、各イベントを記録する
# (otel_config.json に入れるか、上記の env ラップに足す)
IDE_OTEL_LOG_LEVEL=DEBUG
IDE_OTEL_LOG_EVENTS=true

tail -f ~/.local/share/opentelemetry-hooks/otel_hook.log
```

`IDE_OTEL_DEBUG_CONSOLE=true` で span を端末に流すこともできます。

```bash
IDE_OTEL_DEBUG_CONSOLE=true
```

> **Bob では出力先が stdout ではなく stderr になります。**
> OpenTelemetry の `ConsoleSpanExporter` は既定で **stdout** に書きますが、
> Bob は `SessionStart` / `UserPromptSubmit` の stdout をモデルのコンテキストに
> 注入するため、そのままではプロンプトに span JSON が貼り込まれてしまいます。
> そこで Bob の場合は自動的に stderr へ切り替わります（切り替わった旨が
> ログに warning として記録されます）。他のエージェントでは従来どおり stdout です。
>
> したがって Bob でデバッグ出力を見るときは stderr を見てください。

```bash
# span を端末で見る（stderr に出る）
echo '{"event":"Stop","session_id":"dbg1"}' | \
  env IDE_OTEL_DEBUG_CONSOLE=true otel-hook --bob 2>&1 >/dev/null
```

腰を据えて調べる場合は `IDE_OTEL_LOCAL_SPANS`（ファイル出力）のほうが
後から検索・比較できるので便利です。

#### 後片付け

```bash
rm -rf ~/.local/share/opentelemetry-hooks/.state/local_spans/*.jsonl
```

ローカル検証を終えて本番のコレクターに切り替えるときは、`IDE_OTEL_LOCAL_SPANS` を
外し（または `"false"`）、[4-A](#4-a-otlp-コレクターに送る) の
`OTEL_EXPORTER_OTLP_ENDPOINT` を設定してください。方法B-2 で `command` を
書き換えていた場合は `otel-hook setup --agent bob` で元の形に戻せます。

---

## 5. 動作確認

### 5-1. 登録状況の確認

```bash
otel-hook diagnose --agent bob
#   ✓ [bob] 5 events registered (/Users/you/.bob/settings/settings.json)

otel-hook doctor --agent bob
# 登録状況・プライバシー設定・エクスポーターの健全性・未送信状態を表示
```

`doctor` について2点注意があります。

- **劣化状態では終了コード 1 を返します**（`status: degraded`）。エンドポイント
  未設定の状態では `exporter: disabled (no endpoint)` として degraded になるため、
  CI やスクリプトで終了コードを見る場合は考慮してください。JSON で状態を取るには
  `otel-hook doctor --agent bob --json` を使います。
- 出力の `detected agent:` は、**いま `doctor` を実行している環境**で検出された
  エージェント名です。`--agent bob` で指定した対象とは別物なので、ここが `bob` に
  ならなくても問題ありません。Bob の登録状況は `[bob] 5 events` の行を見てください。

### 5-2. hook を手動で叩いてみる

Bob を起動せずに、実際のペイロードを流して span が出るか確認できます。

> **1ターン分を最後の `Stop` まで流してください。** span はバッチ化されて
> `Stop`（世代の終わり）でフラッシュされるため、途中のイベントだけを単発で
> 流してもファイルは作られません。「動いていない」と誤解しやすい点です。

```bash
export IDE_OTEL_LOCAL_SPANS=true

for p in '{"event":"SessionStart","session_id":"ses_test"}' \
         '{"event":"UserPromptSubmit","session_id":"ses_test","prompt":"テスト"}' \
         '{"event":"PreToolUse","session_id":"ses_test","tool":"write_file","input":{"path":"a.ts"}}' \
         '{"event":"PostToolUse","session_id":"ses_test","tool":"write_file","input":{"path":"a.ts"},"output":"done"}' \
         '{"event":"Stop","session_id":"ses_test"}'; do
  echo "$p" | otel-hook --bob
done

# 出力された span を確認
cat ~/.local/share/opentelemetry-hooks/.state/local_spans/ses_test.jsonl | python3 -m json.tool
```

次のような span が出れば正常です。`gen_ai.client.name` が `bob`、
`PreToolUse` / `PostToolUse` の `gen_ai.client.tool_name` が `write_file`
（Bob の `tool` フィールドから変換されたもの）になっていることを確認します。

```
gen_ai.client.hook.UserPromptSubmit   client = bob
gen_ai.client.hook.PreToolUse         client = bob   tool_name = write_file
gen_ai.client.hook.PostToolUse        client = bob   tool_name = write_file
gen_ai.client.hook.Stop               client = bob
gen_ai.client.generation              client = bob
```

`SessionStart` 単体の span がここに無いのは正常です。セッションの root span は
`SessionEnd` 相当のタイミングで出力されますが、Bob には `SessionEnd` が無いため
TTL 経過後になります（[7章](#sessionend-が存在しない)）。

### 5-3. stdout が空であることの確認 ★重要

Bob は `SessionStart` と `UserPromptSubmit` の hook stdout を**モデルの
コンテキストに注入**します。ここで何か出力されていると、毎ターン余計な
文字列がプロンプトに混入します。**必ず空であること**を確認してください。

```bash
for ev in SessionStart UserPromptSubmit PreToolUse PostToolUse Stop; do
  out=$(echo "{\"event\":\"$ev\",\"session_id\":\"ses_test\"}" | otel-hook --bob)
  [ -z "$out" ] && echo "OK   $ev (空)" || echo "NG   $ev -> $out"
done
```

全行が `OK` になるのが正常です。

送信先が未起動だと `Failed to export traces ...` のような**警告が stderr に**
出ることがありますが、これは stdout ではないため上のチェックには影響しません。
むしろ「エラーが出ても stdout は汚れない」ことの確認になります。

### 5-4. 送信先まで届いているかを確認する

エンドポイントを設定したら、実際に**ネットワークに出ているか**を確かめます。
コレクターが無くても、手元に受け口を立てれば確認できます。

```bash
# 受け口を 8 秒だけ立てる
python3 - <<'EOF' &
import http.server, threading, time
got=[]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n=int(self.headers.get('Content-Length',0)); self.rfile.read(n)
        got.append((self.path, n)); self.send_response(200)
        self.send_header('Content-Length','0'); self.end_headers()
    def log_message(self,*a): pass
srv=http.server.HTTPServer(('127.0.0.1',4318),H)
threading.Thread(target=srv.serve_forever,daemon=True).start()
time.sleep(8); srv.shutdown()
print("受信:", got)
EOF
sleep 1

# その受け口に向けて 1 イベント送る
echo '{"hook_event_name":"Stop","session_id":"wire-test","last_assistant_message":"x"}'   | env OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318/v1/traces         OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf         IDE_OTEL_DISABLE_BATCH=true         otel-hook --bob
wait
```

`受信: [('/v1/traces', 1128)]` のように protobuf のボディが届けば送信経路は正常です。

### 5-5. 実際の Bob セッションで確認

Bob で1ターン動かし、バックエンドに `gen_ai.client.name=bob` の span が
届いていることを確認します。届かない場合は[8章](#8-トラブルシューティング)へ。

---

## 6. 組織全体への強制展開（EnforcedHooks）

Bob のグループポリシー `EnforcedHooks` は、**ユーザーが上書きできない** hook を
管理者が定義する仕組みです。ポリシーで強制された hook はユーザー定義の hook より
先に実行されます。組織全体でテレメトリ取得を保証したい場合はこれを使います。

> **この章の検証状況**
> 生成されるポリシー値の内容（スキーマ・イベント・`matcher`・`timeout`）は
> Bob の実設定ファイルと突き合わせて確認済みです。一方**ポリシー欄に実際に
> 投入して適用させる操作は未検証**で、Bob の公開仕様に基づいています。
> 本番展開の前に、必ず[6-6 のパイロット展開](#6-6-段階的に展開する)を行ってください。

### 6-1. 前提: otel-hook を管理対象端末に配布する

先に `otel-hook` を全端末の**既知の絶対パス**に配置してください（例
`/opt/otel-hook/bin/otel-hook`）。MDM、構成管理ツール、社内パッケージ配布などで行います。

### 6-2. ポリシー値を生成する

```bash
# ポリシー欄にそのまま貼り付ける1行（--hook-cmd は配布先の絶対パス）
otel-hook policy --bob --hook-cmd /opt/otel-hook/bin/otel-hook --raw
```

出力例（1行）:

```json
{"PostToolUse":[{"hooks":[{"command":"/opt/otel-hook/bin/otel-hook --bob","timeout":30,"type":"command"}],"matcher":".*"}],"PreToolUse":[...],"SessionStart":[...],"Stop":[...],"UserPromptSubmit":[...]}
```

用途別のオプション:

| コマンド | 用途 |
|---|---|
| `--raw` | ポリシー欄に貼り付ける1行 JSON |
| （オプションなし） | 整形表示。レビュー・差分確認用 |
| `--escaped` | 別の JSON / plist に入れ子で埋め込む文字列エスケープ済みの値 |
| `--timeout N` | hook のタイムアウト秒数を変更（`0` で無効化。既定 30） |
| `--portable` | PATH 依存の `otel-hook --bob` を出力（**非推奨**、下記参照） |

### 6-3. ポリシーに設定する

生成した1行を Bob のグループポリシー `EnforcedHooks` の値に設定します。

> **キー名は PascalCase の `EnforcedHooks` です。** Bob のグループポリシーは
> `DisabledAutoApprovalGroups` / `UpdateMode` / `GatewayUrl` / `EnforcedHooks` と
> すべて PascalCase です。`enforcedHooks` のように綴ると値が読まれず、
> エラーも出ないまま hook が配布されません。
`EnforcedHooks` は JSON 文字列を受け取ります。値が空、または JSON として
不正な場合、ポリシーは**無視され**、hook 設定はユーザー任せに戻ります。

設定例は [`examples/bob-enforced-hooks.example.json`](examples/bob-enforced-hooks.example.json) を参照してください。

> **ポリシーとユーザー設定の両方に登録すると二重計上になります。**
> ポリシーの hook はユーザー定義の hook を**置き換えるのではなく、加えて**
> 実行されます。したがって、ある端末で利用者が既に
> `otel-hook setup --agent bob` を実行していると、1つのイベントに対して
> hook が2回走り、**span が2つ記録されます**（実測で確認：同一イベントを2回
> 配信すると `PreToolUse` / `PostToolUse` / `Stop` はいずれも2個生成されました。
> このフックの重複排除はツールコールバックには効きません）。
>
> ポリシーで展開する場合は、利用者側の登録を外してください。
>
> ```bash
> # 各端末で利用者側の登録状況を確認
> otel-hook diagnose --agent bob
>
> # 利用者側の登録を外す（ポリシー側は残る）
> otel-hook uninstall --agent bob
> otel-hook uninstall --agent bob --no-global   # プロジェクト単位も
> ```

### 6-4. `--portable` を避ける理由

`--portable` は `otel-hook --bob` という PATH 依存のコマンドを出力します。
PATH に `otel-hook` が無い端末では強制 hook が毎回失敗しますが、Bob は失敗を
ログに記録するだけなので、**エラーが表に出ないままテレメトリが欠落**します。
`--portable` を使うと警告が stderr に出ます。原則 `--hook-cmd` で絶対パスを
指定してください。

### 6-5. 展開前チェックリスト

Bob は失敗した hook を黙って無視します。つまり**設定ミスは「エラー」ではなく
「データが無い」という形で現れます**。展開前に次を確認してください。

- [ ] `otel-hook` が全端末の**同一の絶対パス**に存在する（`--hook-cmd` と一致）
- [ ] コマンドに **`--bob` が付いている**。実機の Bob のペイロードは Claude Code と
      区別できないため、これが無いと別エージェントとして誤検出されます
      （[7章](#実機のペイロードは仕様書と異なる重要)）
- [ ] エクスポーター設定を**別途**配布した（ポリシーは hook 登録のみ。
      `otel_config.json` か MDM/レジストリ）
- [ ] HTTP プロトコルなら**エンドポイントにパスまで**書いた
      （`http://collector:4318/v1/traces`。[4-A の注意](#4-a-otlp-コレクターに送る)）
- [ ] `timeout` が十分（既定 30 秒）。Bob の既定 10 秒では
      コールドスタート時に打ち切られます（実測で強制されることを確認済み）
- [ ] 利用者側に既存の登録が**無い**（あると二重計上。[6-3](#6-3-ポリシーに設定する)）
- [ ] プライバシー設定を確認した（既定では本文を送らずハッシュのみ。
      [4-A](#4-a-otlp-コレクターに送る) の「プライバシー関連」の表）

### 6-6. 段階的に展開する

失敗が静かに起きる以上、いきなり全体へ展開するのは避けてください。

1. **1台で検証** — ポリシーを自分の端末だけに適用し、Bob を1ターン動かして
   [5章](#5-動作確認)の確認をすべて通す。特に
   「プロンプトに JSON が混入していないこと」を目視する
2. **パイロット（数名）** — バックエンドに span が届き、`gen_ai.client.name=bob`
   で一貫していることを確認する
3. **全体展開** — 展開後、代表端末で登録状況を確認する

```bash
otel-hook diagnose --agent bob     # 登録されているか
otel-hook doctor --agent bob       # 送信の健全性と未送信の滞留
```

### 6-7. 無効化・ロールバック

`EnforcedHooks` の値を**空にする**か、JSON として不正な値にすると、
ポリシーは無視され hook 設定はユーザー任せに戻ります。ロールバックは
ポリシー欄を空にするのが最も確実です。

ポリシーを外しても各端末の `otel_config.json` は残るので、完全に撤去する場合は
そちらの配布も併せて取り消してください。

---

## 7. Bob 固有の挙動

他エージェントと異なる点で、運用上知っておくべき4点です。

### stdout には何も出力しない

Bob は `SessionStart` と `UserPromptSubmit` の hook stdout をモデルの
コンテキストに注入し、それ以外では無視します。これは仕様書の記述だけでなく、
実機で確認済みです（Bob 用の既存 SessionStart hook が、まさにこの注入を
利用してコンテキストを流し込む作りになっていました）。Bob には stdout の応答仕様が
なく、制御は終了コード 2 で行います。したがって他エージェントで使う
`{"continue": true}` を出力すると、毎ターンその JSON がプロンプトに
貼り込まれてしまいます。そのため Bob アダプターは**全イベントで無出力**、
常に終了コード 0 を返します。

このフックは観測専用で、プロンプトやツール実行を**ブロックしません**。

### `SessionEnd` が存在しない

Bob の `Stop` は「エージェントが停止したとき」＝ターンの終わりに発火するため、
セッションの終わりではなく**世代（generation）の境界**として扱われ、意図的に
`SessionEnd` には対応付けていません。

結果として、セッション終了の瞬間にセッションの root span を閉じるものがありません。
代わりに、セッション状態が `IDE_OTEL_STATE_TTL_SECONDS`（既定 86400 秒＝24時間）
触られなかった時点で、stale セッションのフラッシュ処理が root span を出力します。

Bob 運用では TTL を短くして、セッション span が早く届くようにしてください。

```json
{ "IDE_OTEL_STATE_TTL_SECONDS": "3600" }
```

### 失敗が静かに起きる

Bob は終了コード 2 以外の非ゼロ終了（タイムアウトを含む）を、ログに記録するだけの
非ブロッキングな失敗として扱います。hook コマンドが壊れていても**目に見える
エラーにはならず**、テレメトリが欠落するだけです。だからこそ
`otel-hook diagnose --agent bob` での確認が重要です。

実機（Bob 2.0.2）で確認した挙動:

| 試したこと | 結果 |
|---|---|
| `UserPromptSubmit` で `exit 1` | hook は実行され、**ターンは正常に完走**。エラー表示なし |
| `PreToolUse` で `sleep 8`（`timeout: 2`） | **打ち切られた**（8秒後のマーカーが残らなかった）。ターンは完走 |
| 上記2つが壊れている状態での他イベント | `PostToolUse` / `Stop` の span は**正常に出た** |

**`timeout` は実際に強制されます。** これが `setup` で `timeout: 30` を明示している
理由です。Bob の既定 10 秒では、Python のコールドスタートと OTLP フラッシュが
重なったときに打ち切られ、その回のテレメトリが静かに失われます。

1つのイベントの hook が壊れても他のイベントは独立して動くため、部分的な欠落は
気づきにくい形で起きます。

> なお `timeout: 2` を試した回はターン全体の所要時間が通常（15〜20秒）より
> 長く 43 秒かかりました。打ち切り自体は確認できていますが、この延びの
> 内訳は特定できていません。短い `timeout` を設定する場合はご注意ください。

### 実機のペイロードは仕様書と異なる（重要）

`bob run` で実測したところ、Bob 2.0.2 が hook に渡す JSON は**公式仕様書の
記載と異なり、Claude Code と同じ形**でした。

| 項目 | 仕様書の記載 | 実機 Bob 2.0.2 |
|---|---|---|
| イベント名のキー | `event` | **`hook_event_name`** |
| ツール名 | `tool` | **`tool_name`** |
| ツール入力 | `input` | **`tool_input`** |
| ツール出力 | `output` | **`tool_response`** |
| その他 | — | `cwd`, `source`, `tool_use_id`, `last_assistant_message` |

実測した `PreToolUse` の生ペイロード:

```json
{
  "session_id": "da7d1ea73a84368fbcf3cbdd6cc09e19",
  "cwd": "/Users/you/project",
  "hook_event_name": "PreToolUse",
  "tool_name": "write_file",
  "tool_input": {"path": "hello.txt", "content": "hi\n", "line_count": 1},
  "tool_use_id": "tooluse_I7h1pvcOcHopCD9AAV3nv5"
}
```

**利用者側の対応は不要です。** アダプターは両方の形を受け付けます
（仕様書どおりの `tool` / `input` / `output` が来た場合も変換します）。
`cwd` が入っているためワークスペースとリポジトリの属性も自動で付きます。

ただし**`--bob` フラグは必須**です。実機のペイロードは Claude Code と
見分けがつかないため、フラグが無いと別エージェントとして誤検出されます。
`otel-hook setup --agent bob` と `otel-hook policy --bob` は必ず付けて生成します。

### 取得できるイベント

Bob がサポートするのは5つの lifecycle hook のみです。

| 正規イベント名 | Bob | 備考 |
|---|---|---|
| `SessionStart` | `SessionStart` | |
| `UserPromptSubmit` | `UserPromptSubmit` | |
| `PreToolUse` | `PreToolUse` | `matcher` 対応 |
| `PostToolUse` | `PostToolUse` | `matcher` 対応 |
| `Stop` | `Stop` | ターン終端（世代の境界） |
| `SessionEnd` | — | 存在しない（上記参照） |
| subagent / compaction / エラー専用イベント | — | 存在しない |

シェル実行・ファイル操作・MCP 呼び出しはすべて `PreToolUse` / `PostToolUse` を
通り、`tool_name` で判別できます。専用イベントはありません。

実機の Bob（v2.0.2）で観測されたツール名の例:

```
write_file  apply_diff  search_and_replace  insert_content  read_file
execute_command  spawn_subagent  use_skill  update_todo_list
ask_followup_question  create_chart  create_html_artifact
search_bob_docs  start_workflow  switch_mode
```

いずれも snake_case なので `matcher: ".*"` で全て拾えます。特定のツールだけを
観測したい場合は `matcher` を絞ってください（例: `"^(write_file|apply_diff)$"`）。

**サブエージェントは `spawn_subagent` というツールとして現れます。** Bob には
サブエージェント専用の lifecycle イベントがないため、委譲の観測は
`PreToolUse` / `PostToolUse` の `tool_name=spawn_subagent` で行います。

なお Bob は `tool` / `input` / `output` というフィールド名を使いますが、
アダプターが他エージェントと共通の `tool_name` / `tool_input` / `tool_output` に
変換するため、ダッシュボード側では他エージェントと同じ属性名で扱えます。

---

## 8. トラブルシューティング

### span がバックエンドに届かない

```bash
# 1. 登録されているか
otel-hook diagnose --agent bob

# 2. エクスポーターの健全性と未送信状態
otel-hook doctor --agent bob

# 3. hook 自身のログ
tail -f ~/.local/share/opentelemetry-hooks/otel_hook.log

# 4. 詳細ログを有効にして手動実行
IDE_OTEL_LOG_LEVEL=DEBUG IDE_OTEL_LOG_EVENTS=true \
  sh -c 'echo "{\"event\":\"Stop\",\"session_id\":\"t1\"}" | otel-hook --bob'
```

### プロンプトに JSON が混入する

`--bob` フラグが付いていない可能性があります。設定内のコマンドを確認してください。

```bash
grep -o 'otel-hook[^"]*' ~/.bob/settings/settings.json
# すべて "--bob" で終わっていること
```

付いていなければ再登録します。

```bash
otel-hook setup --agent bob
```

### セッションの span が出てこない

`SessionEnd` が無いため TTL 経過まで出力されません（[7章](#sessionend-が存在しない)）。
`IDE_OTEL_STATE_TTL_SECONDS` を短くしてください。

### hook が実行されているか分からない

Bob は失敗を黙って無視するため、まずローカル span で切り分けます。

```bash
export IDE_OTEL_LOCAL_SPANS=true
# Bob で1ターン操作したあと
ls -la ~/.local/share/opentelemetry-hooks/.state/local_spans/
```

ファイルができていれば hook は動いています。届かないのは送信側の問題です。

### タイムアウトしている疑いがある

`timeout` を延ばすか無効化して切り分けます。

```bash
otel-hook policy --bob --hook-cmd /opt/otel-hook/bin/otel-hook --timeout 60 --raw
```

---

## 9. アンインストール

```bash
# グローバル設定から削除
otel-hook uninstall --agent bob

# プロジェクト設定から削除
otel-hook uninstall --agent bob --no-global
```

`otel-hook` の登録のみが削除され、他の hook は保持されます。
強制展開している場合は、グループポリシーの `EnforcedHooks` も併せて解除してください。

---

## 参考

- [README の IBM Bob セクション（英語・詳細）](README.md#ibm-bob)
- [`examples/bob-hooks.example.json`](examples/bob-hooks.example.json) — settings.json の例
- [`examples/bob-enforced-hooks.example.json`](examples/bob-enforced-hooks.example.json) — EnforcedHooks ポリシーの例
- [設定リファレンス（全変数）](README.md#configuration-reference)
- [FORK.md](FORK.md) — 上流リポジトリとの関係・同期手順
