"""
裁剪工作进程 - 通过日志文件与 GUI 通信，避免 stdout 被 MediaPipe 污染。
"""

import os
import sys
import json
import glob
import warnings
import logging

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'
warnings.filterwarnings('ignore')
logging.disable(logging.WARNING)

import numpy as np
from PIL import Image, ImageOps
import mediapipe as mp

TARGET_W, TARGET_H = 1200, 1600
TARGET_RATIO = TARGET_W / TARGET_H

# 日志文件路径从命令行参数获取
LOG_FILE = sys.argv[1]


def get_model_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "pose_landmarker.task")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "pose_landmarker.task")


def emit(msg_type, **kwargs):
    data = {"type": msg_type}
    data.update(kwargs)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


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

    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
        for i, filepath in enumerate(files, 1):
            filename = os.path.basename(filepath)
            try:
                img = Image.open(filepath)
                img = ImageOps.exif_transpose(img)
                img_rgb = img.convert("RGB")
                img_np = np.array(img_rgb)
                img_w, img_h = img.size

                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_np)
                result = landmarker.detect(mp_image)

                if result.pose_landmarks and len(result.pose_landmarks) > 0:
                    lms = result.pose_landmarks[0]
                    xs = [lm.x for lm in lms]
                    ys = [lm.y for lm in lms]
                    bbox = (min(xs), min(ys), max(xs), max(ys))
                    crop_box = compute_crop_box(img_w, img_h, bbox,
                                               pad_top, pad_bottom, pad_left, pad_right)
                    status = "✓ 检测到人体"
                    detect_count += 1
                else:
                    crop_box = fallback_center_crop(img_w, img_h)
                    status = "✗ 未检测到人体，居中裁剪"
                    fallback_count += 1

                cropped = img.crop(crop_box)
                result_img = cropped.resize((TARGET_W, TARGET_H), Image.LANCZOS)
                result_img.save(os.path.join(out_dir, filename), quality=95)
                success_count += 1
                emit("progress", current=i, total=total, filename=filename, status=status)
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
    emit("done", total=total, success=success_count, failed=fail_count,
         detected=detect_count, fallback=fallback_count)


if __name__ == "__main__":
    main()
