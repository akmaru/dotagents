@~/.claude/AGENTS.md

## Work-Specific Instructions

所属会社用の `CLAUDE.work.md` がある場合、下記の指示も参照してください。

@~/.claude/CLAUDE.work.md

## Memory（Claude Code 固有の対応）

AGENTS.md の Memory が言う「セッション終了時の自動投入」は、Claude Code では `SessionEnd` hook
（`hindsight-retain-hook.sh`）が担う。transcript から会話の地の文だけを抜き出して Hindsight に
POST する。設計と判断の経緯は `docs/adr/0017-session-end-retain-hook.md`。

## Delegation（Claude Code 固有の対応）

AGENTS.md の Delegation を Claude Code で実行するときの対応表。

- 役割の起動: `Agent` ツールの `subagent_type` に役割名を渡す。
- 完了したエージェントの再開: `SendMessage` にエージェント ID を渡す。
- コードの場所探し: 組み込みの `Explore`。実装手順の立案: 組み込みの `Plan`。

