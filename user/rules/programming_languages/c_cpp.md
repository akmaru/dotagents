---
paths:
  - "**/*.c"
  - "**/*.cc"
  - "**/*.cpp"
  - "**/*.h"
  - "**/*.hpp"
---

# C/C++ コーディング指針

C/C++を使ったプロジェクトについて、私がコーディングするときのコーディング指針です。

**プロジェクト固有の規約がある場合には、そちらを優先してください。**

## コーディングスタイル
Google C++ Style Guide に則ってください。ただし、下記の変更を加えています。

- **1行の文字数制限**: 120文字
- **ポインタ修飾子**: 左寄せ (`int* p`)

このコーディングスタイルに則った `.clang-format` をプロジェクトルートに配置し、自動フォーマッティングやフォーマットチェックを適用してください。

## プロジェクト構成

```
project/
├── .clang-format             # Clang Format 設定ファイル
├── .clang-tidy               # Clang Tidy 設定ファイル
├── .cmake-format.yml         # CMake Format 設定ファイル
├── CMakeLists.txt            # CMake ビルド設定
├── include/<project-name>/   # 公開ヘッダ (.h)
├── src/                      # 実装 (.cc) と内部ヘッダ
├── test/                     # テスト (*_test.cc)
└── cmake/                    # CMake モジュール
```

- ソースファイル拡張子: `.cc`
- ヘッダファイル拡張子: `.h`
- 公開 API は `include/<project-name>/` に配置し、内部実装は `src/` に置く

## ビルドシステム

- **CMake**: `cmake_minimum_required` を明示
- **C++ 標準**: C++20
- **ビルドシステム**: Ninja (`cmake -B build -GNinja`)
- **`compile_commands.json`**: `CMAKE_EXPORT_COMPILE_COMMANDS ON` を設定
- **リリースオプション**: `-O3 -march=native -mtune=native`

CMake ファイルは `cmake-format` でフォーマット（120文字、2スペースインデント）。

CMakeLists.txt は、下記のコマンドがそれぞれ下記の実行ができます。

- `cmake --build`: プログラムのビルド
- `cmake --build --target test`: テストのビルド
- `ctest`: テストの実行
- `cpack`: ビルド済みパッケージのビルド

## 静的解析

`.clang-tidy` に従い、以下を有効化:
- `bugprone-*`, `google-*`, `misc-*`, `modernize-*`, `performance-*`, `portability-*`, `readability-*`

WarningsAsErrors: すべての警告をエラーとして扱う。

新規コードは `clang-tidy` のチェックをパスすること。

## テスト

- **フレームワーク**: Google Test (FetchContent で自動取得)
- **ファイル命名**: `<対象>_test.cc`
- **テスト登録**: `gtest_discover_tests()` で自動検出
- **実行**: `ctest --test-dir build`

テストファイルは `test/` ディレクトリに配置。

## エラーハンドリング

- アサーションには `CHECK_*` / `DCHECK_*` マクロを使用
  - `CHECK_EQ`, `CHECK_NE`, `CHECK_LT`, `CHECK_LE`, `CHECK_GT`, `CHECK_GE`
  - `DCHECK_*` は Release ビルドで無効化される
- 重複するログには `WARN_ONCE` を使用

## CI/CD

CI/CD パイプラインでは、以下のステップを実行してください。

- フォーマットチェック: `clang-format --dry-run -Werror`
- リント: `clang-tidy -p build`
- テスト: `ctest`
- リリース: `cpack`
