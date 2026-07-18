# rust

rust-analyzer LSP を組み込んだ Rust 開発ワークフロースキル。`.rs` ファイルや `Cargo.toml` を扱う際に起動し、LSP によるナビゲーション・診断・コードインテリジェンスを提供する。

外部スキル [rust-analyzer-lsp](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/rust-analyzer-lsp) に依存する。

## 前提

`rust-analyzer` がインストールされていること:

```bash
rustup component add rust-analyzer
```

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install rust@dotagents
```

## スキル一覧

| スキル | 内容 |
|--------|------|
| `rust` | rust-analyzer LSP を用いた Rust 開発ワークフロー |
