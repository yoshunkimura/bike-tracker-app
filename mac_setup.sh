#!/bin/bash
# MacBookでこのスクリプトを実行してAPKをビルドします
# 事前条件: Docker Desktop for Mac がインストール済みであること
#           (https://www.docker.com/products/docker-desktop/)

set -e

echo "=== バイク記録アプリ APKビルド (Mac用) ==="

# 1. Dockerが動いているか確認
if ! docker info > /dev/null 2>&1; then
    echo "エラー: Dockerが起動していません。Docker Desktopを起動してから再実行してください。"
    exit 1
fi

# 2. Buildozerの公式Dockerイメージでビルド
echo "APKをビルドしています(初回は30分〜1時間程度かかることがあります)..."
docker run --rm -it --platform linux/amd64 --volume "$(pwd)":/home/user/hostcwd kivy/buildozer android debug

echo "=== ビルド完了 ==="
echo "生成されたAPKは bin/ フォルダの中にあります"
ls -la bin/*.apk 2>/dev/null || echo "(bin/フォルダを確認してください)"
