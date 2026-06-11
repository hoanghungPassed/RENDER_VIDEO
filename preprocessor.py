"""
Module tiền xử lý ảnh bằng Pillow (PIL).
Resize ảnh trên RAM trước khi đưa vào FFmpeg để tăng tốc render.
"""

from PIL import Image
from pathlib import Path
import tempfile
import os

# Kích thước chuẩn
LONG_SIZE = (1920, 1080)   # 16:9
SHORT_SIZE = (1080, 1920)  # 9:16


def get_target_size(video_format: str) -> tuple:
    """
    Trả về kích thước đích dựa trên định dạng video.

    Args:
        video_format: "long" hoặc "short"
    """
    if video_format.lower() == "short":
        return SHORT_SIZE
    return LONG_SIZE


def center_crop_resize(img: Image.Image, target_size: tuple) -> Image.Image:
    """
    Center crop và resize ảnh về kích thước đích.
    Giữ nguyên tỉ lệ bằng cách crop trung tâm trước, rồi resize.

    Args:
        img: PIL Image object
        target_size: (width, height)

    Returns:
        PIL Image đã resize
    """
    target_w, target_h = target_size
    target_ratio = target_w / target_h

    img_w, img_h = img.size
    img_ratio = img_w / img_h

    if img_ratio > target_ratio:
        # Ảnh rộng hơn → crop 2 bên
        new_w = int(img_h * target_ratio)
        offset_x = (img_w - new_w) // 2
        img = img.crop((offset_x, 0, offset_x + new_w, img_h))
    elif img_ratio < target_ratio:
        # Ảnh cao hơn → crop trên dưới
        new_h = int(img_w / target_ratio)
        offset_y = (img_h - new_h) // 2
        img = img.crop((0, offset_y, img_w, offset_y + new_h))

    # Resize về kích thước đích
    img = img.resize(target_size, Image.LANCZOS)
    return img


def preprocess_image(image_path: str, video_format: str) -> Image.Image:
    """
    Mở và tiền xử lý 1 ảnh: center crop + resize trên RAM.

    Args:
        image_path: Đường dẫn file ảnh
        video_format: "long" hoặc "short"

    Returns:
        PIL Image đã xử lý (trên RAM, chưa lưu file)
    """
    target_size = get_target_size(video_format)
    img = Image.open(image_path).convert("RGB")
    return center_crop_resize(img, target_size)


def preprocess_batch(image_paths: list, video_format: str,
                     callback=None) -> list:
    """
    Tiền xử lý hàng loạt ảnh.

    Args:
        image_paths: Danh sách đường dẫn ảnh
        video_format: "long" hoặc "short"
        callback: callback(index, total, path) — tiến trình

    Returns:
        list of (path, PIL.Image) tuples
    """
    results = []
    total = len(image_paths)

    for i, path in enumerate(image_paths):
        try:
            img = preprocess_image(path, video_format)
            results.append((path, img))
            if callback:
                callback(i + 1, total, path)
        except Exception as e:
            print(f"⚠️ Lỗi xử lý ảnh {path}: {e}")
            results.append((path, None))

    return results


def crop_short_from_long_bg(image_path: str) -> Image.Image:
    """
    Cho video Short: chia ảnh background thành 3 phần dọc,
    lấy phần 3 (bên phải) và resize cho vừa khung Short (1080x1920).

    Ảnh background gốc thường là 1920x1080 (hoặc tương tự tỉ lệ ngang).
    Chia thành 3 cột: [Phần 1 | Phần 2 | Phần 3]
    Lấy Phần 3 → crop → resize thành 1080x1920

    Args:
        image_path: Đường dẫn ảnh background gốc

    Returns:
        PIL Image phần 3 đã resize cho Short
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    # Chia thành 3 phần dọc (theo chiều ngang)
    part_w = w // 3

    # Lấy phần 3 (phần bên phải)
    part3 = img.crop((part_w * 2, 0, w, h))

    # Resize cho vừa khung Short 1080x1920
    part3 = center_crop_resize(part3, SHORT_SIZE)

    return part3


def save_image_to_temp(img: Image.Image, name: str = "temp",
                       temp_dir: str = None) -> str:
    """
    Lưu ảnh PIL vào thư mục tạm.

    Args:
        img: PIL Image
        name: Tên file (không cần extension)
        temp_dir: Thư mục tạm (tự tạo nếu None)

    Returns:
        Đường dẫn file đã lưu
    """
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp(prefix="render_video_")
    os.makedirs(temp_dir, exist_ok=True)

    filepath = os.path.join(temp_dir, f"{name}.png")
    img.save(filepath, "PNG")
    return filepath


def save_batch_to_temp(images: list, temp_dir: str = None) -> list:
    """
    Lưu batch ảnh PIL vào thư mục tạm.

    Args:
        images: list of (original_path, PIL.Image) tuples
        temp_dir: Thư mục tạm

    Returns:
        list of (original_path, temp_path) tuples
    """
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp(prefix="render_video_")

    results = []
    for i, (orig_path, img) in enumerate(images):
        if img is not None:
            name = Path(orig_path).stem + f"_processed_{i}"
            temp_path = save_image_to_temp(img, name, temp_dir)
            results.append((orig_path, temp_path))
        else:
            results.append((orig_path, None))

    return results
