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

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Loại bỏ ký tự đặc biệt để làm tên thư mục/file an toàn."""
        import re
        # Thay thế khoảng trắng bằng dấu gạch dưới và loại bỏ ký tự không phải chữ/số
        safe = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
        return safe or "Unknown"

    def _create_thumbnail(self, bg_img: Image.Image, namepng_path: str, 
                         text_img: Image.Image, text_pos: tuple, 
                         video_type: str = 'long', np_s: int = 300) -> Image.Image:
        """
        Tạo ảnh Thumbnail bằng cách ghép các lớp y hệt video.
        - Long: NamePNG ở giữa trên, Text ở vị trí X,Y.
        - Short: NamePNG ở giữa dưới, Text ở vị trí cố định.
        """
        # Copy bg để không làm hỏng ảnh gốc
        thumb = bg_img.copy().convert("RGBA")
        
        # 1. Chèn NamePNG
        if namepng_path and os.path.exists(namepng_path):
            with Image.open(namepng_path).convert("RGBA") as np_img:
                # Scale NamePNG theo cấu hình
                w, h = np_img.size
                new_w = np_s
                new_h = int(h * (new_w / w))
                np_img = np_img.resize((new_w, new_h), Image.LANCZOS)
                
                if video_type == 'long':
                    # Căn giữa phía trên
                    pos = ((thumb.width - new_w) // 2, 50)
                else:
                    # Căn giữa ở phần dưới cho Short (VD: y=1200)
                    pos = ((thumb.width - new_w) // 2, text_pos[1] - 400) # text_pos là của NamePNG trong Short?
                    # Để chính xác hơn, Short dùng np_x, np_y
                    pos = (text_pos[0], text_pos[1])
                
                thumb.alpha_composite(np_img, pos)
        
        # 2. Chèn Text Overlay
        if text_img:
            if video_type == 'long':
                thumb.alpha_composite(text_img, text_pos)
            else:
                # Short video text overlay thường là full size canvas
                thumb.alpha_composite(text_img, (0, 0))
                
        return thumb.convert("RGB")

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
        """Render 1 Video Long + Trích xuất Thumbnail từ video."""
        idx = job['index']
        singer = job.get('singer_name', 'Unknown')
        safe_singer = self._sanitize_filename(singer)
        
        # 1. Tạo cấu trúc thư mục 3 lớp
        base_dir = os.path.join(output_folder, safe_singer)
        video_dir = os.path.join(base_dir, "Video Long")
        thumb_dir = os.path.join(base_dir, "Thumb")
        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(thumb_dir, exist_ok=True)
        os.makedirs(os.path.join(base_dir, "Video Short"), exist_ok=True) # Tạo sẵn cho đồng bộ

        if log_callback: log_callback(f"🎬 LONG #{idx}: Đang xử lý cho {singer}...")

        # Tiền xử lý (Background, Audio, Text)
        bg_img = preprocess_image(job['background'], 'long')
        bg_path = save_image_to_temp(bg_img, f"bg_{idx}", temp_dir)
        music_path = self._concat_audio(job['songs'], temp_dir, f"music_{idx}", log_callback)
        if not music_path: return False

        text_path = None
        if job.get('display_list'):
            text_img = self._create_text_overlay(job['display_list'], job.get('font_path', ''), job.get('font_s', 36))
            text_path = save_image_to_temp(text_img, f"text_{idx}", temp_dir)
            del text_img

        # 2. Render Video
        output_path = os.path.join(video_dir, f"Video_Long_{idx:03d}.mp4")
        cmd = self._build_long_cmd(bg_path, music_path, job.get('effect'), job.get('namepng'), text_path, job.get('font_x', 100), job.get('font_y', 300), output_path)
        
        success = self._run_ffmpeg(cmd, log_callback, f"LONG #{idx}", self.get_audio_duration(music_path), job.get('realtime_cb'))
        
        # 3. Trích xuất Thumb thành công 100% từ video
        if success:
            thumb_path = os.path.join(thumb_dir, f"Thumb_Long_{idx:03d}.jpg")
            extract_cmd = ['ffmpeg', '-y', '-ss', '00:00:02', '-i', output_path, '-vframes', '1', '-q:v', '2', thumb_path]
            subprocess.run(extract_cmd, capture_output=True, creationflags=_CREATE_FLAGS)

        del bg_img
        if success and log_callback:
            log_callback(f"✅ LONG #{idx}: Xong -> [{safe_singer}/Video Long/Video_Long_{idx:03d}.mp4]")
        return success

    # ═══════════════════════════════════════════
    # RENDER SHORT VIDEO
    # ═══════════════════════════════════════════
    def _render_short(self, job, config, output_folder, temp_dir,
                      log_callback) -> bool:
        """Render 1 Video Short (Không tạo Thumb)."""
        idx = job['index']
        singer = job.get('singer_name', 'Unknown')
        safe_singer = self._sanitize_filename(singer)

        # 1. Thư mục con
        video_dir = os.path.join(output_folder, safe_singer, "Video Short")
        os.makedirs(video_dir, exist_ok=True)

        if log_callback: log_callback(f"📱 SHORT #{idx}: Đang xử lý cho {singer}...")

        bg_img = crop_short_from_long_bg(job['background']) if job.get('background') else Image.new('RGB', SHORT_SIZE, (20, 20, 30))
        bg_path = save_image_to_temp(bg_img, f"bg_s_{idx}", temp_dir)
        
        text_path = None
        if job.get('song_name'):
            text_img = self._create_short_song_overlay(job.get('song_name', ''))
            text_path = save_image_to_temp(text_img, f"txt_s_{idx}", temp_dir)
            del text_img

        # 2. Render Video
        output_path = os.path.join(video_dir, f"Video_Short_{idx:03d}.mp4")
        duration = job.get('duration', 60)
        cmd = self._build_short_cmd(bg_path, job['song'], duration, job.get('effect'), job.get('namepng'), job.get('namepng_x', 100), job.get('namepng_y', 800), job.get('namepng_s', 300), text_path, output_path)
        
        success = self._run_ffmpeg(cmd, log_callback, f"SHORT #{idx}", duration, job.get('realtime_cb'))
        
        del bg_img
        if success and log_callback:
            log_callback(f"✅ SHORT #{idx}: Xong -> [{safe_singer}/Video Short/Video_Short_{idx:03d}.mp4]")
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
        """Xây dựng lệnh FFmpeg cho Video Long (16:9) với chế độ hòa trộn Screen."""
        cmd = ['ffmpeg', '-y']
        # Thêm -framerate 30 cho background để chống lỗi sập frame
        cmd.extend(['-framerate', '30', '-loop', '1', '-i', bg_path]) 
        input_map = {'bg': 0}
        next_idx = 1

        has_eff = effect_path and os.path.exists(str(effect_path))
        has_np = namepng_path and os.path.exists(str(namepng_path))
        has_txt = text_path and os.path.exists(str(text_path))

        if has_eff:
            cmd.extend(['-stream_loop', '-1', '-i', effect_path])
            input_map['effect'] = next_idx
            next_idx += 1
        if has_np:
            cmd.extend(['-i', namepng_path])
            input_map['namepng'] = next_idx
            next_idx += 1
        if has_txt:
            cmd.extend(['-i', text_path])
            input_map['text'] = next_idx
            next_idx += 1
        cmd.extend(['-i', music_path])
        input_map['music'] = next_idx

        # --- FILTER COMPLEX ---
        filters = []
        out = 'bg_s'
        filters.append(f"[{input_map['bg']}:v]scale=1920:1080,setsar=1,format=yuv420p[{out}]")

        if has_eff:
            # Sử dụng blend mode 'screen' để giữ nguyên chất lượng ánh sáng của effect
            filters.append(f"[{input_map['effect']}:v]scale=1920:1080,format=yuv420p[eff_v]")
            new_out = 'v_eff'
            filters.append(f"[{out}][eff_v]blend=all_mode='screen':all_opacity=1[{new_out}]")
            out = new_out

        if has_np:
            filters.append(f"[{input_map['namepng']}:v]format=rgba[np_v]")
            new_out = 'v_np'
            filters.append(f"[{out}][np_v]overlay=(W-w)/2:50:format=auto[{new_out}]")
            out = new_out

        if has_txt:
            filters.append(f"[{input_map['text']}:v]format=rgba[txt_v]")
            new_out = 'v_txt'
            filters.append(f"[{out}][txt_v]overlay={text_x}:{text_y}:format=auto[{new_out}]")
            out = new_out

        filters.append(f"[{out}]format=yuv420p[v_final]")
        cmd.extend(['-filter_complex', ';'.join(filters), '-map', '[v_final]', '-map', f'{input_map["music"]}:a'])

        # --- ENCODING (Tối ưu tốc độ) ---
        if self._use_nvenc:
            cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '24', '-rc', 'vbr', '-r', '30', '-pix_fmt', 'yuv420p'])
        else:
            cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24', '-r', '30', '-pix_fmt', 'yuv420p'])

        duration = self.get_audio_duration(music_path)
        if duration > 0: cmd.extend(['-t', f"{duration:.3f}"])
        cmd.extend(['-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', output_path])
        return cmd

    def _build_short_cmd(self, bg_path, music_path, duration,
                         effect_path, namepng_path,
                         np_x, np_y, np_s,
                         text_path, output_path) -> list:
        """Xây dựng lệnh FFmpeg cho Video Short (9:16) với chế độ hòa trộn Screen."""
        cmd = ['ffmpeg', '-y']
        cmd.extend(['-framerate', '30', '-loop', '1', '-i', bg_path])
        input_map = {'bg': 0}
        next_idx = 1

        has_eff = effect_path and os.path.exists(str(effect_path))
        has_np = namepng_path and os.path.exists(str(namepng_path))
        has_txt = text_path and os.path.exists(str(text_path))

        if has_eff:
            cmd.extend(['-stream_loop', '-1', '-i', effect_path])
            input_map['effect'] = next_idx
            next_idx += 1
        if has_np:
            cmd.extend(['-i', namepng_path])
            input_map['namepng'] = next_idx
            next_idx += 1
        if has_txt:
            cmd.extend(['-i', text_path])
            input_map['text'] = next_idx
            next_idx += 1
        cmd.extend(['-i', music_path])
        input_map['music'] = next_idx

        # --- FILTER COMPLEX ---
        filters = []
        out = 'bg_s'
        filters.append(f"[{input_map['bg']}:v]scale=1080:1920,setsar=1,format=yuv420p[{out}]")

        if has_eff:
            filters.append(f"[{input_map['effect']}:v]scale=1080:1920,format=yuv420p[eff_v]")
            new_out = 'v_eff'
            filters.append(f"[{out}][eff_v]blend=all_mode='screen':all_opacity=1[{new_out}]")
            out = new_out

        if has_np:
            filters.append(f"[{input_map['namepng']}:v]format=rgba,scale={np_s}:-1[np_v]")
            new_out = 'v_np'
            filters.append(f"[{out}][np_v]overlay={np_x}:{np_y}:format=auto[{new_out}]")
            out = new_out

        if has_txt:
            filters.append(f"[{input_map['text']}:v]format=rgba[txt_v]")
            new_out = 'v_txt'
            filters.append(f"[{out}][txt_v]overlay=0:0:format=auto[{new_out}]")
            out = new_out

        filters.append(f"[{out}]format=yuv420p[v_final]")
        cmd.extend(['-filter_complex', ';'.join(filters), '-map', '[v_final]', '-map', f'{input_map["music"]}:a'])

        # --- ENCODING ---
        if self._use_nvenc:
            cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '24', '-rc', 'vbr', '-r', '30', '-pix_fmt', 'yuv420p'])
        else:
            cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24', '-r', '30', '-pix_fmt', 'yuv420p'])

        cmd.extend(['-c:a', 'aac', '-b:a', '192k', '-t', str(duration), '-movflags', '+faststart', output_path])
        return cmd

    def _build_visualizer_cmd(self, bg_path, audio_path, wave_mode, wave_color, x, y, effect_path, output_path) -> list:
        """
        Xây dựng lệnh FFmpeg cho Video Sóng Nhạc với:
        - Hiệu ứng Zoompan (Zoom In chậm)
        - Hiệu ứng Sóng nhạc (Showwaves)
        - Hiệu ứng nền hòa trộn Screen (nếu có)
        """
        cmd = ['ffmpeg', '-y']
        
        # Input 0: Background
        cmd.extend(['-loop', '1', '-framerate', '30', '-i', bg_path])
        # Input 1: Audio đã ghép nối
        cmd.extend(['-i', audio_path])
        
        # Input 2: Effect (nếu có)
        has_eff = effect_path and os.path.exists(str(effect_path))
        if has_eff:
            cmd.extend(['-stream_loop', '-1', '-i', effect_path])

        # --- FILTER COMPLEX ---
        filters = []
        
        # 1. Zoompan Background (1920x1080)
        filters.append(
            f"[0:v]scale=1920:1080,setsar=1,"
            f"zoompan=z='min(zoom+0.0005,1.1)':d=7000:s=1920x1080,format=yuv420p[v_bg]"
        )
        
        last_v = "v_bg"

        # 2. Hòa trộn Effect (nếu có) bằng mode 'screen'
        if has_eff:
            filters.append(f"[2:v]scale=1920:1080,format=yuv420p[eff_v]")
            filters.append(f"[{last_v}][eff_v]blend=all_mode='screen':all_opacity=1[v_eff]")
            last_v = "v_eff"

        # 3. Tạo Sóng nhạc từ audio (Input 1)
        filters.append(
            f"[1:a]showwaves=s=1920x200:mode={wave_mode}:colors={wave_color}:rate=30,format=yuva420p[wave]"
        )
        
        # 4. Overlay sóng lên background
        filters.append(f"[{last_v}][wave]overlay=x={x}:y={y}:format=auto[v_final]")
        
        cmd.extend(['-filter_complex', ';'.join(filters)])
        cmd.extend(['-map', '[v_final]', '-map', '1:a'])
        
        # --- ENCODING ---
        if self._use_nvenc:
            cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '24', '-rc', 'vbr', '-r', '30', '-pix_fmt', 'yuv420p'])
        else:
            cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24', '-r', '30', '-pix_fmt', 'yuv420p'])
        
        # Thời lượng theo audio
        cmd.extend(['-shortest', '-movflags', '+faststart', output_path])
        
        return cmd

    def _render_visualizer(self, job, temp_dir, log_callback, realtime_cb=None) -> bool:
        """Render 1 Job Video Sóng Nhạc hàng loạt."""
        idx = job['index']
        output_dir = job.get('output_dir', '.')
        os.makedirs(output_dir, exist_ok=True)
        
        if log_callback: log_callback(f"🎬 VISUALIZER #{idx}: Đang chuẩn bị...")

        # 1. Ghép nối danh sách bài hát
        music_path = self._concat_audio(job['songs'], temp_dir, f"music_vis_{idx}", log_callback)
        if not music_path: return False

        # 2. Xử lý Random Kiểu sóng
        wave_mode = job['wave_mode']
        if job.get('random_wave'):
            import random
            modes = ['cline', 'point', 'p2p', 'line']
            wave_mode = random.choice(modes)
        else:
            # Lấy phần text trước ngoặc (VD: cline (Thanh) -> cline)
            wave_mode = wave_mode.split(' ')[0]

        # 3. Đường dẫn output
        output_path = os.path.join(output_dir, f"Visualizer_Video_{idx:03d}.mp4")

        # 4. Build & Run
        cmd = self._build_visualizer_cmd(
            bg_path=job['background'],
            audio_path=music_path,
            wave_mode=wave_mode,
            wave_color=job['wave_color'],
            x=job['wave_x'],
            y=job['wave_y'],
            effect_path=job.get('effect'),
            output_path=output_path
        )

        duration = self.get_audio_duration(music_path)
        success = self._run_ffmpeg(cmd, log_callback, f"VISUALIZER #{idx}", duration, realtime_cb)

        if success and log_callback:
            log_callback(f"✅ VISUALIZER #{idx}: Xong -> Visualizer_Video_{idx:03d}.mp4")
            
        return success

    def render_visualizer(self, config: dict, log_callback=None, realtime_cb=None) -> bool:
        """
        Tạo video sóng nhạc (Visualizer) từ ảnh nền và âm thanh.
        Sử dụng zoompan cho BG và showwaves cho audio.
        """
        import os
        from pathlib import Path
        
        bg_path = config.get('bg')
        audio_path = config.get('audio')
        output_dir = config.get('output_dir')
        mode = config.get('mode', 'cline').split('(')[-1].split(')')[0] # Lấy cline, point hoặc p2p
        x = config.get('x', '0')
        y = config.get('y', '800')
        color = config.get('color', '#FFFFFF')

        # Đảm bảo thư mục output tồn tại
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, f"Visualizer_{Path(audio_path).stem}.mp4")
        duration = self.get_audio_duration(audio_path)
        
        if duration <= 0:
            if log_callback: log_callback("❌ Lỗi: Không lấy được thời lượng file nhạc!")
            return False

        # --- XÂY DỰNG LỆNH FFMPEG ---
        cmd = ['ffmpeg', '-y']
        
        # Input 0: Background (Sử dụng loop cho zoompan)
        cmd.extend(['-loop', '1', '-framerate', '30', '-i', bg_path])
        # Input 1: Audio
        cmd.extend(['-i', audio_path])

        # Filter Complex:
        # 1. Zoompan cho background (Zoom từ từ)
        # 2. Showwaves cho audio (Tạo sóng nhạc)
        # 3. Overlay sóng lên background
        
        filters = [
            # Layer 1: Zoompan background (1920x1080)
            f"[0:v]scale=1920:1080,setsar=1,zoompan=z='min(zoom+0.001,1.1)':d=700:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',format=yuv420p[v_bg]",
            
            # Layer 2: Showwaves từ audio
            f"[1:a]showwaves=s=1920x200:mode={mode}:colors={color}:rate=30,format=yuva420p[v_wave]",
            
            # Layer 3: Overlay sóng lên bg tại vị trí X, Y
            f"[v_bg][v_wave]overlay={x}:{y}:format=auto[v_final]"
        ]
        
        cmd.extend(['-filter_complex', ';'.join(filters)])
        cmd.extend(['-map', '[v_final]', '-map', '1:a'])
        
        # Encoding settings (Dùng chung bộ tối ưu)
        self._build_common_encoding(cmd)
        
        cmd.extend([
            '-t', f"{duration:.3f}",
            '-movflags', '+faststart',
            output_path
        ])

        if log_callback:
            log_callback(f"🎬 Bắt đầu render Visualizer cho: {Path(audio_path).name}...")

        # Chạy FFmpeg
        success = self._run_ffmpeg(
            cmd, log_callback, "VISUALIZER", 
            duration_sec=duration, 
            realtime_cb=realtime_cb
        )

        if success and log_callback:
            log_callback(f"✅ Render Visualizer Xong -> {Path(output_path).name}")
            
        return success

    # ═══════════════════════════════════════════
    # FFMPEG SUBPROCESS
    # ═══════════════════════════════════════════
    def _run_ffmpeg(self, cmd: list, log_callback=None,
                    label: str = "", duration_sec: float = 0.0, 
                    realtime_cb=None) -> bool:
        """
        Chạy FFmpeg subprocess và theo dõi.
        Đọc log liên tục để tính phần trăm tiến trình (Có throttle 0.5s chống lag UI).
        """
        if self._cancel_event.is_set():
            return False

        try:
            import time
            last_update_time = 0.0

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
                        
                        # Chỉ update UI mỗi 0.5 giây để tránh lag máy
                        now = time.time()
                        if now - last_update_time > 0.5:
                            realtime_cb(label, percent)
                            last_update_time = now

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
