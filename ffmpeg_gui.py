import os
import sys
# Add parent directory to sys.path so we can import the shared _lib
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
from pathlib import Path
import _lib.UniversalUI as UniversalUI

# 設定支援的副檔名
SUPPORTED_EXTENSIONS = {
    # Audio
    '.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.wma', 
    # Video
    '.webm', '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.m4v'
}

# 格式設定定義
FORMAT_CONFIGS = {
    "Audio": {
        "formats": ["mp3", "wav", "ogg", "flac", "m4a"],
        "options_label": "音質 (Bitrate):",
        "options": ["128k", "192k", "256k", "320k"]
    },
    "Video": {
        "formats": ["mp4", "mkv", "avi", "mov"],
        "options_label": "畫質 (Quality):",
        "options": ["1080p", "720p", "480p", "Original"]
    }
}

class FFmpegGUI:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        # Title/Geometry are handled by UniversalApp, but we can access config
        
        # 檢查 FFmpeg
        if not self.check_ffmpeg():
            messagebox.showerror("錯誤", "找不到 FFmpeg！\n請確認 ffmpeg 已安裝並設定在系統環境變數(PATH)中。")
        
        self.file_list = []
        self.is_converting = False

        self.setup_ui()

    def check_ffmpeg(self):
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except:
            return False

    def setup_ui(self):
        # --- 1. 上方控制區 (檔案選取) ---
        control_frame = ttk.LabelFrame(self.root, text="步驟 1: 檔案選取", padding=10)
        control_frame.pack(fill="x", padx=10, pady=5)

        btn_add_files = ttk.Button(control_frame, text="加入檔案 (Files)", command=self.add_files)
        btn_add_files.pack(side="left", padx=5)

        btn_add_folder = ttk.Button(control_frame, text="加入資料夾 (Folder)", command=self.add_folder)
        btn_add_folder.pack(side="left", padx=5)

        btn_clear = ttk.Button(control_frame, text="清空列表", command=self.clear_list)
        btn_clear.pack(side="right", padx=5)

        # --- 2. 設定區 (格式與輸出) ---
        settings_frame = ttk.LabelFrame(self.root, text="步驟 2: 轉檔設定", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=5)

        # 2-1. 格式設定
        format_frame = ttk.Frame(settings_frame)
        format_frame.pack(fill="x", pady=(0, 10))

        # 格式類型 (Audio/Video) 切換
        ttk.Label(format_frame, text="輸出類型:").pack(side="left", padx=5)
        self.type_var = tk.StringVar(value="Audio")
        type_combo = ttk.Combobox(format_frame, textvariable=self.type_var, values=["Audio", "Video"], width=8, state="readonly")
        type_combo.pack(side="left", padx=5)
        type_combo.bind("<<ComboboxSelected>>", self.update_format_options)

        # 輸出格式
        ttk.Label(format_frame, text="格式:").pack(side="left", padx=(15, 5))
        self.format_var = tk.StringVar(value="mp3")
        self.format_combo = ttk.Combobox(format_frame, textvariable=self.format_var, width=8, state="readonly")
        self.format_combo.pack(side="left", padx=5)

        # 品質/Bitrate
        self.quality_label_var = tk.StringVar(value="音質 (Bitrate):")
        ttk.Label(format_frame, textvariable=self.quality_label_var).pack(side="left", padx=(15, 5))
        self.quality_var = tk.StringVar(value="192k")
        self.quality_combo = ttk.Combobox(format_frame, textvariable=self.quality_var, width=10)
        self.quality_combo.pack(side="left", padx=5)
        
        # 初始化選單
        self.update_format_options()

        # 2-2. 輸出路徑設定
        out_frame = ttk.LabelFrame(settings_frame, text="輸出位置", padding=5)
        out_frame.pack(fill="x")

        self.out_mode_var = tk.StringVar(value="auto") # auto or custom
        
        # 選項 A: 來源資料夾下的 converted
        rb_auto = ttk.Radiobutton(out_frame, text="儲存於來源資料夾下的 'converted' 目錄", variable=self.out_mode_var, value="auto", command=self.toggle_output_ui)
        rb_auto.pack(anchor="w", padx=5, pady=2)
        
        # 選項 B: 指定資料夾
        custom_box = ttk.Frame(out_frame)
        custom_box.pack(fill="x", padx=5, pady=2)
        
        rb_custom = ttk.Radiobutton(custom_box, text="指定資料夾:", variable=self.out_mode_var, value="custom", command=self.toggle_output_ui)
        rb_custom.pack(side="left")
        
        self.custom_path_var = tk.StringVar()
        # Restore last used path if available
        last_out = self.app.config.get("last_output_dir", "")
        if last_out: self.custom_path_var.set(last_out)

        self.entry_custom = ttk.Entry(custom_box, textvariable=self.custom_path_var)
        self.entry_custom.pack(side="left", fill="x", expand=True, padx=5)
        
        self.btn_browse_out = ttk.Button(custom_box, text="瀏覽...", command=self.browse_output_folder)
        self.btn_browse_out.pack(side="left")

        # New: Preserve Folder Structure Checkbox
        self.preserve_structure_var = tk.BooleanVar(value=self.app.config.get("preserve_structure", False))
        self.chk_preserve = ttk.Checkbutton(out_frame, text="保持資料夾結構 (Preserve Folder Structure)", variable=self.preserve_structure_var)
        self.chk_preserve.pack(anchor="w", padx=25, pady=(0,5))

        self.toggle_output_ui() # 初始化狀態

        # --- 3. 介面分割 (List + Log) By UniversalUI ---
        # Note: FFmpegGUI has List in middle, Progress/Action at bottom.
        # We put List in the "List pane" and Progress/Action in the "Log pane".
        _, self.list_frame, self.bottom_frame = self.app.create_paned_ui(self.root, list_weight=3, log_weight=0) # Log weight 0 to key it small
        
        # 3.1 列表 (放進上層)
        columns = ("status", "filename", "path")
        self.tree = ttk.Treeview(self.list_frame, columns=columns, show="headings", selectmode="extended")
        
        self.tree.heading("status", text="狀態")
        self.tree.heading("filename", text="檔案名稱")
        self.tree.heading("path", text="來源路徑")
        
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("filename", width=250, anchor="w")
        self.tree.column("path", width=400, anchor="w")

        scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 3.2 底部執行區 (放進下層)
        # Use a sub-frame inside bottom_frame to add padding
        action_area = ttk.Frame(self.bottom_frame, padding=5)
        action_area.pack(fill="x") # Pack at top of bottom frame

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(action_area, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=5)

        self.status_label = ttk.Label(action_area, text="準備就緒")
        self.status_label.pack(side="left")

        self.convert_btn = ttk.Button(action_area, text="開始轉檔 (Start)", command=self.start_conversion_thread)
        self.convert_btn.pack(side="right")
        
        # 3.3 紀錄區 (Log) - 使用 UniversalUI 的 console log
        self.log_txt = self.app.create_console_log(self.bottom_frame, height=5)
        # 增加一點 padding
        self.log_txt.master.pack_configure(padx=5, pady=(0,5))
        
    def log(self, msg):
        self.log_txt.insert(tk.END, f"> {msg}\n")
        self.log_txt.see(tk.END)

    def update_format_options(self, event=None):
        """根據選擇的類型(Audio/Video)更新格式和品質選單"""
        current_type = self.type_var.get()
        config = FORMAT_CONFIGS[current_type]
        
        # 更新格式清單
        self.format_combo['values'] = config['formats']
        self.format_combo.current(0) # 選取第一個
        
        # 更新品質標籤和選項
        self.quality_label_var.set(config['options_label'])
        self.quality_combo['values'] = config['options']
        
        # 設定預設值
        if current_type == "Audio":
            self.quality_combo.set("192k")
        else:
            self.quality_combo.set("1080p")

    def toggle_output_ui(self):
        """切換輸出路徑輸入框的啟用狀態"""
        if self.out_mode_var.get() == "custom":
            self.entry_custom.config(state="normal")
            self.btn_browse_out.config(state="normal")
            self.chk_preserve.config(state="normal")
        else:
            self.entry_custom.config(state="disabled")
            self.btn_browse_out.config(state="disabled")
            self.chk_preserve.config(state="disabled")

    def browse_output_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.custom_path_var.set(folder)

    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Media Files", "*.*")])
        for f in files:
            self.add_file_to_tree(f, source_root=None)

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            path = Path(folder)
            for p in path.rglob("*"):
                if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                    self.add_file_to_tree(str(p), source_root=folder)

    def add_file_to_tree(self, filepath, source_root=None):
        if filepath in [f['path'] for f in self.file_list]:
            return
        p = Path(filepath)
        item_id = self.tree.insert("", "end", values=("等待中", p.name, str(p)))
        self.file_list.append({"id": item_id, "path": filepath, "source_root": source_root})

    def clear_list(self):
        if self.is_converting: return
        self.tree.delete(*self.tree.get_children())
        self.file_list = []

    def start_conversion_thread(self):
        if not self.file_list:
            messagebox.showinfo("提示", "請先加入檔案")
            return
        
        if self.out_mode_var.get() == "custom" and not self.custom_path_var.get():
            messagebox.showwarning("提示", "請選擇輸出資料夾")
            return

        if self.is_converting: return
        self.is_converting = True
        self.convert_btn.config(state="disabled")
        threading.Thread(target=self.run_conversion, daemon=True).start()

    def run_conversion(self):
        total = len(self.file_list)
        conv_type = self.type_var.get()
        target_format = self.format_var.get()
        quality_setting = self.quality_var.get()
        output_mode = self.out_mode_var.get()
        custom_out_dir = self.custom_path_var.get()
        
        completed = 0
        
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        if self.out_mode_var.get() == "custom":
            # Save config for next time
            self.app.config.set("last_output_dir", custom_out_dir)
            self.app.config.set("preserve_structure", self.preserve_structure_var.get())
            self.app.config.save()
            
        self.root.after(0, self.log, f"開始轉檔作業... 總計 {total} 個檔案")

        for idx, item in enumerate(self.file_list):
            item_id = item['id']
            input_path = Path(item['path'])
            source_root = item.get('source_root')
            
            msg = f"正在處理 ({idx+1}/{total}): {input_path.name}"
            self.root.after(0, self.update_status, item_id, "轉檔中...", msg)
            self.root.after(0, self.log, msg)

            if output_mode == "custom":
                if self.preserve_structure_var.get() and source_root:
                    try:
                        rel_path = input_path.relative_to(source_root)
                        output_dir = Path(custom_out_dir) / rel_path.parent
                    except ValueError:
                         # Fallback if relative_to fails (shouldn't happen if logic is correct)
                         output_dir = Path(custom_out_dir)
                else:
                    output_dir = Path(custom_out_dir)
            else:
                output_dir = input_path.parent / "converted"
            
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                err_msg = f"建立目錄失敗: {e}"
                print(err_msg)
                self.root.after(0, self.log, f"Error: {err_msg}")
                self.root.after(0, self.update_status, item_id, "錯誤", None)
                continue

            output_filename = input_path.stem + "." + target_format
            output_path = output_dir / output_filename

            # 組合指令
            cmd = ["ffmpeg", "-y", "-i", str(input_path)]
            
            if conv_type == "Audio":
                # Audio Settings
                if target_format in ['mp3', 'ogg', 'm4a']:
                    cmd.extend(["-b:a", quality_setting])
                elif target_format == 'flac':
                     pass
            else:
                # Video Settings
                # Video Codec: H.264 is safest for mp4/mkv/avi
                cmd.extend(["-c:v", "libx264", "-c:a", "aac"])
                
                # Resolution Mapping
                if quality_setting == "1080p":
                    cmd.extend(["-vf", "scale=-2:1080"])
                elif quality_setting == "720p":
                    cmd.extend(["-vf", "scale=-2:720"])
                elif quality_setting == "480p":
                    cmd.extend(["-vf", "scale=-2:480"])
                # "Original" needs no filter
                
                # Preset for speed/compression balance
                cmd.extend(["-preset", "medium", "-crf", "23"])

            cmd.append(str(output_path))

            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
                self.root.after(0, self.update_status, item_id, "完成", None)
                self.root.after(0, self.log, f"完成: {output_filename}")
            except Exception as e:
                err_str = str(e)
                print(f"Error: {e}")
                self.root.after(0, self.log, f"轉檔失敗: {err_str}")
                self.root.after(0, self.update_status, item_id, "失敗", None)

            completed += 1
            self.root.after(0, lambda p=(completed/total)*100: self.progress_var.set(p))

        self.is_converting = False
        self.root.after(0, lambda: self.convert_btn.config(state="normal"))
        self.root.after(0, lambda: self.status_label.config(text="所有作業已完成！"))
        self.root.after(0, self.log, "================ 作業結束 ================")
        self.root.after(0, lambda: messagebox.showinfo("完成", "轉檔作業結束"))

    def update_status(self, item_id, status, label_text):
        try:
            current_values = self.tree.item(item_id, "values")
            if current_values:
                self.tree.item(item_id, values=(status, current_values[1], current_values[2]))
            if label_text:
                self.status_label.config(text=label_text)
        except:
            pass

if __name__ == "__main__":
    root = tk.Tk()
    # Replace manual setup with UniversalApp
    app_wrapper = UniversalUI.UniversalApp(
        root, 
        "Python FFmpeg 轉檔工具 v1.3 (Audio/Video)", 
        "ffmpeg_converter_sig", # Signature
        defaults={
            "geometry": "850x650",
            "ui_scale": 1.0
        }
    )
    
    app = FFmpegGUI(app_wrapper)
    root.mainloop()
