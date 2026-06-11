"""
Video Render Tool — Entry Point
Ứng dụng render video nhạc với CustomTkinter GUI.
"""

import os
import sys
import shutil
import customtkinter as ctk

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent Unicode encoding crashes
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from app import VideoRenderApp


def setup_ffmpeg_path():
    """Tự động tìm và thêm thư mục chứa ffmpeg/ffprobe vào PATH nếu chưa có."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    user_profile = os.environ.get("USERPROFILE", "C:\\Users\\HoangHung")
    
    # 1. Thử đường dẫn Winget Gyan.FFmpeg cụ thể
    specific_path = os.path.join(
        user_profile, 
        "AppData", "Local", "Microsoft", "WinGet", "Packages", 
        "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe", 
        "ffmpeg-8.1.1-full_build", "bin"
    )
    if os.path.exists(specific_path) and "ffmpeg.exe" in os.listdir(specific_path):
        os.environ["PATH"] = specific_path + os.pathsep + os.environ["PATH"]
        return

    # 2. Quét nhanh trong thư mục Winget Packages
    winget_dir = os.path.join(user_profile, "AppData", "Local", "Microsoft", "WinGet", "Packages")
    if os.path.exists(winget_dir):
        for root, dirs, files in os.walk(winget_dir):
            if "ffmpeg.exe" in files and "ffprobe.exe" in files:
                os.environ["PATH"] = root + os.pathsep + os.environ["PATH"]
                return

    # 3. Thử tìm từ settings.json (folder ca sĩ -> Tool/_internal)
    try:
        import json
        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
        if os.path.exists(settings_file):
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            singer_root = settings.get("folder_singer_root")
            if singer_root:
                from pathlib import Path
                candidate = os.path.join(Path(singer_root).parent.parent, "Tool", "_internal")
                if os.path.exists(candidate) and "ffmpeg.exe" in os.listdir(candidate):
                    os.environ["PATH"] = candidate + os.pathsep + os.environ["PATH"]
                    return
    except Exception:
        pass


def main():
    setup_ffmpeg_path()
    
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = VideoRenderApp()
    app.mainloop()


if __name__ == "__main__":
    main()

