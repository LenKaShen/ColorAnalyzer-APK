import os
import threading
import traceback
from functools import partial
from typing import Dict, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

try:
    from plyer import filechooser
except Exception:
    filechooser = None


ROLE_OPTIONS = ["control_min", "control_max", "sample"]
TEXT_COLOR = (0.93, 0.95, 0.98, 1)
MUTED_TEXT_COLOR = (0.68, 0.73, 0.81, 1)
FIELD_BG = (0.18, 0.2, 0.24, 1)
BTN_BG = (0.23, 0.42, 0.7, 1)


def _resolve_content_uri(uri: str) -> Optional[str]:
    """
    Resolve content:// URI to actual file path if possible.
    Falls back to original URI if resolution fails.
    """
    if not isinstance(uri, str):
        return None
    if not uri.startswith("content://"):
        return uri
    
    try:
        from android.content import Context
        from android.content import ContentResolver
        from jnius import autoclass, cast
        
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        resolver = activity.getContentResolver()
        
        uri_obj = autoclass("android.net.Uri").parse(uri)
        cursor = resolver.query(uri_obj, None, None, None, None)
        
        if cursor and cursor.moveToFirst():
            idx = cursor.getColumnIndex("_data")
            if idx >= 0:
                path = cursor.getString(idx)
                cursor.close()
                if path and os.path.exists(path):
                    print(f"[DEBUG] Resolved content URI to: {path}")
                    return path
        if cursor:
            cursor.close()
    except Exception as e:
        print(f"[DEBUG] Content URI resolution failed: {e}")
    
    return uri


def _label(text: str, muted: bool = False, **kwargs) -> Label:
    return Label(
        text=text,
        color=MUTED_TEXT_COLOR if muted else TEXT_COLOR,
        **kwargs,
    )


def _button(text: str, **kwargs) -> Button:
    return Button(
        text=text,
        color=TEXT_COLOR,
        background_normal="",
        background_color=BTN_BG,
        **kwargs,
    )


def _text_input(text: str, input_filter: str) -> TextInput:
    return TextInput(
        text=text,
        multiline=False,
        input_filter=input_filter,
        foreground_color=TEXT_COLOR,
        background_color=FIELD_BG,
        cursor_color=TEXT_COLOR,
    )


class ROIImage(Image):
    def __init__(self, on_roi_change=None, **kwargs):
        super().__init__(allow_stretch=True, keep_ratio=True, **kwargs)
        self._drag_start: Optional[Tuple[float, float]] = None
        self._drag_end: Optional[Tuple[float, float]] = None
        self.on_roi_change = on_roi_change
        self.bind(pos=lambda *_: self._redraw_roi())
        self.bind(size=lambda *_: self._redraw_roi())
        self.bind(texture=lambda *_: self._redraw_roi())

    def _display_rect(self) -> Tuple[float, float, float, float]:
        draw_w, draw_h = self.norm_image_size
        x0 = self.center_x - draw_w / 2.0
        y0 = self.center_y - draw_h / 2.0
        return (x0, y0, draw_w, draw_h)

    def _clamp_point(self, x: float, y: float) -> Tuple[float, float]:
        x0, y0, w, h = self._display_rect()
        return (max(x0, min(x, x0 + w)), max(y0, min(y, y0 + h)))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        cx, cy = self._clamp_point(touch.x, touch.y)
        self._drag_start = (cx, cy)
        self._drag_end = (cx, cy)
        self._redraw_roi()
        return True

    def on_touch_move(self, touch):
        if self._drag_start is None:
            return super().on_touch_move(touch)
        self._drag_end = self._clamp_point(touch.x, touch.y)
        self._redraw_roi()
        return True

    def on_touch_up(self, touch):
        if self._drag_start is None:
            return super().on_touch_up(touch)
        self._drag_end = self._clamp_point(touch.x, touch.y)
        self._redraw_roi()
        if self.on_roi_change:
            Clock.schedule_once(lambda _: self.on_roi_change(self.get_roi_pixels()))
        return True

    def _redraw_roi(self) -> None:
        self.canvas.after.clear()
        if self._drag_start is None or self._drag_end is None:
            return
        x1, y1 = self._drag_start
        x2, y2 = self._drag_end
        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        if w < 2 or h < 2:
            return
        with self.canvas.after:
            Color(1.0, 0.4, 0.2, 1.0)
            Line(rectangle=(x, y, w, h), width=2.0)

    def get_roi_pixels(self) -> Optional[Tuple[int, int, int, int]]:
        if self._drag_start is None or self._drag_end is None or self.texture is None:
            return None

        x0, y0, w, h = self._display_rect()
        if w <= 1 or h <= 1:
            return None

        x1, y1 = self._drag_start
        x2, y2 = self._drag_end
        left = max(x0, min(x1, x2))
        right = min(x0 + w, max(x1, x2))
        bottom = max(y0, min(y1, y2))
        top = min(y0 + h, max(y1, y2))
        if right - left < 2 or top - bottom < 2:
            return None

        img_w, img_h = self.texture.size

        px_left = int(((left - x0) / w) * img_w)
        px_right = int(((right - x0) / w) * img_w)
        py_top = int((1.0 - ((top - y0) / h)) * img_h)
        py_bottom = int((1.0 - ((bottom - y0) / h)) * img_h)

        roi_x = max(0, min(px_left, img_w - 1))
        roi_y = max(0, min(py_top, img_h - 1))
        roi_w = max(1, min(px_right - px_left, img_w - roi_x))
        roi_h = max(1, min(py_bottom - py_top, img_h - roi_y))
        return (roi_x, roi_y, roi_w, roi_h)


class RolePanel(BoxLayout):
    def __init__(self, role: str, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(6),
            padding=dp(8),
            size_hint_y=None,
            **kwargs,
        )
        self.bind(minimum_height=self.setter("height"))

        self.role = role
        self.video_path: Optional[str] = None
        self.image_start_path: Optional[str] = None
        self.image_end_path: Optional[str] = None
        self.image_rois: Dict[str, Optional[Tuple[int, int, int, int]]] = {
            "start": None,
            "end": None,
        }

        # Header
        self.add_widget(_label(text=f"Role: {role}", size_hint_y=None, height=dp(24)))

        # Video section
        video_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        self.video_btn = _button(text="Pick Video", size_hint_x=0.32)
        self.video_btn.bind(on_release=lambda *_: self.pick_video())
        self.video_label = _label(
            text="No video selected",
            muted=True,
            halign="left",
            valign="middle",
            size_hint_x=0.68,
        )
        self.video_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        video_row.add_widget(self.video_btn)
        video_row.add_widget(self.video_label)
        self.add_widget(video_row)

        # Images section
        img_header = _label(
            text="Or use Frame 1 + Last Frame images (draw ROI on image)",
            muted=True,
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
        )
        img_header.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        self.add_widget(img_header)

        # Frame 1
        start_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        self.start_img_btn = _button(text="Pick Frame 1", size_hint_x=0.32)
        self.start_img_btn.bind(on_release=lambda *_: self.pick_image("start"))
        self.start_img_label = _label(
            text="No frame 1 image",
            muted=True,
            halign="left",
            valign="middle",
            size_hint_x=0.68,
        )
        self.start_img_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        start_row.add_widget(self.start_img_btn)
        start_row.add_widget(self.start_img_label)
        self.add_widget(start_row)

        # Frame 1 ROI display
        self.start_roi_image = ROIImage(
            on_roi_change=lambda roi: self._on_roi_drawn("start", roi),
            size_hint_y=None,
            height=0,
        )
        self.add_widget(self.start_roi_image)

        # Frame 1 ROI label + clear button
        start_roi_label_row = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
        self.start_roi_label = _label(text="ROI: full image", muted=True, halign="left", valign="middle")
        self.start_roi_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        start_roi_clear = _button(text="Clear ROI", size_hint_x=0.28)
        start_roi_clear.bind(on_release=lambda *_: self._clear_roi("start"))
        start_roi_label_row.add_widget(self.start_roi_label)
        start_roi_label_row.add_widget(start_roi_clear)
        self.add_widget(start_roi_label_row)

        # Frame Last
        end_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        self.end_img_btn = _button(text="Pick Last Frame", size_hint_x=0.32)
        self.end_img_btn.bind(on_release=lambda *_: self.pick_image("end"))
        self.end_img_label = _label(
            text="No last frame image",
            muted=True,
            halign="left",
            valign="middle",
            size_hint_x=0.68,
        )
        self.end_img_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        end_row.add_widget(self.end_img_btn)
        end_row.add_widget(self.end_img_label)
        self.add_widget(end_row)

        # Last Frame ROI display
        self.end_roi_image = ROIImage(
            on_roi_change=lambda roi: self._on_roi_drawn("end", roi),
            size_hint_y=None,
            height=0,
        )
        self.add_widget(self.end_roi_image)

        # Last Frame ROI label + clear button
        end_roi_label_row = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
        self.end_roi_label = _label(text="ROI: full image", muted=True, halign="left", valign="middle")
        self.end_roi_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        end_roi_clear = _button(text="Clear ROI", size_hint_x=0.28)
        end_roi_clear.bind(on_release=lambda *_: self._clear_roi("end"))
        end_roi_label_row.add_widget(self.end_roi_label)
        end_roi_label_row.add_widget(end_roi_clear)
        self.add_widget(end_roi_label_row)

    def pick_video(self) -> None:
        if filechooser is None:
            self.video_label.text = "File picker unavailable"
            return
        try:
            selection = filechooser.open_file(
                on_selection=self._on_video_selected,
                filters=["*.mp4", "*.mov", "*.avi", "*.mkv"],
            )
            print(f"[DEBUG] pick_video sync return: {selection}")
            if selection:
                self._on_video_selected(selection)
        except Exception as e:
            print(f"[ERROR] pick_video exception: {e}")
            self.video_label.text = f"Picker error: {e}"

    def pick_image(self, phase: str) -> None:
        if filechooser is None:
            if phase == "start":
                self.start_img_label.text = "File picker unavailable"
            else:
                self.end_img_label.text = "File picker unavailable"
            return
        try:
            callback = partial(self._on_image_selected, phase)
            selection = filechooser.open_file(
                on_selection=callback,
                filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"],
            )
            print(f"[DEBUG] pick_image({phase}) sync return: {selection}")
            if selection:
                self._on_image_selected(phase, selection)
        except Exception as e:
            print(f"[ERROR] pick_image({phase}) exception: {e}")
            label = self.start_img_label if phase == "start" else self.end_img_label
            label.text = f"Picker error: {e}"

    def _extract_selected_path(self, selection=None, *args, **kwargs) -> Optional[str]:
        candidate = selection
        if candidate is None and args:
            candidate = args[0]
        if candidate is None:
            candidate = kwargs.get("selection") or kwargs.get("path")

        print(f"[DEBUG] _extract_selected_path input type: {type(candidate)}, value: {candidate}")

        try:
            path = candidate[0] if isinstance(candidate, (list, tuple)) else str(candidate)
        except (TypeError, IndexError):
            path = str(candidate)

        if not path or not isinstance(path, str) or path.strip() == "":
            print(f"[DEBUG] _extract_selected_path: path invalid or empty")
            return None
        
        # Try to resolve content:// URIs (Android 11+ microSD access)
        resolved_path = _resolve_content_uri(path)
        if not resolved_path:
            return None
        
        print(f"[DEBUG] _extract_selected_path result: {resolved_path}")
        return resolved_path

    def _on_video_selected(self, selection=None, *args, **kwargs):
        path = self._extract_selected_path(selection, *args, **kwargs)
        if not path:
            print(f"[DEBUG] _on_video_selected: no path extracted")
            return

        print(f"[DEBUG] Video selected: {path}")
        self.video_path = path
        name = os.path.basename(path)
        Clock.schedule_once(lambda _: setattr(self.video_label, "text", name or "video selected"))

    def _on_image_selected(self, phase: str, selection=None, *args, **kwargs):
        path = self._extract_selected_path(selection, *args, **kwargs)
        if not path:
            print(f"[DEBUG] _on_image_selected({phase}): no path extracted")
            label = self.start_img_label if phase == "start" else self.end_img_label
            Clock.schedule_once(lambda _: setattr(label, "text", "Selection failed - check logs"))
            return

        print(f"[DEBUG] Image selected ({phase}): {path}")
        name = os.path.basename(path)
        
        def _load_image():
            try:
                preview_h = dp(220) if Window.width >= dp(520) else dp(180)
                if phase == "start":
                    self.image_start_path = path
                    self.image_rois["start"] = None
                    self.start_roi_image.source = path
                    self.start_roi_image.height = preview_h
                    self.start_img_label.text = name or "frame 1 selected"
                    self.start_roi_label.text = "ROI: full image"
                else:
                    self.image_end_path = path
                    self.image_rois["end"] = None
                    self.end_roi_image.source = path
                    self.end_roi_image.height = preview_h
                    self.end_img_label.text = name or "last frame selected"
                    self.end_roi_label.text = "ROI: full image"
            except Exception as e:
                print(f"[ERROR] Failed to load image: {e}")
                label = self.start_img_label if phase == "start" else self.end_img_label
                Clock.schedule_once(lambda _: setattr(label, "text", f"Load failed: {e}"))
        
        Clock.schedule_once(lambda _: _load_image())

    def _clear_roi(self, phase: str) -> None:
        self.image_rois[phase] = None
        roi_image = self.start_roi_image if phase == "start" else self.end_roi_image
        roi_image._drag_start = None
        roi_image._drag_end = None
        roi_image._redraw_roi()
        
        if phase == "start":
            self.start_roi_label.text = "ROI: full image"
        else:
            self.end_roi_label.text = "ROI: full image"
    
    def _update_roi_display(self, phase: str) -> None:
        roi_image = self.start_roi_image if phase == "start" else self.end_roi_image
        roi = roi_image.get_roi_pixels()
        self.image_rois[phase] = roi
        
        if roi is None:
            label = self.start_roi_label if phase == "start" else self.end_roi_label
            label.text = "ROI: full image"
        else:
            text = f"ROI: {roi[0]},{roi[1]},{roi[2]},{roi[3]}"
            label = self.start_roi_label if phase == "start" else self.end_roi_label
            label.text = text

    def _on_roi_drawn(self, phase: str, roi: Optional[Tuple[int, int, int, int]]) -> None:
        """Called automatically when user finishes drawing ROI on image."""
        self.image_rois[phase] = roi
        if roi is None:
            label = self.start_roi_label if phase == "start" else self.end_roi_label
            label.text = "ROI: full image"
        else:
            text = f"ROI: {roi[0]},{roi[1]},{roi[2]},{roi[3]}"
            label = self.start_roi_label if phase == "start" else self.end_roi_label
            label.text = text
            print(f"[DEBUG] ROI drawn for {phase}: {roi}")




class ColorAnalyzerMobileApp(App):
    def build(self):
        Window.clearcolor = (0.08, 0.1, 0.13, 1)

        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        header = Label(
            text="Offline Color Analyzer",
            size_hint_y=None,
            height=dp(36),
            font_size="20sp",
            color=TEXT_COLOR,
        )
        root.add_widget(header)

        main_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        content = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        config_title = _label(
            text="Analysis Settings",
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        config_title.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        content.add_widget(config_title)

        duration_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        duration_row.add_widget(_label(text="Video Duration", size_hint_x=0.34, halign="left", valign="middle"))
        self.hours_input = _text_input(text="0", input_filter="int")
        self.minutes_input = _text_input(text="0", input_filter="int")
        self.seconds_input = _text_input(text="10", input_filter="int")
        self.hours_input.hint_text = "hh"
        self.minutes_input.hint_text = "mm"
        self.seconds_input.hint_text = "ss"
        self.hours_input.size_hint_x = 0.12
        self.minutes_input.size_hint_x = 0.12
        self.seconds_input.size_hint_x = 0.12
        duration_sep1 = _label(text=":", size_hint_x=0.04, muted=True)
        duration_sep2 = _label(text=":", size_hint_x=0.04, muted=True)
        duration_row.add_widget(self.hours_input)
        duration_row.add_widget(duration_sep1)
        duration_row.add_widget(self.minutes_input)
        duration_row.add_widget(duration_sep2)
        duration_row.add_widget(self.seconds_input)
        content.add_widget(duration_row)

        calibration_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        calibration_row.add_widget(
            _label(text="Control Min Target", size_hint_x=0.34, halign="left", valign="middle")
        )
        self.control_min_input = _text_input(text="", input_filter="float")
        self.control_min_input.hint_text = "e.g. 0.0"
        calibration_row.add_widget(self.control_min_input)
        calibration_row.add_widget(
            _label(text="Control Max Target", size_hint_x=0.34, halign="left", valign="middle")
        )
        self.control_max_input = _text_input(text="", input_filter="float")
        self.control_max_input.hint_text = "e.g. 100.0"
        calibration_row.add_widget(self.control_max_input)
        content.add_widget(calibration_row)

        self.role_panels: Dict[str, RolePanel] = {}

        role_title = _label(
            text="Inputs By Role",
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        role_title.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        content.add_widget(role_title)

        for role in ROLE_OPTIONS:
            panel = RolePanel(role=role)
            self.role_panels[role] = panel
            content.add_widget(panel)

        main_scroll.add_widget(content)
        root.add_widget(main_scroll)

        action_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.run_btn = _button(text="Run Analysis", size_hint_x=0.38)
        self.run_btn.bind(on_release=lambda *_: self.run_analysis())
        self.status_label = _label(
            text="Ready",
            muted=True,
            halign="left",
            valign="middle",
            size_hint_x=0.62,
        )
        self.status_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        action_row.add_widget(self.run_btn)
        action_row.add_widget(self.status_label)
        root.add_widget(action_row)

        output_scroll = ScrollView(size_hint_y=None, height=dp(160), do_scroll_x=False)
        self.output_label = _label(text="Ready", halign="left", valign="top", size_hint_y=None)
        self.output_label.bind(texture_size=lambda inst, val: setattr(inst, "height", max(dp(160), val[1])))
        self.output_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        output_scroll.add_widget(self.output_label)
        root.add_widget(output_scroll)

        self._request_android_permissions()
        return root

    def _request_android_permissions(self) -> None:
        try:
            from android.permissions import Permission, request_permissions

            read_media_images = getattr(
                Permission,
                "READ_MEDIA_IMAGES",
                Permission.READ_EXTERNAL_STORAGE,
            )
            read_media_video = getattr(
                Permission,
                "READ_MEDIA_VIDEO",
                Permission.READ_EXTERNAL_STORAGE,
            )

            request_permissions(
                [
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    read_media_images,
                    read_media_video,
                ]
            )
        except Exception:
            # Non-Android runtime or unavailable permission API.
            pass

    def run_analysis(self) -> None:
        self.run_btn.disabled = True
        self.status_label.text = "Running analysis..."
        self.output_label.text = "Running analysis..."
        threading.Thread(target=self._run_analysis_worker, daemon=True).start()

    def _parse_duration_sec(self) -> int:
        h = int(self.hours_input.text or "0")
        m = int(self.minutes_input.text or "0")
        s = int(self.seconds_input.text or "0")
        duration = h * 3600 + m * 60 + s
        if duration <= 0:
            raise ValueError("Duration must be greater than zero")
        return duration

    def _parse_optional_float(self, text: str) -> Optional[float]:
        cleaned = (text or "").strip()
        if cleaned == "":
            return None
        return float(cleaned)

    def _run_analysis_worker(self) -> None:
        try:
            # Import heavy analysis deps lazily so UI can still open if an Android wheel is missing.
            from core_analysis import analyze_three_image_pairs, analyze_three_videos

            duration_sec = self._parse_duration_sec()
            control_min_target = self._parse_optional_float(self.control_min_input.text)
            control_max_target = self._parse_optional_float(self.control_max_input.text)

            if (control_min_target is None) != (control_max_target is None):
                raise ValueError("Enter both calibration targets, or leave both blank")

            mode_by_role: Dict[str, str] = {}
            video_by_role: Dict[str, str] = {}
            start_time_by_role: Dict[str, float] = {}
            image_pair_by_role: Dict[str, Tuple[str, str]] = {}

            for role, panel in self.role_panels.items():
                has_video = bool(panel.video_path)
                has_images = bool(panel.image_start_path and panel.image_end_path)

                if has_video and has_images:
                    raise ValueError(
                        f"Choose one input type for {role}: video or frame images, not both"
                    )
                if has_video:
                    input_modes_role = "video"
                    video_by_role[role] = panel.video_path
                    start_time_by_role[role] = 0.0
                elif has_images:
                    input_modes_role = "images"
                    image_pair_by_role[role] = (panel.image_start_path, panel.image_end_path)
                else:
                    raise ValueError(
                        f"Select either a video or frame 1/last frame images for role: {role}"
                    )
                mode_by_role[role] = input_modes_role

            distinct_modes = set(mode_by_role.values())
            if len(distinct_modes) > 1:
                raise ValueError(
                    "Use one input type for all roles: all videos or all frame image pairs"
                )

            if "video" in distinct_modes:
                result = analyze_three_videos(
                    video_by_role=video_by_role,
                    start_time_by_role=start_time_by_role,
                    duration_sec=duration_sec,
                    control_min_target=control_min_target,
                    control_max_target=control_max_target,
                )
            else:
                rois_by_role: Dict[str, Dict[str, Optional[Tuple[int, int, int, int]]]] = {}
                for role, panel in self.role_panels.items():
                    rois_by_role[role] = {
                        "start": panel.image_rois["start"],
                        "end": panel.image_rois["end"],
                    }
                result = analyze_three_image_pairs(
                    image_pair_by_role=image_pair_by_role,
                    duration_sec=duration_sec,
                    control_min_target=control_min_target,
                    control_max_target=control_max_target,
                    rois_by_role=rois_by_role,
                )

            rows = result["rows"]
            lines = [
                "Analysis complete",
                "",
                "role | delta_e_scalar | rate | target",
            ]
            for row in rows:
                target = row.get("interpolated_target")
                target_text = "" if target is None else f"{target:.6f}"
                lines.append(
                    f"{row['role']} | {row['delta_e_scalar']:.6f} | {row['rate']:.9f} | {target_text}"
                )
                start_roi = row.get("start_roi")
                end_roi = row.get("end_roi")
                if start_roi is not None and end_roi is not None:
                    lines.append(f"  ROI start={start_roi} end={end_roi}")

                start_lab = row.get("start_lab_mean")
                end_lab = row.get("end_lab_mean")
                if start_lab is not None and end_lab is not None:
                    lines.append(
                        "  Lab start="
                        f"({start_lab[0]:.3f},{start_lab[1]:.3f},{start_lab[2]:.3f}) "
                        "end="
                        f"({end_lab[0]:.3f},{end_lab[1]:.3f},{end_lab[2]:.3f})"
                    )

            self._finish_run("\n".join(lines))
        except Exception as exc:
            details = traceback.format_exc(limit=4)
            self._finish_run(f"Error: {exc}\n\n{details}")

    def _finish_run(self, message: str) -> None:
        Clock.schedule_once(lambda _: self._set_output(message), 0)

    def _set_output(self, message: str) -> None:
        self.output_label.text = message
        self.status_label.text = "Complete" if not message.startswith("Error:") else "Error"
        self.run_btn.disabled = False


if __name__ == "__main__":
    ColorAnalyzerMobileApp().run()
