"""
Tab Video Visualizer — Nâng cấp hỗ trợ Render hàng loạt.
Chuyên gia: Xử lý thư mục, cấu hình sóng nhạc, random hiệu ứng và render playlist.
"""

import customtkinter as ctk
from tkinter import filedialog
import os
from pathlib import Path

class VisualizerTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        
        # ─── Biến Thư mục ───
        self.bg_root = ctk.StringVar()
        self.music_root = ctk.StringVar()
        self.folder_effect = ctk.StringVar(value="")
        self.output_root = ctk.StringVar()
        
        # ─── Biến Cấu hình Render ───
        self.num_videos = ctk.IntVar(value=5)
        self.songs_per_video = ctk.IntVar(value=3)
        
        # ─── Biến Cấu hình Sóng Nhạc ───
        self.random_wave_var = ctk.BooleanVar(value=True)
        self.wave_mode = ctk.StringVar(value="cline")
        self.wave_x = ctk.StringVar(value="0")
        self.wave_y = ctk.StringVar(value="800")
        self.wave_color = ctk.StringVar(value="#ffffff")
        
        self._build_ui()

    def _build_ui(self):
        # Container chính cuộn được
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=15, pady=10)

        # ─── SECTION 1: NHẬP THƯ MỤC ───
        sec_folders = self._create_section(container, "📁 QUẢN LÝ THƯ MỤC")
        self._create_folder_row(sec_folders, "Thư mục Ảnh nền:", self.bg_root, 0)
        self._create_folder_row(sec_folders, "Thư mục Nhạc:", self.music_root, 1)
        self._create_folder_row(sec_folders, "Thư mục Effect:", self.folder_effect, 2)
        self._create_folder_row(sec_folders, "Thư mục Output:", self.output_root, 3)

        # ─── SECTION 2: CẤU HÌNH RENDER HÀNG LOẠT ───
        sec_bulk = self._create_section(container, "📊 CẤU HÌNH RENDER HÀNG LOẠT")
        
        # Số lượng video
        f_num = ctk.CTkFrame(sec_bulk, fg_color="transparent")
        f_num.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(f_num, text="Số lượng video:", width=120, anchor="w").pack(side="left")
        ctk.CTkSlider(f_num, from_=1, to=50, number_of_steps=49, variable=self.num_videos, 
                      command=lambda v: self.lbl_num.configure(text=f"{int(v)} video")).pack(side="left", fill="x", expand=True, padx=10)
        self.lbl_num = ctk.CTkLabel(f_num, text=f"{self.num_videos.get()} video", width=70, font=ctk.CTkFont(weight="bold"))
        self.lbl_num.pack(side="right")

        # Số bài mỗi video
        f_songs = ctk.CTkFrame(sec_bulk, fg_color="transparent")
        f_songs.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(f_songs, text="Bài mỗi video:", width=120, anchor="w").pack(side="left")
        ctk.CTkSlider(f_songs, from_=1, to=20, number_of_steps=19, variable=self.songs_per_video,
                      command=lambda v: self.lbl_songs.configure(text=f"{int(v)} bài")).pack(side="left", fill="x", expand=True, padx=10)
        self.lbl_songs = ctk.CTkLabel(f_songs, text=f"{self.songs_per_video.get()} bài", width=70, font=ctk.CTkFont(weight="bold"))
        self.lbl_songs.pack(side="right")

        # ─── SECTION 3: CẤU HÌNH SÓNG NHẠC ───
        sec_wave = self._create_section(container, "🎵 CẤU HÌNH HIỆU ỨNG SÓNG")
        
        # Random Mode & Wave Mode
        top_wave = ctk.CTkFrame(sec_wave, fg_color="transparent")
        top_wave.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkCheckBox(top_wave, text="Tự động Random kiểu sóng", variable=self.random_wave_var, 
                        command=self._on_toggle_random, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 20))
        
        self.mode_combo = ctk.CTkComboBox(top_wave, values=["cline (Thanh)", "point (Điểm)", "p2p (Tần số)"], 
                                         variable=self.wave_mode, width=160)
        self.mode_combo.pack(side="left")
        self._on_toggle_random() # Cập nhật trạng thái ban đầu

        # Vị trí & Màu sắc
        bot_wave = ctk.CTkFrame(sec_wave, fg_color="transparent")
        bot_wave.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(bot_wave, text="Vị trí X:").pack(side="left", padx=5)
        ctk.CTkEntry(bot_wave, textvariable=self.wave_x, width=60).pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(bot_wave, text="Vị trí Y:").pack(side="left", padx=5)
        ctk.CTkEntry(bot_wave, textvariable=self.wave_y, width=60).pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(bot_wave, text="Màu sắc (Hex):").pack(side="left", padx=5)
        ctk.CTkEntry(bot_wave, textvariable=self.wave_color, width=100).pack(side="left")

        # ─── SECTION 4: ĐIỀU KHIỂN ───
        ctrl_frame = ctk.CTkFrame(container, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=10, pady=20)
        
        self.btn_demo = ctk.CTkButton(ctrl_frame, text="👁 Demo Sóng Nhạc", height=40,
                                     fg_color=("gray75", "gray25"), text_color=("black", "white"),
                                     command=lambda: self.app._on_demo_visualizer() if hasattr(self.app, '_on_demo_visualizer') else None)
        self.btn_demo.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_render = ctk.CTkButton(ctrl_frame, text="▶ Bắt đầu Render", height=40,
                                       fg_color="#2563eb", hover_color="#1d4ed8", font=ctk.CTkFont(weight="bold"),
                                       command=self._on_start_render)
        self.btn_render.pack(side="left", fill="x", expand=True)

    def _create_section(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"))
        frame.pack(fill="x", padx=0, pady=(0, 15))
        
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=13, weight="bold"), 
                     text_color=("#2563eb", "#3b82f6")).pack(anchor="w", padx=15, pady=(8, 12))
        
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=5, pady=(0, 10))
        return inner

    def _create_folder_row(self, parent, label, variable, row):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=10, pady=3)
        
        ctk.CTkLabel(f, text=label, width=130, anchor="w").pack(side="left")
        ctk.CTkEntry(f, textvariable=variable).pack(side="left", fill="x", expand=True, padx=10)
        
        def browse():
            path = filedialog.askdirectory()
            if path: variable.set(path)
        
        ctk.CTkButton(f, text="Chọn", width=70, command=browse).pack(side="right")

    def _on_toggle_random(self):
        if self.random_wave_var.get():
            self.mode_combo.configure(state="disabled")
        else:
            self.mode_combo.configure(state="normal")

    def get_folders(self) -> dict:
        return {
            'bg': self.bg_root.get(),
            'music': self.music_root.get(),
            'effect': self.folder_effect.get(),
            'output': self.output_root.get()
        }

    def get_config(self) -> dict:
        return {
            'num_videos': int(self.num_videos.get()),
            'songs_per_video': int(self.songs_per_video.get()),
            'random_wave': self.random_wave_var.get(),
            'wave_mode': self.mode_combo.get(),
            'wave_color': self.wave_color.get(),
            'wave_x': int(self.wave_x.get() or 0),
            'wave_y': int(self.wave_y.get() or 800),
            'effect_folder': self.folder_effect.get()
        }

    def validate(self) -> tuple[bool, str]:
        if not self.bg_root.get() or not os.path.isdir(self.bg_root.get()):
            return False, "Vui lòng chọn thư mục Ảnh nền hợp lệ!"
        if not self.music_root.get() or not os.path.isdir(self.music_root.get()):
            return False, "Vui lòng chọn thư mục Nhạc hợp lệ!"
        if not self.output_root.get() or not os.path.isdir(self.output_root.get()):
            return False, "Vui lòng chọn thư mục Output hợp lệ!"
        return True, ""

    def _on_start_render(self):
        valid, err = self.validate()
        if not valid:
            self.app.log(f"❌ {err}")
            return
            
        # Gọi xử lý render trong app
        if hasattr(self.app, 'start_visualizer_render'):
            self.app.start_visualizer_render(self.get_config(), self.get_folders())
