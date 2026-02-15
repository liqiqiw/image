"""
将 imageSrc 中的照片裁剪为 3:4 (1200x1600) 竖版人像照片。
使用 MediaPipe PoseLandmarker 检测人体，以人体为中心裁剪，保证人体完整且四周留白。
"""

import os
import glob
import numpy as np
from PIL import Image, ImageOps
import mediapipe as mp

SRC_DIR = os.path.expanduser("~/Desktop/imageSrc")
OUT_DIR = os.path.expanduser("~/Desktop/imageOut")
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pose_landmarker.task")
TARGET_W, TARGET_H = 1200, 1600  # 竖版 3:4
TARGET_RATIO = TARGET_W / TARGET_H
PADDING_TOP = 0.15
PADDING_BOTTOM = 0.05
PADDING_SIDE = 0.05

os.makedirs(OUT_DIR, exist_ok=True)

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode


def get_body_bbox(landmarker, image_np):
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_np)
    result = landmarker.detect(mp_image)
    if not result.pose_landmarks or len(result.pose_landmarks) == 0:
        return None
    landmarks = result.pose_landmarks[0]
    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]
    return min(xs), min(ys), max(xs), max(ys)


def compute_crop_box(img_w, img_h, body_bbox):
    bx_min, by_min, bx_max, by_max = body_bbox
    bx_min_px, bx_max_px = bx_min * img_w, bx_max * img_w
    by_min_px, by_max_px = by_min * img_h, by_max * img_h
    body_w = bx_max_px - bx_min_px
    body_h = by_max_px - by_min_px
    pad_x = body_w * PADDING_SIDE
    want_left = bx_min_px - pad_x
    want_right = bx_max_px + pad_x
    want_top = by_min_px - body_h * PADDING_TOP
    want_bottom = by_max_px + body_h * PADDING_BOTTOM
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
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > img_w:
        left -= (right - img_w)
        right = img_w
    if bottom > img_h:
        top -= (bottom - img_h)
        bottom = img_h
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


def process_image(landmarker, filepath):
    filename = os.path.basename(filepath)
    print(f"处理: {filename} ... ", end="", flush=True)
    img = Image.open(filepath)
    img = ImageOps.exif_transpose(img)  # 关键：应用 EXIF 旋转
    img_rgb = img.convert("RGB")
    img_np = np.array(img_rgb)
    img_w, img_h = img.size
    body_bbox = get_body_bbox(landmarker, img_np)
    if body_bbox:
        crop_box = compute_crop_box(img_w, img_h, body_bbox)
        print("人体检测成功 -> ", end="")
    else:
        crop_box = fallback_center_crop(img_w, img_h)
        print("未检测到人体，居中裁剪 -> ", end="")
    cropped = img.crop(crop_box)
    result = cropped.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    out_path = os.path.join(OUT_DIR, filename)
    result.save(out_path, quality=95)
    print("已保存")


def main():
    files = sorted(
        glob.glob(os.path.join(SRC_DIR, "*.JPG"))
        + glob.glob(os.path.join(SRC_DIR, "*.jpg"))
        + glob.glob(os.path.join(SRC_DIR, "*.jpeg"))
        + glob.glob(os.path.join(SRC_DIR, "*.png"))
    )
    print(f"找到 {len(files)} 张图片\n")
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=VisionRunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
    )
    with PoseLandmarker.create_from_options(options) as landmarker:
        for f in files:
            process_image(landmarker, f)
    print(f"\n全部完成! 输出目录: {OUT_DIR}")


if __name__ == "__main__":
    main()
