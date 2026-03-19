import os
import threading
import traceback
from typing import Dict, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider

try:
    from plyer import filechooser
except Exception:
    filechooser = None

TEXT_COLOR = (0.93, 0.95, 0.98, 1)
MUTED_TEXT_COLOR = (0.68, 0.73, 0.81, 1)
BTN_BG = (0.21, 0.43, 0.68, 1)


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


def _resolve_content_uri(uri: str) -> Optional[str]:
    if not isinstance(uri, str):
        return None
    if not uri.startswith("content://"):
        return uri

    try:
        from jnius import autoclass

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
                    return path
        if cursor:
            cursor.close()
    except Exception:
        pass

    return uri


class DishAlignImage(Image):
    def __init__(self, **kwargs):
        super().__init__(allow_stretch=True, keep_ratio=True, **kwargs)
        self.circle_center = None
        self.radius_scale = 0.42
        self.dragging = False
        self._touch_offset = (0.0, 0.0)

        self.bind(pos=lambda *_: self._redraw_overlay())
        self.bind(size=lambda *_: self._redraw_overlay())
        self.bind(texture=lambda *_: self._reset_overlay())

    def _display_rect(self) -> Tuple[float, float, float, float]:
        draw_w, draw_h = self.norm_image_size
        x0 = self.center_x - draw_w / 2.0
        y0 = self.center_y - draw_h / 2.0
        return (x0, y0, draw_w, draw_h)

    def _reset_overlay(self) -> None:
        x0, y0, w, h = self._display_rect()
        if w > 2 and h > 2:
            self.circle_center = (x0 + w / 2.0, y0 + h / 2.0)
        self._redraw_overlay()

    def set_radius_scale(self, value: float) -> None:
        self.radius_scale = max(0.2, min(0.49, float(value)))
        self._redraw_overlay()

    def _overlay_radius(self) -> float:
        x0, y0, w, h = self._display_rect()
        return min(w, h) * self.radius_scale

    def _redraw_overlay(self) -> None:
        self.canvas.after.clear()
        if self.texture is None:
            return

        x0, y0, w, h = self._display_rect()
        if w <= 2 or h <= 2:
            return

        if self.circle_center is None:
            self.circle_center = (x0 + w / 2.0, y0 + h / 2.0)

        cx, cy = self.circle_center
        r = self._overlay_radius()

        with self.canvas.after:
            Color(0.2, 0.92, 0.9, 1.0)
            Line(circle=(cx, cy, r), width=2.0)

            # subtle crosshair for alignment
            Line(points=[cx - r, cy, cx + r, cy], width=1.2)
            Line(points=[cx, cy - r, cx, cy + r], width=1.2)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if self.texture is None:
            return True

        if self.circle_center is None:
            self._reset_overlay()

        cx, cy = self.circle_center
        r = self._overlay_radius()
        dist_sq = (touch.x - cx) ** 2 + (touch.y - cy) ** 2

        if dist_sq <= (r * r):
            self.dragging = True
            self._touch_offset = (touch.x - cx, touch.y - cy)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if not self.dragging:
            return super().on_touch_move(touch)

        x0, y0, w, h = self._display_rect()
        r = self._overlay_radius()
        ox, oy = self._touch_offset

        cx = min(max(touch.x - ox, x0 + r), x0 + w - r)
        cy = min(max(touch.y - oy, y0 + r), y0 + h - r)
        self.circle_center = (cx, cy)
        self._redraw_overlay()
        return True

    def on_touch_up(self, touch):
        if self.dragging:
            self.dragging = False
            return True
        return super().on_touch_up(touch)

    def get_circle_pixels(self) -> Optional[Tuple[int, int, int]]:
        if self.texture is None or self.circle_center is None:
            return None

        x0, y0, w, h = self._display_rect()
        if w <= 2 or h <= 2:
            return None

        cx, cy = self.circle_center
        r = self._overlay_radius()

        img_w, img_h = self.texture.size

        px = int(((cx - x0) / w) * img_w)
        py = int((1.0 - ((cy - y0) / h)) * img_h)
        pr = int((r / min(w, h)) * min(img_w, img_h))

        px = max(0, min(px, img_w - 1))
        py = max(0, min(py, img_h - 1))
        pr = max(20, min(pr, min(img_w, img_h) // 2))
        return (px, py, pr)


class ColorAnalyzerMobileApp(App):
    def build(self):
        Window.clearcolor = (0.08, 0.1, 0.13, 1)

        root = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))

        header = _label(
            text="Microbiological Surface Scanner",
            size_hint_y=None,
            height=dp(40),
            halign="left",
            valign="middle",
            font_size="20sp",
        )
        header.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        root.add_widget(header)

        subhead = _label(
            text="Upload one CompactDry dish photo, align the circular mesh, then analyze.",
            muted=True,
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
        )
        subhead.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        root.add_widget(subhead)

        content_scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        picker_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        self.pick_button = _button(text="Pick Dish Image", size_hint_x=0.36)
        self.pick_button.bind(on_release=lambda *_: self.pick_image())
        self.file_label = _label(text="No image selected", muted=True, halign="left", valign="middle")
        self.file_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        picker_row.add_widget(self.pick_button)
        picker_row.add_widget(self.file_label)
        content.add_widget(picker_row)

        align_label = _label(
            text="Alignment: drag circle to match dish edge, then adjust radius",
            muted=True,
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
        )
        align_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        content.add_widget(align_label)

        self.align_image = DishAlignImage(size_hint_y=None, height=dp(340))
        content.add_widget(self.align_image)

        slider_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        slider_row.add_widget(_label(text="Circle Radius", size_hint_x=0.25, halign="left", valign="middle"))
        self.radius_slider = Slider(min=0.2, max=0.49, value=0.42)
        self.radius_slider.bind(value=lambda _, v: self.align_image.set_radius_scale(v))
        slider_row.add_widget(self.radius_slider)
        content.add_widget(slider_row)

        content_scroll.add_widget(content)
        root.add_widget(content_scroll)

        action_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.analyze_button = _button(text="Analyze Surface", size_hint_x=0.36)
        self.analyze_button.bind(on_release=lambda *_: self.run_analysis())
        self.status_label = _label(text="Ready", muted=True, halign="left", valign="middle")
        self.status_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        action_row.add_widget(self.analyze_button)
        action_row.add_widget(self.status_label)
        root.add_widget(action_row)

        results_title = _label(
            text="Result Summary",
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        results_title.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        root.add_widget(results_title)

        table_scroll = ScrollView(size_hint_y=None, height=dp(160), do_scroll_x=False)
        self.results_grid = GridLayout(
            cols=3,
            size_hint_y=None,
            row_default_height=dp(34),
            row_force_default=True,
            spacing=dp(4),
            padding=dp(4),
        )
        self.results_grid.bind(minimum_height=self.results_grid.setter("height"))
        table_scroll.add_widget(self.results_grid)
        root.add_widget(table_scroll)

        self.note_label = _label(
            text="",
            muted=True,
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(64),
        )
        self.note_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        root.add_widget(self.note_label)

        self._render_empty_table()
        self._request_android_permissions()
        self.selected_image_path: Optional[str] = None
        return root

    def _table_cell(self, text: str, head: bool = False) -> Label:
        cell = Label(
            text=text,
            color=TEXT_COLOR if head else MUTED_TEXT_COLOR,
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(34),
            bold=head,
        )
        cell.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        return cell

    def _render_empty_table(self) -> None:
        self.results_grid.clear_widgets()
        for col in ["Metric", "Value", "Interpretation"]:
            self.results_grid.add_widget(self._table_cell(col, head=True))

        rows = [
            ("Total CFU/mL", "-", "Awaiting analysis"),
            ("E. coli signal", "-", "Deep Purple / Blue"),
            ("Coliform signal", "-", "Red / Pink"),
            ("Clean zones", "-", "Delta E < 15"),
        ]
        for metric, value, note in rows:
            self.results_grid.add_widget(self._table_cell(metric))
            self.results_grid.add_widget(self._table_cell(value))
            self.results_grid.add_widget(self._table_cell(note))

    def _render_results(self, result: Dict[str, object]) -> None:
        self.results_grid.clear_widgets()
        for col in ["Metric", "Value", "Interpretation"]:
            self.results_grid.add_widget(self._table_cell(col, head=True))

        total_cfu = float(result.get("total_cfu_ml", 0.0))
        ecoli_cells = int(result.get("ecoli_cells", 0))
        coliform_cells = int(result.get("coliform_cells", 0))
        clean_cells = int(result.get("clean_cells", 0))

        rows = [
            ("Total CFU/mL", f"{total_cfu:.2f}", "Estimated concentration"),
            ("E. coli signal", str(ecoli_cells), "Fecal Contamination (High Risk)"),
            ("Coliform signal", str(coliform_cells), "Environmental Bacteria (General)"),
            ("Clean zones", str(clean_cells), "Delta E < 15 (Clean / Sterile)"),
        ]

        for metric, value, note in rows:
            self.results_grid.add_widget(self._table_cell(metric))
            self.results_grid.add_widget(self._table_cell(value))
            self.results_grid.add_widget(self._table_cell(note))

        mesh_rgb = result.get("mesh_white_rgb", (0, 0, 0))
        self.note_label.text = (
            "Internal baseline (mesh white RGB): "
            f"{mesh_rgb}. Spatial model active: DeltaE thresholding + grid area summation."
        )

    def _request_android_permissions(self) -> None:
        try:
            from android.permissions import Permission, request_permissions

            read_media_images = getattr(Permission, "READ_MEDIA_IMAGES", Permission.READ_EXTERNAL_STORAGE)
            read_media_video = getattr(Permission, "READ_MEDIA_VIDEO", Permission.READ_EXTERNAL_STORAGE)

            request_permissions(
                [
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    read_media_images,
                    read_media_video,
                ]
            )
        except Exception:
            pass

    def pick_image(self) -> None:
        if filechooser is None:
            self.file_label.text = "File picker unavailable"
            return

        try:
            selection = filechooser.open_file(
                on_selection=self._on_image_selected,
                filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"],
            )
            if selection:
                self._on_image_selected(selection)
        except Exception as exc:
            self.file_label.text = f"Picker error: {exc}"

    def _extract_selected_path(self, selection=None, *args, **kwargs) -> Optional[str]:
        candidate = selection
        if candidate is None and args:
            candidate = args[0]
        if candidate is None:
            candidate = kwargs.get("selection") or kwargs.get("path")

        try:
            path = candidate[0] if isinstance(candidate, (list, tuple)) else str(candidate)
        except (TypeError, IndexError):
            path = str(candidate)

        if not path or path.strip() == "":
            return None

        return _resolve_content_uri(path)

    def _on_image_selected(self, selection=None, *args, **kwargs) -> None:
        path = self._extract_selected_path(selection, *args, **kwargs)
        if not path:
            self.file_label.text = "Selection failed"
            return

        self.selected_image_path = path
        filename = os.path.basename(path)

        def _set_preview(_):
            self.file_label.text = filename or "image selected"
            self.align_image.source = path
            self.align_image._reset_overlay()

        Clock.schedule_once(_set_preview, 0)

    def run_analysis(self) -> None:
        if not self.selected_image_path:
            self.status_label.text = "Pick an image first"
            return

        self.analyze_button.disabled = True
        self.status_label.text = "Analyzing..."
        self.note_label.text = ""
        threading.Thread(target=self._run_analysis_worker, daemon=True).start()

    def _run_analysis_worker(self) -> None:
        try:
            from Analyzer import analyze_microbe_upload

            manual_circle = self.align_image.get_circle_pixels()
            result = analyze_microbe_upload(self.selected_image_path, manual_circle=manual_circle)
            Clock.schedule_once(lambda _: self._set_success(result), 0)
        except Exception as exc:
            details = traceback.format_exc(limit=4)
            Clock.schedule_once(lambda _: self._set_error(f"{exc}\n\n{details}"), 0)

    def _set_success(self, result: Dict[str, object]) -> None:
        self._render_results(result)
        self.status_label.text = "Complete"
        self.analyze_button.disabled = False

    def _set_error(self, message: str) -> None:
        self._render_empty_table()
        self.note_label.text = f"Error: {message}"
        self.status_label.text = "Error"
        self.analyze_button.disabled = False


if __name__ == "__main__":
    ColorAnalyzerMobileApp().run()
