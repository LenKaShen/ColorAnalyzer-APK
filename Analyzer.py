import io
import os
from collections import deque
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np


NOISE_FLOOR_DE = 20.0
PURPLE_B_THRESHOLD = -5.0
DEEP_INDIGO_L_THRESHOLD = 40.0
DEEP_INDIGO_B_THRESHOLD = -15.0
CONFLUENT_AREA_THRESHOLD = 0.70
GRID_SIZE_DEFAULT = 30
MIN_CLUSTER_PIXELS = 4


def _circular_mask(height: int, width: int, circle: Optional[Tuple[int, int, int]]) -> np.ndarray:
    if circle is None:
        cy = height // 2
        cx = width // 2
        radius = min(height, width) // 2
    else:
        cx, cy, radius = [int(v) for v in circle]
        radius = max(10, radius)

    yy, xx = np.ogrid[:height, :width]
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= radius**2


def _laplacian_variance(gray: np.ndarray) -> float:
    # Small finite-difference Laplacian proxy for focus estimation (no OpenCV dependency).
    padded = np.pad(gray, 1, mode="edge")
    lap = (
        -4.0 * padded[1:-1, 1:-1]
        + padded[:-2, 1:-1]
        + padded[2:, 1:-1]
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
    )
    return float(np.var(lap))


def _quality_checks(processed_img: np.ndarray, dish_mask: np.ndarray, mesh_rgb: np.ndarray) -> Dict[str, object]:
    rgb = processed_img.astype(np.float64)
    in_dish = rgb[dish_mask]

    gray = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    blur_score = _laplacian_variance(gray)

    clipped = np.mean((in_dish <= 2.0) | (in_dish >= 253.0))
    mean_luminance = float(np.mean(gray[dish_mask]))
    baseline_std = float(np.std(mesh_rgb.reshape(-1)))

    warnings: List[str] = []
    severe: List[str] = []

    if blur_score < 15.0:
        severe.append("Image appears out of focus (low sharpness).")
    elif blur_score < 35.0:
        warnings.append("Image sharpness is low; colony segmentation may be unstable.")

    if clipped > 0.18:
        severe.append("Image has heavy clipping/glare or dark crush.")
    elif clipped > 0.10:
        warnings.append("Image has moderate clipping; lighting may bias color thresholds.")

    if mean_luminance < 45.0 or mean_luminance > 225.0:
        warnings.append("Exposure is outside recommended range.")

    if baseline_std > 20.0:
        warnings.append("Mesh baseline appears unstable; white reference may be noisy.")

    return {
        "blur_score": blur_score,
        "clipped_ratio": float(clipped),
        "mean_luminance": mean_luminance,
        "baseline_std": baseline_std,
        "warnings": warnings,
        "severe": severe,
    }


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


def _count_clusters(mask: np.ndarray, min_pixels: int = MIN_CLUSTER_PIXELS) -> int:
    """Count connected components (8-neighbor) in a binary mask."""
    if mask.size == 0:
        return 0

    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    clusters = 0

    neighbors = [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    ]

    for y in range(h):
        for x in range(w):
            if not mask[y, x] or visited[y, x]:
                continue

            q = deque([(y, x)])
            visited[y, x] = True
            pixels = 0

            while q:
                cy, cx = q.popleft()
                pixels += 1
                for dy, dx in neighbors:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        q.append((ny, nx))

            if pixels >= min_pixels:
                clusters += 1

    return clusters


def _count_clusters_and_clean(mask: np.ndarray, min_pixels: int = MIN_CLUSTER_PIXELS) -> Tuple[int, np.ndarray]:
    if mask.size == 0:
        return 0, mask

    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    clean = np.zeros((h, w), dtype=bool)
    clusters = 0

    neighbors = [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    ]

    for y in range(h):
        for x in range(w):
            if not mask[y, x] or visited[y, x]:
                continue

            q = deque([(y, x)])
            visited[y, x] = True
            component: List[Tuple[int, int]] = []

            while q:
                cy, cx = q.popleft()
                component.append((cy, cx))
                for dy, dx in neighbors:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        q.append((ny, nx))

            if len(component) >= min_pixels:
                clusters += 1
                for py, px in component:
                    clean[py, px] = True

    return clusters, clean


def _confluent_cfu_from_lightness(
    l_channel: np.ndarray,
    deep_indigo_mask: np.ndarray,
    square_max_cfu: float,
) -> float:
    """
    Map confluent growth intensity to a bounded logarithmic CFU scale.
    Full-plate range is 1e5..1e7; each square contributes a proportional slice.
    """
    if square_max_cfu <= 0:
        return 0.0

    if np.any(deep_indigo_mask):
        mean_l = float(np.mean(l_channel[deep_indigo_mask]))
    else:
        mean_l = float(np.mean(l_channel))

    # Normalize L*: 70 (lighter) -> low bound, 40 (deep indigo) -> high bound.
    norm = np.clip((70.0 - mean_l) / 30.0, 0.0, 1.0)
    log10_cfu = 5.0 + norm * 2.0
    full_scale_cfu = 10 ** log10_cfu

    return float(np.clip(full_scale_cfu / (GRID_SIZE_DEFAULT * GRID_SIZE_DEFAULT), 0.0, square_max_cfu))


def _bootstrap_total_ci(values: np.ndarray, n_bootstrap: int = 300) -> Tuple[float, float]:
    if values.size == 0:
        return 0.0, 0.0
    rng = np.random.default_rng(42)
    totals = []
    n = len(values)
    for _ in range(max(50, n_bootstrap)):
        sample = rng.choice(values, size=n, replace=True)
        totals.append(float(np.sum(sample)))
    ci_low, ci_high = np.percentile(np.array(totals), [2.5, 97.5])
    return float(ci_low), float(ci_high)


def analyze_microbe_upload(
    image_path: str,
    manual_circle: Optional[Tuple[int, int, int]] = None,
    dilution_factor: float = 1.0,
    plated_volume_ml: float = 1.0,
) -> Dict[str, object]:
    dilution_factor = float(dilution_factor)
    plated_volume_ml = float(plated_volume_ml)
    if dilution_factor <= 0:
        raise ValueError("Dilution factor must be > 0")
    if plated_volume_ml <= 0:
        raise ValueError("Plated volume (mL) must be > 0")

    image_data = _load_rgb_image(image_path)
    processed_img = perspective_correction(image_data, manual_circle=manual_circle)
    dish_mask = _circular_mask(processed_img.shape[0], processed_img.shape[1], manual_circle)

    mesh_baseline_rgb = get_mesh_reference(processed_img)
    mesh_lab = srgb_to_lab(mesh_baseline_rgb)[0, 0, :]

    quality = _quality_checks(processed_img, dish_mask, mesh_baseline_rgb)
    if quality["severe"]:
        raise ValueError("; ".join(quality["severe"]))

    grid_size = GRID_SIZE_DEFAULT
    grid_results: List[Dict[str, float]] = []

    ecoli_cells = 0
    coliform_cells = 0
    clean_cells = 0

    total_signal_pixels = 0
    total_pixels = 0
    total_clusters = 0
    square_max_cfu = 1e7 / float(grid_size * grid_size)  # T_max normalized by grid area

    square_cfu_values: List[float] = []
    for square in segment_into_grid(processed_img, size=grid_size):
        cell_lab = srgb_to_lab(square)
        diff_matrix = calculate_ciede2000(cell_lab, mesh_lab)

        # Signal-only masking: ignore all pixels below DeltaE noise floor.
        local_bg = diff_matrix[cell_lab[:, :, 2] >= PURPLE_B_THRESHOLD]
        if local_bg.size > 10:
            bg_med = float(np.median(local_bg))
            bg_mad = float(np.median(np.abs(local_bg - bg_med)))
            dynamic_floor = max(NOISE_FLOOR_DE, bg_med + 4.5 * bg_mad)
        else:
            dynamic_floor = NOISE_FLOOR_DE

        signal_mask = diff_matrix >= dynamic_floor
        purple_mask_raw = signal_mask & (cell_lab[:, :, 2] < PURPLE_B_THRESHOLD)
        cluster_count_raw, purple_mask = _count_clusters_and_clean(purple_mask_raw)
        deep_indigo_mask = purple_mask & (cell_lab[:, :, 0] < DEEP_INDIGO_L_THRESHOLD) & (cell_lab[:, :, 2] < DEEP_INDIGO_B_THRESHOLD)
        red_mask = (diff_matrix > 18.0) & (cell_lab[:, :, 1] > 14.0) & (cell_lab[:, :, 2] > -2.0)

        purple_pixels = int(np.count_nonzero(purple_mask))
        total_in_square = int(purple_mask.size)
        area_ratio = float(purple_pixels) / float(total_in_square)

        total_signal_pixels += purple_pixels
        total_pixels += total_in_square

        if purple_pixels == 0:
            cfu = 0.0
            cluster_count = 0
        elif area_ratio < CONFLUENT_AREA_THRESHOLD:
            # Phase 1: distinct colonies -> count connected clusters (1 cluster ~= 1 CFU).
            cluster_count = cluster_count_raw
            cfu = float(cluster_count)
        else:
            # Phase 2: confluent growth -> intensity-based bounded logarithmic estimate.
            cluster_count = 0
            cfu = _confluent_cfu_from_lightness(cell_lab[:, :, 0], deep_indigo_mask, square_max_cfu)

        total_clusters += cluster_count
        square_cfu_values.append(float(cfu))

        if purple_pixels > 0:
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
                "clusters": float(cluster_count),
                "organism": organism,
                "significance": significance,
            }
        )

    total_cfu = float(sum(cell["cfu"] for cell in grid_results))
    adjusted_cfu_ml = (total_cfu * dilution_factor) / plated_volume_ml
    square_cfu_np = np.array(square_cfu_values, dtype=np.float64)
    ci_low_raw, ci_high_raw = _bootstrap_total_ci(square_cfu_np)
    ci_low_adj = (ci_low_raw * dilution_factor) / plated_volume_ml
    ci_high_adj = (ci_high_raw * dilution_factor) / plated_volume_ml

    return {
        "total_cfu_ml": total_cfu,
        "adjusted_cfu_ml": float(adjusted_cfu_ml),
        "adjusted_cfu_ci_low": float(ci_low_adj),
        "adjusted_cfu_ci_high": float(ci_high_adj),
        "adjusted_cfu_cv_percent": float(100.0 * np.std(square_cfu_np) / max(np.mean(square_cfu_np), 1e-9)),
        "dilution_factor": dilution_factor,
        "plated_volume_ml": plated_volume_ml,
        "grid_size": grid_size,
        "noise_floor_de": NOISE_FLOOR_DE,
        "purple_area_fraction": (float(total_signal_pixels) / float(max(total_pixels, 1))),
        "cluster_count_total": int(total_clusters),
        "quality": quality,
        "mesh_white_rgb": tuple(int(v) for v in mesh_baseline_rgb[0, 0]),
        "ecoli_cells": ecoli_cells,
        "coliform_cells": coliform_cells,
        "clean_cells": clean_cells,
        "grid_results": grid_results,
    }


def analyze_microbe_replicates(
    image_paths: List[str],
    dilution_factor: float = 1.0,
    plated_volume_ml: float = 1.0,
) -> Dict[str, object]:
    if not image_paths:
        raise ValueError("No replicate images provided")

    replicate_results = [
        analyze_microbe_upload(
            path,
            manual_circle=None,
            dilution_factor=dilution_factor,
            plated_volume_ml=plated_volume_ml,
        )
        for path in image_paths
    ]

    adjusted = np.array([float(r.get("adjusted_cfu_ml", 0.0)) for r in replicate_results], dtype=np.float64)
    mean_val = float(np.mean(adjusted))
    std_val = float(np.std(adjusted))
    cv = float(100.0 * std_val / max(mean_val, 1e-9))

    return {
        "replicate_count": len(replicate_results),
        "replicate_adjusted_values": adjusted.tolist(),
        "replicate_mean_adjusted_cfu_ml": mean_val,
        "replicate_std_adjusted_cfu_ml": std_val,
        "replicate_cv_percent": cv,
        "replicate_results": replicate_results,
    }
