"""
Module xử lý dữ liệu: scan thư mục, xáo trộn ngẫu nhiên, ghép cặp.
Chuẩn bị danh sách render jobs cho RenderEngine.
"""

import os
import random
from pathlib import Path
from preprocessor import (
    preprocess_image, crop_short_from_long_bg,
    save_image_to_temp, LONG_SIZE, SHORT_SIZE
)

# Extensions hỗ trợ
MUSIC_EXTENSIONS = {'.mp3', '.wav'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv'}


def scan_folder(folder_path: str, extensions: set) -> list:
    """
    Quét thư mục và trả về danh sách file theo extensions.

    Args:
        folder_path: Đường dẫn thư mục
        extensions: Set các extension hợp lệ (vd: {'.mp3', '.wav'})

    Returns:
        Danh sách đường dẫn file (sorted theo tên)
    """
    if not folder_path or not os.path.isdir(folder_path):
        return []

    files = []
    for f in os.listdir(folder_path):
        ext = Path(f).suffix.lower()
        if ext in extensions:
            files.append(os.path.join(folder_path, f))

    files.sort()
    return files


def scan_all_folders(folders: dict) -> dict:
    """
    Quét tất cả thư mục media.

    Args:
        folders: dict với keys: music, background, namepng, effect_long, effect_short

    Returns:
        dict với danh sách file cho mỗi loại
    """
    return {
        'songs': scan_folder(folders.get('music', ''), MUSIC_EXTENSIONS),
        'backgrounds': scan_folder(folders.get('background', ''), IMAGE_EXTENSIONS),
        'namepngs': scan_folder(folders.get('namepng', ''), IMAGE_EXTENSIONS),
        'effects_long': scan_folder(folders.get('effect_long', ''), VIDEO_EXTENSIONS),
        'effects_short': scan_folder(folders.get('effect_short', ''), VIDEO_EXTENSIONS),
    }


def loop_list(items: list, target_count: int) -> list:
    """
    Lặp lại list nếu target_count > len(items).

    Args:
        items: Danh sách gốc
        target_count: Số phần tử cần

    Returns:
        Danh sách mới với đúng target_count phần tử
    """
    if not items:
        return []
    result = []
    while len(result) < target_count:
        result.extend(items)
    return result[:target_count]


def generate_unique_pairs(list_a: list, list_b: list, count: int) -> list:
    """
    Ghép cặp ngẫu nhiên giữa 2 list, tránh trùng tổ hợp.
    Nếu hết tổ hợp unique thì cho phép lặp lại.

    Args:
        list_a: Danh sách A (vd: backgrounds)
        list_b: Danh sách B (vd: namepngs)
        count: Số cặp cần tạo

    Returns:
        list of (item_a, item_b) tuples
    """
    if not list_a or not list_b:
        return []

    # Tạo tất cả tổ hợp có thể
    all_combos = [(a, b) for a in list_a for b in list_b]
    random.shuffle(all_combos)

    # Lặp lại nếu cần nhiều hơn tổng tổ hợp
    pairs = []
    combo_index = 0
    for _ in range(count):
        if combo_index >= len(all_combos):
            random.shuffle(all_combos)
            combo_index = 0
        pairs.append(all_combos[combo_index])
        combo_index += 1

    return pairs


def generate_long_video_jobs(media: dict, config: dict,
                             log_callback=None) -> list:
    """
    Tạo danh sách render jobs cho Video Long.

    Args:
        media: dict từ scan_all_folders()
        config: dict với keys:
            - songs_per_video: int — số bài ghép mỗi video
            - songs_in_list: int — số bài hiển thị trên màn hình
            - num_videos: int — số video cần render
            - out_multiplier: int — hệ số nhân output
            - font_path: str — đường dẫn font
            - font_x: int, font_y: int, font_s: int — vị trí & kích thước font
        log_callback: callback(message) ghi log

    Returns:
        list of job dicts, mỗi job là 1 video cần render
    """
    songs = media['songs']
    backgrounds = media['backgrounds']
    namepngs = media['namepngs']
    effects = media['effects_long']

    if not songs:
        if log_callback:
            log_callback("❌ Không tìm thấy file nhạc nào!")
        return []

    if not backgrounds:
        if log_callback:
            log_callback("❌ Không tìm thấy ảnh background nào!")
        return []

    num_videos = config.get('num_videos', 1)
    out_multiplier = config.get('out_multiplier', 1)
    total_videos = num_videos * out_multiplier

    songs_per_video = config.get('songs_per_video', len(songs))
    songs_in_list = config.get('songs_in_list', len(songs))

    if log_callback:
        log_callback(f"📊 Cấu hình Long Video:")
        log_callback(f"   Tổng nhạc: {len(songs)} | Background: {len(backgrounds)} "
                     f"| NamePNG: {len(namepngs)} | Effect: {len(effects)}")
        log_callback(f"   Số Video: {num_videos} × Out {out_multiplier} = {total_videos} video")
        log_callback(f"   Bài/video: {songs_per_video} | Bài trong list: {songs_in_list}")

    # Ghép cặp background + namepng ngẫu nhiên, tránh trùng
    pairs = generate_unique_pairs(backgrounds, namepngs if namepngs else [''],
                                  total_videos)

    # Shuffle effects
    shuffled_effects = list(effects) if effects else []
    random.shuffle(shuffled_effects)

    jobs = []
    for i in range(total_videos):
        # Tạo danh sách bài hát cho video này
        song_list = loop_list(songs, songs_per_video)
        random.shuffle(song_list)

        # Danh sách tên hiển thị trên video
        display_names = []
        for s in loop_list(songs, songs_in_list):
            name = Path(s).stem
            display_names.append(name)

        bg_path, namepng_path = pairs[i]

        job = {
            'type': 'long',
            'index': i + 1,
            'songs': song_list,
            'song_names': [Path(s).stem for s in song_list],
            'display_list': display_names,
            'background': bg_path,
            'namepng': namepng_path if namepng_path else None,
            'effect': shuffled_effects[i % len(shuffled_effects)] if shuffled_effects else None,
            'font_path': config.get('font_path', ''),
            'font_x': config.get('font_x', 50),
            'font_y': config.get('font_y', 300),
            'font_s': config.get('font_s', 36),
        }
        jobs.append(job)

        if log_callback:
            bg_name = Path(bg_path).name
            npng_name = Path(namepng_path).name if namepng_path else "N/A"
            log_callback(f"   🎬 Video {i + 1}: BG={bg_name} | "
                         f"NamePNG={npng_name} | "
                         f"Bài: {len(song_list)}")

    return jobs


def generate_short_video_jobs(media: dict, config: dict,
                              log_callback=None) -> list:
    """
    Tạo danh sách render jobs cho Video Short.

    Đặc biệt: Background được chia 3 phần, lấy phần 3 cho Short.

    Args:
        media: dict từ scan_all_folders()
        config: dict với keys:
            - num_short_videos: int
            - short_duration: int (giây)
            - short_namepng_x/y/s: int — vị trí NamePNG trên Short
        log_callback: callback(message)

    Returns:
        list of job dicts
    """
    songs = media['songs']
    backgrounds = media['backgrounds']
    namepngs = media['namepngs']
    effects = media['effects_short']

    if not songs:
        if log_callback:
            log_callback("❌ Không tìm thấy file nhạc cho Short!")
        return []

    num_short = config.get('num_short_videos', 1)
    duration = config.get('short_duration', 60)

    if log_callback:
        log_callback(f"\n📊 Cấu hình Short Video:")
        log_callback(f"   Số video Short: {num_short} | Thời lượng: {duration}s")

    # Ghép cặp ngẫu nhiên
    pairs = generate_unique_pairs(
        backgrounds if backgrounds else [''],
        namepngs if namepngs else [''],
        num_short
    )

    shuffled_effects = list(effects) if effects else []
    random.shuffle(shuffled_effects)

    # Shuffle songs cho short
    shuffled_songs = list(songs)
    random.shuffle(shuffled_songs)

    jobs = []
    for i in range(num_short):
        song = shuffled_songs[i % len(shuffled_songs)]
        bg_path, namepng_path = pairs[i]

        job = {
            'type': 'short',
            'index': i + 1,
            'song': song,
            'song_name': Path(song).stem,
            'background': bg_path if bg_path else None,
            'namepng': namepng_path if namepng_path else None,
            'effect': shuffled_effects[i % len(shuffled_effects)] if shuffled_effects else None,
            'duration': duration,
            'namepng_x': config.get('short_namepng_x', 50),
            'namepng_y': config.get('short_namepng_y', 800),
            'namepng_s': config.get('short_namepng_s', 36),
        }
        jobs.append(job)

        if log_callback:
            song_name = Path(song).stem
            bg_name = Path(bg_path).name if bg_path else "N/A"
            log_callback(f"   🎬 Short {i + 1}: {song_name} | BG={bg_name}")

    return jobs


def scan_singer_media(singer_path: str, folders: dict) -> dict:
    """
    Quét tất cả media của một ca sĩ kết hợp với effect chung.
    """
    music_dir = os.path.join(singer_path, "Musics")
    pics_dir = os.path.join(singer_path, "Pictures")
    namepng_dir = os.path.join(singer_path, "NamePNG")

    return {
        'songs': scan_folder(music_dir, MUSIC_EXTENSIONS),
        'backgrounds': scan_folder(pics_dir, IMAGE_EXTENSIONS),
        'namepngs': scan_folder(namepng_dir, IMAGE_EXTENSIONS),
        'effects_long': scan_folder(folders.get('effect_long', ''), VIDEO_EXTENSIONS),
        'effects_short': scan_folder(folders.get('effect_short', ''), VIDEO_EXTENSIONS),
    }


def prepare_all_jobs(folders: dict, selected_singers: list, long_config: dict, short_config: dict,
                     log_callback=None) -> list:
    """
    Entry point: quét thư mục của từng ca sĩ được chọn, ghép cặp và trả về danh sách jobs render.
    """
    if log_callback:
        log_callback("🔍 Đang chuẩn bị render cho các ca sĩ...")

    all_jobs = []

    for singer in selected_singers:
        singer_name = singer['name']
        singer_path = singer['path']

        if log_callback:
            log_callback(f"\n📂 Quét dữ liệu cho ca sĩ: {singer_name}")

        media = scan_singer_media(singer_path, folders)

        if log_callback:
            log_callback(f"   Tìm thấy: {len(media['songs'])} nhạc, "
                         f"{len(media['backgrounds'])} background, "
                         f"{len(media['namepngs'])} namepng")

        # Long video jobs for this singer
        singer_long_jobs = []
        if long_config.get('num_videos', 0) > 0:
            singer_long_jobs = generate_long_video_jobs(media, long_config, log_callback)
            for job in singer_long_jobs:
                job['singer_name'] = singer_name
                # Thiết lập output_path cho job
                safe_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in singer_name]).replace(" ", "_")
                job['output_path'] = os.path.join(folders.get('output', '.'), f"{safe_name}_Long_{job['index']:03d}.mp4")
            all_jobs.extend(singer_long_jobs)

        # Short video jobs for this singer
        singer_short_jobs = []
        if short_config.get('num_short_videos', 0) > 0:
            singer_short_jobs = generate_short_video_jobs(media, short_config, log_callback)
            for job in singer_short_jobs:
                job['singer_name'] = singer_name
                # Thiết lập output_path cho job
                safe_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in singer_name]).replace(" ", "_")
                job['output_path'] = os.path.join(folders.get('output', '.'), f"{safe_name}_Short_{job['index']:03d}.mp4")
            all_jobs.extend(singer_short_jobs)

    if log_callback:
        log_callback(f"\n✅ Tổng cộng: {len(all_jobs)} video cần render "
                     f"(Long: {sum(1 for j in all_jobs if j['type'] == 'long')}, "
                     f"Short: {sum(1 for j in all_jobs if j['type'] == 'short')})")

    return all_jobs
