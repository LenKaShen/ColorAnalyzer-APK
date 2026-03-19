import io
import os
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np


def _load_rgb_image(path: str) -> np.ndarray:
    from PIL import Image

    if not isinstance(path, str) or not path.strip():
        raise ValueError("Invalid image path")

    if os.path.isfile(path):
        with Image.open(path) as image:
            return np.array(image.convert("RGB"), dtype=np.uint8)

    if path.startswith("content://"):
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()
            uri_obj = autoclass("android.net.Uri").parse(path)
            stream = resolver.openInputStream(uri_obj)

            if stream is None:
                raise RuntimeError("Could not open content URI stream")

            chunks = bytearray()
            while True:
                b = stream.read()
                if b == -1:
                    break
                chunks.append(b & 0xFF)
            stream.close()

            with Image.open(io.BytesIO(bytes(chunks))) as image:
                return np.array(image.convert("RGB"), dtype=np.uint8)
        except Exception as exc:
            raise RuntimeError(f"Could not read content URI: {exc}") from exc

    raise RuntimeError(f"Image not found: {path}")


def srgb_to_lab(rgb_array: np.ndarray) -> np.ndarray:
    rgb_float = rgb_array.astype(np.float64) / 255.0

    linear = np.where(
        rgb_float <= 0.04045,
        rgb_float / 12.92,
        ((rgb_float + 0.055) / 1.055) ** 2.4,
    )

    x = linear[..., 0] * 0.4124564 + linear[..., 1] * 0.3575761 + linear[..., 2] * 0.1804375
    y = linear[..., 0] * 0.2126729 + linear[..., 1] * 0.7151522 + linear[..., 2] * 0.0721750
    z = linear[..., 0] * 0.0193339 + linear[..., 1] * 0.1191920 + linear[..., 2] * 0.9503041

    xn, yn, zn = 0.95047, 1.00000, 1.08883
    xr, yr, zr = x / xn, y / yn, z / zn

    delta = 6.0 / 29.0
    delta3 = delta**3
    inv_3delta2 = 1.0 / (3.0 * delta * delta)
    offset = 4.0 / 29.0

    def f(t: np.ndarray) -> np.ndarray:
        return np.where(t > delta3, np.cbrt(t), t * inv_3delta2 + offset)

    fx, fy, fz = f(xr), f(yr), f(zr)
    l = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return np.stack([l, a, b], axis=-1)


def calculate_ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    l1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    l2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]

    k_l = 1.0
    k_c = 1.0
    k_h = 1.0

    c1 = np.sqrt(a1**2 + b1**2)
    c2 = np.sqrt(a2**2 + b2**2)
    c_bar = (c1 + c2) / 2.0

    c_bar7 = c_bar**7
    g = 0.5 * (1.0 - np.sqrt(c_bar7 / (c_bar7 + 25.0**7 + 1e-12)))

    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = np.sqrt(a1p**2 + b1**2)
    c2p = np.sqrt(a2p**2 + b2**2)

    h1p = (np.degrees(np.arctan2(b1, a1p)) + 360.0) % 360.0
    h2p = (np.degrees(np.arctan2(b2, a2p)) + 360.0) % 360.0

    dlp = l2 - l1
    dcp = c2p - c1p

    dhp = h2p - h1p
    dhp = np.where(dhp > 180.0, dhp - 360.0, dhp)
    dhp = np.where(dhp < -180.0, dhp + 360.0, dhp)
    dhp = np.where((c1p * c2p) == 0.0, 0.0, dhp)

    dhp_rad = np.radians(dhp)
    d_hp = 2.0 * np.sqrt(c1p * c2p) * np.sin(dhp_rad / 2.0)

    l_bar_p = (l1 + l2) / 2.0
    c_bar_p = (c1p + c2p) / 2.0

    abs_h = np.abs(h1p - h2p)
    h_bar_p = (h1p + h2p) / 2.0
    h_bar_p = np.where((c1p * c2p) == 0.0, h1p + h2p, h_bar_p)
    h_bar_p = np.where(((c1p * c2p) != 0.0) & (abs_h > 180.0) & ((h1p + h2p) < 360.0), (h1p + h2p + 360.0) / 2.0, h_bar_p)
    h_bar_p = np.where(((c1p * c2p) != 0.0) & (abs_h > 180.0) & ((h1p + h2p) >= 360.0), (h1p + h2p - 360.0) / 2.0, h_bar_p)

    t = (
        1.0
        - 0.17 * np.cos(np.radians(h_bar_p - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * h_bar_p))
        + 0.32 * np.cos(np.radians(3.0 * h_bar_p + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * h_bar_p - 63.0))
    )

    delta_theta = 30.0 * np.exp(-(((h_bar_p - 275.0) / 25.0) ** 2))
    c_bar_p7 = c_bar_p**7
    r_c = 2.0 * np.sqrt(c_bar_p7 / (c_bar_p7 + 25.0**7 + 1e-12))

    s_l = 1.0 + (0.015 * ((l_bar_p - 50.0) ** 2)) / np.sqrt(20.0 + ((l_bar_p - 50.0) ** 2))
    s_c = 1.0 + 0.045 * c_bar_p
    s_h = 1.0 + 0.015 * c_bar_p * t

    r_t = -np.sin(np.radians(2.0 * delta_theta)) * r_c

    l_term = dlp / (k_l * s_l)
    c_term = dcp / (k_c * s_c)
    h_term = d_hp / (k_h * s_h)

    return np.sqrt(l_term**2 + c_term**2 + h_term**2 + r_t * c_term * h_term)


def _center_square_crop(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    side = min(h, w)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    return img[y0 : y0 + side, x0 : x0 + side]


def _resize_1000(img: np.ndarray) -> np.ndarray:
    from PIL import Image

    pil = Image.fromarray(img.astype(np.uint8), mode="RGB")
    resample = getattr(getattr(Image, "Resampling", Image), "BILINEAR", Image.BILINEAR)
    return np.array(pil.resize((1000, 1000), resample), dtype=np.uint8)


def perspective_correction(image_data: np.ndarray, manual_circle: Optional[Tuple[int, int, int]] = None) -> np.ndarray:
    if image_data.ndim != 3 or image_data.shape[2] != 3:
        raise ValueError("Image must be RGB")

    h, w = image_data.shape[:2]

    if manual_circle is not None:
        cx, cy, radius = [int(v) for v in manual_circle]
        radius = max(20, radius)
        x0 = max(0, cx - radius)
        y0 = max(0, cy - radius)
        x1 = min(w, cx + radius)
        y1 = min(h, cy + radius)
        cropped = image_data[y0:y1, x0:x1]
        if cropped.size > 0:
            return _resize_1000(_center_square_crop(cropped))

    # Fallback: center crop. This keeps pipeline stable if auto dish detection is imperfect.
    return _resize_1000(_center_square_crop(image_data))


def get_mesh_reference(processed_img: np.ndarray) -> np.ndarray:
    rgb = processed_img.astype(np.float64) / 255.0
    max_rgb = np.max(rgb, axis=2)
    min_rgb = np.min(rgb, axis=2)
    sat = np.where(max_rgb == 0.0, 0.0, (max_rgb - min_rgb) / (max_rgb + 1e-8))
    val = max_rgb

    # Mesh white proxy: low saturation + high brightness.
    white_like = (sat < 0.18) & (val > 0.55)

    if np.count_nonzero(white_like) < 500:
        white_like = (sat < 0.25) & (val > 0.45)

    if np.count_nonzero(white_like) < 100:
        # Last fallback: brightest 20% pixels.
        threshold = np.quantile(val, 0.8)
        white_like = val >= threshold

    baseline = processed_img[white_like].reshape(-1, 3).mean(axis=0)
    return baseline.reshape(1, 1, 3).astype(np.uint8)


def segment_into_grid(processed_img: np.ndarray, size: int = 30) -> Iterable[np.ndarray]:
    h, w = processed_img.shape[:2]
    cell_h = max(1, h // size)
    cell_w = max(1, w // size)

    for gy in range(size):
        for gx in range(size):
            y0 = gy * cell_h
            x0 = gx * cell_w
            y1 = h if gy == size - 1 else (gy + 1) * cell_h
            x1 = w if gx == size - 1 else (gx + 1) * cell_w
            yield processed_img[y0:y1, x0:x1]


def analyze_microbe_upload(image_path: str, manual_circle: Optional[Tuple[int, int, int]] = None) -> Dict[str, object]:
    image_data = _load_rgb_image(image_path)
    processed_img = perspective_correction(image_data, manual_circle=manual_circle)

    mesh_baseline_rgb = get_mesh_reference(processed_img)
    mesh_lab = srgb_to_lab(mesh_baseline_rgb)[0, 0, :]

    grid_size = 30
    grid_results: List[Dict[str, float]] = []

    ecoli_cells = 0
    coliform_cells = 0
    clean_cells = 0

    for square in segment_into_grid(processed_img, size=grid_size):
        cell_lab = srgb_to_lab(square)
        diff_matrix = calculate_ciede2000(cell_lab, mesh_lab)

        purple_mask = (diff_matrix > 25.0) & (cell_lab[:, :, 2] < -5.0)
        red_mask = (diff_matrix > 18.0) & (cell_lab[:, :, 1] > 14.0) & (cell_lab[:, :, 2] > -2.0)

        area_ratio = float(np.sum(purple_mask)) / float(purple_mask.size)

        if area_ratio < 0.75:
            cfu = area_ratio * 300.0
        else:
            if np.any(purple_mask):
                mean_l = float(np.mean(cell_lab[:, :, 0][purple_mask]))
                cfu = 10 ** ((100.0 - mean_l) / 10.0)
            else:
                cfu = 0.0

        if np.count_nonzero(purple_mask) > 0:
            ecoli_cells += 1
            organism = "E. coli"
            significance = "Fecal Contamination (High Risk)"
        elif np.count_nonzero(red_mask) > 0:
            coliform_cells += 1
            organism = "Coliforms"
            significance = "Environmental Bacteria (General)"
        else:
            clean_cells += 1
            organism = "None"
            significance = "Clean / Sterile"

        grid_results.append(
            {
                "cfu": float(cfu),
                "area_ratio": area_ratio,
                "organism": organism,
                "significance": significance,
            }
        )

    total_cfu = float(sum(cell["cfu"] for cell in grid_results))

    return {
        "total_cfu_ml": total_cfu,
        "grid_size": grid_size,
        "mesh_white_rgb": tuple(int(v) for v in mesh_baseline_rgb[0, 0]),
        "ecoli_cells": ecoli_cells,
        "coliform_cells": coliform_cells,
        "clean_cells": clean_cells,
        "grid_results": grid_results,
    }
