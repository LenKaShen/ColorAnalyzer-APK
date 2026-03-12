import os
import threading
import traceback
from functools import partial
from typing import Dict, Optional
from typing import Dict, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
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


class RolePanel(BoxLayout):
    def __init__(self, role: str, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(6), size_hint_y=None, **kwargs)
        self.role = role
        self.height = dp(180)

        self.video_path: Optional[str] = None
        self.image_start_path: Optional[str] = None
        self.image_end_path: Optional[str] = None

        self.add_widget(_label(text=f"Role: {role}", size_hint_y=None, height=dp(24)))

        video_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.video_btn = _button(text="Pick Video")
        self.video_btn.bind(on_release=lambda *_: self.pick_video())
        self.video_label = _label(text="No video selected", muted=True, halign="left", valign="middle")
        self.video_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        video_row.add_widget(self.video_btn)
        video_row.add_widget(self.video_label)
        self.add_widget(video_row)

        self.add_widget(
            _label(
                text="Or use Frame 1 + Last Frame images",
                muted=True,
                size_hint_y=None,
                height=dp(20),
            )
        )

        start_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.start_img_btn = _button(text="Pick Frame 1 Image")
        self.start_img_btn.bind(on_release=lambda *_: self.pick_image("start"))
        self.start_img_label = _label(text="No frame 1 image", muted=True, halign="left", valign="middle")
        self.start_img_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        start_row.add_widget(self.start_img_btn)
        start_row.add_widget(self.start_img_label)
        self.add_widget(start_row)

        end_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.end_img_btn = _button(text="Pick Last Frame Image")
        self.end_img_btn.bind(on_release=lambda *_: self.pick_image("end"))
        self.end_img_label = _label(text="No last frame image", muted=True, halign="left", valign="middle")
        self.end_img_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        end_row.add_widget(self.end_img_btn)
        end_row.add_widget(self.end_img_label)
        self.add_widget(end_row)

    def pick_video(self) -> None:
        if filechooser is None:
            self.video_label.text = "File picker unavailable"
            return
        filechooser.open_file(on_selection=self._on_video_selected, filters=["*.mp4", "*.mov", "*.avi", "*.mkv"])

    def pick_image(self, phase: str) -> None:
        if filechooser is None:
            if phase == "start":
                self.start_img_label.text = "File picker unavailable"
            else:
                self.end_img_label.text = "File picker unavailable"
            return
        callback = partial(self._on_image_selected, phase)
        filechooser.open_file(on_selection=callback, filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"])

    def _on_video_selected(self, selection):
        if not selection:
            return
        path = selection[0]
        self.video_path = path
        name = os.path.basename(path)
        Clock.schedule_once(lambda _: setattr(self.video_label, "text", name))

    def _on_image_selected(self, phase: str, selection):
        if not selection:
            return
        path = selection[0]
        name = os.path.basename(path)
        if phase == "start":
            self.image_start_path = path
            Clock.schedule_once(lambda _: setattr(self.start_img_label, "text", name))
        else:
            self.image_end_path = path
            Clock.schedule_once(lambda _: setattr(self.end_img_label, "text", name))


class ColorAnalyzerMobileApp(App):
    def build(self):
        Window.clearcolor = (0.08, 0.1, 0.13, 1)

        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        header = Label(
            text="Offline Color Analyzer",
            size_hint_y=None,
            height=dp(34),
            font_size="20sp",
            color=TEXT_COLOR,
        )
        root.add_widget(header)

        duration_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        duration_row.add_widget(_label(text="Duration h:m:s", size_hint_x=0.35))
        self.hours_input = _text_input(text="0", input_filter="int")
        self.minutes_input = _text_input(text="0", input_filter="int")
        self.seconds_input = _text_input(text="10", input_filter="int")
        duration_row.add_widget(self.hours_input)
        duration_row.add_widget(self.minutes_input)
        duration_row.add_widget(self.seconds_input)
        root.add_widget(duration_row)

        calibration_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        calibration_row.add_widget(_label(text="Control Min Target", size_hint_x=0.35))
        self.control_min_input = _text_input(text="", input_filter="float")
        calibration_row.add_widget(self.control_min_input)
        calibration_row.add_widget(_label(text="Control Max Target", size_hint_x=0.35))
        self.control_max_input = _text_input(text="", input_filter="float")
        calibration_row.add_widget(self.control_max_input)
        root.add_widget(calibration_row)

        self.role_panels: Dict[str, RolePanel] = {}
        scroll = ScrollView()
        role_container = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        role_container.bind(minimum_height=role_container.setter("height"))

        for role in ROLE_OPTIONS:
            panel = RolePanel(role=role)
            self.role_panels[role] = panel
            role_container.add_widget(panel)

        scroll.add_widget(role_container)
        root.add_widget(scroll)

        self.run_btn = _button(text="Run Analysis", size_hint_y=None, height=dp(46))
        self.run_btn.bind(on_release=lambda *_: self.run_analysis())
        root.add_widget(self.run_btn)

        self.output_label = _label(text="Ready", halign="left", valign="top")
        self.output_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        root.add_widget(self.output_label)

        self._request_android_permissions()
        return root

    def _request_android_permissions(self) -> None:
        try:
            from android.permissions import Permission, request_permissions

            request_permissions(
                [
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                ]
            )
        except Exception:
            # Non-Android runtime or unavailable permission API.
            pass

    def run_analysis(self) -> None:
        self.run_btn.disabled = True
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
                result = analyze_three_image_pairs(
                    image_pair_by_role=image_pair_by_role,
                    duration_sec=duration_sec,
                    control_min_target=control_min_target,
                    control_max_target=control_max_target,
                )
            else:
                raise ValueError(
                    "Use one input type for all roles: all videos or all frame image pairs"
                )

            rows = result["rows"]
            lines = ["Analysis complete", "", "role | delta_e_scalar | rate | target"]
            for row in rows:
                target = row.get("interpolated_target")
                target_text = "" if target is None else f"{target:.6f}"
                lines.append(
                    f"{row['role']} | {row['delta_e_scalar']:.6f} | {row['rate']:.9f} | {target_text}"
                )

            self._finish_run("\n".join(lines))
        except Exception as exc:
            details = traceback.format_exc(limit=4)
            self._finish_run(f"Error: {exc}\n\n{details}")

    def _finish_run(self, message: str) -> None:
        Clock.schedule_once(lambda _: self._set_output(message), 0)

    def _set_output(self, message: str) -> None:
        self.output_label.text = message
        self.run_btn.disabled = False


if __name__ == "__main__":
    ColorAnalyzerMobileApp().run()
