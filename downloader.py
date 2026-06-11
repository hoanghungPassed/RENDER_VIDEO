"""
Module tải nhạc từ YouTube sử dụng yt-dlp.
Hỗ trợ tải hàng loạt, convert sang MP3, và callback tiến trình.
"""

import os
import re
import threading
from pathlib import Path


class MusicDownloader:
    """Quản lý tải nhạc từ YouTube với yt-dlp."""

    def __init__(self):
        self._cancel_event = threading.Event()

    def cancel(self):
        """Hủy quá trình tải."""
        self._cancel_event.set()

    def reset(self):
        """Reset trạng thái cancel."""
        self._cancel_event.clear()

    @staticmethod
    def validate_url(url: str) -> bool:
        """Kiểm tra URL YouTube hợp lệ."""
        patterns = [
            r'(https?://)?(www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(https?://)?(www\.)?youtu\.be/[\w-]+',
            r'(https?://)?(www\.)?youtube\.com/shorts/[\w-]+',
            r'(https?://)?music\.youtube\.com/watch\?v=[\w-]+',
        ]
        return any(re.match(p, url.strip()) for p in patterns)

    def download_single(self, url: str, save_folder: str,
                        progress_callback=None, status_callback=None) -> bool:
        """
        Tải 1 video YouTube và convert sang MP3.

        Args:
            url: Link YouTube
            save_folder: Thư mục lưu file MP3
            progress_callback: callback(percent: float) — tiến trình 0-100
            status_callback: callback(message: str) — thông báo trạng thái

        Returns:
            True nếu thành công, False nếu lỗi
        """
        try:
            import yt_dlp
        except ImportError:
            if status_callback:
                status_callback("❌ Lỗi: Chưa cài đặt yt-dlp. Chạy: pip install yt-dlp")
            return False

        if not self.validate_url(url):
            if status_callback:
                status_callback(f"❌ URL không hợp lệ: {url}")
            return False

        os.makedirs(save_folder, exist_ok=True)

        def _progress_hook(d):
            if self._cancel_event.is_set():
                raise Exception("Đã hủy tải nhạc")

            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0 and progress_callback:
                    percent = (downloaded / total) * 100
                    progress_callback(percent)
            elif d['status'] == 'finished':
                if status_callback:
                    filename = Path(d.get('filename', '')).stem
                    status_callback(f"✅ Đã tải xong: {filename} — Đang convert MP3...")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(save_folder, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'progress_hooks': [_progress_hook],
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url.strip(), download=True)
                title = info.get('title', 'Unknown')
                if status_callback:
                    status_callback(f"✅ Hoàn thành: {title}.mp3")
            return True
        except Exception as e:
            error_msg = str(e)
            if "Đã hủy" in error_msg:
                if status_callback:
                    status_callback("⏹ Đã hủy tải nhạc.")
            else:
                if status_callback:
                    status_callback(f"❌ Lỗi tải {url}: {error_msg}")
            return False

    def download_multiple(self, urls: list, save_folder: str,
                          progress_callback=None, status_callback=None,
                          overall_callback=None) -> dict:
        """
        Tải nhiều video YouTube.

        Args:
            urls: Danh sách link YouTube
            save_folder: Thư mục lưu
            progress_callback: callback(percent) cho từng bài
            status_callback: callback(message) trạng thái
            overall_callback: callback(completed, total) tiến trình tổng

        Returns:
            dict với keys 'success' và 'failed' (counts)
        """
        self.reset()
        results = {'success': 0, 'failed': 0, 'total': len(urls)}

        for i, url in enumerate(urls):
            if self._cancel_event.is_set():
                if status_callback:
                    status_callback(f"⏹ Đã hủy. Hoàn thành {results['success']}/{results['total']}")
                break

            url = url.strip()
            if not url:
                continue

            if status_callback:
                status_callback(f"\n⏳ [{i + 1}/{len(urls)}] Đang tải: {url}")

            success = self.download_single(url, save_folder,
                                           progress_callback, status_callback)
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1

            if overall_callback:
                overall_callback(i + 1, len(urls))

        if not self._cancel_event.is_set() and status_callback:
            status_callback(f"\n🎉 Hoàn tất! Thành công: {results['success']}, "
                            f"Thất bại: {results['failed']}")

        return results
