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
import base64
import zipfile
import shutil
from datetime import datetime, timezone, timedelta

from kivy.config import Config

# Kivy標準のキーボードではなく、Android標準のキーボード(日本語IME等)を使う
# Windowをインポートする前に設定する必要があるため、ここで行う
Config.set("kivy", "keyboard_mode", "system")

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.uix.popup import Popup
from kivy.uix.behaviors import ButtonBehavior
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase

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
        "backup_button": "バックアップ",
        "delete_profile_confirm": "「{name}」を削除しますか?\nすべての走行記録・写真・ピンも削除されます",
        "yes_button": "はい",
        "no_button": "いいえ",
        "profile_deleted": "「{name}」を削除しました",
        "import_button": "データをインポート",
        "backup_success": "バックアップを保存しました:\n{path}",
        "backup_failed": "バックアップに失敗しました: {error}",
        "import_success": "「{name}」をインポートしました",
        "import_failed": "インポートに失敗しました: {error}",
        "import_invalid_file": "選択したファイルが正しいバックアップファイルではありません",
        "importing": "インポート中...",
        "exporting": "バックアップを作成中...",
        "add_pin_button": "ここにピンを立てる",
        "getting_location": "位置情報を取得中...",
        "location_failed": "位置情報の取得に失敗しました",
        "add_pin_title": "ピンを追加",
        "pin_location_label": "緯度: {lat}\n経度: {lon}",
        "pin_text_hint": "メモ(例: ここで休憩した)",
        "pin_photo_size_hint": "写真は最大10MBまでです",
        "photo_too_large": "写真サイズが大きすぎます(10MB以下の写真を選んでください)",
        "map_add_pin_button": "+ ピン",
        "map_pin_getting_location": "地図の中心位置を取得中...",
        "map_confirm_pin_button": "ここに追加",
        "save_video_button": "🎥",
        "video_speed_dialog_title": "動画の再生速度を選択",
        "video_capturing": "動画を作成中... {progress}%",
        "video_capture_done": "動画の書き出しが完了しました。保存先を選択してください",
        "video_save_success": "動画を保存しました:\n{path}",
        "video_save_failed": "動画の保存に失敗しました: {error}",
        "video_no_data": "走行記録がないため動画を作成できません",
        "video_cancelled": "動画の作成をキャンセルしました",
        "map_pin_drag_hint": "ピンをドラッグして位置を調整し、「ここに追加」をタップしてください",
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
        "backup_button": "Backup",
        "delete_profile_confirm": "Delete \"{name}\"?\nAll routes, photos, and pins will also be deleted",
        "yes_button": "Yes",
        "no_button": "No",
        "profile_deleted": "Deleted \"{name}\"",
        "import_button": "Import Data",
        "backup_success": "Backup saved to:\n{path}",
        "backup_failed": "Backup failed: {error}",
        "import_success": "Imported \"{name}\"",
        "import_failed": "Import failed: {error}",
        "import_invalid_file": "The selected file is not a valid backup file",
        "importing": "Importing...",
        "exporting": "Creating backup...",
        "add_pin_button": "Add Pin Here",
        "getting_location": "Getting location...",
        "location_failed": "Failed to get location",
        "add_pin_title": "Add Pin",
        "pin_location_label": "Lat: {lat}\nLon: {lon}",
        "pin_text_hint": "Memo (e.g. rested here)",
        "pin_photo_size_hint": "Photos up to 10MB",
        "photo_too_large": "Photo is too large (please choose one under 10MB)",
        "map_add_pin_button": "+ Pin",
        "map_pin_getting_location": "Getting map center...",
        "map_confirm_pin_button": "Place Here",
        "save_video_button": "🎥",
        "video_speed_dialog_title": "Select video playback speed",
        "video_capturing": "Creating video... {progress}%",
        "video_capture_done": "Video encoding complete. Please choose where to save it",
        "video_save_success": "Video saved to:\n{path}",
        "video_save_failed": "Failed to save video: {error}",
        "video_no_data": "No route data available to create a video",
        "video_cancelled": "Video creation cancelled",
        "map_pin_drag_hint": "Drag the pin to adjust its position, then tap \"Place Here\"",
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
# 長押し(ロングプレス)を検知できるコンテナウィジェット
# ---------------------------------------------------------------
class LongPressArea(ButtonBehavior, BoxLayout):
    LONG_PRESS_SECONDS = 0.6

    def __init__(self, on_long_press=None, **kwargs):
        super().__init__(**kwargs)
        self.on_long_press_callback = on_long_press
        self._long_press_event = None
        self._triggered = False

    def on_press(self):
        self._triggered = False
        self._long_press_event = Clock.schedule_once(self._fire_long_press, self.LONG_PRESS_SECONDS)

    def on_release(self):
        if self._long_press_event:
            self._long_press_event.cancel()
            self._long_press_event = None

    def _fire_long_press(self, dt):
        self._triggered = True
        if self.on_long_press_callback:
            self.on_long_press_callback()


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

    def delete_profile(self, profile_id):
        profile = next((p for p in self.profiles if p["id"] == profile_id), None)
        if not profile:
            return

        if profile.get("photo") and os.path.exists(profile["photo"]):
            try:
                os.remove(profile["photo"])
            except Exception as e:
                print(f"[DEBUG] プロファイル写真の削除に失敗: {e}")

        routes_dir = os.path.join(self.routes_dir, profile_id)
        if os.path.isdir(routes_dir):
            shutil.rmtree(routes_dir, ignore_errors=True)

        self.profiles = [p for p in self.profiles if p["id"] != profile_id]
        self._save()

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
# データ管理: ピン(地図上の写真付きマーカー)の保存・読み込み
# ---------------------------------------------------------------
class PinManager:
    MAX_EMBED_BYTES = 10 * 1024 * 1024  # 地図に埋め込む際のファイルサイズ上限(これを超えると写真は省略)

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.pins_dir = os.path.join(base_dir, "pins")
        self.photos_dir = os.path.join(base_dir, "pin_photos")
        os.makedirs(self.pins_dir, exist_ok=True)
        os.makedirs(self.photos_dir, exist_ok=True)

    def _pins_file(self, profile_id):
        return os.path.join(self.pins_dir, f"{profile_id}.json")

    def load_pins(self, profile_id):
        path = self._pins_file(profile_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_pins(self, profile_id, pins):
        with open(self._pins_file(profile_id), "w", encoding="utf-8") as f:
            json.dump(pins, f, ensure_ascii=False, indent=2)

    def _store_photo(self, pin_id, photo_source_path):
        """写真をアプリ専用フォルダにそのままコピーし、保存先のパスを返す"""
        ext = os.path.splitext(photo_source_path)[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png"):
            ext = ".jpg"
        dest_path = os.path.join(self.photos_dir, f"{pin_id}{ext}")
        try:
            with open(photo_source_path, "rb") as src, open(dest_path, "wb") as dst:
                dst.write(src.read())
            return dest_path
        except Exception as e:
            print(f"[DEBUG] 写真のコピーに失敗: {e}")
            return None

    def add_pin(self, profile_id, lat, lon, text, photo_source_path=None):
        pin_id = str(uuid.uuid4())
        stored_photo = None
        if photo_source_path and os.path.exists(photo_source_path):
            stored_photo = self._store_photo(pin_id, photo_source_path)

        pin = {
            "id": pin_id,
            "lat": lat,
            "lon": lon,
            "text": text,
            "photo": stored_photo,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        pins = self.load_pins(profile_id)
        pins.append(pin)
        self._save_pins(profile_id, pins)
        return pin

    def delete_pins_for_profile(self, profile_id):
        pins = self.load_pins(profile_id)
        for pin in pins:
            photo = pin.get("photo")
            if photo and os.path.exists(photo):
                try:
                    os.remove(photo)
                except Exception as e:
                    print(f"[DEBUG] ピン写真の削除に失敗: {e}")

        pins_file = self._pins_file(profile_id)
        if os.path.exists(pins_file):
            try:
                os.remove(pins_file)
            except Exception as e:
                print(f"[DEBUG] ピン情報ファイルの削除に失敗: {e}")

    def photo_as_data_uri(self, pin):
        photo = pin.get("photo")
        if not photo or not os.path.exists(photo):
            return None
        try:
            if os.path.getsize(photo) > self.MAX_EMBED_BYTES:
                # 大きすぎる写真は地図の読み込みが重くなるため埋め込みを省略する
                print(f"[DEBUG] 写真サイズが大きいため地図への埋め込みを省略: {photo}")
                return "TOO_LARGE"
            ext = os.path.splitext(photo)[1].lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            with open(photo, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime};base64,{encoded}"
        except Exception as e:
            print(f"[DEBUG] 写真のbase64変換に失敗: {e}")
            return None


# ---------------------------------------------------------------
# データ管理: プロファイル単位のバックアップ(エクスポート/インポート)
# ---------------------------------------------------------------
class BackupManager:
    def __init__(self, profile_manager, pin_manager):
        self.profile_manager = profile_manager
        self.pin_manager = pin_manager

    def get_export_dir(self):
        """バックアップZIPの保存先(端末のアプリ専用外部保存領域)を返す"""
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            external_dir = activity.getExternalFilesDir(None)
            if external_dir is not None:
                path = os.path.join(external_dir.getAbsolutePath(), "exports")
                os.makedirs(path, exist_ok=True)
                return path
        except Exception as e:
            print(f"[DEBUG] 外部保存領域の取得に失敗: {e}")
        # Android実機以外、または取得失敗時はアプリ内部のフォルダにフォールバック
        path = os.path.join(self.profile_manager.base_dir, "exports")
        os.makedirs(path, exist_ok=True)
        return path

    def build_zip_bytes(self, profile_id):
        """プロファイルのデータをZIP形式のバイト列として組み立てて返す"""
        import io

        profile = next(
            (p for p in self.profile_manager.profiles if p["id"] == profile_id), None
        )
        if not profile:
            raise ValueError("profile not found")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("profile.json", json.dumps(profile, ensure_ascii=False))

            if profile.get("photo") and os.path.exists(profile["photo"]):
                ext = os.path.splitext(profile["photo"])[1] or ".jpg"
                zf.write(profile["photo"], f"photo{ext}")

            routes_dir = os.path.join(self.profile_manager.routes_dir, profile_id)
            if os.path.isdir(routes_dir):
                for fname in os.listdir(routes_dir):
                    zf.write(os.path.join(routes_dir, fname), f"routes/{fname}")

            pins = self.pin_manager.load_pins(profile_id)
            zf.writestr("pins.json", json.dumps(pins, ensure_ascii=False))
            for pin in pins:
                photo = pin.get("photo")
                if photo and os.path.exists(photo):
                    zf.write(photo, f"pin_photos/{os.path.basename(photo)}")

        return buffer.getvalue(), profile["name"]

    def export_profile(self, profile_id):
        """アプリ専用の外部保存領域にZIPを保存する(フォールバック用)"""
        zip_bytes, name = self.build_zip_bytes(profile_id)
        safe_name = "".join(c for c in name if c.isalnum()) or "profile"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = self.get_export_dir()
        dest_path = os.path.join(dest_dir, f"{safe_name}_{timestamp}.biketracker.zip")
        with open(dest_path, "wb") as f:
            f.write(zip_bytes)
        return dest_path

    def import_profile(self, zip_path):
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if "profile.json" not in names:
                raise ValueError("invalid backup file")

            profile_data = json.loads(zf.read("profile.json").decode("utf-8"))
            new_id = str(uuid.uuid4())
            new_name = profile_data.get("name", "Imported")

            new_photo = None
            for name in names:
                if name.startswith("photo."):
                    ext = os.path.splitext(name)[1]
                    dest = os.path.join(self.profile_manager.photos_dir, new_id + ext)
                    with zf.open(name) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    new_photo = dest

            new_profile = {"id": new_id, "name": new_name, "photo": new_photo}
            self.profile_manager.profiles.append(new_profile)
            self.profile_manager._save()

            routes_dest_dir = os.path.join(self.profile_manager.routes_dir, new_id)
            os.makedirs(routes_dest_dir, exist_ok=True)
            for name in names:
                if name.startswith("routes/") and not name.endswith("/"):
                    fname = os.path.basename(name)
                    with zf.open(name) as src, open(
                        os.path.join(routes_dest_dir, fname), "wb"
                    ) as dst:
                        dst.write(src.read())

            pins_data = []
            if "pins.json" in names:
                try:
                    pins_data = json.loads(zf.read("pins.json").decode("utf-8"))
                except Exception:
                    pins_data = []

            new_pins = []
            for pin in pins_data:
                new_pin_id = str(uuid.uuid4())
                new_pin = dict(pin)
                new_pin["id"] = new_pin_id
                old_photo = pin.get("photo")
                new_pin["photo"] = None
                if old_photo:
                    old_entry = f"pin_photos/{os.path.basename(old_photo)}"
                    if old_entry in names:
                        ext = os.path.splitext(old_photo)[1] or ".jpg"
                        dest = os.path.join(self.pin_manager.photos_dir, new_pin_id + ext)
                        with zf.open(old_entry) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
                        new_pin["photo"] = dest
                new_pins.append(new_pin)
            self.pin_manager._save_pins(new_id, new_pins)

            return new_profile


class LongPressImage(ButtonBehavior, KivyImage):
    """一定時間押し続けると on_long_press を呼ぶ画像ウィジェット"""

    def __init__(self, on_long_press=None, **kwargs):
        super().__init__(**kwargs)
        self._on_long_press = on_long_press
        self._long_press_event = None

    def on_press(self):
        self._long_press_event = Clock.schedule_once(self._fire_long_press, 0.6)

    def on_release(self):
        if self._long_press_event:
            self._long_press_event.cancel()
            self._long_press_event = None

    def _fire_long_press(self, dt):
        self._long_press_event = None
        if self._on_long_press:
            self._on_long_press()


class LongPressLabel(ButtonBehavior, Label):
    """写真が無いプロファイル用: 長押しを検出するラベル"""

    def __init__(self, on_long_press=None, **kwargs):
        super().__init__(**kwargs)
        self._on_long_press = on_long_press
        self._long_press_event = None

    def on_press(self):
        self._long_press_event = Clock.schedule_once(self._fire_long_press, 0.6)

    def on_release(self):
        if self._long_press_event:
            self._long_press_event.cancel()
            self._long_press_event = None

    def _fire_long_press(self, dt):
        self._long_press_event = None
        if self._on_long_press:
            self._on_long_press()


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

        self.status_label = Label(text="", font_name="NotoSansJP", font_size="13sp", size_hint=(1, 0.06))
        root.add_widget(self.status_label)

        bottom_buttons = BoxLayout(orientation="horizontal", size_hint=(1, 0.12), spacing=10)
        add_button = Button(
            text=app.tr("add_profile_button"),
            font_name="NotoSansJP",
            font_size="16sp",
            background_color=(0.2, 0.6, 1, 1),
        )
        add_button.bind(on_press=self.go_to_add_profile)
        bottom_buttons.add_widget(add_button)

        import_button = Button(
            text=app.tr("import_button"),
            font_name="NotoSansJP",
            font_size="16sp",
        )
        import_button.bind(on_press=self.import_data)
        bottom_buttons.add_widget(import_button)
        root.add_widget(bottom_buttons)

        self.add_widget(root)

    def go_to_settings(self, instance):
        self.manager.current = "settings"

    def import_data(self, instance):
        app = App.get_running_app()
        try:
            from jnius import autoclass
            from android import activity

            Intent = autoclass("android.content.Intent")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            mactivity = PythonActivity.mActivity

            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("application/zip")

            request_code = 9002

            def on_result(request_code_recv, result_code, data):
                if request_code_recv != request_code:
                    return
                activity.unbind(on_activity_result=on_result)
                Activity = autoclass("android.app.Activity")
                if result_code != Activity.RESULT_OK or data is None:
                    print("[DEBUG] インポート用ファイル選択がキャンセルされました")
                    return
                try:
                    uri = data.getData()
                    print(f"[DEBUG] インポート用に選択されたURI: {uri.toString()}")
                    resolver = mactivity.getContentResolver()

                    # 永続的な読み取り権限を明示的に取得しておく(クラウドプロバイダ対策)
                    try:
                        resolver.takePersistableUriPermission(
                            uri, Intent.FLAG_GRANT_READ_URI_PERMISSION
                        )
                        print("[DEBUG] 永続読み取り権限の取得に成功")
                    except Exception as perm_e:
                        print(f"[DEBUG] 永続読み取り権限の取得に失敗(続行): {perm_e}")

                    ByteArrayOutputStream = autoclass("java.io.ByteArrayOutputStream")
                    input_stream = resolver.openInputStream(uri)
                    print(f"[DEBUG] input_stream: {input_stream}")
                    try:
                        available = input_stream.available()
                        print(f"[DEBUG] available()の結果: {available}")
                    except Exception as avail_e:
                        print(f"[DEBUG] available()呼び出しに失敗: {avail_e}")

                    output_stream = ByteArrayOutputStream()
                    buf = bytearray(8192)
                    n = input_stream.read(buf)
                    print(f"[DEBUG] 最初のread()の戻り値: {n}")
                    while n != -1:
                        output_stream.write(buf, 0, n)
                        n = input_stream.read(buf)
                    input_stream.close()
                    zip_bytes = bytes(output_stream.toByteArray())
                    print(f"[DEBUG] 読み込んだデータサイズ: {len(zip_bytes)} bytes")
                    Clock.schedule_once(lambda dt: self._do_import(zip_bytes))
                except Exception as e:
                    print(f"[DEBUG] ファイル内容の読み込みに失敗: {e}")
                    error_message = app.tr("import_failed", error=e)
                    Clock.schedule_once(
                        lambda dt: setattr(
                            self.status_label, "text", error_message
                        )
                    )

            activity.bind(on_activity_result=on_result)
            mactivity.startActivityForResult(intent, request_code)
        except Exception as e:
            print(f"[DEBUG] ファイル選択ダイアログの表示に失敗: {e}")
            self.status_label.text = app.tr("import_failed", error=e)

    def _do_import(self, zip_bytes):
        app = App.get_running_app()
        print(f"[DEBUG] インポート開始: {len(zip_bytes)} bytes")
        try:
            import io

            imported = app.backup_manager.import_profile(io.BytesIO(zip_bytes))
            print(f"[DEBUG] インポート成功: {imported['name']}")
            message = app.tr("import_success", name=imported["name"])
        except (KeyError, ValueError, zipfile.BadZipFile) as e:
            print(f"[DEBUG] インポート失敗(不正なファイル): {e}")
            message = app.tr("import_invalid_file")
        except Exception as e:
            print(f"[DEBUG] インポートに失敗: {e}")
            message = app.tr("import_failed", error=e)

        # 先に画面を再構築してから、新しく作られたラベルにメッセージを設定する
        # (逆順にすると、再構築時に作られる空のラベルでメッセージが消えてしまう)
        self.build_ui()
        self.status_label.text = message

    def _confirm_delete_profile(self, profile):
        app = App.get_running_app()

        content = BoxLayout(orientation="vertical", spacing=15, padding=15)
        message_label = Label(
            text=app.tr("delete_profile_confirm", name=profile["name"]),
            font_name="NotoSansJP",
            font_size="15sp",
            halign="center",
        )
        message_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        content.add_widget(message_label)

        button_row = BoxLayout(orientation="horizontal", spacing=10, size_hint=(1, 0.4))
        content.add_widget(button_row)

        popup = Popup(
            title="",
            content=content,
            size_hint=(0.85, 0.4),
            auto_dismiss=True,
        )

        def do_delete(instance):
            popup.dismiss()
            app.profile_manager.delete_profile(profile["id"])
            app.pin_manager.delete_pins_for_profile(profile["id"])
            self.build_ui()
            self.status_label.text = app.tr("profile_deleted", name=profile["name"])

        yes_button = Button(text=app.tr("yes_button"), font_name="NotoSansJP")
        yes_button.bind(on_press=do_delete)
        button_row.add_widget(yes_button)

        no_button = Button(text=app.tr("no_button"), font_name="NotoSansJP")
        no_button.bind(on_press=lambda instance: popup.dismiss())
        button_row.add_widget(no_button)

        popup.open()

    def export_profile(self, profile):
        app = App.get_running_app()
        self.status_label.text = app.tr("exporting")

        try:
            zip_bytes, name = app.backup_manager.build_zip_bytes(profile["id"])
        except Exception as e:
            print(f"[DEBUG] バックアップの作成に失敗: {e}")
            self.status_label.text = app.tr("backup_failed", error=e)
            return

        safe_name = "".join(c for c in name if c.isalnum()) or "profile"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}.biketracker.zip"

        try:
            from jnius import autoclass
            from android import activity

            Intent = autoclass("android.content.Intent")
            JString = autoclass("java.lang.String")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            mactivity = PythonActivity.mActivity

            intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("application/zip")
            intent.putExtra(Intent.EXTRA_TITLE, JString(filename))

            request_code = 9001

            def on_result(request_code_recv, result_code, data):
                if request_code_recv != request_code:
                    return
                activity.unbind(on_activity_result=on_result)
                Activity = autoclass("android.app.Activity")
                if result_code != Activity.RESULT_OK or data is None:
                    Clock.schedule_once(
                        lambda dt: setattr(self.status_label, "text", "")
                    )
                    return
                try:
                    uri = data.getData()
                    resolver = mactivity.getContentResolver()
                    out_stream = resolver.openOutputStream(uri)
                    print(f"[DEBUG] 書き込むデータサイズ: {len(zip_bytes)} bytes")
                    out_stream.write(zip_bytes, 0, len(zip_bytes))
                    out_stream.flush()
                    out_stream.close()
                    display_path = uri.toString()
                    Clock.schedule_once(
                        lambda dt: setattr(
                            self.status_label,
                            "text",
                            app.tr("backup_success", path=display_path),
                        )
                    )
                except Exception as e:
                    print(f"[DEBUG] 保存先への書き込みに失敗: {e}")
                    error_message = app.tr("backup_failed", error=e)
                    Clock.schedule_once(
                        lambda dt: setattr(
                            self.status_label, "text", error_message
                        )
                    )

            activity.bind(on_activity_result=on_result)
            mactivity.startActivityForResult(intent, request_code)
        except Exception as e:
            print(f"[DEBUG] 保存先選択ダイアログの表示に失敗: {e}")
            # SAFが使えない環境向けのフォールバック: アプリ専用領域に保存する
            try:
                path = app.backup_manager.export_profile(profile["id"])
                self.status_label.text = app.tr("backup_success", path=path)
            except Exception as e2:
                self.status_label.text = app.tr("backup_failed", error=e2)

    def _build_profile_card(self, profile):
        app = App.get_running_app()
        card = BoxLayout(orientation="vertical", size_hint_y=None, height=230)

        if profile.get("photo") and os.path.exists(profile["photo"]):
            img = LongPressImage(
                source=profile["photo"],
                size_hint=(1, 0.65),
                on_long_press=lambda p=profile: self._confirm_delete_profile(p),
            )
        else:
            img = LongPressLabel(
                text=app.tr("no_photo"),
                font_name="NotoSansJP",
                size_hint=(1, 0.65),
                on_long_press=lambda p=profile: self._confirm_delete_profile(p),
            )
        card.add_widget(img)

        button_row = BoxLayout(orientation="horizontal", size_hint=(1, 0.35), spacing=2)

        name_button = Button(
            text=profile["name"],
            font_name="NotoSansJP",
            font_size="13sp",
        )
        name_button.bind(
            on_press=lambda instance, p=profile: self.go_to_tracker(p)
        )
        button_row.add_widget(name_button)

        map_button = Button(
            text=app.tr("map_button"),
            font_name="NotoSansJP",
            font_size="12sp",
        )
        map_button.bind(
            on_press=lambda instance, p=profile: self.go_to_route_list(p)
        )
        button_row.add_widget(map_button)

        backup_button = Button(
            text=app.tr("backup_button"),
            font_name="NotoSansJP",
            font_size="11sp",
        )
        backup_button.bind(
            on_press=lambda instance, p=profile: self.export_profile(p)
        )
        button_row.add_widget(backup_button)

        card.add_widget(button_row)

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
            input_type="text",
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
# 画面: ピンを追加(緯度経度はあらかじめapp.pending_pin_locationに設定しておく)
# ---------------------------------------------------------------
class AddPinScreen(Screen):
    def on_pre_enter(self, *args):
        self.selected_photo_path = None
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        app = App.get_running_app()
        root = BoxLayout(orientation="vertical", padding=20, spacing=15)

        title = Label(
            text=app.tr("add_pin_title"),
            font_size="22sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.1),
        )
        root.add_widget(title)

        lat, lon = getattr(app, "pending_pin_location", (None, None))
        location_label = Label(
            text=app.tr("pin_location_label", lat=lat, lon=lon),
            font_name="NotoSansJP",
            font_size="14sp",
            size_hint=(1, 0.12),
        )
        root.add_widget(location_label)

        self.text_input = TextInput(
            hint_text=app.tr("pin_text_hint"),
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.15),
            multiline=True,
            input_type="text",
        )
        root.add_widget(self.text_input)

        self.preview_image = KivyImage(size_hint=(1, 0.33))
        root.add_widget(self.preview_image)

        gallery_button = Button(
            text=app.tr("gallery_button"),
            font_name="NotoSansJP",
            font_size="16sp",
            size_hint=(1, 0.1),
        )
        gallery_button.bind(on_press=self.pick_from_gallery)
        root.add_widget(gallery_button)

        size_hint_label = Label(
            text=app.tr("pin_photo_size_hint"),
            font_name="NotoSansJP",
            font_size="12sp",
            color=(0.6, 0.6, 0.6, 1),
            size_hint=(1, 0.05),
        )
        root.add_widget(size_hint_label)

        self.status_label = Label(text="", font_name="NotoSansJP", size_hint=(1, 0.08))
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
        save_button.bind(on_press=self.save_pin)
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
            filechooser.open_file(
                on_selection=self._on_gallery_selected,
                filters=[["画像", "*.jpg", "*.jpeg", "*.png"]],
            )
        except NotImplementedError:
            self.status_label.text = app.tr("gallery_not_supported")
        except Exception as e:
            self.status_label.text = app.tr("gallery_error", error=e)

    def _on_gallery_selected(self, selection):
        app = App.get_running_app()
        if selection and selection[0]:
            Clock.schedule_once(lambda dt: self._set_preview(selection[0]))
        else:
            Clock.schedule_once(
                lambda dt: setattr(self.status_label, "text", app.tr("photo_not_selected"))
            )

    def _set_preview(self, path):
        app = App.get_running_app()
        if not path or not os.path.exists(path):
            self.status_label.text = app.tr("photo_get_failed")
            return
        try:
            self.selected_photo_path = path
            self.preview_image.source = path
            self.preview_image.reload()
            if os.path.getsize(path) > PinManager.MAX_EMBED_BYTES:
                self.status_label.text = app.tr("photo_too_large")
            else:
                self.status_label.text = app.tr("photo_selected")
        except Exception as e:
            self.status_label.text = app.tr("preview_error", error=e)

    def save_pin(self, instance):
        app = App.get_running_app()
        profile = app.selected_profile
        lat, lon = getattr(app, "pending_pin_location", (None, None))
        if not profile or lat is None or lon is None:
            self.status_label.text = app.tr("location_failed")
            return

        app.pin_manager.add_pin(
            profile["id"], lat, lon, self.text_input.text.strip(), self.selected_photo_path
        )
        self._return_to_source()

    def cancel(self, instance):
        self._return_to_source()

    def _return_to_source(self):
        app = App.get_running_app()
        source = getattr(app, "pending_pin_source", "map")
        self.manager.current = "tracker" if source == "tracker" else "map"


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
            size_hint=(1, 0.2),
        )
        root.add_widget(self.status_label)

        self.start_button = Button(
            text=app.tr("start_button"),
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.17),
            background_color=(0.2, 0.6, 1, 1),
        )
        self.start_button.bind(on_press=self.start_tracking)
        root.add_widget(self.start_button)

        self.stop_button = Button(
            text=app.tr("stop_button"),
            font_size="24sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.17),
            background_color=(1, 0.3, 0.3, 1),
        )
        self.stop_button.bind(on_press=self.stop_tracking)
        root.add_widget(self.stop_button)

        self.add_pin_button = Button(
            text=app.tr("add_pin_button"),
            font_size="18sp",
            font_name="NotoSansJP",
            size_hint=(1, 0.15),
            background_color=(0.9, 0.6, 0.1, 1),
        )
        self.add_pin_button.bind(on_press=self.add_pin_here)
        root.add_widget(self.add_pin_button)

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

    def add_pin_here(self, instance):
        app = App.get_running_app()
        if not app.selected_profile:
            self.status_label.text = app.tr("no_profile_selected")
            return
        if not ANDROID_JNIUS_AVAILABLE:
            self.status_label.text = app.tr("location_failed")
            return

        self.status_label.text = app.tr("getting_location")
        try:
            self._start_one_shot_location()
        except Exception as e:
            print(f"[DEBUG] ピン用GPS取得に失敗: {e}")
            self.status_label.text = app.tr("location_failed")

    def _start_one_shot_location(self):
        """
        plyerのgps機能はAndroid 12以降のバッチ形式コールバックに対応しておらず、
        NotImplementedErrorで位置情報を受け取れないため、独自のLocationListenerで
        (service.pyと同様の方式)一度だけ位置情報を取得する。
        """
        from jnius import autoclass, cast, PythonJavaClass, java_method

        Context = autoclass("android.content.Context")
        LocationManager = autoclass("android.location.LocationManager")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity

        location_manager = cast(
            "android.location.LocationManager",
            activity.getSystemService(Context.LOCATION_SERVICE),
        )

        screen = self

        class OneShotLocationListener(PythonJavaClass):
            __javainterfaces__ = ["android/location/LocationListener"]
            __javacontext__ = "app"

            @java_method("(Landroid/location/Location;)V", name="onLocationChanged")
            def onLocationChanged_single(self, location):
                screen._handle_pin_location(location.getLatitude(), location.getLongitude())

            @java_method("(Ljava/util/List;)V", name="onLocationChanged")
            def onLocationChanged_batch(self, locations):
                if locations.size() > 0:
                    loc = locations.get(locations.size() - 1)
                    screen._handle_pin_location(loc.getLatitude(), loc.getLongitude())

            @java_method("(Ljava/lang/String;)V")
            def onProviderDisabled(self, provider):
                pass

            @java_method("(Ljava/lang/String;)V")
            def onProviderEnabled(self, provider):
                pass

            @java_method("(Ljava/lang/String;ILandroid/os/Bundle;)V")
            def onStatusChanged(self, provider, status, extras):
                pass

        self._pin_location_listener = OneShotLocationListener()
        location_manager.requestLocationUpdates(
            LocationManager.GPS_PROVIDER, 1000, 0, self._pin_location_listener, activity.getMainLooper()
        )

    def _handle_pin_location(self, lat, lon):
        # 1回受け取ったら以降の更新は不要なので停止する
        try:
            from jnius import autoclass, cast

            Context = autoclass("android.content.Context")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            location_manager = cast(
                "android.location.LocationManager",
                activity.getSystemService(Context.LOCATION_SERVICE),
            )
            location_manager.removeUpdates(self._pin_location_listener)
        except Exception as e:
            print(f"[DEBUG] 位置情報リスナーの停止に失敗: {e}")

        def _go_to_add_pin(dt):
            app = App.get_running_app()
            app.pending_pin_location = (lat, lon)
            app.pending_pin_source = "tracker"
            self.manager.current = "add_pin"

        Clock.schedule_once(_go_to_add_pin)

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
        self.pin_button_native = None
        self.video_button_native = None
        self.video_progress_native = None
        self.video_cancel_button_native = None
        self.pin_mode = False
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

    def _build_html(self, segments_with_time, info_text="", total_distance_km=0.0, pins=None):
        """
        segments_with_time: [[(time_label, lat, lon), ...], ...] (日付ごとのリストのリスト)
        pins: [{"lat":.., "lon":.., "text":.., "photo_data_uri": ".." or None}, ...]
        """
        app = App.get_running_app()
        pins = pins or []
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

        # ピンをJavaScriptオブジェクトの配列として埋め込む(json.dumpsでエスケープを安全に行う)
        pins_data = [
            {
                "lat": p["lat"],
                "lon": p["lon"],
                "text": p.get("text") or "",
                "photo": p.get("photo_data_uri"),
            }
            for p in pins
        ]
        pins_js = json.dumps(pins_data, ensure_ascii=False)

        # 再生機能用: 日付をまたいで時系列順に並べたフラットな座標リスト(累積距離付き)
        playback_points = []
        cumulative_km = 0.0
        prev = None
        for seg in segments_with_time:
            for t, lat, lon in seg:
                if prev is not None:
                    cumulative_km += haversine_km(prev[0], prev[1], lat, lon)
                playback_points.append(
                    {"lat": lat, "lon": lon, "time": t, "distance_km": round(cumulative_km, 2)}
                )
                prev = (lat, lon)
        playback_js = json.dumps(playback_points, ensure_ascii=False)

        # 動画キャプチャ機能でPython側からも使うため保持しておく
        self._video_playback_points = playback_points
        self._video_pins = pins_data

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
    .pin-popup img {{ max-width: 200px; max-height: 200px; display: block; margin-bottom: 6px; }}
    .pin-popup p {{ margin: 0; white-space: pre-wrap; }}
    #playback-info {{
      position: fixed; top: 40px; left: 0; right: 0; z-index: 1000;
      display: none; pointer-events: none;
    }}
    #playback-time {{
      position: absolute; top: 0; left: 8px;
      background: rgba(0,0,0,0.6); color: white; padding: 4px 10px;
      border-radius: 4px; font-size: 14px;
    }}
    #playback-distance {{
      position: absolute; top: 0; right: 8px;
      background: rgba(0,0,0,0.6); color: white; padding: 4px 10px;
      border-radius: 4px; font-size: 14px;
    }}
    #playback-controls {{
      position: fixed; bottom: 100px; left: 50%; transform: translateX(-50%);
      z-index: 1000; background: rgba(0,0,0,0.7); border-radius: 8px;
      padding: 6px; display: flex; gap: 4px; align-items: center;
      max-width: 94vw; overflow-x: auto;
    }}
    #playback-controls button {{
      background: #1976D2; color: white; border: none; border-radius: 4px;
      padding: 7px 9px; font-size: 13px; flex-shrink: 0;
    }}
    #playback-controls button.active {{ background: #F57C00; }}
    #pin-closeup {{
      position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000;
      display: none; background: rgba(0,0,0,0.85);
      flex-direction: column; align-items: center; justify-content: center;
    }}
    #pin-closeup img {{ max-width: 90%; max-height: 65%; border-radius: 8px; }}
    #pin-closeup p {{
      color: white; font-size: 18px; margin-top: 16px; padding: 0 20px;
      text-align: center; white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <div id="banner">{banner}</div>
  <div id="map"></div>
  <div id="playback-info">
    <div id="playback-time"></div>
    <div id="playback-distance"></div>
  </div>
  <div id="pin-closeup"><img id="pin-closeup-img"><p id="pin-closeup-text"></p></div>
  <div id="playback-controls"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    var segments = {segments_js};
    var pins = {pins_js};
    var map = L.map('map', {{preferCanvas: true}}).setView({center_js}, 15);
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

    // ピン(写真付きマーカー)を描画する
    var pinIcon = L.icon({{
      iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      iconSize: [30, 46], iconAnchor: [15, 46]
    }});
    pins.forEach(function(pin) {{
      var marker = L.marker([pin.lat, pin.lon], {{icon: pinIcon}}).addTo(map);
      var html = '<div class="pin-popup">';
      if (pin.photo === 'TOO_LARGE') {{
        html += '<p style="color:#888;">(写真サイズが大きいため表示できません)</p>';
      }} else if (pin.photo) {{
        html += '<img src="' + pin.photo + '">';
      }}
      html += '<p>' + (pin.text || '') + '</p></div>';
      marker.bindPopup(html);
      allBounds.push(L.latLngBounds([[pin.lat, pin.lon]]));
    }});

    if (allBounds.length > 0) {{
      var combined = allBounds[0];
      for (var i = 1; i < allBounds.length; i++) {{
        combined = combined.extend(allBounds[i]);
      }}
      map.fitBounds(combined);
    }}

    // ---------------- 再生機能 ----------------
    var playbackPoints = {playback_js};
    var playbackSpeed = 6;
    var playbackTimer = null;
    var playbackIndex = 0;
    var playbackMarker = null;
    var shownPins = {{}};  // 一度クローズアップ表示したピンは再度表示しない(id代わりにインデックス)
    var basestepMs = 3000; // 実際の記録間隔の目安(約3秒)

    var bikeIcon = L.divIcon({{
      html: '<div style="font-size:34px; line-height:34px;">🏍️</div>',
      className: '', iconSize: [34, 34], iconAnchor: [17, 17]
    }});

    function nearestPinWithin(lat, lon, meters) {{
      for (var i = 0; i < pins.length; i++) {{
        if (shownPins[i]) continue;
        var d = map.distance([lat, lon], [pins[i].lat, pins[i].lon]);
        if (d <= meters) return i;
      }}
      return -1;
    }}

    function showPinCloseup(pinIndex, callback) {{
      var pin = pins[pinIndex];
      shownPins[pinIndex] = true;
      var closeup = document.getElementById('pin-closeup');
      var img = document.getElementById('pin-closeup-img');
      var text = document.getElementById('pin-closeup-text');
      if (pin.photo && pin.photo !== 'TOO_LARGE') {{
        img.src = pin.photo;
        img.style.display = 'block';
      }} else {{
        img.style.display = 'none';
      }}
      text.textContent = pin.text || '';
      closeup.style.display = 'flex';
      setTimeout(function() {{
        closeup.style.display = 'none';
        callback();
      }}, 2000);
    }}

    function playbackStep() {{
      if (playbackIndex >= playbackPoints.length) {{
        stopPlayback();
        return;
      }}
      var p = playbackPoints[playbackIndex];
      var latlng = [p.lat, p.lon];

      if (!playbackMarker) {{
        playbackMarker = L.marker(latlng, {{icon: bikeIcon}}).addTo(map);
      }} else {{
        playbackMarker.setLatLng(latlng);
      }}
      map.panTo(latlng, {{animate: true, duration: 0.3}});

      document.getElementById('playback-time').textContent = p.time;
      document.getElementById('playback-distance').textContent = p.distance_km.toFixed(1) + ' km';

      var nearPin = nearestPinWithin(p.lat, p.lon, 30);
      playbackIndex++;

      if (nearPin >= 0) {{
        clearTimeout(playbackTimer);
        showPinCloseup(nearPin, function() {{
          if (playbackIndex < playbackPoints.length) {{
            playbackTimer = setTimeout(playbackStep, basestepMs / playbackSpeed);
          }} else {{
            stopPlayback();
          }}
        }});
      }} else {{
        playbackTimer = setTimeout(playbackStep, basestepMs / playbackSpeed);
      }}
    }}

    function startPlayback() {{
      if (playbackPoints.length === 0) return;
      playbackIndex = 0;
      shownPins = {{}};
      if (playbackMarker) {{ map.removeLayer(playbackMarker); playbackMarker = null; }}
      document.getElementById('playback-info').style.display = 'block';
      playbackStep();
    }}

    function stopPlayback() {{
      clearTimeout(playbackTimer);
      playbackTimer = null;
      document.getElementById('playback-info').style.display = 'none';
      if (playbackMarker) {{ map.removeLayer(playbackMarker); playbackMarker = null; }}
    }}

    // ---------------- 動画キャプチャ用(コマ撮り、アニメーションなし) ----------------
    window.frameReady = true;

    window.setPlaybackFrame = function(index, closeupPinIndex) {{
      if (index < 0 || index >= playbackPoints.length) return;
      window.frameReady = false;
      var p = playbackPoints[index];
      var latlng = [p.lat, p.lon];
      if (!playbackMarker) {{
        playbackMarker = L.marker(latlng, {{icon: bikeIcon}}).addTo(map);
      }} else {{
        playbackMarker.setLatLng(latlng);
      }}
      map.setView(latlng, map.getZoom(), {{animate: false}});
      document.getElementById('playback-info').style.display = 'block';
      document.getElementById('playback-time').textContent = p.time;
      document.getElementById('playback-distance').textContent = p.distance_km.toFixed(1) + ' km';

      var closeup = document.getElementById('pin-closeup');
      if (closeupPinIndex >= 0 && closeupPinIndex < pins.length) {{
        var pin = pins[closeupPinIndex];
        var img = document.getElementById('pin-closeup-img');
        var text = document.getElementById('pin-closeup-text');
        if (pin.photo && pin.photo !== 'TOO_LARGE') {{
          img.src = pin.photo;
          img.style.display = 'block';
        }} else {{
          img.style.display = 'none';
        }}
        text.textContent = pin.text || '';
        closeup.style.display = 'flex';
      }} else {{
        closeup.style.display = 'none';
      }}

      // 地図の再投影・再描画が完了してから撮影できるよう、
      // 二重のrequestAnimationFrameで1回分の描画サイクルを待つ
      requestAnimationFrame(function() {{
        requestAnimationFrame(function() {{
          window.frameReady = true;
        }});
      }});
    }};

    window.clearPlaybackFrame = function() {{
      if (playbackMarker) {{ map.removeLayer(playbackMarker); playbackMarker = null; }}
      document.getElementById('playback-info').style.display = 'none';
      document.getElementById('pin-closeup').style.display = 'none';
      window.frameReady = true;
    }};

    // 再生コントロールのボタンを組み立てる
    var controls = document.getElementById('playback-controls');
    if (playbackPoints.length > 0) {{
      var playBtn = document.createElement('button');
      playBtn.textContent = '▶ 再生';
      playBtn.onclick = function() {{ startPlayback(); }};
      controls.appendChild(playBtn);

      var stopBtn = document.createElement('button');
      stopBtn.textContent = '■ 停止';
      stopBtn.onclick = function() {{ stopPlayback(); }};
      controls.appendChild(stopBtn);

      [1, 6, 20, 40, 100].forEach(function(speed) {{
        var btn = document.createElement('button');
        btn.textContent = speed + 'x';
        if (speed === playbackSpeed) btn.classList.add('active');
        btn.onclick = function() {{
          playbackSpeed = speed;
          Array.from(controls.querySelectorAll('button')).forEach(function(b) {{
            b.classList.remove('active');
          }});
          btn.classList.add('active');
        }};
        controls.appendChild(btn);
      }});
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

        # ピン(写真付きマーカー)を読み込み、写真はbase64に変換してHTMLに埋め込む
        raw_pins = app.pin_manager.load_pins(profile["id"])
        pins = []
        for p in raw_pins:
            pins.append(
                {
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "text": p.get("text", ""),
                    "photo_data_uri": app.pin_manager.photo_as_data_uri(p),
                }
            )

        html = self._build_html(segments_local_time, info_text, total_km, pins)

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
                    print("[DEBUG] ボタンのonClickが呼ばれました")
                    self.callback()

            class MapCenterCallback(PythonJavaClass):
                __javainterfaces__ = ["android/webkit/ValueCallback"]
                __javacontext__ = "app"

                def __init__(self, callback):
                    super().__init__()
                    self.callback = callback

                @java_method("(Ljava/lang/Object;)V")
                def onReceiveValue(self, value):
                    self.callback(str(value))

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

                JString = autoclass("java.lang.String")

                back_button = AndroidButton(activity)
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

                back_params = FrameLayoutParams(dp(120), dp(56))
                back_params.gravity = Gravity.BOTTOM | Gravity.LEFT
                back_params.setMargins(dp(16), 0, 0, dp(24))
                activity.addContentView(back_button, back_params)
                back_button.bringToFront()
                self.back_button_native = back_button

                # 地図の上に重ねて表示する「＋ピン」ボタン(右下)
                pin_button = AndroidButton(activity)
                pin_button.setText(JString(app.tr("map_add_pin_button")))
                pin_button.setTextColor(Color.WHITE)
                pin_button.setBackgroundColor(Color.parseColor("#CC9C6B0A"))
                pin_button.setAllCaps(False)
                pin_button.setClickable(True)
                pin_button.setFocusable(True)
                pin_button.setElevation(dp(8))

                self._pin_click_listener = OnClickListener(
                    lambda: self._toggle_pin_mode()
                )
                pin_button.setOnClickListener(self._pin_click_listener)

                pin_params = FrameLayoutParams(dp(140), dp(56))
                pin_params.gravity = Gravity.BOTTOM | Gravity.RIGHT
                pin_params.setMargins(0, 0, dp(16), dp(24))
                activity.addContentView(pin_button, pin_params)
                pin_button.bringToFront()
                self.pin_button_native = pin_button
                self._map_center_callback_class = MapCenterCallback

                # 地図の右端(縦中央)に配置する「動画として保存」ボタン
                video_button = AndroidButton(activity)
                video_button.setText(JString(app.tr("save_video_button")))
                video_button.setTextColor(Color.WHITE)
                video_button.setBackgroundColor(Color.parseColor("#CC2E7D32"))
                video_button.setAllCaps(False)
                video_button.setClickable(True)
                video_button.setFocusable(True)
                video_button.setElevation(dp(8))
                video_button.setTextSize(11)
                video_button.setPadding(dp(4), dp(4), dp(4), dp(4))

                self._video_click_listener = OnClickListener(
                    lambda: Clock.schedule_once(lambda dt: self._show_video_speed_dialog())
                )
                video_button.setOnClickListener(self._video_click_listener)

                video_params = FrameLayoutParams(dp(64), dp(64))
                video_params.gravity = Gravity.RIGHT | Gravity.CENTER_VERTICAL
                video_params.setMargins(0, 0, dp(8), 0)
                activity.addContentView(video_button, video_params)
                video_button.bringToFront()
                self.video_button_native = video_button

            _create_webview()
        except Exception as e:
            print(f"[DEBUG] WebView表示に失敗: {e}")
            self.info_label.text = f"地図の表示に失敗しました: {e}\n(Android実機で確認してください)"

    def _toggle_pin_mode(self):
        app = App.get_running_app()
        if self.webview is None:
            return
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            JString = autoclass("java.lang.String")

            if not self.pin_mode:
                # 地図の中心にドラッグ可能な仮ピンを表示する
                js = (
                    "if (window.pendingMarker) { map.removeLayer(window.pendingMarker); } "
                    "window.pendingMarker = L.marker(map.getCenter(), "
                    "{draggable: true}).addTo(map); null;"
                )

                @run_on_ui_thread
                def _inject():
                    self.webview.evaluateJavascript(JString(js), None)
                    if self.pin_button_native is not None:
                        self.pin_button_native.setText(JString(app.tr("map_confirm_pin_button")))

                _inject()
                self.pin_mode = True
                Clock.schedule_once(
                    lambda dt: setattr(self.info_label, "text", app.tr("map_pin_drag_hint"))
                )
            else:
                callback = self._map_center_callback_class(self._on_pin_position_received)

                @run_on_ui_thread
                def _eval():
                    self.webview.evaluateJavascript(
                        JString("JSON.stringify(window.pendingMarker.getLatLng())"), callback
                    )
                    self._pending_map_center_callback = callback  # GC対策で参照を保持

                _eval()
        except Exception as e:
            print(f"[DEBUG] ピン配置モードの切り替えに失敗: {e}")

    def _on_pin_position_received(self, value_json):
        # value_jsonの例: "\"{\\\"lat\\\":35.68,\\\"lng\\\":139.76}\"" のように二重にエスケープされている
        try:
            unescaped = json.loads(value_json)
            center = json.loads(unescaped)
            lat, lon = center["lat"], center["lng"]
        except Exception as e:
            print(f"[DEBUG] ピン位置のパースに失敗: {e}, value={value_json!r}")
            return

        def _cleanup_and_go(dt):
            app = App.get_running_app()
            try:
                from jnius import autoclass
                from android.runnable import run_on_ui_thread

                JString = autoclass("java.lang.String")
                cleanup_js = (
                    "if (window.pendingMarker) { map.removeLayer(window.pendingMarker); "
                    "window.pendingMarker = null; }"
                )

                @run_on_ui_thread
                def _cleanup():
                    if self.webview is not None:
                        self.webview.evaluateJavascript(JString(cleanup_js), None)
                    if self.pin_button_native is not None:
                        self.pin_button_native.setText(JString(app.tr("map_add_pin_button")))

                _cleanup()
            except Exception as e:
                print(f"[DEBUG] 仮ピンの後片付けに失敗: {e}")

            self.pin_mode = False
            app.pending_pin_location = (lat, lon)
            app.pending_pin_source = "map"
            self.manager.current = "add_pin"

        Clock.schedule_once(_cleanup_and_go)

    # ---------------------------------------------------------------
    # 動画として保存する機能
    # ---------------------------------------------------------------
    def _set_banner_text(self, text):
        """WebView内のバナー表示を書き換える(進捗表示に使う)"""
        if self.webview is None:
            return
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            JString = autoclass("java.lang.String")
            escaped = json.dumps(text)
            js = f"document.getElementById('banner').innerText = {escaped};"

            @run_on_ui_thread
            def _apply():
                self.webview.evaluateJavascript(JString(js), None)

            _apply()
        except Exception as e:
            print(f"[DEBUG] バナー表示の更新に失敗: {e}")

    def _set_map_controls_visible(self, visible):
        """ネイティブボタンと再生コントロールの表示・非表示を切り替える"""
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            View = autoclass("android.view.View")
            visibility = View.VISIBLE if visible else View.GONE

            @run_on_ui_thread
            def _apply():
                for btn in (
                    self.back_button_native,
                    self.pin_button_native,
                    self.video_button_native,
                ):
                    if btn is not None:
                        btn.setVisibility(visibility)

            _apply()
        except Exception as e:
            print(f"[DEBUG] ボタン表示切替に失敗: {e}")

        if self.webview is not None:
            try:
                from jnius import autoclass
                from android.runnable import run_on_ui_thread

                JString = autoclass("java.lang.String")
                display = "flex" if visible else "none"
                js = f"var c = document.getElementById('playback-controls'); if (c) c.style.display = '{display}';"

                @run_on_ui_thread
                def _eval():
                    self.webview.evaluateJavascript(JString(js), None)

                _eval()
            except Exception as e:
                print(f"[DEBUG] 再生コントロールの表示切替に失敗: {e}")

    def _show_video_progress_ui(self):
        """動画撮影の進捗表示とキャンセルボタンをネイティブビューとして表示する
        (WebViewの外側に重ねるので、撮影される映像には映り込まない)"""
        app = App.get_running_app()
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            from android.runnable import run_on_ui_thread

            AndroidButton = autoclass("android.widget.Button")
            TextView = autoclass("android.widget.TextView")
            FrameLayoutParams = autoclass("android.widget.FrameLayout$LayoutParams")
            Gravity = autoclass("android.view.Gravity")
            Color = autoclass("android.graphics.Color")
            JString = autoclass("java.lang.String")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity

            class OnClickListener(PythonJavaClass):
                __javainterfaces__ = ["android/view/View$OnClickListener"]
                __javacontext__ = "app"

                def __init__(self, callback):
                    super().__init__()
                    self.callback = callback

                @java_method("(Landroid/view/View;)V")
                def onClick(self, view):
                    self.callback()

            density = activity.getResources().getDisplayMetrics().density

            def dp(v):
                return int(v * density)

            @run_on_ui_thread
            def _create():
                progress_label = TextView(activity)
                progress_label.setText(JString(app.tr("video_capturing", progress=0)))
                progress_label.setTextColor(Color.WHITE)
                progress_label.setBackgroundColor(Color.parseColor("#CC000000"))
                progress_label.setPadding(dp(16), dp(10), dp(16), dp(10))
                progress_label.setTextSize(14)

                progress_params = FrameLayoutParams(
                    FrameLayoutParams.WRAP_CONTENT, FrameLayoutParams.WRAP_CONTENT
                )
                progress_params.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL
                progress_params.setMargins(0, dp(80), 0, 0)
                activity.addContentView(progress_label, progress_params)
                progress_label.bringToFront()
                self.video_progress_native = progress_label

                cancel_button = AndroidButton(activity)
                cancel_button.setText(JString(app.tr("cancel_button")))
                cancel_button.setTextColor(Color.WHITE)
                cancel_button.setBackgroundColor(Color.parseColor("#CCB71C1C"))
                cancel_button.setAllCaps(False)
                cancel_button.setClickable(True)
                cancel_button.setFocusable(True)
                cancel_button.setElevation(dp(8))

                self._video_cancel_click_listener = OnClickListener(
                    lambda: Clock.schedule_once(lambda dt: self._request_cancel_video_capture())
                )
                cancel_button.setOnClickListener(self._video_cancel_click_listener)

                cancel_params = FrameLayoutParams(dp(120), dp(48))
                cancel_params.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL
                cancel_params.setMargins(0, dp(130), 0, 0)
                activity.addContentView(cancel_button, cancel_params)
                cancel_button.bringToFront()
                self.video_cancel_button_native = cancel_button

            _create()
        except Exception as e:
            print(f"[DEBUG] 動画進捗表示の作成に失敗: {e}")

    def _update_video_progress_ui(self, percent):
        app = App.get_running_app()
        if getattr(self, "video_progress_native", None) is None:
            return
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            JString = autoclass("java.lang.String")
            text = app.tr("video_capturing", progress=percent)

            @run_on_ui_thread
            def _update():
                if self.video_progress_native is not None:
                    self.video_progress_native.setText(JString(text))

            _update()
        except Exception as e:
            print(f"[DEBUG] 動画進捗表示の更新に失敗: {e}")

    def _hide_video_progress_ui(self):
        try:
            from jnius import autoclass, cast
            from android.runnable import run_on_ui_thread

            ViewGroup = autoclass("android.view.ViewGroup")
            views = [
                getattr(self, "video_progress_native", None),
                getattr(self, "video_cancel_button_native", None),
            ]

            @run_on_ui_thread
            def _remove():
                for v in views:
                    if v is not None:
                        parent = v.getParent()
                        if parent is not None:
                            cast(ViewGroup, parent).removeView(v)

            _remove()
        except Exception as e:
            print(f"[DEBUG] 動画進捗表示の削除に失敗: {e}")
        self.video_progress_native = None
        self.video_cancel_button_native = None

    def _request_cancel_video_capture(self):
        """撮影中にキャンセルボタンが押された"""
        self._video_cancel_requested = True

    def _show_video_speed_dialog(self):
        app = App.get_running_app()
        if getattr(self, "_video_capturing", False):
            return
        points = getattr(self, "_video_playback_points", None)
        if not points:
            self._set_banner_text(app.tr("video_no_data"))
            return

        try:
            from jnius import autoclass, PythonJavaClass, java_method
            from android.runnable import run_on_ui_thread

            AlertDialogBuilder = autoclass("android.app.AlertDialog$Builder")
            JString = autoclass("java.lang.String")
            ArrayAdapter = autoclass("android.widget.ArrayAdapter")
            ArrayList = autoclass("java.util.ArrayList")
            RLayout = autoclass("android.R$layout")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity

            speeds = [1, 6, 20, 40, 100]
            labels = [f"{s}x" for s in speeds]

            class DialogClickListener(PythonJavaClass):
                __javainterfaces__ = ["android/content/DialogInterface$OnClickListener"]
                __javacontext__ = "app"

                def __init__(self, callback):
                    super().__init__()
                    self.callback = callback

                @java_method("(Landroid/content/DialogInterface;I)V")
                def onClick(self, dialog, which):
                    self.callback(which)

            def on_choice(which):
                speed = speeds[which]
                Clock.schedule_once(lambda dt: self._start_video_capture(speed))

            listener = DialogClickListener(on_choice)
            self._video_dialog_listener = listener  # ガベージコレクション対策で参照を保持

            @run_on_ui_thread
            def _show():
                items = ArrayList()
                for label in labels:
                    items.add(JString(label))
                adapter = ArrayAdapter(activity, RLayout.simple_list_item_1, items)

                builder = AlertDialogBuilder(activity)
                builder.setTitle(JString(app.tr("video_speed_dialog_title")))
                builder.setAdapter(adapter, listener)
                builder.show()

            _show()
        except Exception as e:
            print(f"[DEBUG] 速度選択ダイアログの表示に失敗: {e}")
            self._set_banner_text(app.tr("video_save_failed", error=e))

    def _start_video_capture(self, speed):
        app = App.get_running_app()
        if getattr(self, "_video_capturing", False):
            return
        points = getattr(self, "_video_playback_points", None) or []
        pins = getattr(self, "_video_pins", None) or []
        if not points:
            return

        self._video_capturing = True
        fps = 10
        basestep_ms = 3000  # 実際の記録間隔の目安(再生機能と同じ値)
        total_real_ms = len(points) * basestep_ms
        total_video_ms = total_real_ms / speed
        total_frames = max(1, int(round(total_video_ms / 1000 * fps)))
        # 動画が長くなりすぎて実用的でなくなるのを防ぐための上限(約10分)
        total_frames = min(total_frames, fps * 600)

        frame_plan = []
        shown_pin_indices = set()
        for frame_i in range(total_frames):
            video_t_ms = frame_i / fps * 1000
            real_t_ms = video_t_ms * speed
            point_index = min(len(points) - 1, int(real_t_ms / basestep_ms))
            frame_plan.append((point_index, -1))

            p = points[point_index]
            for pin_idx, pin in enumerate(pins):
                if pin_idx in shown_pin_indices:
                    continue
                dist_km = haversine_km(p["lat"], p["lon"], pin["lat"], pin["lon"])
                if dist_km * 1000 <= 30:
                    shown_pin_indices.add(pin_idx)
                    closeup_frames = max(1, int(round(2 * fps)))
                    for _ in range(closeup_frames):
                        frame_plan.append((point_index, pin_idx))
                    break

        self._video_frame_plan = frame_plan
        self._video_frame_index = 0
        self._video_fps = fps
        self._video_cancel_requested = False
        self._video_temp_path = os.path.join(app.user_data_dir, "temp_export_video.mp4")

        self._set_map_controls_visible(False)
        self._show_video_progress_ui()
        # Canvas描画のルート線がハードウェア描画では正しくキャプチャされないため、
        # 撮影中だけWebViewをソフトウェア描画モードに切り替える
        self._set_webview_layer_type(software=True)

        try:
            self._init_video_encoder()
        except Exception as e:
            print(f"[DEBUG] 動画エンコーダの初期化に失敗: {e}")
            self._video_capturing = False
            self._set_map_controls_visible(True)
            self._hide_video_progress_ui()
            self._set_webview_layer_type(software=False)
            self._set_banner_text(app.tr("video_save_failed", error=e))
            return

        Clock.schedule_once(lambda dt: self._capture_next_frame(), 0.3)

    def _set_webview_layer_type(self, software):
        """撮影中はWebViewをソフトウェア描画にして、Canvas等の内容も
        確実にBitmapへキャプチャできるようにする(撮影後は元(ハードウェア)に戻す)"""
        if self.webview is None:
            return
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            View = autoclass("android.view.View")
            layer_type = View.LAYER_TYPE_SOFTWARE if software else View.LAYER_TYPE_HARDWARE

            @run_on_ui_thread
            def _apply():
                if self.webview is not None:
                    self.webview.setLayerType(layer_type, None)

            _apply()
        except Exception as e:
            print(f"[DEBUG] WebViewの描画モード切替に失敗: {e}")

    def _init_video_encoder(self):
        from jnius import autoclass
        import threading

        MediaFormat = autoclass("android.media.MediaFormat")
        MediaCodec = autoclass("android.media.MediaCodec")
        MediaMuxer = autoclass("android.media.MediaMuxer")
        MuxerOutputFormat = autoclass("android.media.MediaMuxer$OutputFormat")
        CodecCapabilities = autoclass("android.media.MediaCodecInfo$CodecCapabilities")
        from android.runnable import run_on_ui_thread

        size_result = {}
        done_event = threading.Event()

        @run_on_ui_thread
        def _get_size():
            size_result["width"] = self.webview.getWidth()
            size_result["height"] = self.webview.getHeight()
            done_event.set()

        _get_size()
        done_event.wait(timeout=5.0)

        width = size_result.get("width", 0) or 0
        height = size_result.get("height", 0) or 0
        width -= width % 2
        height -= height % 2
        if width <= 0 or height <= 0:
            raise ValueError("WebViewの表示サイズを取得できませんでした")

        self._video_width = width
        self._video_height = height

        mime = "video/avc"
        fmt = MediaFormat.createVideoFormat(mime, width, height)
        fmt.setInteger(
            MediaFormat.KEY_COLOR_FORMAT,
            CodecCapabilities.COLOR_FormatSurface,
        )
        fmt.setInteger(MediaFormat.KEY_BIT_RATE, 4000000)
        fmt.setInteger(MediaFormat.KEY_FRAME_RATE, self._video_fps)
        fmt.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 2)

        codec = MediaCodec.createEncoderByType(mime)
        codec.configure(fmt, None, None, MediaCodec.CONFIGURE_FLAG_ENCODE)
        input_surface = codec.createInputSurface()
        codec.start()

        muxer = MediaMuxer(
            self._video_temp_path, MuxerOutputFormat.MUXER_OUTPUT_MPEG_4
        )

        self._video_codec = codec
        self._video_input_surface = input_surface
        self._video_muxer = muxer
        self._video_muxer_started = False
        self._video_track_index = -1

    def _capture_next_frame(self):
        if self._video_frame_index >= len(self._video_frame_plan):
            self._finish_video_capture()
            return

        if getattr(self, "_video_cancel_requested", False):
            self._handle_video_cancel()
            return

        point_index, closeup_pin_index = self._video_frame_plan[self._video_frame_index]

        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            JString = autoclass("java.lang.String")
            js = f"setPlaybackFrame({point_index}, {closeup_pin_index});"

            @run_on_ui_thread
            def _set_frame():
                self.webview.evaluateJavascript(JString(js), None)

            _set_frame()
        except Exception as e:
            print(f"[DEBUG] フレーム設定に失敗: {e}")

        # 地図の再描画(座標の再投影)が完了したことを確認してからキャプチャする
        self._wait_for_frame_ready(self._capture_and_encode_frame)

    def _wait_for_frame_ready(self, on_ready, attempts_left=25):
        if getattr(self, "_video_cancel_requested", False):
            self._handle_video_cancel()
            return
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            JString = autoclass("java.lang.String")
            callback_class = getattr(self, "_map_center_callback_class", None)
            if callback_class is None or attempts_left <= 0 or self.webview is None:
                # 仕組みが使えない場合や、最大待機に達した場合はそのまま進める
                Clock.schedule_once(lambda dt: on_ready(), 0.05)
                return

            def _on_value(value_str):
                ready = "true" in (value_str or "").lower()
                if ready:
                    Clock.schedule_once(lambda dt: on_ready())
                else:
                    Clock.schedule_once(
                        lambda dt: self._wait_for_frame_ready(on_ready, attempts_left - 1),
                        0.03,
                    )

            callback = callback_class(_on_value)
            self._pending_frame_ready_callback = callback  # ガベージコレクション対策

            @run_on_ui_thread
            def _check():
                self.webview.evaluateJavascript(
                    JString("window.frameReady === true"), callback
                )

            _check()
        except Exception as e:
            print(f"[DEBUG] フレーム準備確認に失敗: {e}")
            Clock.schedule_once(lambda dt: on_ready(), 0.05)

    def _capture_and_encode_frame(self):
        if getattr(self, "_video_cancel_requested", False):
            self._handle_video_cancel()
            return
        try:
            self._draw_frame_to_encoder()
            self._drain_encoder(end_of_stream=False)
        except Exception as e:
            print(f"[DEBUG] フレームの描画・エンコードに失敗: {e}")
            self._abort_video_capture(str(e))
            return

        self._video_frame_index += 1
        progress = int(self._video_frame_index / len(self._video_frame_plan) * 100)
        self._update_video_progress_ui(progress)

        Clock.schedule_once(lambda dt: self._capture_next_frame(), 0)

    def _draw_frame_to_encoder(self):
        from jnius import autoclass
        from android.runnable import run_on_ui_thread
        import threading

        Bitmap = autoclass("android.graphics.Bitmap")
        BitmapConfig = autoclass("android.graphics.Bitmap$Config")
        AndroidCanvas = autoclass("android.graphics.Canvas")

        done_event = threading.Event()
        result = {}

        @run_on_ui_thread
        def _draw():
            try:
                bitmap = Bitmap.createBitmap(
                    self._video_width, self._video_height, BitmapConfig.ARGB_8888
                )
                canvas = AndroidCanvas(bitmap)
                self.webview.draw(canvas)

                surface_canvas = self._video_input_surface.lockCanvas(None)
                surface_canvas.drawBitmap(bitmap, 0, 0, None)
                self._video_input_surface.unlockCanvasAndPost(surface_canvas)
                bitmap.recycle()
            except Exception as e:
                result["error"] = str(e)
            finally:
                done_event.set()

        _draw()
        if not done_event.wait(timeout=5.0):
            raise RuntimeError("フレーム描画がタイムアウトしました")
        if result.get("error"):
            raise RuntimeError(result["error"])

    def _drain_encoder(self, end_of_stream):
        from jnius import autoclass

        MediaCodec = autoclass("android.media.MediaCodec")
        BufferInfo = autoclass("android.media.MediaCodec$BufferInfo")

        codec = self._video_codec
        muxer = self._video_muxer

        if end_of_stream:
            codec.signalEndOfInputStream()

        timeout_us = 10000
        buffer_info = BufferInfo()

        while True:
            output_index = codec.dequeueOutputBuffer(buffer_info, timeout_us)
            if output_index == MediaCodec.INFO_TRY_AGAIN_LATER:
                if not end_of_stream:
                    break
                else:
                    continue
            elif output_index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED:
                if self._video_muxer_started:
                    raise RuntimeError("動画フォーマットが2回変化しました")
                new_format = codec.getOutputFormat()
                self._video_track_index = muxer.addTrack(new_format)
                muxer.start()
                self._video_muxer_started = True
            elif output_index >= 0:
                encoded_data = codec.getOutputBuffer(output_index)
                if buffer_info.size > 0 and self._video_muxer_started:
                    encoded_data.position(buffer_info.offset)
                    encoded_data.limit(buffer_info.offset + buffer_info.size)
                    muxer.writeSampleData(self._video_track_index, encoded_data, buffer_info)
                codec.releaseOutputBuffer(output_index, False)
                if (buffer_info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0:
                    break

    def _finish_video_capture(self):
        app = App.get_running_app()
        try:
            self._drain_encoder(end_of_stream=True)
            self._video_codec.stop()
            self._video_codec.release()
            self._video_muxer.stop()
            self._video_muxer.release()
        except Exception as e:
            print(f"[DEBUG] 動画エンコーダの終了処理に失敗: {e}")
            self._abort_video_capture(str(e))
            return

        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            JString = autoclass("java.lang.String")

            @run_on_ui_thread
            def _clear():
                self.webview.evaluateJavascript(JString("clearPlaybackFrame();"), None)

            _clear()
        except Exception as e:
            print(f"[DEBUG] フレームのクリアに失敗: {e}")

        self._set_map_controls_visible(True)
        self._hide_video_progress_ui()
        self._set_webview_layer_type(software=False)
        self._video_capturing = False
        self._set_banner_text(app.tr("video_capture_done"))
        self._save_video_via_saf()

    def _abort_video_capture(self, error_message):
        app = App.get_running_app()
        try:
            if getattr(self, "_video_codec", None) is not None:
                self._video_codec.stop()
                self._video_codec.release()
        except Exception:
            pass
        try:
            if getattr(self, "_video_muxer", None) is not None:
                if getattr(self, "_video_muxer_started", False):
                    self._video_muxer.stop()
                self._video_muxer.release()
        except Exception:
            pass
        self._set_map_controls_visible(True)
        self._hide_video_progress_ui()
        self._set_webview_layer_type(software=False)
        self._video_capturing = False
        self._set_banner_text(app.tr("video_save_failed", error=error_message))

    def _handle_video_cancel(self):
        """撮影中にキャンセルボタンが押された場合の後片付け"""
        app = App.get_running_app()
        try:
            if getattr(self, "_video_codec", None) is not None:
                self._video_codec.stop()
                self._video_codec.release()
        except Exception:
            pass
        try:
            if getattr(self, "_video_muxer", None) is not None:
                if getattr(self, "_video_muxer_started", False):
                    self._video_muxer.stop()
                self._video_muxer.release()
        except Exception:
            pass
        try:
            temp_path = getattr(self, "_video_temp_path", None)
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            print(f"[DEBUG] 一時動画ファイルの削除に失敗: {e}")

        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            JString = autoclass("java.lang.String")

            @run_on_ui_thread
            def _clear():
                if self.webview is not None:
                    self.webview.evaluateJavascript(JString("clearPlaybackFrame();"), None)

            _clear()
        except Exception as e:
            print(f"[DEBUG] フレームのクリアに失敗: {e}")

        self._set_map_controls_visible(True)
        self._hide_video_progress_ui()
        self._set_webview_layer_type(software=False)
        self._video_capturing = False
        self._video_cancel_requested = False
        self._set_banner_text(app.tr("video_cancelled"))

    def _save_video_via_saf(self):
        app = App.get_running_app()
        try:
            from jnius import autoclass
            from android import activity

            Intent = autoclass("android.content.Intent")
            JString = autoclass("java.lang.String")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            mactivity = PythonActivity.mActivity

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"route_video_{timestamp}.mp4"

            intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("video/mp4")
            intent.putExtra(Intent.EXTRA_TITLE, JString(filename))

            request_code = 9003

            def on_result(request_code_recv, result_code, data):
                if request_code_recv != request_code:
                    return
                activity.unbind(on_activity_result=on_result)
                Activity = autoclass("android.app.Activity")
                if result_code != Activity.RESULT_OK or data is None:
                    return
                try:
                    uri = data.getData()
                    resolver = mactivity.getContentResolver()
                    out_stream = resolver.openOutputStream(uri)
                    with open(self._video_temp_path, "rb") as f:
                        video_bytes = f.read()
                    out_stream.write(video_bytes, 0, len(video_bytes))
                    out_stream.flush()
                    out_stream.close()
                    display_path = uri.toString()
                    message = app.tr("video_save_success", path=display_path)
                    Clock.schedule_once(lambda dt: self._set_banner_text(message))
                except Exception as e:
                    print(f"[DEBUG] 動画の保存に失敗: {e}")
                    message = app.tr("video_save_failed", error=e)
                    Clock.schedule_once(lambda dt: self._set_banner_text(message))

            activity.bind(on_activity_result=on_result)
            mactivity.startActivityForResult(intent, request_code)
        except Exception as e:
            print(f"[DEBUG] 保存先選択ダイアログの表示に失敗: {e}")
            self._set_banner_text(app.tr("video_save_failed", error=e))

    def _remove_webview(self):
        views_to_remove = [
            getattr(self, "webview", None),
            getattr(self, "back_button_native", None),
            getattr(self, "pin_button_native", None),
            getattr(self, "video_button_native", None),
            getattr(self, "video_progress_native", None),
            getattr(self, "video_cancel_button_native", None),
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
            self.pin_button_native = None
            self.video_button_native = None
            self.video_progress_native = None
            self.video_cancel_button_native = None

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
        self.pin_manager = PinManager(self.user_data_dir)
        self.backup_manager = BackupManager(self.profile_manager, self.pin_manager)
        self.settings_manager = SettingsManager(self.user_data_dir)
        self.language = self.settings_manager.get_language()
        self.timezone_offset = self.settings_manager.get_timezone_offset()
        self.selected_profile = None
        self.selected_route_date = None
        self.selected_route_dates = []  # 期間指定で選ばれた複数日付
        self.pending_pin_location = (None, None)
        self.pending_pin_source = "map"

        sm = ScreenManager()
        sm.add_widget(ProfileListScreen(name="profile_list"))
        sm.add_widget(AddProfileScreen(name="add_profile"))
        sm.add_widget(TrackerScreen(name="tracker"))
        sm.add_widget(RouteListScreen(name="route_list"))
        sm.add_widget(MapScreen(name="map"))
        sm.add_widget(SettingsScreen(name="settings"))
        sm.add_widget(CalendarRangeScreen(name="calendar_range"))
        sm.add_widget(AddPinScreen(name="add_pin"))
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