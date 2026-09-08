# -*- coding: utf-8 -*-
"""
バイクツーリング記録アプリ - ステップ2
プロファイル(バイクごと)を作成・選択してから、GPS記録を開始できるアプリ。

画面構成:
- ProfileListScreen: プロファイル一覧。タップで記録画面へ、+で新規作成へ
- AddProfileScreen: 名前入力 + 写真(撮影 or ギャラリー選択)でプロファイル作成
- TrackerScreen: 選んだプロファイルでGPS記録を開始/停止し、座標をファイルに保存

保存場所:
- プロファイル情報: <アプリ専用フォルダ>/profiles.json
- プロファイル写真: <アプリ専用フォルダ>/profile_photos/<id>.jpg
- 走行記録:       <アプリ専用フォルダ>/routes/<profile_id>/<日付>.csv
"""

import os
import json
import uuid
import csv
from datetime import datetime

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.config import Config

# 日本語フォント(Noto Sans JP)をデフォルトフォントとして登録する
LabelBase.register(
    name="NotoSansJP",
    fn_regular="fonts/NotoSansJP-Regular.ttf",
)
Config.set("kivy", "default_font", ["NotoSansJP", "fonts/NotoSansJP-Regular.ttf"])

try:
    from plyer import gps, camera, filechooser
    PLYER_AVAILABLE = True
except Exception:
    PLYER_AVAILABLE = False


# ---------------------------------------------------------------
# データ管理: プロファイルの保存・読み込み、走行記録ファイルの管理
# ---------------------------------------------------------------
class ProfileManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.profiles_file = os.path.join(self.base_dir, "profiles.json")
        self.photos_dir = os.path.join(self.base_dir, "profile_photos")
        self.routes_dir = os.path.join(self.base_dir, "routes")
        os.makedirs(self.photos_dir, exist_ok=True)
        os.makedirs(self.routes_dir, exist_ok=True)
        self.profiles = self._load()

    def _load(self):
        if os.path.exists(self.profiles_file):
            try:
                with open(self.profiles_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self):
        with open(self.profiles_file, "w", encoding="utf-8") as f:
            json.dump(self.profiles, f, ensure_ascii=False, indent=2)

    def add_profile(self, name, photo_source_path=None):
        profile_id = str(uuid.uuid4())
        stored_photo = None
        if photo_source_path and os.path.exists(photo_source_path):
            ext = os.path.splitext(photo_source_path)[1] or ".jpg"
            stored_photo = os.path.join(self.photos_dir, profile_id + ext)
            try:
                with open(photo_source_path, "rb") as src, open(stored_photo, "wb") as dst:
                    dst.write(src.read())
            except Exception:
                stored_photo = None

        profile = {"id": profile_id, "name": name, "photo": stored_photo}
        self.profiles.append(profile)
        self._save()
        return profile

    def route_file_for(self, profile_id):
        date_str = datetime.now().strftime("%Y-%m-%d")
        folder = os.path.join(self.routes_dir, profile_id)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{date_str}.csv")
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "lat", "lon"])
        return path


# ---------------------------------------------------------------
# 画面1: プロファイル一覧
# ---------------------------------------------------------------
class ProfileListScreen(Screen):
    def on_pre_enter(self, *args):
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=20, spacing=15)

        title = Label(
            text="プロファイルを選択",
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.12),
        )
        root.add_widget(title)

        scroll = ScrollView(size_hint=(1, 0.72))
        grid = GridLayout(cols=2, spacing=15, size_hint_y=None, padding=5)
        grid.bind(minimum_height=grid.setter("height"))

        app = App.get_running_app()
        profiles = app.profile_manager.profiles

        if not profiles:
            empty_label = Label(
                text="まだプロファイルがありません\n右下の「+」から作成してください",
                font_name="NotoSansJP",
                font_size="16sp",
                size_hint_y=None,
                height=100,
            )
            grid.add_widget(empty_label)
        else:
            for profile in profiles:
                grid.add_widget(self._build_profile_card(profile))

        scroll.add_widget(grid)
        root.add_widget(scroll)

        add_button = Button(
            text="+ 新しいプロファイルを作成",
            font_name="NotoSansJP",
            font_size="18sp",
            size_hint=(1, 0.12),
            background_color=(0.2, 0.6, 1, 1),
        )
        add_button.bind(on_press=self.go_to_add_profile)
        root.add_widget(add_button)

        self.add_widget(root)

    def _build_profile_card(self, profile):
        card = BoxLayout(orientation="vertical", size_hint_y=None, height=200)

        if profile.get("photo") and os.path.exists(profile["photo"]):
            img = KivyImage(source=profile["photo"], size_hint=(1, 0.7))
        else:
            img = Label(text="(写真なし)", font_name="NotoSansJP", size_hint=(1, 0.7))
        card.add_widget(img)

        name_button = Button(
            text=profile["name"],
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.3),
        )
        name_button.bind(
            on_press=lambda instance, p=profile: self.go_to_tracker(p)
        )
        card.add_widget(name_button)

        return card

    def go_to_add_profile(self, instance):
        self.manager.current = "add_profile"

    def go_to_tracker(self, profile):
        app = App.get_running_app()
        app.selected_profile = profile
        self.manager.current = "tracker"


# ---------------------------------------------------------------
# 画面2: プロファイル新規作成
# ---------------------------------------------------------------
class AddProfileScreen(Screen):
    def on_pre_enter(self, *args):
        self.selected_photo_path = None
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=20, spacing=15)

        title = Label(
            text="新しいプロファイル",
            font_size="22sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.1),
        )
        root.add_widget(title)

        self.name_input = TextInput(
            hint_text="バイクの名前(例: CB400SF)",
            font_name="NotoSansJP",
            font_size="18sp",
            size_hint=(1, 0.12),
            multiline=False,
        )
        root.add_widget(self.name_input)

        self.preview_image = KivyImage(size_hint=(1, 0.4))
        root.add_widget(self.preview_image)

        photo_buttons = BoxLayout(orientation="horizontal", size_hint=(1, 0.12), spacing=10)
        camera_button = Button(text="写真を撮影", font_name="NotoSansJP", font_size="16sp")
        camera_button.bind(on_press=self.take_photo)
        gallery_button = Button(text="ギャラリーから選択", font_name="NotoSansJP", font_size="16sp")
        gallery_button.bind(on_press=self.pick_from_gallery)
        photo_buttons.add_widget(camera_button)
        photo_buttons.add_widget(gallery_button)
        root.add_widget(photo_buttons)

        self.status_label = Label(text="", font_name="NotoSansJP", size_hint=(1, 0.1))
        root.add_widget(self.status_label)

        bottom_buttons = BoxLayout(orientation="horizontal", size_hint=(1, 0.12), spacing=10)
        cancel_button = Button(text="キャンセル", font_name="NotoSansJP", font_size="16sp")
        cancel_button.bind(on_press=self.cancel)
        save_button = Button(
            text="保存",
            font_name="NotoSansJP",
            font_size="18sp",
            background_color=(0.2, 0.6, 1, 1),
        )
        save_button.bind(on_press=self.save_profile)
        bottom_buttons.add_widget(cancel_button)
        bottom_buttons.add_widget(save_button)
        root.add_widget(bottom_buttons)

        self.add_widget(root)

    def take_photo(self, instance):
        if not PLYER_AVAILABLE:
            self.status_label.text = "カメラ機能が利用できません(実機で確認してください)"
            return
        app = App.get_running_app()
        photo_path = os.path.join(app.user_data_dir, f"tmp_camera_{uuid.uuid4().hex}.jpg")
        try:
            camera.take_photo(filename=photo_path, on_complete=self._on_photo_taken)
        except NotImplementedError:
            self.status_label.text = "この端末ではカメラがサポートされていません"
        except Exception as e:
            self.status_label.text = f"カメラエラー: {e}"

    def _on_photo_taken(self, path):
        # 端末によっては、コールバック実行時点でまだファイル書き込みが
        # 完了していない場合があるため、少し待ってから確認する
        def check(dt):
            if path and os.path.exists(path):
                self._set_preview(path)
            else:
                self.status_label.text = "撮影がキャンセルされました"

        Clock.schedule_once(check, 0.3)

    def pick_from_gallery(self, instance):
        if not PLYER_AVAILABLE:
            self.status_label.text = "ギャラリー機能が利用できません(実機で確認してください)"
            return
        try:
            filechooser.open_file(
                on_selection=self._on_gallery_selected,
                filters=[["画像", "*.jpg", "*.jpeg", "*.png"]],
            )
        except NotImplementedError:
            self.status_label.text = "この端末ではギャラリー選択がサポートされていません"
        except Exception as e:
            self.status_label.text = f"ギャラリーエラー: {e}"

    def _on_gallery_selected(self, selection):
        if selection and selection[0]:
            Clock.schedule_once(lambda dt: self._set_preview(selection[0]))
        else:
            Clock.schedule_once(
                lambda dt: setattr(self.status_label, "text", "写真が選択されませんでした")
            )

    def _set_preview(self, path):
        if not path or not os.path.exists(path):
            self.status_label.text = "写真を取得できませんでした。もう一度お試しください"
            return
        try:
            self.selected_photo_path = path
            self.preview_image.source = path
            self.preview_image.reload()
            self.status_label.text = "写真を選択しました"
        except Exception as e:
            self.status_label.text = f"プレビューエラー: {e}"

    def cancel(self, instance):
        self.manager.current = "profile_list"

    def save_profile(self, instance):
        name = self.name_input.text.strip()
        if not name:
            self.status_label.text = "バイクの名前を入力してください"
            return

        app = App.get_running_app()
        app.profile_manager.add_profile(name, self.selected_photo_path)
        self.manager.current = "profile_list"


# ---------------------------------------------------------------
# 画面3: GPS記録画面(プロファイルごとにファイルへ保存)
# ---------------------------------------------------------------
class TrackerScreen(Screen):
    def on_pre_enter(self, *args):
        self.tracking = False
        self.route_file_path = None
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=20, spacing=20)

        app = App.get_running_app()
        profile_name = app.selected_profile["name"] if app.selected_profile else "(不明)"

        self.title_label = Label(
            text=f"プロファイル: {profile_name}",
            font_size="18sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.15),
        )
        root.add_widget(self.title_label)

        self.status_label = Label(
            text="スタートボタンを押してください",
            font_size="20sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.25),
        )
        root.add_widget(self.status_label)

        self.start_button = Button(
            text="スタート",
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.2),
            background_color=(0.2, 0.6, 1, 1),
        )
        self.start_button.bind(on_press=self.start_tracking)
        root.add_widget(self.start_button)

        self.stop_button = Button(
            text="ストップ",
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.2),
            background_color=(1, 0.3, 0.3, 1),
        )
        self.stop_button.bind(on_press=self.stop_tracking)
        root.add_widget(self.stop_button)

        back_button = Button(
            text="プロファイル一覧に戻る",
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.15),
        )
        back_button.bind(on_press=self.go_back)
        root.add_widget(back_button)

        self.add_widget(root)

    def start_tracking(self, instance):
        if not PLYER_AVAILABLE:
            self.status_label.text = "GPS機能が利用できません\n(Android実機で実行してください)"
            return

        app = App.get_running_app()
        if not app.selected_profile:
            self.status_label.text = "プロファイルが選択されていません"
            return

        self.route_file_path = app.profile_manager.route_file_for(app.selected_profile["id"])

        try:
            gps.configure(on_location=self.on_location, on_status=self.on_status)
            gps.start(minTime=1000, minDistance=1)
            self.tracking = True
            self.status_label.text = "記録開始しました...\n座標取得を待っています"
        except NotImplementedError:
            self.status_label.text = "この端末ではGPSがサポートされていません"
        except Exception as e:
            self.status_label.text = f"エラー: {e}"

    def stop_tracking(self, instance):
        if PLYER_AVAILABLE and self.tracking:
            gps.stop()
            self.tracking = False
            self.status_label.text = "記録を停止しました"

    def on_location(self, **kwargs):
        lat = kwargs.get("lat")
        lon = kwargs.get("lon")
        self.status_label.text = f"緯度: {lat}\n経度: {lon}"

        if self.route_file_path and lat is not None and lon is not None:
            try:
                with open(self.route_file_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.now().isoformat(), lat, lon])
            except Exception as e:
                print(f"座標の保存に失敗しました: {e}")

    def on_status(self, stype, status):
        print(f"GPS status: {stype} - {status}")

    def go_back(self, instance):
        if self.tracking:
            self.stop_tracking(None)
        self.manager.current = "profile_list"


# ---------------------------------------------------------------
# アプリ本体
# ---------------------------------------------------------------
class BikeTrackerApp(App):
    def build(self):
        self.title = "バイク記録アプリ"
        self.profile_manager = ProfileManager(self.user_data_dir)
        self.selected_profile = None

        sm = ScreenManager()
        sm.add_widget(ProfileListScreen(name="profile_list"))
        sm.add_widget(AddProfileScreen(name="add_profile"))
        sm.add_widget(TrackerScreen(name="tracker"))
        return sm

    def on_start(self):
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION,
                Permission.CAMERA,
            ])
        except ImportError:
            pass


if __name__ == "__main__":
    BikeTrackerApp().run()