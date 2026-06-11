"""
Tab Tải Nhạc — Giao diện tải nhạc YouTube hàng loạt.
Nhập nhiều link (mỗi dòng 1 link), chọn thư mục lưu, tải hàng loạt.
"""

import customtkinter as ctk
from tkinter import filedialog
import threading


class DownloadTab(ctk.CTkFrame):
    """Tab tải nhạc từ YouTube."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._download_thread = None
        self._downloader = None

        # Biến
        self.save_folder = ctk.StringVar(value="")

        self._build_ui()

    def _build_ui(self):
        """Xây dựng giao diện tab Tải Nhạc."""

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)  # Textbox links mở rộng
        self.grid_rowconfigure(6, weight=1)  # Log mở rộng

        # ═══════════════════════════════════════
        # HEADER
        # ═══════════════════════════════════════
        header = ctk.CTkLabel(
            self, text="🎵  TẢI NHẠC TỪ YOUTUBE",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w"
        )
        header.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        # ═══════════════════════════════════════
        # THƯ MỤC LƯU
        # ═══════════════════════════════════════
        save_frame = ctk.CTkFrame(self, fg_color=("gray88", "gray17"))
        save_frame.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="ew")
        save_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            save_frame, text="📂 Chọn thư mục lưu nhạc",
            width=240, font=ctk.CTkFont(size=13),
            fg_color=("gray78", "gray25"),
            hover_color=("gray68", "gray35"),
            text_color=("gray10", "gray90"),
            command=self._browse_save_folder
        ).grid(row=0, column=0, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(
            save_frame,
            textvariable=self.save_folder,
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
            anchor="w"
        ).grid(row=0, column=1, padx=(5, 10), pady=8, sticky="ew")

        # ═══════════════════════════════════════
        # NHẬP LINK
        # ═══════════════════════════════════════
        link_label = ctk.CTkLabel(
            self, text="🔗  Nhập link YouTube (mỗi link 1 dòng):",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        link_label.grid(row=2, column=0, padx=15, pady=(5, 5), sticky="w")

        self.links_textbox = ctk.CTkTextbox(
            self, font=ctk.CTkFont(size=13, family="Consolas"),
            fg_color=("gray92", "gray14"),
            border_color=("gray70", "gray30"),
            border_width=1,
            height=180,
        )
        self.links_textbox.grid(row=3, column=0, padx=15, pady=(0, 10),
                                sticky="nsew")

        # Placeholder text
        self.links_textbox.insert("1.0",
                                  "https://www.youtube.com/watch?v=...\n"
                                  "https://www.youtube.com/watch?v=...\n"
                                  "https://www.youtube.com/watch?v=...")
        self.links_textbox.configure(text_color=("gray60", "gray50"))

        # Bind focus events cho placeholder
        self.links_textbox.bind("<FocusIn>", self._on_focus_in)
        self.links_textbox.bind("<FocusOut>", self._on_focus_out)
        self._placeholder_active = True

        # ═══════════════════════════════════════
        # NÚT TẢI & PROGRESS
        # ═══════════════════════════════════════
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=4, column=0, padx=15, pady=(0, 5), sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        self.download_btn = ctk.CTkButton(
            action_frame, text="⬇️  Tải Nhạc",
            width=160, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#2563eb", "#1d4ed8"),
            hover_color=("#1e40af", "#1e3a8a"),
            command=self._start_download
        )
        self.download_btn.grid(row=0, column=0, padx=(0, 15), pady=5, sticky="w")

        self.status_label = ctk.CTkLabel(
            action_frame, text="Sẵn sàng",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray60"),
            anchor="w"
        )
        self.status_label.grid(row=0, column=1, padx=0, pady=5, sticky="ew")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self, height=6,
            progress_color=("#2563eb", "#3b82f6"),
        )
        self.progress_bar.grid(row=5, column=0, padx=15, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)

        # ═══════════════════════════════════════
        # LOG TẢI NHẠC
        # ═══════════════════════════════════════
        log_label = ctk.CTkLabel(
            self, text="📋  Nhật ký tải nhạc:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        log_label.grid(row=6, column=0, padx=15, pady=(0, 3), sticky="nw")

        self.log_textbox = ctk.CTkTextbox(
            self, font=ctk.CTkFont(size=12, family="Consolas"),
            fg_color=("gray95", "gray10"),
            border_color=("gray70", "gray30"),
            border_width=1,
            state="disabled",
            height=150,
        )
        self.log_textbox.grid(row=7, column=0, padx=15, pady=(0, 10),
                              sticky="nsew")
        self.grid_rowconfigure(7, weight=1)

    # ─────────────────────────────────────────────
    # PLACEHOLDER HANDLING
    # ─────────────────────────────────────────────
    def _on_focus_in(self, event):
        if self._placeholder_active:
            self.links_textbox.delete("1.0", "end")
            self.links_textbox.configure(
                text_color=("gray10", "gray90")
            )
            self._placeholder_active = False

    def _on_focus_out(self, event):
        content = self.links_textbox.get("1.0", "end").strip()
        if not content:
            self._placeholder_active = True
            self.links_textbox.insert("1.0",
                                      "https://www.youtube.com/watch?v=...\n"
                                      "https://www.youtube.com/watch?v=...\n"
                                      "https://www.youtube.com/watch?v=...")
            self.links_textbox.configure(
                text_color=("gray60", "gray50")
            )

    # ─────────────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────────────
    def _browse_save_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu nhạc")
        if folder:
            self.save_folder.set(folder)

    def _get_urls(self) -> list:
        """Lấy danh sách URL từ textbox."""
        if self._placeholder_active:
            return []
        content = self.links_textbox.get("1.0", "end").strip()
        urls = [line.strip() for line in content.split("\n") if line.strip()]
        return urls

    def _log(self, message: str):
        """Ghi log ra textbox (thread-safe)."""
        def _update():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", message + "\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
        self.after(0, _update)

    def _update_progress(self, percent: float):
        """Cập nhật progress bar (thread-safe)."""
        def _update():
            self.progress_bar.set(percent / 100.0)
        self.after(0, _update)

    def _update_overall(self, completed: int, total: int):
        """Cập nhật tiến trình tổng (thread-safe)."""
        def _update():
            self.status_label.configure(
                text=f"⏳ Đang tải: {completed}/{total}"
            )
            self.progress_bar.set(completed / total)
        self.after(0, _update)

    def _start_download(self):
        """Bắt đầu tải nhạc trên thread riêng."""
        urls = self._get_urls()
        save_folder = self.save_folder.get()

        if not save_folder:
            self._log("❌ Chưa chọn thư mục lưu nhạc!")
            return

        if not urls:
            self._log("❌ Chưa nhập link YouTube nào!")
            return

        self._log(f"\n🚀 Bắt đầu tải {len(urls)} bài nhạc...")
        self._log(f"📂 Lưu vào: {save_folder}\n")

        # Disable nút tải
        self.download_btn.configure(state="disabled", text="⏳ Đang tải...")
        self.progress_bar.set(0)

        from downloader import MusicDownloader
        self._downloader = MusicDownloader()

        def _download_worker():
            try:
                self._downloader.download_multiple(
                    urls=urls,
                    save_folder=save_folder,
                    progress_callback=self._update_progress,
                    status_callback=self._log,
                    overall_callback=self._update_overall,
                )
            finally:
                def _restore():
                    self.download_btn.configure(
                        state="normal", text="⬇️  Tải Nhạc"
                    )
                    self.status_label.configure(text="✅ Hoàn tất")
                    self.progress_bar.set(1.0)
                self.after(0, _restore)

        self._download_thread = threading.Thread(
            target=_download_worker, daemon=True
        )
        self._download_thread.start()

    def cancel_download(self):
        """Hủy tải nhạc đang chạy."""
        if self._downloader:
            self._downloader.cancel()
            self._log("⏹ Đang hủy tải nhạc...")
