# -*- coding: utf-8 -*-
"""
バイクツーリング記録アプリ - ステップ1
「スタート」ボタンを押すとGPS座標を取得して画面に表示するだけのシンプルな検証用アプリ。

このステップの目的:
- Kivyアプリの基本構造を理解する
- plyer経由でAndroidのGPSにアクセスできることを確認する

次のステップで追加予定:
- 座標をリスト/ファイルに保存する記録機能
- ForegroundServiceでバックグラウンド記録に対応
- Googleマップ上への描画
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.config import Config

# 日本語フォント(Noto Sans JP)をデフォルトフォントとして登録する
# これがないと、日本語の文字が文字化け(豆腐/□)して表示されない
LabelBase.register(
    name="NotoSansJP",
    fn_regular="fonts/NotoSansJP-Regular.ttf",
)
Config.set("kivy", "default_font", ["NotoSansJP", "fonts/NotoSansJP-Regular.ttf"])

try:
    from plyer import gps
    GPS_AVAILABLE = True
except Exception:
    GPS_AVAILABLE = False


class TrackerLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=20, spacing=20, **kwargs)

        self.status_label = Label(
            text="スタートボタンを押してください",
            font_size="20sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.3),
        )
        self.add_widget(self.status_label)

        self.start_button = Button(
            text="スタート",
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.35),
            background_color=(0.2, 0.6, 1, 1),
        )
        self.start_button.bind(on_press=self.start_tracking)
        self.add_widget(self.start_button)

        self.stop_button = Button(
            text="ストップ",
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.35),
            background_color=(1, 0.3, 0.3, 1),
        )
        self.stop_button.bind(on_press=self.stop_tracking)
        self.add_widget(self.stop_button)

        self.tracking = False

    def start_tracking(self, instance):
        if not GPS_AVAILABLE:
            self.status_label.text = "GPS機能が利用できません\n(Android実機で実行してください)"
            return

        try:
            gps.configure(on_location=self.on_location, on_status=self.on_status)
            gps.start(minTime=1000, minDistance=1)  # 1秒ごと、1m移動ごとに更新
            self.tracking = True
            self.status_label.text = "記録開始しました...\n座標取得を待っています"
        except NotImplementedError:
            self.status_label.text = "この端末ではGPSがサポートされていません"
        except Exception as e:
            self.status_label.text = f"エラー: {e}"

    def stop_tracking(self, instance):
        if GPS_AVAILABLE and self.tracking:
            gps.stop()
            self.tracking = False
            self.status_label.text = "記録を停止しました"

    def on_location(self, **kwargs):
        lat = kwargs.get("lat", "不明")
        lon = kwargs.get("lon", "不明")
        self.status_label.text = f"緯度: {lat}\n経度: {lon}"

    def on_status(self, stype, status):
        print(f"GPS status: {stype} - {status}")


class BikeTrackerApp(App):
    def build(self):
        self.title = "バイク記録アプリ (ステップ1)"
        return TrackerLayout()

    def on_start(self):
        # Android実機でGPS権限をリクエストする
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION,
            ])
        except ImportError:
            # Android以外の環境(PCでのテストなど)では無視
            pass


if __name__ == "__main__":
    BikeTrackerApp().run()
