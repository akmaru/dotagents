# agent-dx

エージェントを使っていて感じた利用体験の課題や、実現したいことを、その場で dotagents の GitHub Issue に起票するスキル。
`agent-dx` ラベルの付いた Issue は、GitHub Actions のエージェントがトリアージ・設計・実装を進めて PR を出す。
オーナーは PR を隔離した環境で試し、approve すると merge される
（[ADR 0027](../../docs/adr/0027-agent-dx-improvement-loop-via-github-issues.md)）。

スキル名とラベル名の `agent-dx` は仮の名前（ADR 0027 の未決事項）。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install agent-dx@dotagents
```

`gh` が akmaru/dotagents に Issue を作れる状態で認証されている必要がある。

## 使い方

作業中に `/agent-dx <一言>` と打つ。スキルが今のセッションの文脈を添えて Issue の下書きを作り、確認を取ってから起票する。

## 改善ループを動かすための準備

ループ（`.github/workflows/agent-dx.yml`）を新しく動かすには、akmaru/dotagents に対して次の 3 つを一度だけ行う。

1. **Claude GitHub App を入れる**
   [Claude GitHub App](https://github.com/apps/claude) を akmaru/dotagents に入れる。
   Repository access は Only select repositories にして、dotagents だけを選ぶ。
2. **OAuth トークンを repository secret に登録する**
   個人の Max アカウントで `claude setup-token` を実行し、出たトークンを secret `CLAUDE_CODE_OAUTH_TOKEN` に登録する。

   ```bash
   gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo akmaru/dotagents
   ```

   - `claude setup-token` は、作業中のエージェントのセッションではなく別のターミナルで実行する。
     トークンが会話に残ると、会話は Hindsight に投入される。
   - ブラウザで会社のアカウントにログインしていると、そのアカウントのトークンが発行される。
     個人の Max アカウントでログインしていることを確かめてから実行する。
3. **ラベル `agent-dx` を作る**

   ```bash
   gh label create agent-dx --repo akmaru/dotagents
   ```

### ワークフローを変える PR は merge するまで効かない

ワークフローは main にあるファイルから起動する。そのため、ワークフロー（`.github/workflows/`）を変える PR は、
merge するまでループに反映されない。
