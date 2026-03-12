import os
import threading
import traceback
from functools import partial
from typing import Dict, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

try:
    from plyer import filechooser
except Exception:
    filechooser = None


ROLE_OPTIONS = ["control_min", "control_max", "sample"]


class RolePanel(BoxLayout):
    def __init__(self, role: str, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(6), size_hint_y=None, **kwargs)
        self.role = role
        self.height = dp(300)

        self.video_path: Optional[str] = None
        self.image_start_path: Optional[str] = None
        self.image_end_path: Optional[str] = None

        self.add_widget(Label(text=f"Role: {role}", size_hint_y=None, height=dp(24)))

        video_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.video_btn = Button(text="Pick Video")
        self.video_btn.bind(on_release=lambda *_: self.pick_video())
        self.video_label = Label(text="No video selected", halign="left", valign="middle")
        self.video_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        video_row.add_widget(self.video_btn)
        video_row.add_widget(self.video_label)
        self.add_widget(video_row)

        start_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.start_img_btn = Button(text="Pick Start Image")
        self.start_img_btn.bind(on_release=lambda *_: self.pick_image("start"))
        self.start_img_label = Label(text="No start image", halign="left", valign="middle")
        self.start_img_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        start_row.add_widget(self.start_img_btn)
        start_row.add_widget(self.start_img_label)
        self.add_widget(start_row)

        end_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.end_img_btn = Button(text="Pick End Image")
        self.end_img_btn.bind(on_release=lambda *_: self.pick_image("end"))
        self.end_img_label = Label(text="No end image", halign="left", valign="middle")
        self.end_img_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        end_row.add_widget(self.end_img_btn)
        end_row.add_widget(self.end_img_label)
        self.add_widget(end_row)

        time_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        time_row.add_widget(Label(text="Video Start Time (s)", size_hint_x=0.5))
        self.start_time_input = TextInput(text="0", multiline=False, input_filter="float")
        time_row.add_widget(self.start_time_input)
        self.add_widget(time_row)

        self.start_roi_inputs = self._add_roi_row("Start ROI x,y,w,h")
        self.end_roi_inputs = self._add_roi_row("End ROI x,y,w,h")

    def _add_roi_row(self, label_text: str):
        row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(4))
        row.add_widget(Label(text=label_text, size_hint_x=0.38))

        x_input = TextInput(text="0", multiline=False, input_filter="int")
        y_input = TextInput(text="0", multiline=False, input_filter="int")
        w_input = TextInput(text="0", multiline=False, input_filter="int")
        h_input = TextInput(text="0", multiline=False, input_filter="int")

        row.add_widget(x_input)
        row.add_widget(y_input)
        row.add_widget(w_input)
        row.add_widget(h_input)
        self.add_widget(row)
        return {"x": x_input, "y": y_input, "w": w_input, "h": h_input}

    def get_roi_values(self) -> Dict[str, Tuple[int, int, int, int]]:
        def parse(inputs):
            return (
                int(inputs["x"].text or "0"),
                int(inputs["y"].text or "0"),
                int(inputs["w"].text or "0"),
                int(inputs["h"].text or "0"),
            )

        return {"start": parse(self.start_roi_inputs), "end": parse(self.end_roi_inputs)}

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
        if selection:
            self.video_path = selection[0]
            self.video_label.text = os.path.basename(self.video_path)

    def _on_image_selected(self, phase: str, selection):
        if not selection:
            return
        selected = selection[0]
        if phase == "start":
            self.image_start_path = selected
            self.start_img_label.text = os.path.basename(selected)
        else:
            self.image_end_path = selected
            self.end_img_label.text = os.path.basename(selected)


class ColorAnalyzerMobileApp(App):
    def build(self):
        Window.clearcolor = (0.97, 0.98, 0.99, 1)

        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        header = Label(
            text="Offline Color Analyzer",
            size_hint_y=None,
            height=dp(34),
            font_size="20sp",
        )
        root.add_widget(header)

        mode_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        mode_row.add_widget(Label(text="Input Mode", size_hint_x=0.25))
        self.mode_spinner = Spinner(text="Videos", values=["Videos", "Image Pairs"])
        mode_row.add_widget(self.mode_spinner)
        root.add_widget(mode_row)

        duration_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        duration_row.add_widget(Label(text="Duration h:m:s", size_hint_x=0.35))
        self.hours_input = TextInput(text="0", multiline=False, input_filter="int")
        self.minutes_input = TextInput(text="0", multiline=False, input_filter="int")
        self.seconds_input = TextInput(text="10", multiline=False, input_filter="int")
        duration_row.add_widget(self.hours_input)
        duration_row.add_widget(self.minutes_input)
        duration_row.add_widget(self.seconds_input)
        root.add_widget(duration_row)

        calibration_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        calibration_row.add_widget(Label(text="Control Min Target", size_hint_x=0.35))
        self.control_min_input = TextInput(text="", multiline=False, input_filter="float")
        calibration_row.add_widget(self.control_min_input)
        calibration_row.add_widget(Label(text="Control Max Target", size_hint_x=0.35))
        self.control_max_input = TextInput(text="", multiline=False, input_filter="float")
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

        self.run_btn = Button(text="Run Analysis", size_hint_y=None, height=dp(46))
        self.run_btn.bind(on_release=lambda *_: self.run_analysis())
        root.add_widget(self.run_btn)

        self.output_label = Label(text="Ready", halign="left", valign="top")
        self.output_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        root.add_widget(self.output_label)

        self.mode_spinner.bind(text=lambda _, mode: self._on_mode_change(mode))
        self._on_mode_change(self.mode_spinner.text)

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

    def _on_mode_change(self, mode: str) -> None:
        is_video = mode == "Videos"
        for panel in self.role_panels.values():
            panel.video_btn.disabled = not is_video
            panel.start_time_input.disabled = not is_video
            panel.start_img_btn.disabled = is_video
            panel.end_img_btn.disabled = is_video

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

            if self.mode_spinner.text == "Videos":
                video_by_role: Dict[str, str] = {}
                start_time_by_role: Dict[str, float] = {}
                rois_by_role: Dict[str, Dict[str, Tuple[int, int, int, int]]] = {}
                for role, panel in self.role_panels.items():
                    if not panel.video_path:
                        raise ValueError(f"Select a video for role: {role}")
                    video_by_role[role] = panel.video_path
                    start_time_by_role[role] = float(panel.start_time_input.text or "0")
                    rois_by_role[role] = panel.get_roi_values()

                result = analyze_three_videos(
                    video_by_role=video_by_role,
                    start_time_by_role=start_time_by_role,
                    duration_sec=duration_sec,
                    control_min_target=control_min_target,
                    control_max_target=control_max_target,
                    rois_by_role=rois_by_role,
                )
            else:
                image_pair_by_role: Dict[str, Tuple[str, str]] = {}
                rois_by_role: Dict[str, Dict[str, Tuple[int, int, int, int]]] = {}
                for role, panel in self.role_panels.items():
                    if not panel.image_start_path or not panel.image_end_path:
                        raise ValueError(f"Select start and end images for role: {role}")
                    image_pair_by_role[role] = (panel.image_start_path, panel.image_end_path)
                    rois_by_role[role] = panel.get_roi_values()

                result = analyze_three_image_pairs(
                    image_pair_by_role=image_pair_by_role,
                    duration_sec=duration_sec,
                    control_min_target=control_min_target,
                    control_max_target=control_max_target,
                    rois_by_role=rois_by_role,
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
