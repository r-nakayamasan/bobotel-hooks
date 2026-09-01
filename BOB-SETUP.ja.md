# IBM Bob セットアップガイド（日本語）

`otel-hook` を IBM Bob に組み込み、エージェントの活動を OpenTelemetry の
トレース／ログとして任意の OTLP バックエンドへ送るための手順書です。

英語版は [README の IBM Bob セクション](README.md#ibm-bob) にあります。

- **個人で試す場合** → [1〜4章](#1-前提条件)
- **組織全体に強制展開する場合** → [6章 enforcedHooks](#6-組織全体への強制展開enforcedhooks)

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
pipx install git+https://github.ibm.com/Ryo-Nakayama/opentelemetry-hooks-bob.git@feat/bob-adapter
```

> 社内 Enterprise のリポジトリなので、事前に github.ibm.com への git 認証
> （credential helper か SSH）が必要です。組織展開ではビルド済み wheel を
> 配布するほうが確実です。

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

## 4. 送信先（OTLP エクスポーター）の設定

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

### 主な設定項目

| 変数 | 説明 | 既定値 |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP コレクターのエンドポイント | `http://localhost:4317` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` / `http/protobuf` / `http/json` | `grpc` |
| `OTEL_EXPORTER_OTLP_HEADERS` | 認証ヘッダー（URL エンコードした `key=value`） | — |
| `OTEL_EXPORTER_OTLP_INSECURE` | **gRPC のみ**。TLS を使う場合は `false` | `true` |
| `OTEL_SERVICE_NAME` | トレース上のサービス名 | `ide-agent` |
| `IDE_OTEL_BATCH_ON_STOP` | セッション単位のバッチ送信（推奨） | `false` |
| `IDE_OTEL_STATE_TTL_SECONDS` | 状態ファイルの TTL。**Bob では短縮推奨**（[7章](#sessionend-が存在しない)） | `86400` |

### プライバシー関連（既定はすべて無効＝本文を送らない）

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

### 5-4. 実際の Bob セッションで確認

Bob で1ターン動かし、バックエンドに `gen_ai.client.name=bob` の span が
届いていることを確認します。届かない場合は[8章](#8-トラブルシューティング)へ。

---

## 6. 組織全体への強制展開（enforcedHooks）

Bob のグループポリシー `enforcedHooks` は、**ユーザーが上書きできない** hook を
管理者が定義する仕組みです。ポリシーで強制された hook はユーザー定義の hook より
先に実行されます。組織全体でテレメトリ取得を保証したい場合はこれを使います。

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

生成した1行を Bob のグループポリシー `enforcedHooks` の値に設定します。
`enforcedHooks` は JSON 文字列を受け取ります。値が空、または JSON として
不正な場合、ポリシーは**無視され**、hook 設定はユーザー任せに戻ります。

設定例は [`examples/bob-enforced-hooks.example.json`](examples/bob-enforced-hooks.example.json) を参照してください。

### 6-4. `--portable` を避ける理由

`--portable` は `otel-hook --bob` という PATH 依存のコマンドを出力します。
PATH に `otel-hook` が無い端末では強制 hook が毎回失敗しますが、Bob は失敗を
ログに記録するだけなので、**エラーが表に出ないままテレメトリが欠落**します。
`--portable` を使うと警告が stderr に出ます。原則 `--hook-cmd` で絶対パスを
指定してください。

### 6-5. 展開後の確認

エクスポーターの設定はポリシーの対象外です。hook の登録（ポリシー）と
エクスポーター設定（`otel_config.json` または本リポジトリの MDM/レジストリ設定）は
別々に配布してください。詳細は README の
[MDM / Managed Configuration](README.md#mdm--managed-configuration) を参照。

展開後、代表的な端末で必ず確認します。

```bash
otel-hook diagnose --agent bob
```

---

## 7. Bob 固有の挙動

他エージェントと異なる点で、運用上知っておくべき4点です。

### stdout には何も出力しない

Bob は `SessionStart` と `UserPromptSubmit` の hook stdout をモデルの
コンテキストに注入し、それ以外では無視します。Bob には stdout の応答仕様が
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
強制展開している場合は、グループポリシーの `enforcedHooks` も併せて解除してください。

---

## 参考

- [README の IBM Bob セクション（英語・詳細）](README.md#ibm-bob)
- [`examples/bob-hooks.example.json`](examples/bob-hooks.example.json) — settings.json の例
- [`examples/bob-enforced-hooks.example.json`](examples/bob-enforced-hooks.example.json) — enforcedHooks ポリシーの例
- [設定リファレンス（全変数）](README.md#configuration-reference)
- [FORK.md](FORK.md) — 上流リポジトリとの関係・同期手順
