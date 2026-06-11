"""
Video Render App — Ứng dụng chính.
Kết hợp TabView (Video + Tải Nhạc), control buttons, progress bar, log.
"""

import customtkinter as ctk
import threading
from tab_video import VideoTab
from tab_download import DownloadTab
from data_handler import prepare_all_jobs
from render_engine import RenderEngine, RenderState


class VideoRenderApp(ctk.CTk):
    """Ứng dụng chính Video Render Tool."""

    APP_TITLE = "🎬 Video Render Tool"
    APP_WIDTH = 950
    APP_HEIGHT = 780

    def __init__(self):
        super().__init__()

        # ─── Window config ───
        self.title(self.APP_TITLE)
        self.geometry(f"{self.APP_WIDTH}x{self.APP_HEIGHT}")
        self.minsize(800, 650)

        # Center window
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - self.APP_WIDTH) // 2
        y = (screen_h - self.APP_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

        # ─── State ───
        self.render_engine = RenderEngine()
        self._render_thread = None

        # ─── Build UI ───
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Tabview mở rộng

        self._build_header()
        self._build_tabview()

        # Initial button states
        self._update_button_states()

        # Tải cấu hình cũ đã lưu nếu có
        self._load_settings()

        # Đăng ký sự kiện đóng ứng dụng để lưu cấu hình
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ═══════════════════════════════════════════
    # HEADER
    # ═══════════════════════════════════════════
    def _build_header(self):
        """Tiêu đề ứng dụng."""
        header_frame = ctk.CTkFrame(self, fg_color=("gray85", "gray13"),
                                    height=55, corner_radius=0)
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.grid_propagate(False)
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header_frame,
            text="🎬  VIDEO RENDER TOOL",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=("gray10", "#e0e7ff"),
        )
        title.grid(row=0, column=0, padx=20, pady=12, sticky="w")

        # Version label
        ver = ctk.CTkLabel(
            header_frame,
            text="v1.0 — Phase 1 & 2",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray50"),
        )
        ver.grid(row=0, column=1, padx=20, pady=12, sticky="e")

    # ═══════════════════════════════════════════
    # TABVIEW
    # ═══════════════════════════════════════════
    def _build_tabview(self):
        """TabView với 2 tab: Video và Tải Nhạc."""
        self.tabview = ctk.CTkTabview(
            self,
            command=self._on_tab_change,
            segmented_button_fg_color=("gray80", "gray20"),
            segmented_button_selected_color=("#2563eb", "#1d4ed8"),
            segmented_button_selected_hover_color=("#1e40af", "#1e3a8a"),
            segmented_button_unselected_color=("gray75", "gray25"),
            segmented_button_unselected_hover_color=("gray65", "gray35"),
            fg_color=("gray93", "gray12"),
        )
        self.tabview.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="nsew")

        # Tab 1: Video Long + Short
        tab1 = self.tabview.add("📹  Video Long + Short")
        tab1.grid_columnconfigure(0, weight=1)
        tab1.grid_rowconfigure(0, weight=1)

        self.video_tab = VideoTab(tab1, self)
        self.video_tab.grid(row=0, column=0, sticky="nsew")

        # Tab 2: Tải Nhạc
        tab2 = self.tabview.add("🎵  Tải Nhạc")
        tab2.grid_columnconfigure(0, weight=1)
        tab2.grid_rowconfigure(0, weight=1)

        self.download_tab = DownloadTab(tab2, self)
        self.download_tab.grid(row=0, column=0, sticky="nsew")

    # ═══════════════════════════════════════════
    # LOG HELPER
    # ═══════════════════════════════════════════
    def log(self, message: str):
        """Ghi log ra console."""
        import sys
        try:
            print(message)
        except Exception:
            try:
                # Fallback: encode with console encoding and replace unsupported chars
                enc = sys.stdout.encoding or 'utf-8'
                safe_msg = message.encode(enc, errors='replace').decode(enc)
                print(safe_msg)
            except Exception:
                pass

    def _clear_log(self):
        """Xóa log (no-op)."""
        pass

    # ═══════════════════════════════════════════
    # BUTTON STATE MANAGEMENT
    # ═══════════════════════════════════════════
    def _update_button_states(self):
        """Cập nhật trạng thái nút dựa trên trạng thái render."""
        if not hasattr(self, 'video_tab'):
            return
        state = self.render_engine.state

        if state == RenderState.IDLE or state == RenderState.COMPLETED or \
                state == RenderState.CANCELLED:
            self.video_tab.btn_start.configure(state="normal")
            self.video_tab.btn_pause.configure(state="disabled")
            self.video_tab.btn_resume.configure(state="disabled")
            self.video_tab.btn_cancel.configure(state="disabled")
            status_text = "⏹ Chờ lệnh"
            if state == RenderState.COMPLETED:
                status_text = "✅ Hoàn tất"
            elif state == RenderState.CANCELLED:
                status_text = "⏹ Đã hủy"

        elif state == RenderState.RUNNING:
            self.video_tab.btn_start.configure(state="disabled")
            self.video_tab.btn_pause.configure(state="normal")
            self.video_tab.btn_resume.configure(state="disabled")
            self.video_tab.btn_cancel.configure(state="normal")
            status_text = "🔄 Đang render..."

        elif state == RenderState.PAUSED:
            self.video_tab.btn_start.configure(state="disabled")
            self.video_tab.btn_pause.configure(state="disabled")
            self.video_tab.btn_resume.configure(state="normal")
            self.video_tab.btn_cancel.configure(state="normal")
            status_text = "⏸ Tạm dừng"

        else:
            status_text = "⏹ Chờ lệnh"

        self.video_tab.render_status.configure(text=status_text)

    # ═══════════════════════════════════════════
    # DEMO
    # ═══════════════════════════════════════════
    def _on_demo(self):
        """Mở popup chọn xem Demo Long hoặc Short."""
        popup = ctk.CTkToplevel(self)
        popup.title("👁 Chọn loại Demo")
        popup.geometry("340x200")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        # Center popup
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 340) // 2
        y = self.winfo_y() + (self.winfo_height() - 200) // 2
        popup.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            popup, text="Chọn loại video để xem Demo",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(25, 20))

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=(0, 15))

        ctk.CTkButton(
            btn_frame, text="🎬  Demo Long (16:9)",
            width=140, height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#7c3aed", "#6d28d9"),
            hover_color=("#6d28d9", "#5b21b6"),
            command=lambda: self._run_demo("long", popup)
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame, text="📱  Demo Short (9:16)",
            width=140, height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#0891b2", "#0e7490"),
            hover_color=("#0e7490", "#155e75"),
            command=lambda: self._run_demo("short", popup)
        ).pack(side="left", padx=8)

    def _run_demo(self, demo_type: str, popup):
        """Tạo sample jobs theo đúng số lượng cấu hình và hiển thị ảnh demo có nút chuyển tiếp."""
        popup.destroy()

        # Validate
        is_valid, error = self.video_tab.validate()
        if not is_valid:
            self.log(error)
            return

        import os
        from data_handler import scan_singer_media, generate_long_video_jobs, generate_short_video_jobs
        from pathlib import Path

        folders = self.video_tab.get_folders()
        selected_singers = self.video_tab.get_selected_singers()
        long_config = self.video_tab.get_long_config()
        short_config = self.video_tab.get_short_config()

        # Ghi nhớ cấu hình
        self._save_settings()

        self._clear_log()
        self.log(f"👁 DEMO — {'Video Long (16:9)' if demo_type == 'long' else 'Video Short (9:16)'}")
        self.log(f"{'═' * 50}\n")

        singer = selected_singers[0]
        self.log(f"🎤 Chạy Demo với Ca sĩ: {singer['name']}")
        media = scan_singer_media(singer['path'], folders)

        if demo_type == "long":
            demo_config = dict(long_config)
            # Không ghi đè số lượng về 1 nữa, dùng đúng số lượng cấu hình thực tế
            jobs = generate_long_video_jobs(media, demo_config, self.log)
            if jobs:
                safe_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in singer['name']]).replace(" ", "_")
                for job in jobs:
                    job['singer_name'] = singer['name']
                    job['output_path'] = os.path.join(folders.get('output', '.'), f"{safe_name}_Long_{job['index']:03d}.mp4")
        else:
            demo_config = dict(short_config)
            jobs = generate_short_video_jobs(media, demo_config, self.log)
            if jobs:
                safe_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in singer['name']]).replace(" ", "_")
                for job in jobs:
                    job['singer_name'] = singer['name']
                    job['output_path'] = os.path.join(folders.get('output', '.'), f"{safe_name}_Short_{job['index']:03d}.mp4")

        if not jobs:
            self.log("\n❌ Không đủ dữ liệu để tạo demo!")
            return

        self.log(f"\n⚡ Đã khởi tạo {len(jobs)} bản ghi demo trực quan.")

        # ─── Hiển thị hình ảnh Demo trực quan (Carousel) ───
        try:
            from PIL import Image
            from preprocessor import preprocess_image, crop_short_from_long_bg

            preview_images = []
            for job in jobs:
                if demo_type == "long":
                    # 1. Background image (1920x1080)
                    bg_img = preprocess_image(job['background'], 'long')
                    bg_img = bg_img.convert("RGBA")

                    # 2. Ghép NamePNG (giữa màn hình, cách top 50px)
                    if job.get('namepng') and os.path.exists(job['namepng']):
                        np_img = Image.open(job['namepng']).convert("RGBA")
                        np_x = (1920 - np_img.width) // 2
                        np_y = 50
                        bg_img.paste(np_img, (np_x, np_y), np_img)

                    # 3. Ghép danh sách bài hát
                    if job.get('display_list'):
                        text_img = self.render_engine._create_text_overlay(
                            names=job['display_list'],
                            font_path=job.get('font_path', ''),
                            font_size=job.get('font_s', 36),
                        )
                        text_x = job.get('font_x', 100)
                        text_y = job.get('font_y', 300)
                        bg_img.paste(text_img, (text_x, text_y), text_img)
                else:
                    # 1. Background image (1080x1920, cắt phần 3)
                    if job.get('background') and os.path.exists(job['background']):
                        bg_img = crop_short_from_long_bg(job['background'])
                    else:
                        bg_img = Image.new('RGBA', (1080, 1920), (20, 20, 30, 255))
                    bg_img = bg_img.convert("RGBA")

                    # 2. Ghép NamePNG (vị trí x, y, size của Short)
                    if job.get('namepng') and os.path.exists(job['namepng']):
                        np_img = Image.open(job['namepng']).convert("RGBA")
                        np_s = job.get('namepng_s', 300)
                        # Resize giữ nguyên tỉ lệ
                        aspect = np_img.height / np_img.width
                        new_h = int(np_s * aspect)
                        np_img = np_img.resize((np_s, new_h), Image.LANCZOS)
                        np_x = job.get('namepng_x', 100)
                        np_y = job.get('namepng_y', 1200)
                        bg_img.paste(np_img, (np_x, np_y), np_img)

                    # 3. Ghép tên bài hát short
                    if job.get('song_name'):
                        text_img = self.render_engine._create_short_song_overlay(job['song_name'])
                        bg_img.paste(text_img, (0, 0), text_img)

                preview_images.append(bg_img)

            # Mở cửa sổ popup hiển thị ảnh demo dạng Carousel
            preview_popup = ctk.CTkToplevel(self)
            preview_popup.title(f"👁️ Bản xem trước Demo — {'Long (16:9)' if demo_type == 'long' else 'Short (9:16)'}")
            preview_popup.transient(self)
            preview_popup.grab_set()

            # Tính toán kích thước hiển thị thu nhỏ
            if demo_type == "long":
                display_w = 800
                display_h = 450
            else:
                display_w = 320
                display_h = 569

            # Thêm khoảng trống 140px cho nút mũi tên 2 bên và 160px cho tiêu đề + thông tin
            preview_popup.geometry(f"{display_w + 140}x{display_h + 160}")
            preview_popup.resizable(False, False)

            # Căn giữa popup
            preview_popup.update_idletasks()
            x_pos = self.winfo_x() + (self.winfo_width() - (display_w + 140)) // 2
            y_pos = self.winfo_y() + (self.winfo_height() - (display_h + 160)) // 2
            preview_popup.geometry(f"+{x_pos}+{y_pos}")

            current_idx = 0
            total_images = len(preview_images)

            # --- Điều hướng trong Carousel ---
            def update_preview():
                nonlocal current_idx
                # Cập nhật tiêu đề chỉ số
                lbl_title.configure(text=f"🎥 Bản xem trước Video {current_idx + 1} / {total_images}")

                # Resize PIL Image
                pil_img = preview_images[current_idx]
                display_img = pil_img.resize((display_w, display_h), Image.LANCZOS)

                # Dựng CTkImage
                from customtkinter import CTkImage
                ctk_img = CTkImage(light_image=display_img, dark_image=display_img, size=(display_w, display_h))
                preview_popup.ctk_img = ctk_img  # Tránh garbage collection
                lbl_img.configure(image=ctk_img)

                # Cập nhật chi tiết tệp
                job = jobs[current_idx]
                if demo_type == "long":
                    details = f"🖼️ BG: {Path(job['background']).name}  |  🏷️ NamePNG: {Path(job['namepng']).name if job.get('namepng') else 'N/A'}\n🎵 Nhạc: {len(job['songs'])} bài"
                else:
                    details = f"🖼️ BG: {Path(job['background']).name if job.get('background') else 'N/A'}  |  🏷️ NamePNG: {Path(job['namepng']).name if job.get('namepng') else 'N/A'}\n🎵 Bài: {job.get('song_name', 'N/A')} ({job.get('duration', 60)} giây)"
                lbl_details.configure(text=details)

                # Bật/tắt nút điều hướng
                btn_prev.configure(state="normal" if current_idx > 0 else "disabled")
                btn_next.configure(state="normal" if current_idx < total_images - 1 else "disabled")

            def on_prev():
                nonlocal current_idx
                if current_idx > 0:
                    current_idx -= 1
                    update_preview()

            def on_next():
                nonlocal current_idx
                if current_idx < total_images - 1:
                    current_idx += 1
                    update_preview()

            # ─── XÂY DỰNG LAYOUT CHO POPUP ───
            # 1. Chỉ số
            lbl_title = ctk.CTkLabel(
                preview_popup, text="",
                font=ctk.CTkFont(size=14, weight="bold")
            )
            lbl_title.pack(pady=(12, 6))

            # 2. Vùng hiển thị chính (Nút Trái | Ảnh | Nút Phải)
            main_row = ctk.CTkFrame(preview_popup, fg_color="transparent")
            main_row.pack(fill="x", padx=10)

            btn_prev = ctk.CTkButton(
                main_row, text="◀", width=45, height=45,
                font=ctk.CTkFont(size=20, weight="bold"),
                fg_color=("gray75", "gray25"),
                hover_color=("gray65", "gray35"),
                text_color=("gray10", "gray90"),
                command=on_prev
            )
            btn_prev.pack(side="left", padx=10)

            lbl_img = ctk.CTkLabel(main_row, text="")
            lbl_img.pack(side="left", expand=True)

            btn_next = ctk.CTkButton(
                main_row, text="▶", width=45, height=45,
                font=ctk.CTkFont(size=20, weight="bold"),
                fg_color=("gray75", "gray25"),
                hover_color=("gray65", "gray35"),
                text_color=("gray10", "gray90"),
                command=on_next
            )
            btn_next.pack(side="right", padx=10)

            # 3. Thông tin chi tiết
            lbl_details = ctk.CTkLabel(
                preview_popup, text="",
                font=ctk.CTkFont(size=12, slant="italic"),
                text_color=("gray40", "gray60"),
                justify="center"
            )
            lbl_details.pack(pady=8)

            # 4. Nút Đóng
            btn_close = ctk.CTkButton(
                preview_popup, text="Đóng", width=120, height=32,
                font=ctk.CTkFont(size=13, weight="bold"),
                command=preview_popup.destroy
            )
            btn_close.pack(pady=(4, 10))

            # Chạy hiển thị ảnh đầu tiên
            update_preview()

            self.log("✅ Demo hoàn tất. Nhấn 'Bắt đầu' để render thực tế.")

        except Exception as preview_err:
            self.log(f"⚠️ Không thể tạo ảnh xem trước demo: {preview_err}")

    # ═══════════════════════════════════════════
    # CONTROL BUTTON ACTIONS
    # ═══════════════════════════════════════════
    def _on_start(self):
        """Xử lý nút Bắt đầu."""
        # Validate
        is_valid, error = self.video_tab.validate()
        if not is_valid:
            self.log(error)
            return

        # Lấy cấu hình
        folders = self.video_tab.get_folders()
        selected_singers = self.video_tab.get_selected_singers()
        long_config = self.video_tab.get_long_config()
        short_config = self.video_tab.get_short_config()

        # Ghi nhớ cấu hình
        self._save_settings()

        self._clear_log()
        self.log("🚀 Bắt đầu chuẩn bị render...\n")
        self.video_tab.render_progress.set(0)

        # Chuẩn bị jobs trên thread riêng
        def _prepare_and_render():
            try:
                import time
                from data_handler import prepare_all_jobs

                # Phase 2: Ghép cặp ngẫu nhiên & tiền xử lý
                jobs = prepare_all_jobs(
                    folders=folders,
                    selected_singers=selected_singers,
                    long_config=long_config,
                    short_config=short_config,
                    log_callback=self.log
                )

                if not jobs:
                    self.log("\n❌ Không có video nào để render!")
                    self.after(0, self._update_button_states)
                    return

                # Khởi tạo tracking trạng thái render của từng ca sĩ
                singer_tracking = {}
                for s in selected_singers:
                    name = s['name']
                    singer_jobs = [j for j in jobs if j.get('singer_name') == name]
                    if singer_jobs:
                        singer_tracking[name] = {
                            'total': len(singer_jobs),
                            'completed': 0,
                            'status': 'Chờ',
                            'start_time': None,
                            'final_time': None
                        }
                        self.video_tab.update_singer_status(name, "Chờ")
                        self.video_tab.update_singer_time(name, "-")
                    else:
                        self.video_tab.update_singer_status(name, "Bỏ qua")

                # Cập nhật trạng thái các ca sĩ không được chọn sang Bỏ qua
                all_singers = [s['name'] for s in self.video_tab.singers_data]
                selected_names = [s['name'] for s in selected_singers]
                for name in all_singers:
                    if name not in selected_names:
                        self.video_tab.update_singer_status(name, "Bỏ qua")
                        self.video_tab.update_singer_time(name, "-")

                self.log(f"\n{'═' * 50}")
                self.log("🎬 Bắt đầu render...")
                self.log(f"{'═' * 50}\n")

                # Cập nhật trạng thái nút
                self.after(0, self._update_button_states)

                # Callback khi hoàn tất 1 job
                def _job_complete(job, success):
                    singer_name = job.get('singer_name')
                    if singer_name in singer_tracking:
                        info = singer_tracking[singer_name]
                        if info['start_time'] is None:
                            info['start_time'] = time.time()
                            self.video_tab.update_singer_status(singer_name, "Đang render", 0)

                        info['completed'] += 1
                        percent = (info['completed'] / info['total']) * 100

                        if info['completed'] >= info['total']:
                            final_elapsed = int(time.time() - info['start_time'])
                            mins = final_elapsed // 60
                            secs = final_elapsed % 60
                            info['final_time'] = final_elapsed
                            self.video_tab.update_singer_time(singer_name, f"{mins:02d}:{secs:02d}")
                            self.video_tab.update_singer_status(singer_name, "Xong")
                        else:
                            self.video_tab.update_singer_status(singer_name, "Đang render", percent)

                # Cập nhật thời gian render từng ca sĩ liên tục
                def _update_singer_clocks():
                    if self.render_engine.is_running:
                        current_time = time.time()
                        for name, info in singer_tracking.items():
                            if info['completed'] < info['total']:
                                if info['start_time'] is not None:
                                    elapsed = int(current_time - info['start_time'])
                                    mins = elapsed // 60
                                    secs = elapsed % 60
                                    self.video_tab.update_singer_time(name, f"{mins:02d}:{secs:02d}")
                        self.after(1000, _update_singer_clocks)

                self.after(1000, _update_singer_clocks)

                # Phase 3: Render
                def _progress(current, total):
                    def _update():
                        self.video_tab.render_progress.set(current / total)
                        self.video_tab.render_status.configure(
                            text=f"🔄 Render: {current}/{total}"
                        )
                    self.after(0, _update)

                self.render_engine.start(
                    jobs=jobs,
                    config={'folders': folders, 'long': long_config,
                            'short': short_config},
                    max_workers=self.video_tab.get_thread_count(),
                    progress_callback=_progress,
                    log_callback=self.log,
                    job_complete_callback=_job_complete
                )

                # Đợi render hoàn tất
                if self.render_engine._thread:
                    self.render_engine._thread.join()

                # Cập nhật UI sau khi xong
                self.after(0, self._update_button_states)

            except Exception as e:
                self.log(f"\n❌ Lỗi: {e}")
                self.after(0, self._update_button_states)

        # Cập nhật nút ngay
        self.video_tab.btn_start.configure(state="disabled")
        self.video_tab.render_status.configure(text="🔄 Đang chuẩn bị...")

        self._render_thread = threading.Thread(
            target=_prepare_and_render, daemon=True
        )
        self._render_thread.start()

    def _on_pause(self):
        """Xử lý nút Tạm dừng."""
        self.render_engine.pause()
        self.log("⏸ Đã tạm dừng render.")
        self._update_button_states()

    def _on_resume(self):
        """Xử lý nút Tiếp tục."""
        self.render_engine.resume()
        self.log("▶ Tiếp tục render...")
        self._update_button_states()

    def _on_cancel(self):
        """Xử lý nút Hủy bỏ."""
        self.render_engine.cancel()
        self.log("✖ Đã hủy render!")
        self._update_button_states()
        self.video_tab.render_progress.set(0)

    def _on_tab_change(self):
        """Không làm gì vì nút đã nằm trong tab."""
        pass

    # ═══════════════════════════════════════════
    # SETTINGS PERSISTENCE (Ghi nhớ cấu hình)
    # ═══════════════════════════════════════════
    def _on_closing(self):
        """Xử lý sự kiện đóng cửa sổ chính."""
        self._save_settings()
        self.destroy()

    def _save_settings(self):
        """Lưu cấu hình đã thiết lập vào file settings.json."""
        import json
        settings = {}
        try:
            # Video tab
            if hasattr(self, 'video_tab'):
                for key, var in self.video_tab.folders.items():
                    settings[f"folder_{key}"] = var.get()
                settings["font_path"] = self.video_tab.font_path.get()
                settings["font_x"] = self.video_tab.font_x.get()
                settings["font_y"] = self.video_tab.font_y.get()
                settings["font_s"] = self.video_tab.font_s.get()
                settings["songs_per_video"] = self.video_tab.songs_per_video.get()
                settings["songs_in_list"] = self.video_tab.songs_in_list.get()
                settings["num_long_videos"] = self.video_tab.num_long_videos.get()
                settings["out_multiplier"] = self.video_tab.out_multiplier.get()
                settings["short_duration"] = self.video_tab.short_duration.get()
                settings["num_short_videos"] = self.video_tab.num_short_videos.get()
                settings["short_namepng_x"] = self.video_tab.short_namepng_x.get()
                settings["short_namepng_y"] = self.video_tab.short_namepng_y.get()
                settings["short_namepng_s"] = self.video_tab.short_namepng_s.get()
                settings["thread_count"] = self.video_tab.thread_count.get()

            # Download tab
            if hasattr(self, 'download_tab'):
                settings["download_save_folder"] = self.download_tab.save_folder.get()

            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            print("💾 Đã lưu cấu hình vào settings.json")
        except Exception as e:
            print(f"⚠️ Không thể lưu cấu hình: {e}")

    def _load_settings(self):
        """Đọc và khôi phục cấu hình từ settings.json."""
        import json
        import os
        if not os.path.exists("settings.json"):
            return

        try:
            with open("settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)

            # Khôi phục Video tab
            if hasattr(self, 'video_tab'):
                for key, var in self.video_tab.folders.items():
                    val = settings.get(f"folder_{key}")
                    if val is not None:
                        var.set(val)

                # Khôi phục các cấu hình khác
                config_mappings = {
                    "font_path": self.video_tab.font_path,
                    "font_x": self.video_tab.font_x,
                    "font_y": self.video_tab.font_y,
                    "font_s": self.video_tab.font_s,
                    "songs_per_video": self.video_tab.songs_per_video,
                    "songs_in_list": self.video_tab.songs_in_list,
                    "num_long_videos": self.video_tab.num_long_videos,
                    "out_multiplier": self.video_tab.out_multiplier,
                    "short_duration": self.video_tab.short_duration,
                    "num_short_videos": self.video_tab.num_short_videos,
                    "short_namepng_x": self.video_tab.short_namepng_x,
                    "short_namepng_y": self.video_tab.short_namepng_y,
                    "short_namepng_s": self.video_tab.short_namepng_s,
                }
                for key, var in config_mappings.items():
                    val = settings.get(key)
                    if val is not None:
                        var.set(val)

                # Khôi phục thread slider
                thread_count = settings.get("thread_count")
                if thread_count is not None:
                    self.video_tab.thread_count.set(thread_count)
                    self.video_tab.thread_slider.set(thread_count)
                    self.video_tab.thread_label.configure(text=f"{thread_count} luồng")

                # Cập nhật danh sách ca sĩ nếu có singer_root
                self.video_tab.update_singers_list()

            # Khôi phục Download tab
            if hasattr(self, 'download_tab'):
                val = settings.get("download_save_folder")
                if val is not None:
                    self.download_tab.save_folder.set(val)

            print("📂 Đã tải cấu hình từ settings.json")
        except Exception as e:
            print(f"⚠️ Không thể tải cấu hình: {e}")
