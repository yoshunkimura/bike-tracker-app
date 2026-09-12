[app]

title = バイク記録アプリ
package.name = biketracker
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 0.1

requirements = python3,kivy,plyer

orientation = portrait
fullscreen = 0

# ステップ3: バックグラウンド記録のため FOREGROUND_SERVICE 等を追加。
android.permissions = ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,ACCESS_BACKGROUND_LOCATION,FOREGROUND_SERVICE,FOREGROUND_SERVICE_LOCATION,POST_NOTIFICATIONS,READ_MEDIA_IMAGES,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# バックグラウンドでGPS記録を続けるためのフォアグラウンドサービス
services = tracker:service.py:foreground

android.api = 33
android.build_tools_version = 33.0.2
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 0
