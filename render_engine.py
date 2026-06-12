"""
Render Engine — FFmpeg video rendering with NVIDIA GPU acceleration.
Sử dụng subprocess để gọi FFmpeg, concurrent.futures cho đa luồng.
Hỗ trợ h264_nvenc (NVIDIA), fallback sang libx264 (CPU).
"""

import os
import sys
import subprocess
import threading
import tempfile
import shutil
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from preprocessor import (
    preprocess_image, crop_short_from_long_bg,
    save_image_to_temp, LONG_SIZE, SHORT_SIZE
)

# Ẩn cửa sổ cmd trên Windows
_CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0


class RenderState:
    """Enum trạng thái render."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class RenderEngine:
    """
    Engine render video sử dụng FFmpeg.
    - NVIDIA GPU: h264_nvenc, preset p6, bitrate 5000k
    - Multi-threading: concurrent.futures.ThreadPoolExecutor
    - Pause/Resume/Cancel: threading.Event + subprocess tracking
    """

    def __init__(self):
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_event = threading.Event()
        self._state = RenderState.IDLE
        self._thread = None
        self._lock = threading.Lock()
        self._active_processes = []
        self._temp_dir = None
        self._use_nvenc = False

    # ─── Properties ───
    @property
    def state(self) -> str:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == RenderState.RUNNING

    @property
    def is_paused(self) -> bool:
        return self._state == RenderState.PAUSED

    @property
    def is_idle(self) -> bool:
        return self._state in (RenderState.IDLE, RenderState.COMPLETED,
                               RenderState.CANCELLED)

    # ═══════════════════════════════════════════
    # GPU DETECTION
    # ═══════════════════════════════════════════
    def check_nvidia(self) -> bool:
        """Kiểm tra h264_nvenc có thực sự hoạt động được không."""
        try:
            # 1. Kiểm tra h264_nvenc có trong danh sách encoders không
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=10,
                creationflags=_CREATE_FLAGS
            )
            if 'h264_nvenc' not in result.stdout:
                self._use_nvenc = False
                return False

            # 2. Chạy thử một lệnh encode cực nhỏ để xem GPU/driver có thực sự hỗ trợ phiên bản API hiện tại không
            test_cmd = [
                'ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:d=0.1',
                '-c:v', 'h264_nvenc', '-f', 'null', '-'
            ]
            test_result = subprocess.run(
                test_cmd, capture_output=True, timeout=10,
                creationflags=_CREATE_FLAGS
            )
            self._use_nvenc = (test_result.returncode == 0)
            return self._use_nvenc
        except Exception:
            self._use_nvenc = False
            return False

    @staticmethod
    def check_ffmpeg() -> bool:
        """Kiểm tra FFmpeg có trong PATH không."""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True, timeout=5,
                creationflags=_CREATE_FLAGS
            )
            return True
        except Exception:
            return False

    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        """Lấy thời lượng file audio sử dụng ffprobe."""
        if not audio_path or not os.path.exists(audio_path):
            return 0.0
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_path
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                creationflags=_CREATE_FLAGS
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return 0.0

    # ═══════════════════════════════════════════
    # MAIN START / CONTROL
    # ═══════════════════════════════════════════
    def start(self, jobs: list, config: dict, max_workers: int = 3,
              progress_callback=None, log_callback=None, job_complete_callback=None):
        """
        Bắt đầu render tất cả jobs với đa luồng.

        Args:
            jobs: Danh sách render jobs từ data_handler
            config: Cấu hình tổng (folders, long, short)
            max_workers: Số luồng FFmpeg chạy đồng thời (1-5)
            progress_callback: callback(completed, total)
            log_callback: callback(message)
            job_complete_callback: callback(job, success)
        """
        self.reset()
        self._state = RenderState.RUNNING

        # Tạo thư mục temp chung
        self._temp_dir = tempfile.mkdtemp(prefix="render_video_")

        # Kiểm tra GPU
        self.check_nvidia()

        def _worker():
            completed = 0
            failed = 0
            total = len(jobs)

            if log_callback:
                if self._use_nvenc:
                    log_callback("🎮 NVIDIA GPU — Sử dụng h264_nvenc encoder")
                else:
                    log_callback("💻 CPU mode — Sử dụng libx264 encoder")
                log_callback(f"🧵 Số luồng render: {max_workers}")
                log_callback(f"📊 Tổng video cần render: {total}\n")

            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {}

                    for job in jobs:
                        # Kiểm tra pause
                        self._pause_event.wait()
                        # Kiểm tra cancel
                        if self._cancel_event.is_set():
                            break

                        future = executor.submit(
                            self._render_single_job, job, config, log_callback
                        )
                        futures[future] = job

                    for future in as_completed(futures):
                        if self._cancel_event.is_set():
                            # Cancel remaining futures
                            for f in futures:
                                f.cancel()
                            break

                        job = futures[future]
                        try:
                            success = future.result()
                            if success:
                                completed += 1
                            else:
                                failed += 1
                        except Exception as e:
                            success = False
                            failed += 1
                            if log_callback:
                                log_callback(f"❌ Lỗi: {e}")

                        if job_complete_callback:
                            job_complete_callback(job, success)

                        if progress_callback:
                            progress_callback(completed + failed, total)

            except Exception as e:
                if log_callback:
                    log_callback(f"❌ Lỗi nghiêm trọng: {e}")

            # Dọn dẹp temp
            try:
                if self._temp_dir and os.path.exists(self._temp_dir):
                    shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass

            # Cập nhật trạng thái
            if not self._cancel_event.is_set():
                self._state = RenderState.COMPLETED
                if log_callback:
                    log_callback(f"\n{'═' * 50}")
                    log_callback(f"🎉 HOÀN TẤT RENDER!")
                    log_callback(f"   ✅ Thành công: {completed}")
                    log_callback(f"   ❌ Thất bại: {failed}")
                    log_callback(f"   📊 Tổng: {completed + failed}/{total}")
                    log_callback(f"{'═' * 50}")
            else:
                self._state = RenderState.CANCELLED
                if log_callback:
                    log_callback(f"\n⏹ ĐÃ HỦY. Hoàn thành: {completed}/{total}")

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def pause(self):
        """Tạm dừng — không submit job mới, job đang chạy tiếp tục."""
        if self._state == RenderState.RUNNING:
            self._pause_event.clear()
            self._state = RenderState.PAUSED

    def resume(self):
        """Tiếp tục render."""
        if self._state == RenderState.PAUSED:
            self._state = RenderState.RUNNING
            self._pause_event.set()

    def cancel(self):
        """Hủy bỏ — kill tất cả FFmpeg processes đang chạy."""
        self._cancel_event.set()
        self._pause_event.set()  # Unblock nếu đang pause
        self._state = RenderState.CANCELLED

        # Kill tất cả FFmpeg processes
        with self._lock:
            for proc in self._active_processes:
                try:
                    proc.terminate()
                except Exception:
                    pass
            self._active_processes.clear()

    def reset(self):
        """Reset trạng thái."""
        self._pause_event.set()
        self._cancel_event.clear()
        self._state = RenderState.IDLE
        self._thread = None
        self._active_processes = []

    # ═══════════════════════════════════════════
    # RENDER SINGLE JOB
    # ═══════════════════════════════════════════
    def _render_single_job(self, job: dict, config: dict,
                           log_callback=None) -> bool:
        """Render 1 video job."""
        if self._cancel_event.is_set():
            return False

        job_type = job.get('type', 'long')
        job_idx = job.get('index', 0)
        output_folder = config.get('folders', {}).get('output', '.')
        os.makedirs(output_folder, exist_ok=True)

        # Tạo temp dir riêng cho job này
        job_temp = os.path.join(self._temp_dir, f"job_{job_type}_{job_idx}")
        os.makedirs(job_temp, exist_ok=True)

        try:
            if job_type == 'long':
                return self._render_long(job, config, output_folder,
                                         job_temp, log_callback)
            else:
                return self._render_short(job, config, output_folder,
                                          job_temp, log_callback)
        except Exception as e:
            if log_callback:
                log_callback(f"❌ {job_type.upper()} #{job_idx}: {e}")
            return False
        finally:
            # Dọn temp của job
            try:
                shutil.rmtree(job_temp, ignore_errors=True)
            except Exception:
                pass

    # ═══════════════════════════════════════════
    # RENDER LONG VIDEO
    # ═══════════════════════════════════════════
    def _render_long(self, job, config, output_folder, temp_dir,
                     log_callback) -> bool:
        """Render 1 Video Long (16:9)."""
        idx = job['index']

        if log_callback:
            log_callback(f"🎬 LONG #{idx}: Chuẩn bị...")

        # 1. Tiền xử lý Background (resize 1920x1080)
        bg_img = preprocess_image(job['background'], 'long')
        bg_path = save_image_to_temp(bg_img, f"bg_{idx}", temp_dir)

        # 2. Ghép nối audio (nhiều bài → 1 file)
        music_path = self._concat_audio(
            job['songs'], temp_dir, f"music_{idx}", log_callback
        )
        if not music_path:
            if log_callback:
                log_callback(f"❌ LONG #{idx}: Không thể ghép audio!")
            return False

        # 3. Tạo text overlay (danh sách bài hát) bằng Pillow
        text_path = None
        if job.get('display_list'):
            text_img = self._create_text_overlay(
                names=job['display_list'],
                font_path=job.get('font_path', ''),
                font_size=job.get('font_s', 36),
            )
            text_path = save_image_to_temp(text_img, f"text_{idx}", temp_dir)

        # 4. Output path
        output_path = job.get('output_path')
        if not output_path:
            output_path = os.path.join(output_folder, f"Video_Long_{idx:03d}.mp4")

        # 5. Build FFmpeg command
        duration = self.get_audio_duration(music_path)
        cmd = self._build_long_cmd(
            bg_path=bg_path,
            music_path=music_path,
            effect_path=job.get('effect'),
            namepng_path=job.get('namepng'),
            text_path=text_path,
            text_x=job.get('font_x', 100),
            text_y=job.get('font_y', 300),
            output_path=output_path,
        )

        # 6. Chạy FFmpeg
        if log_callback:
            log_callback(f"🎬 LONG #{idx}: Đang render...")

        # Truyền duration để tính %
        success = self._run_ffmpeg(
            cmd, log_callback, f"LONG #{idx}", 
            duration_sec=duration, 
            realtime_cb=job.get('realtime_cb')
        )

        if success and log_callback:
            log_callback(f"✅ LONG #{idx}: Xong → {Path(output_path).name}")

        return success

    # ═══════════════════════════════════════════
    # RENDER SHORT VIDEO
    # ═══════════════════════════════════════════
    def _render_short(self, job, config, output_folder, temp_dir,
                      log_callback) -> bool:
        """Render 1 Video Short (9:16)."""
        idx = job['index']

        if log_callback:
            log_callback(f"📱 SHORT #{idx}: Chuẩn bị...")

        # 1. Tiền xử lý Background (cắt phần 3 → 1080x1920)
        if job.get('background') and os.path.exists(job['background']):
            bg_img = crop_short_from_long_bg(job['background'])
        else:
            bg_img = Image.new('RGB', SHORT_SIZE, (20, 20, 30))
        bg_path = save_image_to_temp(bg_img, f"bg_short_{idx}", temp_dir)

        # 2. Music (1 bài, cắt theo duration)
        music_path = job.get('song', '')
        if not music_path or not os.path.exists(music_path):
            if log_callback:
                log_callback(f"❌ SHORT #{idx}: Không tìm thấy file nhạc!")
            return False

        # 3. Song name overlay
        text_path = None
        song_name = job.get('song_name', '')
        if song_name:
            text_img = self._create_short_song_overlay(song_name)
            text_path = save_image_to_temp(text_img, f"txt_short_{idx}", temp_dir)

        # 4. Output path
        duration = job.get('duration', 60)
        output_path = job.get('output_path')
        if not output_path:
            output_path = os.path.join(output_folder, f"Video_Short_{idx:03d}.mp4")

        # 5. Build FFmpeg command
        cmd = self._build_short_cmd(
            bg_path=bg_path,
            music_path=music_path,
            duration=duration,
            effect_path=job.get('effect'),
            namepng_path=job.get('namepng'),
            np_x=job.get('namepng_x', 100),
            np_y=job.get('namepng_y', 800),
            np_s=job.get('namepng_s', 300),
            text_path=text_path,
            output_path=output_path,
        )

        # 6. Chạy FFmpeg
        if log_callback:
            log_callback(f"📱 SHORT #{idx}: Đang render ({duration}s)...")

        success = self._run_ffmpeg(
            cmd, log_callback, f"SHORT #{idx}", 
            duration_sec=duration, 
            realtime_cb=job.get('realtime_cb')
        )

        if success and log_callback:
            log_callback(f"✅ SHORT #{idx}: Xong → {Path(output_path).name}")

        return success

    # ═══════════════════════════════════════════
    # AUDIO CONCAT
    # ═══════════════════════════════════════════
    def _concat_audio(self, song_paths: list, temp_dir: str,
                      name: str, log_callback=None) -> str:
        """
        Ghép nối nhiều file nhạc thành 1 file MP3.
        Sử dụng FFmpeg concat demuxer.
        """
        if not song_paths:
            return None

        if len(song_paths) == 1:
            return song_paths[0]

        # Tạo file danh sách concat
        list_path = os.path.join(temp_dir, f"{name}_list.txt")
        with open(list_path, 'w', encoding='utf-8') as f:
            for song in song_paths:
                # Escape path cho FFmpeg
                escaped = song.replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        output = os.path.join(temp_dir, f"{name}.mp3")

        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', list_path,
            '-c:a', 'libmp3lame', '-q:a', '2',
            output
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
                creationflags=_CREATE_FLAGS
            )
            if result.returncode == 0 and os.path.exists(output):
                return output

            # Fallback: thử copy codec
            cmd_copy = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', list_path, '-c', 'copy', output
            ]
            subprocess.run(
                cmd_copy, capture_output=True, timeout=600,
                creationflags=_CREATE_FLAGS
            )
            return output if os.path.exists(output) else song_paths[0]

        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ Concat audio fallback: dùng bài đầu tiên ({e})")
            return song_paths[0]

    # ═══════════════════════════════════════════
    # TEXT OVERLAY (PILLOW)
    # ═══════════════════════════════════════════
    def _create_text_overlay(self, names: list, font_path: str,
                             font_size: int) -> Image.Image:
        """
        Tạo ảnh PNG trong suốt chứa danh sách tên bài hát.
        Dùng Pillow thay vì FFmpeg drawtext để hỗ trợ Unicode/Tiếng Việt.
        """
        font = self._load_font(font_path, font_size)
        line_height = int(font_size * 1.5)
        padding = 10

        # Tính kích thước canvas
        max_width = 800
        total_height = len(names) * line_height + padding * 2

        img = Image.new('RGBA', (max_width, total_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        for i, name in enumerate(names):
            y = padding + i * line_height
            text = f"  {i + 1}. {name}"

            # Shadow (viền tối)
            draw.text((3, y + 3), text, font=font, fill=(0, 0, 0, 200))
            draw.text((1, y + 1), text, font=font, fill=(0, 0, 0, 140))
            # Text chính (trắng)
            draw.text((0, y), text, font=font, fill=(255, 255, 255, 255))

        return img

    def _create_short_song_overlay(self, song_name: str) -> Image.Image:
        """
        Tạo overlay tên bài hát cho Short video.
        Hiển thị tên bài ở phần dưới, căn giữa.
        """
        font = self._load_font('', 34)

        text = f"♪ {song_name}"
        # Tạo canvas kích thước Short
        img = Image.new('RGBA', SHORT_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Tính vị trí căn giữa, phần dưới
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        x = (SHORT_SIZE[0] - text_w) // 2
        y = SHORT_SIZE[1] - 180  # Gần đáy

        # Shadow
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 200))
        # Text chính
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

        return img

    @staticmethod
    def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
        """Load font an toàn, fallback nhiều cấp."""
        # Thử font người dùng chọn
        if font_path and os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass

        # Thử các font hệ thống phổ biến
        fallback_fonts = [
            'arial.ttf', 'Arial.ttf',
            'segoeui.ttf', 'tahoma.ttf',
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/segoeui.ttf',
            'C:/Windows/Fonts/tahoma.ttf',
        ]
        for f in fallback_fonts:
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue

        # Fallback cuối: default
        try:
            return ImageFont.load_default(size)
        except TypeError:
            return ImageFont.load_default()

    # ═══════════════════════════════════════════
    # FFMPEG COMMAND BUILDERS
    # ═══════════════════════════════════════════
    def _build_long_cmd(self, bg_path, music_path, effect_path,
                        namepng_path, text_path,
                        text_x, text_y, output_path) -> list:
        """
        Xây dựng lệnh FFmpeg cho Video Long (16:9).
        Filter chain: Background → Effect overlay → NamePNG → Text overlay
        """
        cmd = ['ffmpeg', '-y']

        # ─── INPUTS ───
        cmd.extend(['-loop', '1', '-i', bg_path])           # 0: background
        input_map = {'bg': 0}
        next_idx = 1

        has_effect = effect_path and os.path.exists(str(effect_path))
        has_namepng = namepng_path and os.path.exists(str(namepng_path))
        has_text = text_path and os.path.exists(str(text_path))

        if has_effect:
            cmd.extend(['-stream_loop', '-1', '-i', effect_path])
            input_map['effect'] = next_idx
            next_idx += 1

        if has_namepng:
            cmd.extend(['-i', namepng_path])
            input_map['namepng'] = next_idx
            next_idx += 1

        if has_text:
            cmd.extend(['-i', text_path])
            input_map['text'] = next_idx
            next_idx += 1

        cmd.extend(['-i', music_path])                      # audio
        input_map['music'] = next_idx

        # ─── FILTER COMPLEX ───
        filters = []
        out = 'bg_s'

        # Layer 1: Background (scale + format)
        filters.append(
            f"[{input_map['bg']}:v]scale=1920:1080,setsar=1,"
            f"format=yuv420p[{out}]"
        )

        # Layer 2: Effect overlay (Sử dụng colorkey để xóa nền đen cho các video effect MP4)
        if has_effect:
            filters.append(
                f"[{input_map['effect']}:v]scale=1920:1080,"
                f"colorkey=0x000000:0.1:0.1,format=yuva420p[eff]"
            )
            new_out = 'v_eff'
            filters.append(
                f"[{out}][eff]overlay=0:0:format=auto[{new_out}]"
            )
            out = new_out

        # Layer 3: NamePNG (ảnh tên ca sĩ — căn giữa phía trên)
        if has_namepng:
            filters.append(
                f"[{input_map['namepng']}:v]format=rgba[npng]"
            )
            new_out = 'v_npng'
            filters.append(
                f"[{out}][npng]overlay=(W-w)/2:50:format=auto[{new_out}]"
            )
            out = new_out

        # Layer 4: Text overlay (danh sách bài — ở vị trí X, Y)
        if has_text:
            filters.append(
                f"[{input_map['text']}:v]format=rgba[txt]"
            )
            new_out = 'v_txt'
            filters.append(
                f"[{out}][txt]overlay={text_x}:{text_y}:format=auto[{new_out}]"
            )
            out = new_out

        # Đảm bảo định dạng màu đầu ra chuẩn yuv420p để tương thích mọi thiết bị
        new_out = 'v_final'
        filters.append(f"[{out}]format=yuv420p[{new_out}]")
        out = new_out

        cmd.extend(['-filter_complex', ';'.join(filters)])

        # ─── MAP ───
        cmd.extend(['-map', f'[{out}]'])
        cmd.extend(['-map', f'{input_map["music"]}:a'])

        # ─── ENCODING ───
        if self._use_nvenc:
            cmd.extend([
                '-c:v', 'h264_nvenc',
                '-preset', 'p5',       # p5 cho chất lượng/tốc độ nén tốt nhất
                '-cq', '28',           # SỬ DỤNG CQ THAY VÌ BITRATE CỐ ĐỊNH (Giảm cực mạnh dung lượng)
                '-rc', 'vbr',          # Variable bitrate
                '-r', '30',            # Giới hạn FPS ở mức 30 để tránh file bị nặng do effect
                '-pix_fmt', 'yuv420p',
            ])
        else:
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', 'veryfast',  
                '-crf', '28',          
                '-r', '30',
                '-pix_fmt', 'yuv420p',
            ])

        # Lấy thời lượng file nhạc để dùng -t thay vì -shortest nhằm tránh loop vô tận khi có effect loop
        duration = self.get_audio_duration(music_path)
        if duration > 0:
            cmd.extend(['-t', f"{duration:.3f}"])
        else:
            cmd.extend(['-shortest'])

        cmd.extend([
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            output_path
        ])

        return cmd

    def _build_short_cmd(self, bg_path, music_path, duration,
                         effect_path, namepng_path,
                         np_x, np_y, np_s,
                         text_path, output_path) -> list:
        """
        Xây dựng lệnh FFmpeg cho Video Short (9:16).
        BG đã được cắt phần 3 bởi Pillow.
        """
        cmd = ['ffmpeg', '-y']

        # ─── INPUTS ───
        cmd.extend(['-loop', '1', '-i', bg_path])
        input_map = {'bg': 0}
        next_idx = 1

        has_effect = effect_path and os.path.exists(str(effect_path))
        has_namepng = namepng_path and os.path.exists(str(namepng_path))
        has_text = text_path and os.path.exists(str(text_path))

        if has_effect:
            cmd.extend(['-stream_loop', '-1', '-i', effect_path])
            input_map['effect'] = next_idx
            next_idx += 1

        if has_namepng:
            cmd.extend(['-i', namepng_path])
            input_map['namepng'] = next_idx
            next_idx += 1

        if has_text:
            cmd.extend(['-i', text_path])
            input_map['text'] = next_idx
            next_idx += 1

        cmd.extend(['-i', music_path])
        input_map['music'] = next_idx

        # ─── FILTER COMPLEX ───
        filters = []
        out = 'bg_s'

        # Layer 1: Background
        filters.append(
            f"[{input_map['bg']}:v]scale=1080:1920,setsar=1,"
            f"format=yuv420p[{out}]"
        )

        # Layer 2: Effect overlay (Sử dụng colorkey để xóa nền đen cho các video effect MP4)
        if has_effect:
            filters.append(
                f"[{input_map['effect']}:v]scale=1080:1920,"
                f"colorkey=0x000000:0.1:0.1,format=yuva420p[eff]"
            )
            new_out = 'v_eff'
            filters.append(
                f"[{out}][eff]overlay=0:0:format=auto[{new_out}]"
            )
            out = new_out

        # Layer 3: NamePNG (scale theo np_s = width pixels)
        if has_namepng:
            filters.append(
                f"[{input_map['namepng']}:v]format=rgba,"
                f"scale={np_s}:-1[npng]"
            )
            new_out = 'v_npng'
            filters.append(
                f"[{out}][npng]overlay={np_x}:{np_y}:format=auto[{new_out}]"
            )
            out = new_out

        # Layer 4: Song name text (full canvas, overlay at 0:0)
        if has_text:
            filters.append(
                f"[{input_map['text']}:v]format=rgba[txt]"
            )
            new_out = 'v_txt'
            filters.append(
                f"[{out}][txt]overlay=0:0:format=auto[{new_out}]"
            )
            out = new_out

        # Đảm bảo định dạng màu đầu ra chuẩn yuv420p để tương thích mọi thiết bị
        new_out = 'v_final'
        filters.append(f"[{out}]format=yuv420p[{new_out}]")
        out = new_out

        cmd.extend(['-filter_complex', ';'.join(filters)])

        # ─── MAP ───
        cmd.extend(['-map', f'[{out}]'])
        cmd.extend(['-map', f'{input_map["music"]}:a'])

        # ─── ENCODING ───
        if self._use_nvenc:
            cmd.extend([
                '-c:v', 'h264_nvenc',
                '-preset', 'p5',       # p5 cho chất lượng/tốc độ nén tốt nhất
                '-cq', '28',           # SỬ DỤNG CQ THAY VÌ BITRATE CỐ ĐỊNH (Giảm cực mạnh dung lượng)
                '-rc', 'vbr',          # Variable bitrate
                '-r', '30',            # Giới hạn FPS ở mức 30 để tránh file bị nặng do effect
                '-pix_fmt', 'yuv420p',
            ])
        else:
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', 'veryfast',  
                '-crf', '28',          
                '-r', '30',
                '-pix_fmt', 'yuv420p',
            ])

        cmd.extend([
            '-c:a', 'aac',
            '-b:a', '192k',
            '-t', str(duration),
            '-movflags', '+faststart',
            output_path
        ])

        return cmd

    # ═══════════════════════════════════════════
    # FFMPEG SUBPROCESS
    # ═══════════════════════════════════════════
    def _run_ffmpeg(self, cmd: list, log_callback=None,
                    label: str = "", duration_sec: float = 0.0, 
                    realtime_cb=None) -> bool:
        """
        Chạy FFmpeg subprocess và theo dõi.
        Đọc log liên tục để tính phần trăm tiến trình.
        """
        if self._cancel_event.is_set():
            return False

        try:
            # Chạy subprocess và đọc liên tục (stdout/stderr)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_CREATE_FLAGS,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            with self._lock:
                self._active_processes.append(process)

            # Regex bắt thời gian từ FFmpeg output: "time=00:03:15.23"
            time_pattern = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})")
            
            # Đọc từng dòng log của FFmpeg trong lúc đang chạy
            for line in process.stderr:
                if self._cancel_event.is_set():
                    process.terminate()
                    break
                    
                if realtime_cb and duration_sec > 0:
                    match = time_pattern.search(line)
                    if match:
                        h, m, s = match.groups()
                        current_sec = int(h) * 3600 + int(m) * 60 + float(s)
                        percent = min((current_sec / duration_sec) * 100, 99.9)
                        realtime_cb(label, percent)

            process.wait()

            with self._lock:
                if process in self._active_processes:
                    self._active_processes.remove(process)

            if process.returncode != 0 and not self._cancel_event.is_set():
                if log_callback:
                    log_callback(f"❌ {label} FFmpeg lỗi hoặc tự động chuyển CPU...")
                return False

            if realtime_cb:
                realtime_cb(label, 100.0) # Báo hoàn thành 100%
            return True

        except Exception as e:
            if log_callback:
                log_callback(f"❌ {label} Lỗi subprocess: {e}")
            return False
