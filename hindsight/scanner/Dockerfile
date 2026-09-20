# 検出は正規表現と HTTP だけなので標準ライブラリで足りる。依存を足さないこと
# 自体が、Hindsight 本体のバージョン上げに引きずられない条件になっている。
FROM python:3.12-slim

WORKDIR /app
COPY scanner.py /app/scanner.py

USER nobody
ENTRYPOINT ["python", "-u", "/app/scanner.py"]
