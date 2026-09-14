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
import math
import calendar
from datetime import datetime, timezone, timedelta

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
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.config import Config

try:
    from jnius import autoclass
    ANDROID_JNIUS_AVAILABLE = True
except Exception:
    ANDROID_JNIUS_AVAILABLE = False

# 日本語フォント(Noto Sans JP)をデフォルトフォントとして登録する
LabelBase.register(
    name="NotoSansJP",
    fn_regular="fonts/NotoSansJP-Regular.ttf",
)
Config.set("kivy", "default_font", ["NotoSansJP", "fonts/NotoSansJP-Regular.ttf"])

try:
    from plyer import gps, filechooser
    PLYER_AVAILABLE = True
except Exception:
    PLYER_AVAILABLE = False


# ---------------------------------------------------------------
# 距離計算(2点間の距離をkmで返す/ルート全体の距離を合計する)
# ---------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0  # 地球の半径(km)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(min(1, math.sqrt(a)))


def route_distance_km(points):
    total = 0.0
    for i in range(1, len(points)):
        lat1, lon1 = points[i - 1][0], points[i - 1][1]
        lat2, lon2 = points[i][0], points[i][1]
        total += haversine_km(lat1, lon1, lat2, lon2)
    return total


# ---------------------------------------------------------------
# タイムゾーン選択肢(固定オフセット方式。タイムゾーンDB不要で軽量)
# ---------------------------------------------------------------
TIMEZONE_CHOICES = [
    ("UTC-8 (米国太平洋)", -8),
    ("UTC-5 (米国東部)", -5),
    ("UTC+0 (UTC)", 0),
    ("UTC+1 (中央ヨーロッパ)", 1),
    ("UTC+8 (中国/台湾)", 8),
    ("UTC+9 (日本/韓国)", 9),
    ("UTC+10 (東部オーストラリア)", 10),
]


def format_time_in_offset(iso_str, offset_hours):
    """
    UTC('Z'付き)のISO時刻文字列を指定したオフセットのローカル時刻(HH:MM)に変換する。
    'Z'が付いていない古い形式のデータは、タイムゾーン変換をせずそのまま解釈する
    (アップデート前の記録との互換性のため)。
    """
    try:
        if iso_str.endswith("Z"):
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            dt = dt.astimezone(timezone(timedelta(hours=offset_hours)))
        else:
            dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%H:%M")
    except Exception:
        return "--:--"


# ---------------------------------------------------------------
# 翻訳データ(日本語・英語)
# ---------------------------------------------------------------
TRANSLATIONS = {
    "ja": {
        "profile_list_title": "プロファイルを選択",
        "profile_list_empty": "まだプロファイルがありません\n右下の「+」から作成してください",
        "add_profile_button": "+ 新しいプロファイルを作成",
        "map_button": "地図で見る",
        "no_photo": "(写真なし)",
        "settings_button": "設定",
        "add_profile_title": "新しいプロファイル",
        "bike_name_hint": "バイクの名前(例: CB400SF)",
        "gallery_button": "写真を選択(ギャラリーから)",
        "cancel_button": "キャンセル",
        "save_button": "保存",
        "name_required": "バイクの名前を入力してください",
        "gallery_unavailable": "ギャラリー機能が利用できません(実機で確認してください)",
        "gallery_not_supported": "この端末ではギャラリー選択がサポートされていません",
        "gallery_error": "ギャラリーエラー: {error}",
        "photo_not_selected": "写真が選択されませんでした",
        "photo_selected": "写真を選択しました",
        "photo_get_failed": "写真を取得できませんでした。もう一度お試しください",
        "preview_error": "プレビューエラー: {error}",
        "tracker_title": "プロファイル: {name}",
        "tracker_status_initial": "スタートボタンを押してください\n(スリープ中も記録が続きます)",
        "start_button": "スタート",
        "stop_button": "ストップ",
        "back_to_profile_list": "プロファイル一覧に戻る",
        "no_profile_selected": "プロファイルが選択されていません",
        "state_write_failed": "状態ファイルの書き込みに失敗: {error}",
        "tracking_started": "バックグラウンドで記録中です\n(通知バーを確認してください)",
        "service_start_error": "サービス起動エラー: {error}",
        "tracking_stopped": "記録を停止しました",
        "route_list_title": "{name} の記録一覧",
        "route_list_empty": "まだ記録がありません",
        "map_loading": "地図を読み込んでいます...",
        "map_no_data": "表示する記録が選択されていません",
        "map_info": "{name} / {date}({count}点)",
        "map_no_points_banner": "座標が記録されていません(記録時間が短すぎた可能性があります)",
        "map_back_button": "< 戻る",
        "settings_title": "設定",
        "language_label": "言語 / Language",
        "language_ja": "日本語",
        "language_en": "English",
        "timezone_label": "タイムゾーン",
        "total_distance": "累計走行距離: {distance} km",
        "day_distance": "{date}({distance} km)",
        "range_select_button": "期間を指定して見る",
        "calendar_title": "期間を選択",
        "calendar_start": "開始日: {date}",
        "calendar_end": "終了日: {date}",
        "calendar_not_set": "未選択",
        "calendar_confirm_map": "地図で見る",
        "calendar_confirm_distance": "距離を見る",
        "calendar_reset": "選択をやり直す",
        "calendar_no_data": "この期間の記録がありません",
        "range_distance_result": "{start} 〜 {end}\n走行距離: {distance} km",
        "close_button": "閉じる",
    },
    "en": {
        "profile_list_title": "Select Profile",
        "profile_list_empty": "No profiles yet\nTap \"+\" below to create one",
        "add_profile_button": "+ Add New Profile",
        "map_button": "View Map",
        "no_photo": "(no photo)",
        "settings_button": "Settings",
        "add_profile_title": "New Profile",
        "bike_name_hint": "Bike name (e.g. CB400SF)",
        "gallery_button": "Choose Photo (Gallery)",
        "cancel_button": "Cancel",
        "save_button": "Save",
        "name_required": "Please enter a bike name",
        "gallery_unavailable": "Gallery is unavailable (please test on a real device)",
        "gallery_not_supported": "Gallery selection is not supported on this device",
        "gallery_error": "Gallery error: {error}",
        "photo_not_selected": "No photo was selected",
        "photo_selected": "Photo selected",
        "photo_get_failed": "Could not get the photo. Please try again",
        "preview_error": "Preview error: {error}",
        "tracker_title": "Profile: {name}",
        "tracker_status_initial": "Press Start to begin\n(recording continues while asleep)",
        "start_button": "Start",
        "stop_button": "Stop",
        "back_to_profile_list": "Back to Profile List",
        "no_profile_selected": "No profile selected",
        "state_write_failed": "Failed to write state file: {error}",
        "tracking_started": "Recording in background\n(check the notification bar)",
        "service_start_error": "Service start error: {error}",
        "tracking_stopped": "Recording stopped",
        "route_list_title": "{name}'s Records",
        "route_list_empty": "No records yet",
        "map_loading": "Loading map...",
        "map_no_data": "No record selected to display",
        "map_info": "{name} / {date} ({count} points)",
        "map_no_points_banner": "No coordinates recorded (recording time may have been too short)",
        "map_back_button": "< Back",
        "settings_title": "Settings",
        "language_label": "言語 / Language",
        "language_ja": "日本語",
        "language_en": "English",
        "timezone_label": "Time Zone",
        "total_distance": "Total distance: {distance} km",
        "day_distance": "{date} ({distance} km)",
        "range_select_button": "View by Date Range",
        "calendar_title": "Select Date Range",
        "calendar_start": "Start: {date}",
        "calendar_end": "End: {date}",
        "calendar_not_set": "Not set",
        "calendar_confirm_map": "View Map",
        "calendar_confirm_distance": "View Distance",
        "calendar_reset": "Reset Selection",
        "calendar_no_data": "No records in this date range",
        "range_distance_result": "{start} - {end}\nDistance: {distance} km",
        "close_button": "Close",
    },
}


# ---------------------------------------------------------------
# 設定管理: 選択中の言語の保存・読み込み
# ---------------------------------------------------------------
class SettingsManager:
    def __init__(self, base_dir):
        self.settings_file = os.path.join(base_dir, "settings.json")
        self.settings = self._load()

    def _load(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def get_language(self):
        return self.settings.get("language", "ja")

    def set_language(self, language):
        self.settings["language"] = language
        self._save()

    def get_timezone_offset(self):
        return self.settings.get("timezone_offset", 9)  # デフォルトは日本(UTC+9)

    def set_timezone_offset(self, offset_hours):
        self.settings["timezone_offset"] = offset_hours
        self._save()


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

    def list_route_dates(self, profile_id):
        folder = os.path.join(self.routes_dir, profile_id)
        if not os.path.isdir(folder):
            return []
        dates = [f[:-4] for f in os.listdir(folder) if f.endswith(".csv")]
        return sorted(dates, reverse=True)

    def load_route_points_with_time(self, profile_id, date_str):
        """[(timestamp_str, lat, lon), ...] を返す"""
        path = os.path.join(self.routes_dir, profile_id, f"{date_str}.csv")
        points = []
        if not os.path.exists(path):
            return points
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    points.append(
                        (row.get("timestamp", ""), float(row["lat"]), float(row["lon"]))
                    )
                except (KeyError, ValueError):
                    continue
        return points

    def load_route_points(self, profile_id, date_str):
        return [(lat, lon) for _, lat, lon in self.load_route_points_with_time(profile_id, date_str)]

    def route_distance_for_date(self, profile_id, date_str):
        points = self.load_route_points(profile_id, date_str)
        return route_distance_km(points)

    def total_distance_km(self, profile_id):
        total = 0.0
        for date_str in self.list_route_dates(profile_id):
            total += self.route_distance_for_date(profile_id, date_str)
        return total

    def dates_in_range(self, profile_id, start_date, end_date):
        """start_date, end_dateは 'YYYY-MM-DD' 文字列。両端を含む範囲で該当する日付を返す"""
        all_dates = self.list_route_dates(profile_id)
        return sorted([d for d in all_dates if start_date <= d <= end_date])

    def distance_km_in_range(self, profile_id, start_date, end_date):
        total = 0.0
        for date_str in self.dates_in_range(profile_id, start_date, end_date):
            total += self.route_distance_for_date(profile_id, date_str)
        return total

    def load_route_segments(self, profile_id, dates):
        """複数日付ぶんの座標を、日付ごとの区切り(セグメント)のリストとして返す"""
        segments = []
        for date_str in dates:
            points = self.load_route_points(profile_id, date_str)
            if points:
                segments.append(points)
        return segments


# ---------------------------------------------------------------
# 画面1: プロファイル一覧
# ---------------------------------------------------------------
class ProfileListScreen(Screen):
    def on_pre_enter(self, *args):
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        app = App.get_running_app()
        root = BoxLayout(orientation="vertical", padding=20, spacing=15)

        title_row = BoxLayout(orientation="horizontal", size_hint=(1, 0.12), spacing=10)
        title = Label(
            text=app.tr("profile_list_title"),
            font_size="24sp",
            font_name="NotoSansJP",
        )
        title_row.add_widget(title)

        settings_button = Button(
            text=app.tr("settings_button"),
            font_name="NotoSansJP",
            font_size="14sp",
            size_hint=(0.3, 1),
        )
        settings_button.bind(on_press=self.go_to_settings)
        title_row.add_widget(settings_button)
        root.add_widget(title_row)

        scroll = ScrollView(size_hint=(1, 0.72))
        grid = GridLayout(cols=2, spacing=15, size_hint_y=None, padding=5)
        grid.bind(minimum_height=grid.setter("height"))

        profiles = app.profile_manager.profiles

        if not profiles:
            empty_label = Label(
                text=app.tr("profile_list_empty"),
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
            text=app.tr("add_profile_button"),
            font_name="NotoSansJP",
            font_size="18sp",
            size_hint=(1, 0.12),
            background_color=(0.2, 0.6, 1, 1),
        )
        add_button.bind(on_press=self.go_to_add_profile)
        root.add_widget(add_button)

        self.add_widget(root)

    def go_to_settings(self, instance):
        self.manager.current = "settings"

    def _build_profile_card(self, profile):
        app = App.get_running_app()
        card = BoxLayout(orientation="vertical", size_hint_y=None, height=230)

        if profile.get("photo") and os.path.exists(profile["photo"]):
            img = KivyImage(source=profile["photo"], size_hint=(1, 0.6))
        else:
            img = Label(text=app.tr("no_photo"), font_name="NotoSansJP", size_hint=(1, 0.6))
        card.add_widget(img)

        name_button = Button(
            text=profile["name"],
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.22),
        )
        name_button.bind(
            on_press=lambda instance, p=profile: self.go_to_tracker(p)
        )
        card.add_widget(name_button)

        map_button = Button(
            text=app.tr("map_button"),
            font_name="NotoSansJP",
            font_size="14sp",
            size_hint=(1, 0.18),
        )
        map_button.bind(
            on_press=lambda instance, p=profile: self.go_to_route_list(p)
        )
        card.add_widget(map_button)

        return card

    def go_to_add_profile(self, instance):
        self.manager.current = "add_profile"

    def go_to_tracker(self, profile):
        app = App.get_running_app()
        app.selected_profile = profile
        self.manager.current = "tracker"

    def go_to_route_list(self, profile):
        app = App.get_running_app()
        app.selected_profile = profile
        self.manager.current = "route_list"


# ---------------------------------------------------------------
# 画面2: プロファイル新規作成
# ---------------------------------------------------------------
class AddProfileScreen(Screen):
    def on_pre_enter(self, *args):
        self.selected_photo_path = None
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        app = App.get_running_app()
        root = BoxLayout(orientation="vertical", padding=20, spacing=15)

        title = Label(
            text=app.tr("add_profile_title"),
            font_size="22sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.1),
        )
        root.add_widget(title)

        self.name_input = TextInput(
            hint_text=app.tr("bike_name_hint"),
            font_name="NotoSansJP",
            font_size="18sp",
            size_hint=(1, 0.12),
            multiline=False,
        )
        root.add_widget(self.name_input)

        self.preview_image = KivyImage(size_hint=(1, 0.4))
        root.add_widget(self.preview_image)

        photo_buttons = BoxLayout(orientation="horizontal", size_hint=(1, 0.12), spacing=10)
        gallery_button = Button(
            text=app.tr("gallery_button"),
            font_name="NotoSansJP",
            font_size="16sp",
        )
        gallery_button.bind(on_press=self.pick_from_gallery)
        photo_buttons.add_widget(gallery_button)
        root.add_widget(photo_buttons)

        self.status_label = Label(text="", font_name="NotoSansJP", size_hint=(1, 0.1))
        root.add_widget(self.status_label)

        bottom_buttons = BoxLayout(orientation="horizontal", size_hint=(1, 0.12), spacing=10)
        cancel_button = Button(text=app.tr("cancel_button"), font_name="NotoSansJP", font_size="16sp")
        cancel_button.bind(on_press=self.cancel)
        save_button = Button(
            text=app.tr("save_button"),
            font_name="NotoSansJP",
            font_size="18sp",
            background_color=(0.2, 0.6, 1, 1),
        )
        save_button.bind(on_press=self.save_profile)
        bottom_buttons.add_widget(cancel_button)
        bottom_buttons.add_widget(save_button)
        root.add_widget(bottom_buttons)

        self.add_widget(root)

    def pick_from_gallery(self, instance):
        app = App.get_running_app()
        if not PLYER_AVAILABLE:
            self.status_label.text = app.tr("gallery_unavailable")
            return
        try:
            print("[DEBUG] filechooser.open_fileを呼び出します")
            filechooser.open_file(
                on_selection=self._on_gallery_selected,
                filters=[["画像", "*.jpg", "*.jpeg", "*.png"]],
            )
        except NotImplementedError:
            self.status_label.text = app.tr("gallery_not_supported")
        except Exception as e:
            print(f"[DEBUG] filechooserで例外発生: {e}")
            self.status_label.text = app.tr("gallery_error", error=e)

    def _on_gallery_selected(self, selection):
        app = App.get_running_app()
        print(f"[DEBUG] ギャラリー選択結果(生データ): {selection!r}")
        if selection and selection[0]:
            Clock.schedule_once(lambda dt: self._set_preview(selection[0]))
        else:
            Clock.schedule_once(
                lambda dt: setattr(self.status_label, "text", app.tr("photo_not_selected"))
            )

    def _set_preview(self, path):
        app = App.get_running_app()
        print(f"[DEBUG] _set_previewに渡されたpath: {path!r}")
        if not path or not os.path.exists(path):
            print(f"[DEBUG] pathが空、またはファイルが存在しません: {path!r}")
            self.status_label.text = app.tr("photo_get_failed")
            return
        try:
            self.selected_photo_path = path
            self.preview_image.source = path
            self.preview_image.reload()
            self.status_label.text = app.tr("photo_selected")
        except Exception as e:
            print(f"[DEBUG] プレビュー表示で例外発生: {e}")
            self.status_label.text = app.tr("preview_error", error=e)

    def cancel(self, instance):
        self.manager.current = "profile_list"

    def save_profile(self, instance):
        app = App.get_running_app()
        name = self.name_input.text.strip()
        if not name:
            self.status_label.text = app.tr("name_required")
            return

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
        profile_name = app.selected_profile["name"] if app.selected_profile else "(?)"

        self.title_label = Label(
            text=app.tr("tracker_title", name=profile_name),
            font_size="18sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.15),
        )
        root.add_widget(self.title_label)

        self.status_label = Label(
            text=app.tr("tracker_status_initial"),
            font_size="18sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.25),
        )
        root.add_widget(self.status_label)

        self.start_button = Button(
            text=app.tr("start_button"),
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.2),
            background_color=(0.2, 0.6, 1, 1),
        )
        self.start_button.bind(on_press=self.start_tracking)
        root.add_widget(self.start_button)

        self.stop_button = Button(
            text=app.tr("stop_button"),
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.2),
            background_color=(1, 0.3, 0.3, 1),
        )
        self.stop_button.bind(on_press=self.stop_tracking)
        root.add_widget(self.stop_button)

        back_button = Button(
            text=app.tr("back_to_profile_list"),
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.15),
        )
        back_button.bind(on_press=self.go_back)
        root.add_widget(back_button)

        self.add_widget(root)

    def _get_service_class(self):
        if not ANDROID_JNIUS_AVAILABLE:
            raise RuntimeError("Android実機でのみ利用できます")
        # buildozer.specの package.domain + package.name + "Service" + サービス名(先頭大文字)
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        service_class = autoclass("org.example.biketracker.ServiceTracker")
        return service_class, PythonActivity.mActivity

    def start_tracking(self, instance):
        app = App.get_running_app()
        if not app.selected_profile:
            self.status_label.text = app.tr("no_profile_selected")
            return

        self.route_file_path = app.profile_manager.route_file_for(app.selected_profile["id"])

        # サービス側に「どのファイルに保存するか」を伝えるための状態ファイルを書く
        state_file = os.path.join(app.user_data_dir, "service_state.json")
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"route_file": self.route_file_path}, f, ensure_ascii=False)
        except Exception as e:
            self.status_label.text = app.tr("state_write_failed", error=e)
            return

        try:
            service_class, mactivity = self._get_service_class()
            service_class.start(mactivity, "")
            self.tracking = True
            self.status_label.text = app.tr("tracking_started")
        except Exception as e:
            print(f"[DEBUG] サービス起動に失敗: {e}")
            self.status_label.text = app.tr("service_start_error", error=e)

    def stop_tracking(self, instance):
        app = App.get_running_app()
        if not self.tracking:
            return
        try:
            service_class, mactivity = self._get_service_class()
            service_class.stop(mactivity)
        except Exception as e:
            print(f"[DEBUG] サービス停止に失敗: {e}")
        self.tracking = False
        self.status_label.text = app.tr("tracking_stopped")

    def go_back(self, instance):
        # 記録中でも、バックグラウンドで動き続けさせたいので
        # ここではサービスを止めずに画面だけ戻る
        self.manager.current = "profile_list"


# ---------------------------------------------------------------
# 画面4: 記録した日付の一覧(プロファイルごと)
# ---------------------------------------------------------------
class RouteListScreen(Screen):
    def on_pre_enter(self, *args):
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=20, spacing=15)

        app = App.get_running_app()
        profile = app.selected_profile
        profile_name = profile["name"] if profile else "(不明)"

        title = Label(
            text=app.tr("route_list_title", name=profile_name),
            font_size="20sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.1),
        )
        root.add_widget(title)

        total_km = app.profile_manager.total_distance_km(profile["id"]) if profile else 0.0
        total_label = Label(
            text=app.tr("total_distance", distance=f"{total_km:.1f}"),
            font_size="16sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.08),
        )
        root.add_widget(total_label)

        range_button = Button(
            text=app.tr("range_select_button"),
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.1),
        )
        range_button.bind(on_press=self.go_to_calendar)
        root.add_widget(range_button)

        scroll = ScrollView(size_hint=(1, 0.52))
        box = BoxLayout(orientation="vertical", spacing=10, size_hint_y=None, padding=5)
        box.bind(minimum_height=box.setter("height"))

        dates = app.profile_manager.list_route_dates(profile["id"]) if profile else []

        if not dates:
            box.add_widget(
                Label(
                    text=app.tr("route_list_empty"),
                    font_name="NotoSansJP",
                    size_hint_y=None,
                    height=60,
                )
            )
        else:
            for date_str in dates:
                day_km = app.profile_manager.route_distance_for_date(profile["id"], date_str)
                btn = Button(
                    text=app.tr("day_distance", date=date_str, distance=f"{day_km:.1f}"),
                    font_name="NotoSansJP",
                    font_size="16sp",
                    size_hint_y=None,
                    height=70,
                )
                btn.bind(on_press=lambda instance, d=date_str: self.show_map(d))
                box.add_widget(btn)

        scroll.add_widget(box)
        root.add_widget(scroll)

        back_button = Button(
            text=app.tr("back_to_profile_list"),
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.1),
        )
        back_button.bind(on_press=self.go_back)
        root.add_widget(back_button)

        self.add_widget(root)

    def show_map(self, date_str):
        app = App.get_running_app()
        app.selected_route_date = date_str
        app.selected_route_dates = [date_str]
        self.manager.current = "map"

    def go_to_calendar(self, instance):
        self.manager.current = "calendar_range"

    def go_back(self, instance):
        self.manager.current = "profile_list"


# ---------------------------------------------------------------
# 画面5: 地図表示(Leaflet.js + OpenStreetMapをWebViewで表示)
# ---------------------------------------------------------------
class MapScreen(Screen):
    def on_pre_enter(self, *args):
        self.webview = None
        self.back_button_native = None
        self.build_ui()
        self.show_map()
        Window.bind(on_keyboard=self._on_keyboard)

    def on_pre_leave(self, *args):
        Window.unbind(on_keyboard=self._on_keyboard)
        self._remove_webview()

    def _on_keyboard(self, window, key, *args):
        # key=27 はAndroidの「戻る」ボタン/ジェスチャー
        if key == 27:
            self.go_back(None)
            return True
        return False

    def build_ui(self):
        self.clear_widgets()
        app = App.get_running_app()
        root = BoxLayout(orientation="vertical", padding=10, spacing=10)

        self.info_label = Label(
            text=app.tr("map_loading"),
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 1),
        )
        root.add_widget(self.info_label)

        self.add_widget(root)

    def _build_html(self, segments_with_time, info_text="", total_distance_km=0.0):
        """
        segments_with_time: [[(time_label, lat, lon), ...], ...] (日付ごとのリストのリスト)
        """
        app = App.get_running_app()
        has_points = any(len(seg) > 0 for seg in segments_with_time)

        if not has_points:
            segments_js = "[]"
            center_js = "[35.681236, 139.767125]"  # 東京駅(データが無い場合のデフォルト)
            banner = app.tr("map_no_points_banner")
        else:
            # [[[lat, lon, "HH:MM"], ...], ...] の形にする
            segments_js = str(
                [[[lat, lon, t] for t, lat, lon in seg] for seg in segments_with_time if seg]
            )
            first_seg = next(seg for seg in segments_with_time if seg)
            center_js = str([first_seg[0][1], first_seg[0][2]])
            banner = f"{info_text} - {total_distance_km:.1f} km"

        return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
    #banner {{
      position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
      background: rgba(0,0,0,0.6); color: white; padding: 8px;
      font-size: 14px; text-align: left;
    }}
  </style>
</head>
<body>
  <div id="banner">{banner}</div>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    var segments = {segments_js};
    var map = L.map('map').setView({center_js}, 15);
    // キャッシュを使わず常に最新のタイルを取得する
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png?t=' + Date.now(), {{
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    var allBounds = [];
    var colors = ['blue', 'red', 'green', 'purple', 'orange', 'darkcyan'];

    segments.forEach(function(seg, segIndex) {{
      if (seg.length === 0) return;
      var latlngs = seg.map(function(p) {{ return [p[0], p[1]]; }});
      var color = colors[segIndex % colors.length];
      var line = L.polyline(latlngs, {{color: color, weight: 4}}).addTo(map);
      allBounds.push(line.getBounds());

      // 線をタップすると、一番近い座標の時刻を表示する
      line.on('click', function(e) {{
        var clickLatLng = e.latlng;
        var nearest = seg[0];
        var minDist = Infinity;
        seg.forEach(function(p) {{
          var d = map.distance(clickLatLng, [p[0], p[1]]);
          if (d < minDist) {{ minDist = d; nearest = p; }}
        }});
        L.popup()
          .setLatLng([nearest[0], nearest[1]])
          .setContent(nearest[2])
          .openOn(map);
      }});

      L.marker(latlngs[0]).addTo(map).bindPopup('Start: ' + seg[0][2]);
      L.marker(latlngs[latlngs.length - 1]).addTo(map).bindPopup('End: ' + seg[seg.length - 1][2]);
    }});

    if (allBounds.length > 0) {{
      var combined = allBounds[0];
      for (var i = 1; i < allBounds.length; i++) {{
        combined = combined.extend(allBounds[i]);
      }}
      map.fitBounds(combined);
    }}
  </script>
</body>
</html>
"""

    def show_map(self):
        app = App.get_running_app()
        profile = app.selected_profile
        dates = getattr(app, "selected_route_dates", None) or []

        if not profile or not dates:
            self.info_label.text = app.tr("map_no_data")
            return

        segments_with_time = [
            app.profile_manager.load_route_points_with_time(profile["id"], d) for d in dates
        ]
        total_points = sum(len(seg) for seg in segments_with_time)
        all_points_flat = [(lat, lon) for seg in segments_with_time for _, lat, lon in seg]
        total_km = route_distance_km(all_points_flat)

        date_label = dates[0] if len(dates) == 1 else f"{dates[-1]} - {dates[0]}"
        info_text = app.tr("map_info", name=profile["name"], date=date_label, count=total_points)
        self.info_label.text = info_text

        # 時刻表示は設定したタイムゾーンに変換しておく
        segments_local_time = [
            [(app.format_time(ts), lat, lon) for ts, lat, lon in seg]
            for seg in segments_with_time
        ]

        html = self._build_html(segments_local_time, info_text, total_km)

        try:
            from jnius import autoclass, PythonJavaClass, java_method
            from android.runnable import run_on_ui_thread

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            WebView = autoclass("android.webkit.WebView")
            WebViewClient = autoclass("android.webkit.WebViewClient")
            LayoutParams = autoclass("android.view.ViewGroup$LayoutParams")
            FrameLayoutParams = autoclass("android.widget.FrameLayout$LayoutParams")
            AndroidButton = autoclass("android.widget.Button")
            Gravity = autoclass("android.view.Gravity")
            Color = autoclass("android.graphics.Color")

            activity = PythonActivity.mActivity

            class OnClickListener(PythonJavaClass):
                __javainterfaces__ = ["android/view/View$OnClickListener"]
                __javacontext__ = "app"

                def __init__(self, callback):
                    super().__init__()
                    self.callback = callback

                @java_method("(Landroid/view/View;)V")
                def onClick(self, view):
                    print("[DEBUG] 戻るボタンのonClickが呼ばれました")
                    self.callback()

            @run_on_ui_thread
            def _create_webview():
                webview = WebView(activity)
                settings = webview.getSettings()
                settings.setJavaScriptEnabled(True)
                webview.setWebViewClient(WebViewClient())
                webview.loadDataWithBaseURL(None, html, "text/html", "utf-8", None)
                activity.addContentView(webview, LayoutParams(-1, -1))
                self.webview = webview

                # 地図の上に重ねて表示する「戻る」ボタン(左下、ズームボタンと重ならない位置)
                density = activity.getResources().getDisplayMetrics().density
                def dp(v):
                    return int(v * density)

                back_button = AndroidButton(activity)
                JString = autoclass("java.lang.String")
                back_button.setText(JString(app.tr("map_back_button")))
                back_button.setTextColor(Color.WHITE)
                back_button.setBackgroundColor(Color.parseColor("#CC1976D2"))
                back_button.setAllCaps(False)
                back_button.setClickable(True)
                back_button.setFocusable(True)
                back_button.setElevation(dp(8))

                self._back_click_listener = OnClickListener(
                    lambda: Clock.schedule_once(lambda dt: self.go_back(None))
                )
                back_button.setOnClickListener(self._back_click_listener)

                params = FrameLayoutParams(dp(120), dp(56))
                params.gravity = Gravity.BOTTOM | Gravity.LEFT
                params.setMargins(dp(16), 0, 0, dp(24))
                activity.addContentView(back_button, params)
                back_button.bringToFront()
                self.back_button_native = back_button

            _create_webview()
        except Exception as e:
            print(f"[DEBUG] WebView表示に失敗: {e}")
            self.info_label.text = f"地図の表示に失敗しました: {e}\n(Android実機で確認してください)"

    def _remove_webview(self):
        views_to_remove = [
            getattr(self, "webview", None),
            getattr(self, "back_button_native", None),
        ]
        if any(v is not None for v in views_to_remove):
            try:
                from jnius import autoclass, cast
                from android.runnable import run_on_ui_thread

                ViewGroup = autoclass("android.view.ViewGroup")

                @run_on_ui_thread
                def _remove():
                    for v in views_to_remove:
                        if v is not None:
                            parent = v.getParent()
                            if parent is not None:
                                cast(ViewGroup, parent).removeView(v)

                _remove()
            except Exception as e:
                print(f"[DEBUG] WebView削除に失敗: {e}")
            self.webview = None
            self.back_button_native = None

    def go_back(self, instance):
        self.manager.current = "route_list"


# ---------------------------------------------------------------
# 画面6: 設定(言語選択)
# ---------------------------------------------------------------
class CalendarRangeScreen(Screen):
    def on_pre_enter(self, *args):
        today = datetime.now()
        self.current_year = today.year
        self.current_month = today.month
        self.range_start = None
        self.range_end = None
        self.result_text = ""
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        app = App.get_running_app()
        root = BoxLayout(orientation="vertical", padding=15, spacing=10)

        title = Label(
            text=app.tr("calendar_title"),
            font_size="20sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.08),
        )
        root.add_widget(title)

        nav_row = BoxLayout(orientation="horizontal", size_hint=(1, 0.08))
        prev_btn = Button(text="<", font_size="20sp", size_hint=(0.2, 1))
        prev_btn.bind(on_press=self.prev_month)
        nav_row.add_widget(prev_btn)

        month_label = Label(
            text=f"{self.current_year}-{self.current_month:02d}",
            font_size="18sp",
            font_name="NotoSansJP",
        )
        nav_row.add_widget(month_label)

        next_btn = Button(text=">", font_size="20sp", size_hint=(0.2, 1))
        next_btn.bind(on_press=self.next_month)
        nav_row.add_widget(next_btn)
        root.add_widget(nav_row)

        # 曜日ヘッダー
        weekday_row = GridLayout(cols=7, size_hint=(1, 0.06))
        for wd in ["月", "火", "水", "木", "金", "土", "日"]:
            weekday_row.add_widget(
                Label(text=wd, font_name="NotoSansJP", font_size="13sp")
            )
        root.add_widget(weekday_row)

        # 日付グリッド
        grid = GridLayout(cols=7, size_hint=(1, 0.38), spacing=3)
        weeks = calendar.monthcalendar(self.current_year, self.current_month)
        for week in weeks:
            for day in week:
                if day == 0:
                    grid.add_widget(Label(text=""))
                    continue
                date_str = f"{self.current_year}-{self.current_month:02d}-{day:02d}"
                is_in_range = (
                    self.range_start and self.range_end
                    and self.range_start <= date_str <= self.range_end
                )
                is_endpoint = date_str in (self.range_start, self.range_end)
                if is_endpoint:
                    color = (0.2, 0.6, 1, 1)
                elif is_in_range:
                    color = (0.5, 0.75, 1, 1)
                else:
                    color = (0.35, 0.35, 0.35, 1)
                day_btn = Button(
                    text=str(day),
                    font_size="14sp",
                    background_color=color,
                )
                day_btn.bind(on_press=lambda instance, d=date_str: self.select_date(d))
                grid.add_widget(day_btn)
        root.add_widget(grid)

        start_text = self.range_start or app.tr("calendar_not_set")
        end_text = self.range_end or app.tr("calendar_not_set")
        status_label = Label(
            text=f"{app.tr('calendar_start', date=start_text)}   {app.tr('calendar_end', date=end_text)}",
            font_name="NotoSansJP",
            font_size="15sp",
            size_hint=(1, 0.08),
        )
        root.add_widget(status_label)

        if self.result_text:
            result_label = Label(
                text=self.result_text,
                font_name="NotoSansJP",
                font_size="16sp",
                size_hint=(1, 0.1),
            )
            root.add_widget(result_label)

        action_row = BoxLayout(orientation="horizontal", size_hint=(1, 0.12), spacing=8)
        map_btn = Button(
            text=app.tr("calendar_confirm_map"),
            font_name="NotoSansJP",
            font_size="15sp",
        )
        map_btn.bind(on_press=self.confirm_map)
        action_row.add_widget(map_btn)

        distance_btn = Button(
            text=app.tr("calendar_confirm_distance"),
            font_name="NotoSansJP",
            font_size="15sp",
        )
        distance_btn.bind(on_press=self.confirm_distance)
        action_row.add_widget(distance_btn)
        root.add_widget(action_row)

        bottom_row = BoxLayout(orientation="horizontal", size_hint=(1, 0.1), spacing=8)
        reset_btn = Button(
            text=app.tr("calendar_reset"),
            font_name="NotoSansJP",
            font_size="14sp",
        )
        reset_btn.bind(on_press=self.reset_selection)
        bottom_row.add_widget(reset_btn)

        back_btn = Button(
            text=app.tr("back_to_profile_list"),
            font_name="NotoSansJP",
            font_size="14sp",
        )
        back_btn.bind(on_press=self.go_back)
        bottom_row.add_widget(back_btn)
        root.add_widget(bottom_row)

        self.add_widget(root)

    def prev_month(self, instance):
        self.current_month -= 1
        if self.current_month < 1:
            self.current_month = 12
            self.current_year -= 1
        self.build_ui()

    def next_month(self, instance):
        self.current_month += 1
        if self.current_month > 12:
            self.current_month = 1
            self.current_year += 1
        self.build_ui()

    def select_date(self, date_str):
        if not self.range_start or (self.range_start and self.range_end):
            self.range_start = date_str
            self.range_end = None
        elif date_str < self.range_start:
            self.range_end = self.range_start
            self.range_start = date_str
        else:
            self.range_end = date_str
        self.result_text = ""
        self.build_ui()

    def reset_selection(self, instance):
        self.range_start = None
        self.range_end = None
        self.result_text = ""
        self.build_ui()

    def _get_range(self):
        if not self.range_start:
            return None, None
        end = self.range_end or self.range_start
        return self.range_start, end

    def confirm_map(self, instance):
        app = App.get_running_app()
        profile = app.selected_profile
        start, end = self._get_range()
        if not profile or not start:
            return
        dates = app.profile_manager.dates_in_range(profile["id"], start, end)
        if not dates:
            self.result_text = app.tr("calendar_no_data")
            self.build_ui()
            return
        app.selected_route_dates = list(reversed(dates))  # 新しい日付が先頭に来るように
        self.manager.current = "map"

    def confirm_distance(self, instance):
        app = App.get_running_app()
        profile = app.selected_profile
        start, end = self._get_range()
        if not profile or not start:
            return
        distance = app.profile_manager.distance_km_in_range(profile["id"], start, end)
        self.result_text = app.tr(
            "range_distance_result", start=start, end=end, distance=f"{distance:.1f}"
        )
        self.build_ui()

    def go_back(self, instance):
        self.manager.current = "route_list"


# ---------------------------------------------------------------
class SettingsScreen(Screen):
    def on_pre_enter(self, *args):
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        app = App.get_running_app()
        root = BoxLayout(orientation="vertical", padding=20, spacing=15)

        title = Label(
            text=app.tr("settings_title"),
            font_size="22sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.1),
        )
        root.add_widget(title)

        scroll = ScrollView(size_hint=(1, 0.75))
        content = BoxLayout(orientation="vertical", spacing=15, size_hint_y=None, padding=5)
        content.bind(minimum_height=content.setter("height"))

        lang_label = Label(
            text=app.tr("language_label"),
            font_size="18sp",
            font_name="NotoSansJP",
            size_hint_y=None,
            height=40,
        )
        content.add_widget(lang_label)

        ja_button = Button(
            text=app.tr("language_ja"),
            font_name="NotoSansJP",
            font_size="18sp",
            size_hint_y=None,
            height=60,
            background_color=(0.2, 0.6, 1, 1) if app.language == "ja" else (0.5, 0.5, 0.5, 1),
        )
        ja_button.bind(on_press=lambda instance: self.set_language("ja"))
        content.add_widget(ja_button)

        en_button = Button(
            text=app.tr("language_en"),
            font_name="NotoSansJP",
            font_size="18sp",
            size_hint_y=None,
            height=60,
            background_color=(0.2, 0.6, 1, 1) if app.language == "en" else (0.5, 0.5, 0.5, 1),
        )
        en_button.bind(on_press=lambda instance: self.set_language("en"))
        content.add_widget(en_button)

        tz_label = Label(
            text=app.tr("timezone_label"),
            font_size="18sp",
            font_name="NotoSansJP",
            size_hint_y=None,
            height=40,
        )
        content.add_widget(tz_label)

        for label_text, offset in TIMEZONE_CHOICES:
            is_selected = app.timezone_offset == offset
            tz_button = Button(
                text=label_text,
                font_name="NotoSansJP",
                font_size="16sp",
                size_hint_y=None,
                height=55,
                background_color=(0.2, 0.6, 1, 1) if is_selected else (0.5, 0.5, 0.5, 1),
            )
            tz_button.bind(on_press=lambda instance, o=offset: self.set_timezone(o))
            content.add_widget(tz_button)

        scroll.add_widget(content)
        root.add_widget(scroll)

        back_button = Button(
            text=app.tr("back_to_profile_list"),
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.15),
        )
        back_button.bind(on_press=self.go_back)
        root.add_widget(back_button)

        self.add_widget(root)

    def set_language(self, language):
        app = App.get_running_app()
        app.set_language(language)
        self.build_ui()

    def set_timezone(self, offset):
        app = App.get_running_app()
        app.set_timezone_offset(offset)
        self.build_ui()

    def go_back(self, instance):
        self.manager.current = "profile_list"


# ---------------------------------------------------------------
# アプリ本体
# ---------------------------------------------------------------
class BikeTrackerApp(App):
    def build(self):
        self.title = "バイク記録アプリ"
        self.profile_manager = ProfileManager(self.user_data_dir)
        self.settings_manager = SettingsManager(self.user_data_dir)
        self.language = self.settings_manager.get_language()
        self.timezone_offset = self.settings_manager.get_timezone_offset()
        self.selected_profile = None
        self.selected_route_date = None
        self.selected_route_dates = []  # 期間指定で選ばれた複数日付

        sm = ScreenManager()
        sm.add_widget(ProfileListScreen(name="profile_list"))
        sm.add_widget(AddProfileScreen(name="add_profile"))
        sm.add_widget(TrackerScreen(name="tracker"))
        sm.add_widget(RouteListScreen(name="route_list"))
        sm.add_widget(MapScreen(name="map"))
        sm.add_widget(SettingsScreen(name="settings"))
        sm.add_widget(CalendarRangeScreen(name="calendar_range"))
        return sm

    def tr(self, key, **kwargs):
        text = TRANSLATIONS.get(self.language, TRANSLATIONS["ja"]).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def set_language(self, language):
        self.language = language
        self.settings_manager.set_language(language)

    def set_timezone_offset(self, offset_hours):
        self.timezone_offset = offset_hours
        self.settings_manager.set_timezone_offset(offset_hours)

    def format_time(self, iso_str):
        return format_time_in_offset(iso_str, self.timezone_offset)

    def on_start(self):
        try:
            from android.permissions import request_permissions, Permission
            perms = [
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION,
            ]
            # Android のバージョンによって存在しない権限名があるため、
            # 存在するものだけ追加する
            for name in ("READ_MEDIA_IMAGES", "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "POST_NOTIFICATIONS"):
                if hasattr(Permission, name):
                    perms.append(getattr(Permission, name))
            request_permissions(perms, self._on_permissions_result)
        except ImportError:
            pass

    def _on_permissions_result(self, permissions, grants):
        # バックグラウンド位置情報は、前景の位置情報が許可された後でないと
        # Androidがダイアログを出さない仕様のため、別途あとからリクエストする
        try:
            from android.permissions import request_permissions, Permission
            if hasattr(Permission, "ACCESS_BACKGROUND_LOCATION"):
                request_permissions([Permission.ACCESS_BACKGROUND_LOCATION])
        except Exception as e:
            print(f"[DEBUG] バックグラウンド位置情報の権限リクエストに失敗: {e}")


if __name__ == "__main__":
    BikeTrackerApp().run()