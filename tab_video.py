"""
Tab Video Long + Short — Giao diện cấu hình render video.
Bao gồm: Import thư mục, cấu hình Long, cấu hình Short.
"""

import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path


class VideoTab(ctk.CTkFrame):
    """Tab cấu hình Video Long + Short."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        # ─── Biến lưu đường dẫn thư mục ───
        self.folders = {
            'singer_root': ctk.StringVar(value=""),
            'effect_long': ctk.StringVar(value=""),
            'effect_short': ctk.StringVar(value=""),
            'output': ctk.StringVar(value=""),
        }
        self.folders['singer_root'].trace_add("write", self._on_singer_root_changed)
        self.singers_data = []

        # ─── Biến cấu hình Font (Long) ───
        self.font_path = ctk.StringVar(value="")
        self.font_x = ctk.StringVar(value="100")
        self.font_y = ctk.StringVar(value="300")
        self.font_s = ctk.StringVar(value="40")

        # ─── Biến cấu hình số lượng (Long) ───
        self.songs_per_video = ctk.StringVar(value="5")
        self.songs_in_list = ctk.StringVar(value="5")
        self.num_long_videos = ctk.StringVar(value="1")
        self.out_multiplier = ctk.StringVar(value="1")

        # ─── Biến cấu hình Short ───
        self.short_duration = ctk.StringVar(value="60")
        self.num_short_videos = ctk.StringVar(value="1")
        self.short_namepng_x = ctk.StringVar(value="100")
        self.short_namepng_y = ctk.StringVar(value="1200")
        self.short_namepng_s = ctk.StringVar(value="300")

        # ─── Biến thread ───
        self.thread_count = ctk.IntVar(value=3)

        self._build_ui()

    def _build_ui(self):
        """Xây dựng toàn bộ giao diện tab Video không scroll chính."""
        self.grid_columnconfigure(0, weight=1)

        # ═══════════════════════════════════════
        # SECTION 1: IMPORT THƯ MỤC & SỐ LUỒNG (Dòng đầu tiên, chia 2 cột)
        # ═══════════════════════════════════════
        top_row_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_row_frame.pack(fill="x", padx=15, pady=(6, 4))
        top_row_frame.grid_columnconfigure(0, weight=1)
        top_row_frame.grid_columnconfigure(1, weight=0)

        # Cột trái: Thư mục import/export (2x2 grid)
        folders_container = ctk.CTkFrame(top_row_frame, fg_color="transparent")
        folders_container.grid(row=0, column=0, padx=(0, 15), pady=0, sticky="nsew")
        self._build_folders_section(folders_container)

        # Cột phải: Số luồng render
        thread_container = ctk.CTkFrame(top_row_frame, fg_color="transparent")
        thread_container.grid(row=0, column=1, padx=0, pady=0, sticky="ne")
        self._build_thread_section(thread_container)

        # Separator mỏng
        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray25")
                     ).pack(fill="x", padx=15, pady=(4, 4))

        # ═══════════════════════════════════════
        # SECTION 2: CẤU HÌNH LONG & SHORT (Dòng thứ hai, đặt song song)
        # ═══════════════════════════════════════
        config_row_frame = ctk.CTkFrame(self, fg_color="transparent")
        config_row_frame.pack(fill="x", padx=15, pady=(2, 4))
        config_row_frame.grid_columnconfigure(0, weight=1, uniform="col")
        config_row_frame.grid_columnconfigure(1, weight=1, uniform="col")

        # Cấu hình Long bên trái
        long_container = ctk.CTkFrame(config_row_frame, fg_color="transparent")
        long_container.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="nsew")
        self._build_long_config_section(long_container)

        # Cấu hình Short bên phải
        short_container = ctk.CTkFrame(config_row_frame, fg_color="transparent")
        short_container.grid(row=0, column=1, padx=(10, 0), pady=0, sticky="nsew")
        self._build_short_config_section(short_container)

        # Separator mỏng
        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray25")
                     ).pack(fill="x", padx=15, pady=(4, 4))

        # ═══════════════════════════════════════
        # SECTION 3: DÒNG CHỜ LỆNH (Thanh điều khiển + Progress Bar)
        # ═══════════════════════════════════════
        self._build_controls_section()

        # Separator mỏng
        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray25")
                     ).pack(fill="x", padx=15, pady=(4, 4))

        # ═══════════════════════════════════════
        # SECTION 4: DANH SÁCH CA SĨ (Dòng cuối cùng, tự co giãn)
        # ═══════════════════════════════════════
        self._build_singers_section()

    # ─────────────────────────────────────────────
    # SECTION 1: THƯ MỤC IMPORT
    # ─────────────────────────────────────────────
    def _build_folders_section(self, parent):
        """Xây dựng phần import thư mục tối ưu 2x2 grid."""
        header = ctk.CTkLabel(
            parent, text="📁  THƯ MỤC IMPORT / EXPORT",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        header.pack(fill="x", padx=0, pady=(0, 4))

        folder_frame = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"))
        folder_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        folder_frame.grid_columnconfigure(1, weight=1)
        folder_frame.grid_columnconfigure(3, weight=1)

        folder_defs = [
            ('singer_root', '🎤  Thư mục Ca Sĩ', 0, 0),
            ('output',      '📤  Thư mục Output', 0, 2),
            ('effect_long', '🎞️  Effect Long', 1, 0),
            ('effect_short','🎞️  Effect Short', 1, 2),
        ]

        for key, label_text, row, col in folder_defs:
            # Nút chọn thư mục
            btn = ctk.CTkButton(
                folder_frame, text=label_text, width=150, height=26,
                anchor="w", font=ctk.CTkFont(size=12),
                fg_color=("gray78", "gray25"),
                hover_color=("gray68", "gray35"),
                text_color=("gray10", "gray90"),
                command=lambda k=key: self._browse_folder(k)
            )
            btn.grid(row=row, column=col, padx=(8, 4), pady=3, sticky="w")

            # Label hiện đường dẫn
            path_label = ctk.CTkLabel(
                folder_frame,
                textvariable=self.folders[key],
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray60"),
                anchor="w",
                width=120
            )
            path_label.grid(row=row, column=col+1, padx=(4, 8), pady=3, sticky="ew")

    # ─────────────────────────────────────────────
    # SECTION 1.5: DANH SÁCH CA SĨ
    # ─────────────────────────────────────────────
    def _build_singers_section(self):
        """Xây dựng bảng danh sách ca sĩ tự động co giãn theo chiều cao cửa sổ."""
        self.singers_section = ctk.CTkFrame(self, fg_color="transparent")
        self.singers_section.pack(fill="both", expand=True, padx=15, pady=(2, 6))

        title_frame = ctk.CTkFrame(self.singers_section, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 3))

        lbl = ctk.CTkLabel(
            title_frame, text="👥  DANH SÁCH CA SĨ",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        lbl.pack(side="left")

        self.select_all_var = ctk.IntVar(value=1)
        self.select_all_cb = ctk.CTkCheckBox(
            title_frame, text="Chọn tất cả / Bỏ chọn",
            variable=self.select_all_var,
            command=self._on_toggle_select_all,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.select_all_cb.pack(side="right", padx=10)

        table_frame = ctk.CTkFrame(self.singers_section, fg_color=("gray85", "gray15"))
        table_frame.pack(fill="both", expand=True, pady=1)

        headers = [
            ("Chọn", 80),
            ("Tên Ca Sĩ", 220),
            ("Số Ảnh", 100),
            ("Số Nhạc", 100),
            ("Thời Gian", 120),
            ("Trạng Thái", 160)
        ]

        header_row = ctk.CTkFrame(table_frame, fg_color=("gray75", "gray22"), height=26)
        header_row.pack(fill="x")
        header_row.pack_propagate(False)

        current_x = 10
        for col_name, width in headers:
            col_lbl = ctk.CTkLabel(
                header_row, text=col_name,
                width=width, height=24,
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="center" if col_name != "Tên Ca Sĩ" else "w"
            )
            col_lbl.place(x=current_x, y=1)
            current_x += width + 10

        self.singers_scroll = ctk.CTkScrollableFrame(
            table_frame, fg_color="transparent"
        )
        self.singers_scroll.pack(fill="both", expand=True, pady=1)

    def _on_toggle_select_all(self):
        val = self.select_all_var.get()
        for s in self.singers_data:
            s['selected'].set(val)

    def _on_singer_root_changed(self, *args):
        self.update_singers_list()

    def update_singers_list(self):
        import os
        from pathlib import Path

        for s in self.singers_data:
            try:
                s['row_frame'].destroy()
            except Exception:
                pass
        self.singers_data.clear()

        singer_root = self.folders['singer_root'].get()
        if not singer_root or not os.path.isdir(singer_root):
            return

        try:
            subdirs = sorted([d for d in os.listdir(singer_root) if os.path.isdir(os.path.join(singer_root, d))])
        except Exception as e:
            print(f"Error scanning singer root: {e}")
            return

        for d in subdirs:
            singer_path = os.path.join(singer_root, d)
            music_dir = os.path.join(singer_path, "Musics")
            pics_dir = os.path.join(singer_path, "Pictures")

            num_songs = 0
            if os.path.exists(music_dir):
                num_songs = len([f for f in os.listdir(music_dir) if Path(f).suffix.lower() in {'.mp3', '.wav'}])

            num_images = 0
            if os.path.exists(pics_dir):
                num_images = len([f for f in os.listdir(pics_dir) if Path(f).suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}])

            sel_var = ctk.IntVar(value=1)
            row_frame = ctk.CTkFrame(self.singers_scroll, fg_color="transparent", height=32)
            row_frame.pack(fill="x", pady=1)
            row_frame.pack_propagate(False)

            cb_frame = ctk.CTkFrame(row_frame, fg_color="transparent", width=80, height=28)
            cb_frame.place(x=10, y=2)
            cb = ctk.CTkCheckBox(cb_frame, text="", variable=sel_var, width=20)
            cb.pack(expand=True)

            lbl_name = ctk.CTkLabel(row_frame, text=d, width=220, height=28, font=ctk.CTkFont(size=13), anchor="w")
            lbl_name.place(x=100, y=2)

            lbl_images = ctk.CTkLabel(row_frame, text=str(num_images), width=100, height=28, font=ctk.CTkFont(size=13), anchor="center")
            lbl_images.place(x=330, y=2)

            lbl_songs = ctk.CTkLabel(row_frame, text=str(num_songs), width=100, height=28, font=ctk.CTkFont(size=13), anchor="center")
            lbl_songs.place(x=440, y=2)

            lbl_time = ctk.CTkLabel(row_frame, text="-", width=120, height=28, font=ctk.CTkFont(size=13), anchor="center")
            lbl_time.place(x=550, y=2)

            lbl_status = ctk.CTkLabel(row_frame, text="Chờ", width=160, height=28, font=ctk.CTkFont(size=13, weight="bold"), text_color="gray", anchor="center")
            lbl_status.place(x=680, y=2)

            self.singers_data.append({
                'name': d,
                'path': singer_path,
                'num_images': num_images,
                'num_songs': num_songs,
                'selected': sel_var,
                'row_frame': row_frame,
                'label_time': lbl_time,
                'label_status': lbl_status
            })

    def update_singer_status(self, singer_name: str, status: str, percent: float = None):
        for s in self.singers_data:
            if s['name'] == singer_name:
                text = status
                if percent is not None:
                    text = f"{status} ({percent:.0f}%)"
                color = "gray"
                if "Đang" in status or "render" in status.lower():
                    color = ("#2563eb", "#3b82f6")
                elif "Xong" in status or "Hoàn" in status or "Thành công" in status:
                    color = ("#16a34a", "#22c55e")
                elif "Lỗi" in status or "Thất bại" in status:
                    color = ("#dc2626", "#ef4444")
                elif "Bỏ" in status:
                    color = "gray50"
                s['label_status'].configure(text=text, text_color=color)
                break

    def update_singer_time(self, singer_name: str, elapsed_str: str):
        for s in self.singers_data:
            if s['name'] == singer_name:
                s['label_time'].configure(text=elapsed_str)
                break

    def get_selected_singers(self) -> list:
        return [
            {
                'name': s['name'],
                'path': s['path'],
                'num_images': s['num_images'],
                'num_songs': s['num_songs']
            }
            for s in self.singers_data if s['selected'].get() == 1
        ]

    def _build_long_config_section(self, parent):
        """Xây dựng phần cấu hình Video Long (Compact)."""
        header = ctk.CTkLabel(
            parent, text="🎬  CẤU HÌNH VIDEO LONG (16:9)",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        header.pack(fill="x", padx=0, pady=(0, 4))

        config_frame = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"))
        config_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Row 0: Font Picker & Font Path
        font_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        font_frame.pack(fill="x", padx=10, pady=(4, 2))
        font_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            font_frame, text="📂 Chọn Font (.ttf/.otf)",
            width=150, height=24, font=ctk.CTkFont(size=11),
            fg_color=("gray78", "gray25"),
            hover_color=("gray68", "gray35"),
            text_color=("gray10", "gray90"),
            command=self._browse_font
        ).grid(row=0, column=0, padx=(0, 5), pady=0, sticky="w")

        ctk.CTkLabel(
            font_frame,
            textvariable=self.font_path,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            anchor="w"
        ).grid(row=0, column=1, padx=0, pady=0, sticky="ew")

        # Row 1: X, Y, Size of Font (inline)
        pos_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        pos_frame.pack(fill="x", padx=10, pady=2)
        self._add_inline_entries(pos_frame, [
            ("X (ngang):", self.font_x),
            ("Y (dọc):", self.font_y),
            ("S (cỡ chữ):", self.font_s),
        ])

        # Row 2: Songs per video, Songs in list
        qty_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        qty_frame.pack(fill="x", padx=10, pady=2)
        self._add_inline_entries(qty_frame, [
            ("Số bài ghép:", self.songs_per_video),
            ("Số bài hiển thị list:", self.songs_in_list),
        ])

        # Row 3: Num Long videos, Out multiplier
        qty_frame2 = ctk.CTkFrame(config_frame, fg_color="transparent")
        qty_frame2.pack(fill="x", padx=10, pady=(2, 4))
        self._add_inline_entries(qty_frame2, [
            ("Số lượng Video:", self.num_long_videos),
            ("Out (nhân bản):", self.out_multiplier),
        ])

    # ─────────────────────────────────────────────
    # SECTION 3: CẤU HÌNH VIDEO SHORT (9:16)
    # ─────────────────────────────────────────────
    def _build_short_config_section(self, parent):
        """Xây dựng phần cấu hình Video Short (Compact)."""
        header = ctk.CTkLabel(
            parent, text="📱  CẤU HÌNH VIDEO SHORT (9:16)",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        header.pack(fill="x", padx=0, pady=(0, 4))

        config_frame = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"))
        config_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Row 0: Duration, Num short videos
        top_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=(4, 2))
        self._add_inline_entries(top_frame, [
            ("Thời gian (giây):", self.short_duration),
            ("Số lượng Short:", self.num_short_videos),
        ])

        # Row 1: NamePNG position X, Y, Size
        pos_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        pos_frame.pack(fill="x", padx=10, pady=(2, 4))
        self._add_inline_entries(pos_frame, [
            ("X (ngang):", self.short_namepng_x),
            ("Y (dọc):", self.short_namepng_y),
            ("S (cỡ):", self.short_namepng_s),
        ])

    # ─────────────────────────────────────────────
    # HELPER METHODS
    # ─────────────────────────────────────────────
    def _add_inline_entries(self, parent, fields: list):
        """
        Thêm nhóm Label + Entry inline (Compact).
        fields: list of (label_text, StringVar)
        """
        for col, (label_text, var) in enumerate(fields):
            col_offset = col * 2
            ctk.CTkLabel(
                parent, text=label_text,
                font=ctk.CTkFont(size=12), anchor="w"
            ).grid(row=0, column=col_offset, padx=(0 if col == 0 else 10, 3),
                   pady=2, sticky="w")

            ctk.CTkEntry(
                parent, textvariable=var, width=60, height=24,
                font=ctk.CTkFont(size=12), justify="center"
            ).grid(row=0, column=col_offset + 1, padx=(0, 2), pady=2, sticky="w")

    # ─────────────────────────────────────────────
    # SECTION 4: THREAD SLIDER
    # ─────────────────────────────────────────────
    def _build_thread_section(self, parent):
        """Thanh trượt chọn số luồng render đồng thời (Compact)."""
        header = ctk.CTkLabel(
            parent, text="🧵  SỐ LUỒNG RENDER",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        header.pack(fill="x", padx=0, pady=(0, 4))

        thread_frame = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"))
        thread_frame.pack(fill="both", expand=True, padx=0, pady=0)

        inner = ctk.CTkFrame(thread_frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=10, pady=8)

        ctk.CTkLabel(
            inner, text="Luồng:",
            font=ctk.CTkFont(size=12), anchor="w"
        ).pack(side="left", padx=(0, 5))

        self.thread_slider = ctk.CTkSlider(
            inner, from_=1, to=5, number_of_steps=4,
            width=100,
            variable=self.thread_count,
            command=self._on_thread_change,
            progress_color=("#2563eb", "#3b82f6"),
            button_color=("#1d4ed8", "#2563eb"),
            button_hover_color=("#1e40af", "#1d4ed8"),
        )
        self.thread_slider.pack(side="left", padx=(0, 5))
        self.thread_slider.set(3)

        self.thread_label = ctk.CTkLabel(
            inner, text="3 luồng",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#2563eb", "#3b82f6"),
            width=60
        )
        self.thread_label.pack(side="left")

    def _build_controls_section(self):
        """Xây dựng dòng chờ lệnh (các nút điều khiển + Progress Bar)."""
        controls_container = ctk.CTkFrame(self, fg_color="transparent")
        controls_container.pack(fill="x", padx=15, pady=(2, 4))

        self.control_frame = ctk.CTkFrame(controls_container, fg_color=("gray88", "gray15"))
        self.control_frame.pack(fill="x", pady=(0, 3))
        self.control_frame.grid_columnconfigure(5, weight=1)

        btn_style = {
            'height': 32,
            'font': ctk.CTkFont(size=13, weight="bold"),
            'corner_radius': 6,
        }

        # 👁 Demo
        self.btn_demo = ctk.CTkButton(
            self.control_frame, text="👁  Demo", width=100,
            fg_color=("#7c3aed", "#6d28d9"),
            hover_color=("#6d28d9", "#5b21b6"),
            command=self.app._on_demo,
            **btn_style
        )
        self.btn_demo.grid(row=0, column=0, padx=(10, 4), pady=6)

        # ▶ Bắt đầu
        self.btn_start = ctk.CTkButton(
            self.control_frame, text="▶  Bắt đầu", width=100,
            fg_color=("#16a34a", "#15803d"),
            hover_color=("#15803d", "#166534"),
            command=self.app._on_start,
            **btn_style
        )
        self.btn_start.grid(row=0, column=1, padx=4, pady=6)

        # ⏸ Tạm dừng
        self.btn_pause = ctk.CTkButton(
            self.control_frame, text="⏸  Tạm dừng", width=100,
            fg_color=("#d97706", "#b45309"),
            hover_color=("#b45309", "#92400e"),
            command=self.app._on_pause,
            **btn_style
        )
        self.btn_pause.grid(row=0, column=2, padx=4, pady=6)

        # ▶ Tiếp tục
        self.btn_resume = ctk.CTkButton(
            self.control_frame, text="▶  Tiếp tục", width=100,
            fg_color=("#2563eb", "#1d4ed8"),
            hover_color=("#1d4ed8", "#1e3a8a"),
            command=self.app._on_resume,
            **btn_style
        )
        self.btn_resume.grid(row=0, column=3, padx=4, pady=6)

        # ✖ Hủy bỏ
        self.btn_cancel = ctk.CTkButton(
            self.control_frame, text="✖  Hủy bỏ", width=100,
            fg_color=("#dc2626", "#b91c1c"),
            hover_color=("#b91c1c", "#991b1b"),
            command=self.app._on_cancel,
            **btn_style
        )
        self.btn_cancel.grid(row=0, column=4, padx=(4, 10), pady=6)

        # Status label
        self.render_status = ctk.CTkLabel(
            self.control_frame, text="⏹ Chờ lệnh",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray55"),
            anchor="e"
        )
        self.render_status.grid(row=0, column=5, padx=(10, 15), pady=6, sticky="e")

        # Progress bar
        self.render_progress = ctk.CTkProgressBar(
            controls_container, height=6,
            progress_color=("#16a34a", "#22c55e"),
            fg_color=("gray80", "gray20"),
        )
        self.render_progress.pack(fill="x", pady=0)
        self.render_progress.set(0)

    def _on_thread_change(self, value):
        """Cập nhật label khi kéo slider."""
        n = int(round(value))
        self.thread_count.set(n)
        self.thread_label.configure(text=f"{n} luồng")

    def _browse_folder(self, key: str):
        """Mở dialog chọn thư mục."""
        folder = filedialog.askdirectory(
            title=f"Chọn thư mục — {key}"
        )
        if folder:
            self.folders[key].set(folder)

    def _browse_font(self):
        """Mở dialog chọn file font."""
        font_file = filedialog.askopenfilename(
            title="Chọn file Font",
            filetypes=[
                ("Font files", "*.ttf *.otf *.TTF *.OTF"),
                ("TrueType Font", "*.ttf"),
                ("OpenType Font", "*.otf"),
                ("All files", "*.*"),
            ]
        )
        if font_file:
            self.font_path.set(font_file)

    # ─────────────────────────────────────────────
    # PUBLIC METHODS (gọi từ app.py)
    # ─────────────────────────────────────────────
    def get_folders(self) -> dict:
        """Trả về dict đường dẫn thư mục."""
        return {k: v.get() for k, v in self.folders.items()}

    def get_long_config(self) -> dict:
        """Trả về cấu hình Video Long."""
        return {
            'font_path': self.font_path.get(),
            'font_x': self._safe_int(self.font_x.get(), 100),
            'font_y': self._safe_int(self.font_y.get(), 300),
            'font_s': self._safe_int(self.font_s.get(), 40),
            'songs_per_video': self._safe_int(self.songs_per_video.get(), 5),
            'songs_in_list': self._safe_int(self.songs_in_list.get(), 5),
            'num_videos': self._safe_int(self.num_long_videos.get(), 1),
            'out_multiplier': self._safe_int(self.out_multiplier.get(), 1),
        }

    def get_short_config(self) -> dict:
        """Trả về cấu hình Video Short."""
        return {
            'short_duration': self._safe_int(self.short_duration.get(), 60),
            'num_short_videos': self._safe_int(self.num_short_videos.get(), 1),
            'short_namepng_x': self._safe_int(self.short_namepng_x.get(), 100),
            'short_namepng_y': self._safe_int(self.short_namepng_y.get(), 1200),
            'short_namepng_s': self._safe_int(self.short_namepng_s.get(), 36),
        }

    def validate(self) -> tuple:
        """
        Kiểm tra dữ liệu hợp lệ.

        Returns:
            (is_valid: bool, error_message: str)
        """
        folders = self.get_folders()

        # Kiểm tra thư mục bắt buộc
        required = {
            'singer_root': 'Thư mục Ca Sĩ',
            'output': 'Thư mục Output',
        }
        for key, name in required.items():
            if not folders[key]:
                return False, f"❌ Chưa chọn {name}!"

        # Kiểm tra thư mục tồn tại
        import os
        for key, path in folders.items():
            if path and not os.path.isdir(path):
                return False, f"❌ Thư mục không tồn tại: {path}"

        # Kiểm tra danh sách ca sĩ chọn
        selected = self.get_selected_singers()
        if not selected:
            return False, "❌ Chưa chọn ca sĩ nào để render!"

        # Kiểm tra số lượng video
        long_cfg = self.get_long_config()
        short_cfg = self.get_short_config()

        if long_cfg['num_videos'] < 0:
            return False, "❌ Số Video Long phải >= 0!"
        if short_cfg['num_short_videos'] < 0:
            return False, "❌ Số Video Short phải >= 0!"
        if long_cfg['num_videos'] == 0 and short_cfg['num_short_videos'] == 0:
            return False, "❌ Phải có ít nhất 1 video Long hoặc Short!"

        return True, ""

    @staticmethod
    def _safe_int(value: str, default: int = 0) -> int:
        """Convert string sang int an toàn."""
        try:
            return max(0, int(value))
        except (ValueError, TypeError):
            return default

    def get_thread_count(self) -> int:
        """Trả về số luồng render."""
        return max(1, min(5, self.thread_count.get()))
