---
paths:
  - "**/herdr/config.toml"
---

# herdr のキー割り当ての決まり

herdr の `config.toml` にキーを足す・変えるときの決まり。以下の「キー」は、すべて prefix（この config では
`ctrl+q`）の後に押すキーを指す。

## 修飾キーは、操作する対象の階層で決める

| 修飾キー | 対象 | 例 |
|---|---|---|
| なし | タブ（herdr の既定の層） | `prefix+c` 新規 / `prefix+n`・`p` 次・前 / `prefix+1..9` 番号で移動 |
| `shift` | workspace | `prefix+shift+c` / `shift+n`・`shift+p` / `shift+1..9` |
| `alt` | エージェントと、エージェントの横に開く道具 | `prefix+alt+n`・`alt+p` / `alt+1..9`、nvim（`alt+e`・`alt+o`）、lazygit（`alt+g`）、用語集（`alt+t`）、explainer（`alt+f`）、zoetrope の分割（`alt+z`） |

- workspace とエージェントの移動は、タブの同じ操作に修飾キーを足した形にする。同じ文字は、どの層でも
  同じ意味にする（`n` は次、`p` は前、`c` は新規、`1..9` は番号）。
  herdr の既定では workspace の新規が `prefix+shift+n` で、shift の層で `n` が「新規」と「次」の 2 つの
  意味を持っていた。そのため `prefix+shift+c` に移した。
- エージェントのセッションを見る道具や、エージェントの出力を使う道具は `alt` に置く。文字は道具の
  名前か動作の頭文字から選び、`alt` の層の既存のキーと重ねない。

## 決まりから外れているキー

外れている理由を残しておく。新しいキーをここに足すのは、決まりに沿う割り当てが無いときだけにする。

- `rename_pane = "prefix+comma"`: rename の頭文字の規則（t=タブ / w=workspace / p=pane）は、
  shift と alt のどちらの層でも空きが無く守れない。shift=workspace、alt=エージェントの区別を崩さない方を
  優先し、tmux の rename（`prefix+,`）に倣って修飾キーなしの層に置いた。
- `prefix+f`（Claude Code のセッションを分岐する）と `prefix+d`（reviewr）: エージェントを扱う道具だが、
  修飾キーなしの層にある。`alt` に移すかはまだ決めていない。
- `prefix+shift+z`（zoetrope を overlay で開く）: プラグインの作者が勧めるキーをそのまま使っている。
  shift=workspace の決まりから外れる。

## 足す前に確かめること

- **herdr の既定のキーと重ねない。** `[[keys.command]]` が既定のキーと重なっても、`herdr config check` は
  何も報告しない。どちらか一方が黙って効かなくなる。既定のキーは herdr の文書で確かめる。手早く当たりを
  付けるなら、実行ファイルに埋め込まれた文字列を見る:
  `strings "$(command -v herdr)" | grep -oE '"prefix\+[a-z+0-9.]+"' | sort -u`
  （この出力は既定のキー以外の文字列も含みうるので、目安として使う）。
- **`type = "plugin_action"` のキーを足したら、そのプラグインを `user/install.sh` の `HERDR_PLUGINS` に
  コミット固定で書く**（docs/adr/0010-herdr-plugins-declared-in-install-sh.md）。書かないと、他の
  マシンにキーだけが配られ、プラグイン本体が入らない。`tests/test_herdr.py` がこの対応を検査する。
- **`popup` / `shell` で外部コマンドを呼ぶなら、絶対パスか `PATH=` を明示する。** herdr サーバの PATH は
  `/usr/bin:/bin:/usr/sbin:/sbin` まで削られている（同じ ADR）。
- 足した後は `herdr config check` と `herdr server reload-config` を流し、実際にキーを押して効くことを
  確かめる。
