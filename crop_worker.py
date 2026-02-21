"""
裁剪工作进程 - 通过日志文件与 GUI 通信，避免 stdout 被 MediaPipe 污染。
支持水平矫正（基于肩膀关键点）。
"""

import os
import sys
import json
import glob
import math
import warnings
import logging

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'
warnings.filterwarnings('ignore')
logging.disable(logging.WARNING)

import numpy as np
from PIL import Image, ImageOps
import mediapipe as mp
import cv2

TARGET_W, TARGET_H = 1200, 1600
TARGET_RATIO = TARGET_W / TARGET_H

LOG_FILE = sys.argv[1]

# 水平矫正无需人体关键点，使用图像直线检测


def get_model_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "pose_landmarker.task")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "pose_landmarker.task")


def emit(msg_type, **kwargs):
    data = {"type": msg_type}
    data.update(kwargs)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def detect_tilt_angle(img_np):
    """
    使用 Canny 边缘检测 + Hough 直线检测图片倾斜角度。
    分析接近水平和接近垂直的直线，取中位数作为倾斜角。
    """
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # 缩小图片加速处理
    h, w = gray.shape
    scale = min(1.0, 1000.0 / max(h, w))
    if scale < 1.0:
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)))

    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, math.pi / 180, threshold=100,
                            minLineLength=int(min(gray.shape) * 0.1),
                            maxLineGap=10)

    if lines is None or len(lines) == 0:
        emit("log", msg=f"    直线检测: 未找到直线")
        return 0.0

    h_angles = []  # 水平线
    v_angles = []  # 垂直线
    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 20:
            continue
        angle = math.degrees(math.atan2(dy, dx))

        # 接近水平的线
        if abs(angle) < 15:
            h_angles.append((angle, length))
        elif abs(angle) > 165:
            a = angle - 180 if angle > 0 else angle + 180
            h_angles.append((a, length))
        # 接近垂直的线
        elif 75 < abs(angle) < 105:
            a = angle - 90 if angle > 0 else angle + 90
            v_angles.append((a, length))

    angles = h_angles + v_angles

    emit("log", msg=f"    直线检测: 共 {len(lines)} 条, 水平参考 {len(h_angles)} 条, 垂直参考 {len(v_angles)} 条")

    if h_angles:
        top3_h = sorted(h_angles, key=lambda x: -x[1])[:3]
        for a, l in top3_h:
            emit("log", msg=f"      水平线: {a:+.2f}° (长度 {l:.0f}px)")
    if v_angles:
        top3_v = sorted(v_angles, key=lambda x: -x[1])[:3]
        for a, l in top3_v:
            emit("log", msg=f"      垂直线: {a:+.2f}° (长度 {l:.0f}px)")

    if not angles:
        emit("log", msg=f"    结论: 无有效参考线，跳过矫正")
        return 0.0

    # 按线段长度加权，取加权中位数
    angles.sort(key=lambda x: x[0])
    total_weight = sum(l for _, l in angles)
    cumsum = 0
    result = angles[0][0]
    for a, l in angles:
        cumsum += l
        if cumsum >= total_weight / 2:
            result = a
            break

    emit("log", msg=f"    结论: 倾斜 {result:+.2f}°")
    return result


def level_image(img, angle):
    """旋转图片，用边缘像素填充"""
    img_np = np.array(img)
    h, w = img_np.shape[:2]
    center = (w / 2, h / 2)

    # 计算旋转后的新尺寸
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos_a = abs(M[0, 0])
    sin_a = abs(M[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)
    M[0, 2] += (new_w - w) / 2
    M[1, 2] += (new_h - h) / 2

    # 用边缘像素填充 (BORDER_REPLICATE)
    rotated = cv2.warpAffine(img_np, M, (new_w, new_h),
                             borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(rotated)


def compute_crop_box(img_w, img_h, bbox, pad_top, pad_bottom, pad_left, pad_right):
    bx_min, by_min, bx_max, by_max = bbox
    bx_min_px, bx_max_px = bx_min * img_w, bx_max * img_w
    by_min_px, by_max_px = by_min * img_h, by_max * img_h
    body_w = bx_max_px - bx_min_px
    body_h = by_max_px - by_min_px
    want_left = bx_min_px - body_w * pad_left
    want_right = bx_max_px + body_w * pad_right
    want_top = by_min_px - body_h * pad_top
    want_bottom = by_max_px + body_h * pad_bottom
    want_w = want_right - want_left
    want_h = want_bottom - want_top
    want_cx = (want_left + want_right) / 2
    want_cy = (want_top + want_bottom) / 2
    if want_w / want_h > TARGET_RATIO:
        crop_w = want_w
        crop_h = crop_w / TARGET_RATIO
    else:
        crop_h = want_h
        crop_w = crop_h * TARGET_RATIO
    left = want_cx - crop_w / 2
    top = want_cy - crop_h / 2
    right = want_cx + crop_w / 2
    bottom = want_cy + crop_h / 2
    if left < 0:
        right -= left; left = 0
    if top < 0:
        bottom -= top; top = 0
    if right > img_w:
        left -= (right - img_w); right = img_w
    if bottom > img_h:
        top -= (bottom - img_h); bottom = img_h
    return int(max(0, left)), int(max(0, top)), int(min(img_w, right)), int(min(img_h, bottom))


def fallback_center_crop(img_w, img_h):
    if img_w / img_h > TARGET_RATIO:
        crop_h = img_h
        crop_w = int(crop_h * TARGET_RATIO)
    else:
        crop_w = img_w
        crop_h = int(crop_w / TARGET_RATIO)
    left = (img_w - crop_w) // 2
    top = (img_h - crop_h) // 2
    return left, top, left + crop_w, top + crop_h


def main():
    params = json.loads(sys.argv[2])
    src_dir = params["src_dir"]
    out_dir = params["out_dir"]
    pad_top = params["pad_top"]
    pad_bottom = params["pad_bottom"]
    pad_left = params["pad_left"]
    pad_right = params["pad_right"]
    auto_level = params.get("auto_level", False)

    os.makedirs(out_dir, exist_ok=True)

    files = sorted(
        glob.glob(os.path.join(src_dir, "*.JPG"))
        + glob.glob(os.path.join(src_dir, "*.jpg"))
        + glob.glob(os.path.join(src_dir, "*.jpeg"))
        + glob.glob(os.path.join(src_dir, "*.png"))
    )

    total = len(files)
    if total == 0:
        emit("log", msg="未找到图片文件")
        emit("done", total=0, success=0, failed=0, detected=0, fallback=0)
        return

    emit("log", msg=f"共找到 {total} 张图片，开始处理...")
    if auto_level:
        emit("log", msg="已启用水平矫正")

    model_path = get_model_path()
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
        running_mode=mp.tasks.vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
    )

    success_count = 0
    fail_count = 0
    detect_count = 0
    fallback_count = 0
    leveled_count = 0

    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
        for i, filepath in enumerate(files, 1):
            filename = os.path.basename(filepath)
            try:
                img = Image.open(filepath)
                img = ImageOps.exif_transpose(img)
                img_rgb = img.convert("RGB")
                img_np = np.array(img_rgb)

                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_np)
                result = landmarker.detect(mp_image)

                status_parts = []

                if result.pose_landmarks and len(result.pose_landmarks) > 0:
                    lms = result.pose_landmarks[0]
                    detect_count += 1

                    # 水平矫正（基于图像直线检测，不依赖人体关键点）
                    if auto_level:
                        angle = detect_tilt_angle(img_np)
                        if abs(angle) > 0.3:
                            img = level_image(img, angle)
                            status_parts.append(f"矫正 {angle:.1f}°")
                            emit("log", msg=f"    -> 已旋转 {angle:.2f}°")
                        else:
                            emit("log", msg=f"    -> 倾斜 {angle:.2f}°，无需矫正")
                            leveled_count += 1
                            # 矫正后重新检测
                            img_rgb = img.convert("RGB")
                            img_np = np.array(img_rgb)
                            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_np)
                            result2 = landmarker.detect(mp_image)
                            if result2.pose_landmarks and len(result2.pose_landmarks) > 0:
                                lms = result2.pose_landmarks[0]

                    img_w, img_h = img.size
                    xs = [lm.x for lm in lms]
                    ys = [lm.y for lm in lms]
                    bbox = (min(xs), min(ys), max(xs), max(ys))
                    crop_box = compute_crop_box(img_w, img_h, bbox,
                                               pad_top, pad_bottom, pad_left, pad_right)
                    status_parts.insert(0, "✓ 检测到人体")
                else:
                    img_w, img_h = img.size
                    crop_box = fallback_center_crop(img_w, img_h)
                    status_parts.append("✗ 未检测到人体，居中裁剪")
                    fallback_count += 1

                cropped = img.crop(crop_box)
                result_img = cropped.resize((TARGET_W, TARGET_H), Image.LANCZOS)
                result_img.save(os.path.join(out_dir, filename), quality=95)
                success_count += 1
                emit("progress", current=i, total=total, filename=filename,
                     status=" | ".join(status_parts))
            except Exception as e:
                fail_count += 1
                emit("progress", current=i, total=total, filename=filename, status=f"✗ 错误: {e}")

    emit("log", msg="========================================")
    emit("log", msg="处理完成!")
    emit("log", msg=f"  总数: {total} 张")
    emit("log", msg=f"  成功: {success_count} 张")
    emit("log", msg=f"  失败: {fail_count} 张")
    emit("log", msg=f"  检测到人体: {detect_count} 张")
    emit("log", msg=f"  未检测到人体: {fallback_count} 张")
    if auto_level:
        emit("log", msg=f"  水平矫正: {leveled_count} 张")
    emit("done", total=total, success=success_count, failed=fail_count,
         detected=detect_count, fallback=fallback_count)


if __name__ == "__main__":
    main()
