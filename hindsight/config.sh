#!/usr/bin/env bash
#
# Hindsight サーバーの非秘密の設定。起動スクリプトから source される。
# API キーはここに書かない（hindsight-start.sh が Keychain または環境変数から取得する）。
#

# 未設定だと config.py の DEFAULT_LLM_PROVIDER="openai" にフォールバックし、
# Anthropic のキーを OpenAI へ送って 401 invalid_api_key になる。必ず明示する。
export HINDSIGHT_API_LLM_PROVIDER=anthropic

# reflect のみ上位モデルにする。既定の claude-haiku-4-5 は記憶にない情報を捏造し、
# directive も無視する。retain / consolidation は投入量が多いので haiku のまま据え置く。
export HINDSIGHT_API_REFLECT_LLM_MODEL=claude-sonnet-5

# 日本語で投入しても retain が fact を英語や中国語に翻訳して保存することがある。
# 未設定は「ソースの言語を保持する」建前だが実際には保持されないため明示する。
# retain / consolidation / reflect すべてに一律で効く。
export HINDSIGHT_API_LLM_OUTPUT_LANGUAGE=Japanese

# 認証を有効にしていないので、ループバック限定で待ち受ける。
export HINDSIGHT_API_HOST=127.0.0.1
export HINDSIGHT_API_PORT=8888
