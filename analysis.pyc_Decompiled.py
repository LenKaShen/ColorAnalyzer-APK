# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'scripts\\analysis.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

import os
import json
import tempfile
import time
from datetime import datetime
from typing import Tuple, Dict, Optional
import numpy as np
import cv2
from skimage import color
from scripts import db
db.init_db()
_temp_upload = tempfile.TemporaryDirectory(prefix='uploads_')
_temp_prov = tempfile.TemporaryDirectory(prefix='provenance_')
UPLOAD_DIR = _temp_upload.name
PROVENANCE_DIR = _temp_prov.name
def srgb_to_lab(rgb_array: np.ndarray) -> np.ndarray:
    rgb_float = rgb_array.astype(np.float64) / 255.0
    lab_array = color.rgb2lab(rgb_float)
    return lab_array
def compute_delta_e_2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    delta_e_array = color.deltaE_ciede2000(lab1, lab2)
    return delta_e_array
def analyze_pair(first_frame_rgb: np.ndarray, last_frame_rgb: np.ndarray, start_roi: Tuple[int, int, int, int], end_roi: Tuple[int, int, int, int], duration: float) -> Dict:
    if duration <= 0:
        raise ValueError('Duration must be > 0')
    else:
        if first_frame_rgb.shape!= last_frame_rgb.shape:
            raise ValueError('Frame dimensions must match')
        else:
            x1, y1, w1, h1 = start_roi
            frame_height, frame_width = first_frame_rgb.shape[:2]
            if x1 < 0 or y1 < 0 or x1 + w1 > frame_width or (y1 + h1 > frame_height) or (w1 <= 0) or (h1 <= 0):
                raise ValueError(f'Start ROI {start_roi} exceeds frame bounds ({frame_width}x{frame_height})')
            else:
                x2, y2, w2, h2 = end_roi
                if x2 < 0 or y2 < 0 or x2 + w2 > frame_width or (y2 + h2 > frame_height) or (w2 <= 0) or (h2 <= 0):
                    raise ValueError(f'End ROI {end_roi} exceeds frame bounds ({frame_width}x{frame_height})')
                else:
                    first_crop = first_frame_rgb[y1:y1 + h1, x1:x1 + w1]
                    last_crop = last_frame_rgb[y2:y2 + h2, x2:x2 + w2]
                    if first_crop.shape[:2]!= last_crop.shape[:2]:
                        last_crop = cv2.resize(last_crop, (first_crop.shape[1], first_crop.shape[0]), interpolation=cv2.INTER_AREA)
                    first_saturated = np.sum((first_crop == 0) | (first_crop == 255)) / first_crop.size
                    last_saturated = np.sum((last_crop == 0) | (last_crop == 255)) / last_crop.size
                    if first_saturated > 0.8 or last_saturated > 0.8:
                        raise ValueError('ROI invalid: too many saturated pixels')
                    else:
                        try:
                            first_lab = srgb_to_lab(first_crop)
                            last_lab = srgb_to_lab(last_crop)
                        except Exception as e:
                            raise ValueError(f'Color conversion failed: {str(e)}')
                        try:
                            delta_e_array = compute_delta_e_2000(first_lab, last_lab)
                        except Exception as e:
                            raise ValueError(f'Delta E computation failed: {str(e)}')
                        if np.any(np.isnan(delta_e_array)) or np.any(np.isinf(delta_e_array)):
                            raise ValueError('Analysis failed: invalid ΔE')
                        else:
                            delta_e_flat = delta_e_array.flatten()
                            delta_e_sorted = np.sort(delta_e_flat)
                            n_values = len(delta_e_sorted)
                            trim_count = max(1, int(0.05 * n_values))
                            if n_values <= 2 * trim_count:
                                trimmed_values = delta_e_sorted
                            else:
                                trimmed_values = delta_e_sorted[trim_count:-trim_count]
                            delta_e_scalar = np.mean(trimmed_values)
                            if np.isnan(delta_e_scalar) or np.isinf(delta_e_scalar):
                                raise ValueError('Analysis failed: invalid ΔE')
                            else:
                                rate = delta_e_scalar / duration
                                return {'delta_e_scalar': float(delta_e_scalar), 'rate': float(rate)}
def extract_frame(filepath: str, t_sec: float) -> np.ndarray:
    if t_sec < 0:
        raise ValueError('Requested frame time is negative')
    else:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            raise RuntimeError(f'Failed to open video: {os.path.basename(filepath)}')
        else:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            duration_ms = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(fps, 0.0001) * 1000.0
            target_ms = max(0.0, min(t_sec * 1000.0, max(0.0, duration_ms - 1000.0 / max(fps, 0.0001))))
            cap.set(cv2.CAP_PROP_POS_MSEC, target_ms)
            ok, frame_bgr = cap.read()
            cap.release()
            if not ok or frame_bgr is None:
                raise RuntimeError(f'Failed to read frame at {t_sec:.3f}s from {os.path.basename(filepath)}')
            else:
                return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
def roi_from_annotation(annotation: Optional[Dict], full_frame_shape: Tuple[int, int]) -> Tuple[int, int, int, int]:
    h_total, w_total = full_frame_shape[:2]
    if not annotation or 'boxes' not in annotation or (not annotation['boxes']):
        return (0, 0, w_total, h_total)
    else:
        boxes = annotation['boxes']
        best = None
        best_area = (-1)
        for b in boxes:
            xmin = int(b.get('xmin', 0))
            ymin = int(b.get('ymin', 0))
            xmax = int(b.get('xmax', 0))
            ymax = int(b.get('ymax', 0))
            w = max(0, xmax - xmin)
            h = max(0, ymax - ymin)
            area = w * h
            if area > best_area:
                best_area = area
                best = (xmin, ymin, w, h)
        if best is None:
            return (0, 0, w_total, h_total)
        else:
            x, y, w, h = best
            x = max(0, min(x, w_total - 1))
            y = max(0, min(y, h_total - 1))
            w = max(1, min(w, w_total - x))
            h = max(1, min(h, h_total - y))
            return (x, y, w, h)
def compute_delta_from_crops(first_crop: np.ndarray, last_crop: np.ndarray, duration: float) -> Dict:
    if duration <= 0:
        raise ValueError('Duration must be > 0')
    else:
        first_saturated = np.sum((first_crop == 0) | (first_crop == 255)) / first_crop.size
        last_saturated = np.sum((last_crop == 0) | (last_crop == 255)) / last_crop.size
        if first_saturated > 0.8 or last_saturated > 0.8:
            raise ValueError('ROI invalid: too many saturated pixels')
        else:
            try:
                first_lab = srgb_to_lab(first_crop)
                last_lab = srgb_to_lab(last_crop)
            except Exception as e:
                raise ValueError(f'Color conversion failed: {e}')
            try:
                delta_e_array = compute_delta_e_2000(first_lab, last_lab)
            except Exception as e:
                raise ValueError(f'Delta E computation failed: {e}')
            if np.any(np.isnan(delta_e_array)) or np.any(np.isinf(delta_e_array)):
                raise ValueError('Analysis failed: invalid ΔE')
            else:
                delta_e_flat = delta_e_array.flatten()
                delta_e_sorted = np.sort(delta_e_flat)
                n_values = len(delta_e_sorted)
                trim_count = max(1, int(0.05 * n_values))
                if n_values <= 2 * trim_count:
                    trimmed_values = delta_e_sorted
                else:
                    trimmed_values = delta_e_sorted[trim_count:-trim_count]
                delta_e_scalar = np.mean(trimmed_values)
                if np.isnan(delta_e_scalar) or np.isinf(delta_e_scalar):
                    raise ValueError('Analysis failed: invalid ΔE scalar')
                else:
                    rate = float(delta_e_scalar) / float(duration)
                    return {'delta_e_scalar': float(delta_e_scalar), 'rate': float(rate)}
def interpolate_sample_target(control_min_rate: float, control_max_rate: float, control_min_target: float, control_max_target: float, sample_rate: float) -> float:
    if abs(control_max_rate - control_min_rate) < 1e-09:
        raise ValueError('Control rates are too similar for calibration')
    else:
        slope = (control_max_target - control_min_target) / (control_max_rate - control_min_rate)
        intercept = control_min_target - slope * control_min_rate
        return slope * sample_rate + intercept
def sanitize_filename(name: str) -> str:
    name = os.path.basename(name)
    name = name.replace(' ', '_')
    keep = '-_.()abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join((c for c in name if c in keep))
def save_uploaded_file(uploaded) -> str:
    if isinstance(uploaded, str) and os.path.exists(uploaded):
        filename = sanitize_filename(os.path.basename(uploaded))
        dest = os.path.join(UPLOAD_DIR, f'{int(time.time())}_{filename}')
        with open(uploaded, 'rb') as src, open(dest, 'wb') as dst:
                dst.write(src.read())
        return dest
    else:
        if hasattr(uploaded, 'name') and hasattr(uploaded, 'file'):
            filename = sanitize_filename(uploaded.name)
            dest = os.path.join(UPLOAD_DIR, f'{int(time.time())}_{filename}')
            with open(dest, 'wb') as f:
                uploaded.file.seek(0)
                f.write(uploaded.file.read())
            return dest
        else:
            raise ValueError('Unsupported uploaded file object')
def run_full_analysis(uploaded_files, role_options, duration_h: int, duration_m: int, duration_s: int, start_times_list, roles_list, annot_start0, annot_end0, annot_start1, annot_end1, annot_start2, annot_end2, control_min_target: Optional[float]=None, control_max_target: Optional[float]=None):
    duration_sec = int(duration_h) * 3600 + int(duration_m) * 60 + int(duration_s)
    if duration_sec <= 0:
        raise ValueError('Duration must be greater than zero seconds.')
    else:
        annotations = [annot_start0, annot_end0, annot_start1, annot_end1, annot_start2, annot_end2]
        if uploaded_files and len(uploaded_files) == 3:
            mode = 'videos'
        else:
            if not uploaded_files and all(annotations):
                mode = 'images'
            else:
                raise ValueError('Please upload either 3 videos OR 3 sets of ROI images.')
        if sorted(roles_list)!= sorted(role_options):
            raise ValueError('Please assign each role (control_min, control_max, sample) exactly once.')
        else:
            use_calibration = control_min_target is not None and control_max_target is not None
            if use_calibration and abs(control_min_target - control_max_target) < 1e-09:
                raise ValueError('Control target values must be different for calibration.')
            else:
                results = []
                provenance = {'timestamp': datetime.utcnow().isoformat() + 'Z', 'duration_sec': duration_sec, 'calibration': {'control_min_target': control_min_target, 'control_max_target': control_max_target} if use_calibration else None, 'videos': [], 'analysis_results': []}
                rates_by_role = {}
                if mode == 'videos':
                    ann_starts = [annot_start0, annot_start1, annot_start2]
                    ann_ends = [annot_end0, annot_end1, annot_end2]
                    pending = []
                    for i, upload in enumerate(uploaded_files):
                        role = roles_list[i]
                        filepath = save_uploaded_file(upload)
                        filename = os.path.basename(filepath)
                        video_id = db.insert_video(role=role, filename=filename, filepath=filepath)
                        start_time = float(start_times_list[i])
                        db.upsert_video_interval(video_id=video_id, start_time=start_time, duration=float(duration_sec))
                        start_frame = extract_frame(filepath, start_time)
                        end_frame = extract_frame(filepath, start_time + duration_sec)
                        start_roi = roi_from_annotation(ann_starts[i], start_frame.shape)
                        end_roi = roi_from_annotation(ann_ends[i], end_frame.shape)
                        for frame_type, roi, frame in [('start', start_roi, start_frame), ('end', end_roi, end_frame)]:
                            db.upsert_roi(video_id=video_id, frame_type=frame_type, x=int(roi[0]), y=int(roi[1]), width=int(roi[2]), height=int(roi[3]), image_width=int(frame.shape[1]), image_height=int(frame.shape[0]))
                        analysis_out = analyze_pair(first_frame_rgb=start_frame, last_frame_rgb=end_frame, start_roi=start_roi, end_roi=end_roi, duration=float(duration_sec))
                        rates_by_role[role] = analysis_out['rate']
                        pending.append({'video_id': video_id, 'role': role, 'filename': filename, 'analysis_out': analysis_out, 'calibration_target': control_min_target if role == 'control_min' else control_max_target if role == 'control_max' else None, 'start_time': start_time, 'start_roi': start_roi, 'end_roi': end_roi})
                        provenance['videos'].append({'video_id': video_id, 'role': role, 'filename': filename, 'start_time': start_time, 'start_roi': start_roi, 'end_roi': end_roi})
                    if use_calibration:
                        cm = rates_by_role.get('control_min')
                        cM = rates_by_role.get('control_max')
                        if cm is None or cM is None:
                            raise ValueError('Calibration requested but control rates are missing; ensure both control_min and control_max are provided.')
                        else:
                            if abs(cm - cM) < 1e-09:
                                raise ValueError('Control rates are too similar for calibration')
                            else:
                                for item in pending:
                                    if item['role'] == 'sample':
                                        item['interpolated_target'] = interpolate_sample_target(cm, cM, control_min_target, control_max_target, item['analysis_out']['rate'])
                                    else:
                                        item['interpolated_target'] = None
                    else:
                        for item in pending:
                            item['interpolated_target'] = None
                    for item in pending:
                        analysis_out = item['analysis_out']
                        result_id = db.insert_analysis_result(video_id=item['video_id'], delta_e_scalar=analysis_out['delta_e_scalar'], rate=analysis_out['rate'], duration=float(duration_sec), interpolated_target=item.get('interpolated_target'), calibration_target=item.get('calibration_target'), notes=f'Automated analysis run at {datetime.utcnow().isoformat()}Z')
                        if use_calibration and item['role'] in ['control_min', 'control_max']:
                                target = item['calibration_target']
                                db.insert_calibration_point(item['video_id'], item['analysis_out']['rate'], target)
                        results.append({'video_id': item['video_id'], 'role': item['role'], 'filename': item['filename'], 'delta_e_scalar': analysis_out['delta_e_scalar'], 'rate': analysis_out['rate'], 'interpolated_target': item.get('interpolated_target'), 'result_id': result_id})
                        provenance['analysis_results'].append({'video_id': item['video_id'], 'delta_e_scalar': analysis_out['delta_e_scalar'], 'rate': analysis_out['rate'], 'interpolated_target': item.get('interpolated_target'), 'result_id': result_id})
                else:
                    if mode == 'images':
                        ann_pairs = [(roles_list[0], annot_start0, annot_end0), (roles_list[1], annot_start1, annot_end1), (roles_list[2], annot_start2, annot_end2)]
                        pending = []
                        for role, start_annot, end_annot in ann_pairs:
                            start_frame = np.array(start_annot['image'], dtype=np.uint8)
                            end_frame = np.array(end_annot['image'], dtype=np.uint8)
                            start_roi = roi_from_annotation(start_annot, start_frame.shape)
                            end_roi = roi_from_annotation(end_annot, end_frame.shape)
                            analysis_out = analyze_pair(first_frame_rgb=start_frame, last_frame_rgb=end_frame, start_roi=start_roi, end_roi=end_roi, duration=float(duration_sec))
                            rates_by_role[role] = analysis_out['rate']
                            pending.append({'video_id': None, 'role': role, 'filename': f'{role}_image', 'analysis_out': analysis_out, 'calibration_target': control_min_target if role == 'control_min' else control_max_target if role == 'control_max' else None, 'start_roi': start_roi, 'end_roi': end_roi})
                            provenance['videos'].append({'video_id': None, 'role': role, 'filename': f'{role}_image'})
                        if use_calibration:
                            cm = rates_by_role.get('control_min')
                            cM = rates_by_role.get('control_max')
                            if cm is None or cM is None:
                                raise ValueError('Calibration requested but control rates are missing; ensure both control_min and control_max are provided.')
                            else:
                                if abs(cm - cM) < 1e-09:
                                    raise ValueError('Control rates are too similar for calibration')
                                else:
                                    for item in pending:
                                        if item['role'] == 'sample':
                                            item['interpolated_target'] = interpolate_sample_target(cm, cM, control_min_target, control_max_target, item['analysis_out']['rate'])
                                        else:
                                            item['interpolated_target'] = None
                        else:
                            for item in pending:
                                item['interpolated_target'] = None
                        for item in pending:
                            analysis_out = item['analysis_out']
                            results.append({'video_id': None, 'role': item['role'], 'filename': item['filename'], 'delta_e_scalar': analysis_out['delta_e_scalar'], 'rate': analysis_out['rate'], 'interpolated_target': item.get('interpolated_target'), 'result_id': None})
                            provenance['analysis_results'].append({'video_id': None, 'delta_e_scalar': analysis_out['delta_e_scalar'], 'rate': analysis_out['rate'], 'interpolated_target': item.get('interpolated_target')})
                prov_fn = os.path.join(PROVENANCE_DIR, f'prov_{int(time.time())}.json')
                with open(prov_fn, 'w', encoding='utf-8') as f:
                    json.dump(provenance, f, indent=2)
                table_rows = []
                for r in results:
                    if r['role'] == 'sample':
                        target_val = round(r['interpolated_target'], 6) if r['interpolated_target'] is not None else ''
                    else:
                        if r['role'] == 'control_min':
                            target_val = round(control_min_target, 6) if control_min_target is not None else ''
                        else:
                            if r['role'] == 'control_max':
                                target_val = round(control_max_target, 6) if control_max_target is not None else ''
                            else:
                                target_val = ''
                    table_rows.append([r['role'], r['filename'], round(r['delta_e_scalar'], 6), round(r['rate'], 9), target_val])
                return {'message': 'Analysis complete', 'rows': table_rows, 'provenance': prov_fn}