[app]

title = バイク記録アプリ
package.name = biketracker
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.1

requirements = python3,kivy,plyer

orientation = portrait
fullscreen = 0

# ステップ1ではGPSの取得権限のみ。
# 次のステップ(バックグラウンド記録)で FOREGROUND_SERVICE 等を追加予定。
android.permissions = ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION

android.api = 33
android.build_tools_version = 33.0.2
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 0
