import os
from typing import Dict, Optional, Tuple

import numpy as np

ROLE_OPTIONS = ["control_min", "control_max", "sample"]


def srgb_to_lab(rgb_array: np.ndarray) -> np.ndarray:
    rgb_float = rgb_array.astype(np.float64) / 255.0

    # sRGB to linear RGB
    linear = np.where(
        rgb_float <= 0.04045,
        rgb_float / 12.92,
        ((rgb_float + 0.055) / 1.055) ** 2.4,
    )

    # linear RGB to XYZ (D65)
    x = linear[..., 0] * 0.4124564 + linear[..., 1] * 0.3575761 + linear[..., 2] * 0.1804375
    y = linear[..., 0] * 0.2126729 + linear[..., 1] * 0.7151522 + linear[..., 2] * 0.0721750
    z = linear[..., 0] * 0.0193339 + linear[..., 1] * 0.1191920 + linear[..., 2] * 0.9503041

    # XYZ to Lab
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


def compute_delta_e_2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
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


def _validate_roi(roi: Tuple[int, int, int, int], frame_shape: Tuple[int, int]) -> None:
    x, y, w, h = roi
    frame_height, frame_width = frame_shape[:2]
    if x < 0 or y < 0 or x + w > frame_width or y + h > frame_height or w <= 0 or h <= 0:
        raise ValueError(f"ROI {roi} exceeds frame bounds ({frame_width}x{frame_height})")


def normalize_roi(
    roi: Optional[Tuple[int, int, int, int]], frame_shape: Tuple[int, int]
) -> Tuple[int, int, int, int]:
    frame_height, frame_width = frame_shape[:2]
    if roi is None:
        return (0, 0, frame_width, frame_height)

    x, y, w, h = [int(v) for v in roi]
    x = max(0, min(x, frame_width - 1))
    y = max(0, min(y, frame_height - 1))

    if w <= 0:
        w = frame_width - x
    if h <= 0:
        h = frame_height - y

    w = max(1, min(w, frame_width - x))
    h = max(1, min(h, frame_height - y))
    return (x, y, w, h)


def _trimmed_mean(values: np.ndarray) -> float:
    flat = values.flatten()
    sorted_values = np.sort(flat)
    n_values = len(sorted_values)
    trim_count = max(1, int(0.05 * n_values))
    if n_values <= 2 * trim_count:
        trimmed_values = sorted_values
    else:
        trimmed_values = sorted_values[trim_count:-trim_count]
    scalar = float(np.mean(trimmed_values))
    if np.isnan(scalar) or np.isinf(scalar):
        raise ValueError("Analysis failed: invalid Delta E scalar")
    return scalar


def analyze_pair(
    first_frame_rgb: np.ndarray,
    last_frame_rgb: np.ndarray,
    start_roi: Tuple[int, int, int, int],
    end_roi: Tuple[int, int, int, int],
    duration: float,
) -> Dict[str, object]:
    if duration <= 0:
        raise ValueError("Duration must be > 0")
    if first_frame_rgb.shape != last_frame_rgb.shape:
        raise ValueError("Frame dimensions must match")

    _validate_roi(start_roi, first_frame_rgb.shape)
    _validate_roi(end_roi, last_frame_rgb.shape)

    x1, y1, w1, h1 = start_roi
    x2, y2, w2, h2 = end_roi

    first_crop = first_frame_rgb[y1 : y1 + h1, x1 : x1 + w1]
    last_crop = last_frame_rgb[y2 : y2 + h2, x2 : x2 + w2]

    if first_crop.shape[:2] != last_crop.shape[:2]:
        from PIL import Image

        try:
            resample_filter = Image.Resampling.BILINEAR
        except AttributeError:
            resample_filter = Image.BILINEAR

        last_crop = np.array(
            Image.fromarray(last_crop).resize(
                (first_crop.shape[1], first_crop.shape[0]),
                resample=resample_filter,
            )
        )

    first_saturated = np.sum((first_crop == 0) | (first_crop == 255)) / first_crop.size
    last_saturated = np.sum((last_crop == 0) | (last_crop == 255)) / last_crop.size
    if first_saturated > 0.8 or last_saturated > 0.8:
        raise ValueError("ROI invalid: too many saturated pixels")

    try:
        first_lab = srgb_to_lab(first_crop)
        last_lab = srgb_to_lab(last_crop)
    except Exception as exc:
        raise ValueError(f"Color conversion failed: {exc}") from exc

    try:
        delta_e_array = compute_delta_e_2000(first_lab, last_lab)
    except Exception as exc:
        raise ValueError(f"Delta E computation failed: {exc}") from exc

    if np.any(np.isnan(delta_e_array)) or np.any(np.isinf(delta_e_array)):
        raise ValueError("Analysis failed: invalid Delta E")

    delta_e_scalar = _trimmed_mean(delta_e_array)
    rate = float(delta_e_scalar) / float(duration)
    start_lab_mean = first_lab.reshape(-1, 3).mean(axis=0)
    end_lab_mean = last_lab.reshape(-1, 3).mean(axis=0)
    return {
        "delta_e_scalar": float(delta_e_scalar),
        "rate": float(rate),
        "start_roi": tuple(int(v) for v in start_roi),
        "end_roi": tuple(int(v) for v in end_roi),
        "start_lab_mean": (
            float(start_lab_mean[0]),
            float(start_lab_mean[1]),
            float(start_lab_mean[2]),
        ),
        "end_lab_mean": (
            float(end_lab_mean[0]),
            float(end_lab_mean[1]),
            float(end_lab_mean[2]),
        ),
    }


def extract_frame(filepath: str, t_sec: float) -> np.ndarray:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(
            "OpenCV is unavailable in this build. Use frame image inputs or rebuild with a working opencv recipe."
        ) from exc
    if t_sec < 0:
        raise ValueError("Requested frame time is negative")

    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {os.path.basename(filepath)}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    duration_ms = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(fps, 0.0001) * 1000.0
    target_ms = max(
        0.0,
        min(t_sec * 1000.0, max(0.0, duration_ms - 1000.0 / max(fps, 0.0001))),
    )

    cap.set(cv2.CAP_PROP_POS_MSEC, target_ms)
    ok, frame_bgr = cap.read()
    cap.release()

    if not ok or frame_bgr is None:
        raise RuntimeError(
            f"Failed to read frame at {t_sec:.3f}s from {os.path.basename(filepath)}"
        )

    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)


def interpolate_sample_target(
    control_min_rate: float,
    control_max_rate: float,
    control_min_target: float,
    control_max_target: float,
    sample_rate: float,
) -> float:
    if abs(control_max_rate - control_min_rate) < 1e-9:
        raise ValueError("Control rates are too similar for calibration")

    slope = (control_max_target - control_min_target) / (
        control_max_rate - control_min_rate
    )
    intercept = control_min_target - slope * control_min_rate
    return slope * sample_rate + intercept


def _load_image_rgb(path: str) -> np.ndarray:
    from PIL import Image

    try:
        with Image.open(path) as image:
            return np.array(image.convert("RGB"), dtype=np.uint8)
    except Exception as exc:
        raise RuntimeError(f"Could not read image: {os.path.basename(path)}") from exc


def analyze_three_videos(
    video_by_role: Dict[str, str],
    start_time_by_role: Dict[str, float],
    duration_sec: float,
    control_min_target: Optional[float],
    control_max_target: Optional[float],
    rois_by_role: Optional[
        Dict[str, Dict[str, Optional[Tuple[int, int, int, int]]]]
    ] = None,
) -> Dict[str, object]:
    rows = []
    rates = {}

    for role in ROLE_OPTIONS:
        video_path = video_by_role.get(role)
        if not video_path:
            raise ValueError(f"Missing video for role: {role}")

        start_time = float(start_time_by_role.get(role, 0.0))
        start_frame = extract_frame(video_path, start_time)
        end_frame = extract_frame(video_path, start_time + float(duration_sec))

        role_rois = (rois_by_role or {}).get(role, {})
        start_roi = normalize_roi(role_rois.get("start"), start_frame.shape)
        end_roi = normalize_roi(role_rois.get("end"), end_frame.shape)
        analysis = analyze_pair(start_frame, end_frame, start_roi, end_roi, duration_sec)
        rates[role] = analysis["rate"]

        rows.append(
            {
                "role": role,
                "source": os.path.basename(video_path),
                "delta_e_scalar": analysis["delta_e_scalar"],
                "rate": analysis["rate"],
                "start_roi": analysis["start_roi"],
                "end_roi": analysis["end_roi"],
                "start_lab_mean": analysis["start_lab_mean"],
                "end_lab_mean": analysis["end_lab_mean"],
                "interpolated_target": None,
            }
        )

    _apply_calibration(rows, rates, control_min_target, control_max_target)
    return {"rows": rows}


def analyze_three_image_pairs(
    image_pair_by_role: Dict[str, Tuple[str, str]],
    duration_sec: float,
    control_min_target: Optional[float],
    control_max_target: Optional[float],
    rois_by_role: Optional[
        Dict[str, Dict[str, Optional[Tuple[int, int, int, int]]]]
    ] = None,
) -> Dict[str, object]:
    rows = []
    rates = {}

    for role in ROLE_OPTIONS:
        pair = image_pair_by_role.get(role)
        if not pair or len(pair) != 2:
            raise ValueError(f"Missing start/end images for role: {role}")

        start_path, end_path = pair
        start_frame = _load_image_rgb(start_path)
        end_frame = _load_image_rgb(end_path)

        if start_frame.shape != end_frame.shape:
            raise ValueError(
                f"Image dimensions must match for role {role}. "
                f"Start: {start_frame.shape}, End: {end_frame.shape}"
            )

        role_rois = (rois_by_role or {}).get(role, {})
        start_roi = normalize_roi(role_rois.get("start"), start_frame.shape)
        end_roi = normalize_roi(role_rois.get("end"), end_frame.shape)
        analysis = analyze_pair(start_frame, end_frame, start_roi, end_roi, duration_sec)
        rates[role] = analysis["rate"]

        rows.append(
            {
                "role": role,
                "source": f"{os.path.basename(start_path)} -> {os.path.basename(end_path)}",
                "delta_e_scalar": analysis["delta_e_scalar"],
                "rate": analysis["rate"],
                "start_roi": analysis["start_roi"],
                "end_roi": analysis["end_roi"],
                "start_lab_mean": analysis["start_lab_mean"],
                "end_lab_mean": analysis["end_lab_mean"],
                "interpolated_target": None,
            }
        )

    _apply_calibration(rows, rates, control_min_target, control_max_target)
    return {"rows": rows}


def _apply_calibration(
    rows: list,
    rates_by_role: Dict[str, float],
    control_min_target: Optional[float],
    control_max_target: Optional[float],
) -> None:
    use_calibration = (
        control_min_target is not None and control_max_target is not None
    )
    if not use_calibration:
        return

    if abs(float(control_min_target) - float(control_max_target)) < 1e-9:
        raise ValueError("Control target values must be different for calibration")

    cm = rates_by_role.get("control_min")
    cmax = rates_by_role.get("control_max")
    sample = rates_by_role.get("sample")
    if cm is None or cmax is None or sample is None:
        raise ValueError("Calibration requested, but one or more role rates are missing")

    sample_target = interpolate_sample_target(
        cm,
        cmax,
        float(control_min_target),
        float(control_max_target),
        sample,
    )

    for row in rows:
        if row["role"] == "sample":
            row["interpolated_target"] = float(sample_target)
        elif row["role"] == "control_min":
            row["interpolated_target"] = float(control_min_target)
        elif row["role"] == "control_max":
            row["interpolated_target"] = float(control_max_target)
