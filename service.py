# -*- coding: utf-8 -*-
"""
バックグラウンドGPS記録用サービス。

アプリ本体(画面)とは別プロセスとして動き続け、
スマホがスリープしていても位置情報を取得し、ファイルに保存し続ける。

main.py側(TrackerScreen)が記録開始時に、
「どのファイルに保存するか」を service_state.json に書き込んでから
このサービスを起動する仕組み。
"""

import os
import csv
import json
import traceback
from datetime import datetime

from jnius import autoclass, cast, PythonJavaClass, java_method

PythonService = autoclass("org.kivy.android.PythonService")
Context = autoclass("android.content.Context")
LocationManager = autoclass("android.location.LocationManager")
Looper = autoclass("android.os.Looper")

service = PythonService.mService
STATE_FILE = os.path.join(service.getFilesDir().getAbsolutePath(), "service_state.json")


def log(message):
    # このprintはAndroidのlogcatに "python" タグで出力される
    print(f"[service] {message}")


def read_route_file():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state.get("route_file")
    except Exception as e:
        log(f"service_state.jsonの読み込みに失敗: {e}")
        return None


def append_point(route_file, lat, lon):
    try:
        with open(route_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), lat, lon])
        log(f"座標を保存しました: {lat}, {lon}")
    except Exception as e:
        log(f"座標の保存に失敗: {e}")


class LocationListener(PythonJavaClass):
    __javainterfaces__ = ["android/location/LocationListener"]
    __javacontext__ = "app"

    def __init__(self, route_file):
        super().__init__()
        self.route_file = route_file

    @java_method("(Landroid/location/Location;)V", name="onLocationChanged")
    def onLocationChanged_single(self, location):
        lat = location.getLatitude()
        lon = location.getLongitude()
        append_point(self.route_file, lat, lon)

    @java_method("(Ljava/util/List;)V", name="onLocationChanged")
    def onLocationChanged_batch(self, locations):
        # Android 12以降、位置情報がリストでまとめて届く場合がある
        count = locations.size()
        for i in range(count):
            location = locations.get(i)
            lat = location.getLatitude()
            lon = location.getLongitude()
            append_point(self.route_file, lat, lon)

    @java_method("(Ljava/lang/String;)V")
    def onProviderDisabled(self, provider):
        log(f"プロバイダが無効化されました: {provider}")

    @java_method("(Ljava/lang/String;)V")
    def onProviderEnabled(self, provider):
        log(f"プロバイダが有効化されました: {provider}")

    @java_method("(Ljava/lang/String;ILandroid/os/Bundle;)V")
    def onStatusChanged(self, provider, status, extras):
        pass


def main():
    log("サービス開始")

    # フォアグラウンドサービスとして通知を表示する
    # (plyerのAndroidServiceヘルパーが環境によって失敗するため、Android標準APIで直接行う)
    try:
        NotificationBuilder = autoclass("android.app.Notification$Builder")
        NotificationChannel = autoclass("android.app.NotificationChannel")
        NotificationManager = autoclass("android.app.NotificationManager")
        Build_VERSION = autoclass("android.os.Build$VERSION")

        channel_id = "bike_tracker_channel"
        notification_manager = cast(
            "android.app.NotificationManager",
            service.getSystemService(Context.NOTIFICATION_SERVICE),
        )

        if Build_VERSION.SDK_INT >= 26:
            channel = NotificationChannel(
                channel_id, "バイク記録", NotificationManager.IMPORTANCE_LOW
            )
            notification_manager.createNotificationChannel(channel)
            builder = NotificationBuilder(service, channel_id)
        else:
            builder = NotificationBuilder(service)

        builder.setContentTitle("バイク記録アプリ")
        builder.setContentText("位置情報を記録しています")
        builder.setSmallIcon(service.getApplicationInfo().icon)
        notification = builder.build()
        service.startForeground(1, notification)
        log("フォアグラウンド通知を表示しました")
    except Exception as e:
        log(f"通知の表示に失敗(処理は続行): {e}")
        traceback.print_exc()

    route_file = read_route_file()
    if not route_file:
        log("route_fileが取得できなかったため終了します")
        return

    log(f"保存先: {route_file}")

    try:
        Looper.prepare()
        my_looper = Looper.myLooper()
        location_manager = cast(
            "android.location.LocationManager",
            service.getSystemService(Context.LOCATION_SERVICE),
        )
        listener = LocationListener(route_file)
        # 3秒ごと、1m移動ごとに更新。コールバックは今まさに準備した
        # このスレッドのLooperで受け取り、直後のLooper.loop()でそれを処理し続ける
        location_manager.requestLocationUpdates(
            LocationManager.GPS_PROVIDER, 3000, 1, listener, my_looper
        )
        log("位置情報リスナーの登録に成功しました。更新を待ちます")
        Looper.loop()
    except Exception as e:
        log(f"位置情報リスナーの登録に失敗: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()