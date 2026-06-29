import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import winreg

# Add parent directory to sys.path so we can import the shared _lib
# Since this file is in MVlab/PLG, the root is 3 levels up
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from _lib.UniversalUI import UniversalApp, UniversalTreeview, UniversalToplevel
import plg

def set_association_in_registry(ext, associate=True):
    """
    將播放清單副檔名與右鍵選單「使用 PLG 編輯」進行關聯 (針對當前使用者)
    使用更強力、相容性更高的 ProgID 註冊方式
    """
    python_exe = sys.executable
    script_path = os.path.abspath(__file__)
    
    # 清理副檔名的點 (例如 .xspf -> xspf)
    ext_clean = ext.lstrip('.')
    
    # 1. 取得或建立該副檔名的 ProgID (例如 xspf_auto_file)
    prog_id = f"{ext_clean}_auto_file"
    
    # 註冊表路徑
    # 途徑 A: 直接註冊在副檔名類別 (ProgID) 的 shell 下
    prog_key_path = f"Software\\Classes\\{prog_id}\\shell\\EditWithPLG"
    # 途徑 B: 傳統的 SystemFileAssociations 作為備用
    sys_key_path = f"Software\\Classes\\SystemFileAssociations\\.{ext_clean}\\shell\\EditWithPLG"
    
    if associate:
        try:
            # 確保副檔名指向我們的 ProgID (若原本沒有關聯)
            ext_key_path = f"Software\\Classes\\.{ext_clean}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ext_key_path) as key:
                # 取得原本的 ProgID，如果沒有，才設定為我們自訂的 prog_id
                try:
                    existing_prog, _ = winreg.QueryValueEx(key, "")
                    if existing_prog:
                        prog_id = existing_prog
                        prog_key_path = f"Software\\Classes\\{prog_id}\\shell\\EditWithPLG"
                except FileNotFoundError:
                    winreg.SetValue(key, "", winreg.REG_SZ, prog_id)
            
            # 寫入 ProgID 的右鍵選單
            for key_path in [prog_key_path, sys_key_path]:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    winreg.SetValue(key, "", winreg.REG_SZ, "使用 PLG 編輯")
                    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, python_exe)
                    
                cmd_key_path = f"{key_path}\\command"
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key_path) as key:
                    command = f'"{python_exe}" "{script_path}" "/G" "%1"'
                    winreg.SetValue(key, "", winreg.REG_SZ, command)
        except Exception as e:
            print(f"寫入註冊表失敗 ({ext}): {e}")
    else:
        try:
            # 如果原本有 ProgID，也一併刪除
            ext_key_path = f"Software\\Classes\\.{ext_clean}"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ext_key_path) as key:
                    existing_prog, _ = winreg.QueryValueEx(key, "")
                    if existing_prog:
                        prog_id = existing_prog
            except:
                pass
                
            prog_key_path = f"Software\\Classes\\{prog_id}\\shell\\EditWithPLG"
            
            def delete_key_recursive(root, subkey):
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, 0)
                                delete_key_recursive(root, f"{subkey}\\{subkey_name}")
                            except OSError:
                                break
                    winreg.DeleteKey(root, subkey)
                except FileNotFoundError:
                    pass
                    
            delete_key_recursive(winreg.HKEY_CURRENT_USER, prog_key_path)
            delete_key_recursive(winreg.HKEY_CURRENT_USER, sys_key_path)
        except Exception as e:
            print(f"刪除註冊表失敗 ({ext}): {e}")

def check_association_in_registry(ext):
    """檢查該副檔名是否已關聯「使用 PLG 編輯」"""
    ext_clean = ext.lstrip('.')
    prog_id = f"{ext_clean}_auto_file"
    
    # 嘗試取得目前的 ProgID
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\.{ext_clean}") as key:
            existing_prog, _ = winreg.QueryValueEx(key, "")
            if existing_prog:
                prog_id = existing_prog
    except:
        pass
        
    prog_cmd_path = f"Software\\Classes\\{prog_id}\\shell\\EditWithPLG\\command"
    sys_cmd_path = f"Software\\Classes\\SystemFileAssociations\\.{ext_clean}\\shell\\EditWithPLG\\command"
    
    script_path = os.path.abspath(__file__)
    script_name = os.path.basename(script_path).lower()
    
    for path in [prog_cmd_path, sys_cmd_path]:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                val, _ = winreg.QueryValueEx(key, "")
                if script_name in val.lower():
                    return True
        except FileNotFoundError:
            continue
    return False

class PLGSettingsDialog(UniversalToplevel):
    def __init__(self, parent, config, on_save_callback):
        super().__init__(parent, "PLG 設定")
        self.state_id = "plg_settings"
        self.config = config
        self.on_save_callback = on_save_callback
        
        # 載入先前儲存的位置
        geo = self.config.get("window_plg_settings")
        if geo:
            try: self.geometry(geo)
            except: self.geometry("450x460")
        else:
            self.geometry("450x460")
            
        self.resizable(False, False)
        self.grab_set()
        
        # 綁定視窗關閉事件
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.vars = {}
        self.build_ui()
        
    def build_ui(self):
        lbl_title = ttk.Label(self, text="⚙️ PLG 設定與檔案關聯", font=("Microsoft JhengHei UI", 12, "bold"))
        lbl_title.pack(anchor="w", padx=20, pady=15)
        
        assoc_frame = ttk.LabelFrame(self, text="Windows 右鍵選單關聯 (使用 PLG 編輯)", padding=15)
        assoc_frame.pack(fill="x", padx=20, pady=5)
        
        self.vars["assoc_xspf"] = tk.BooleanVar(value=self.config.get("assoc_xspf", True))
        ttk.Checkbutton(assoc_frame, text="關聯 .xspf 檔案 (XML 播放清單格式)", variable=self.vars["assoc_xspf"]).pack(anchor="w", pady=3)
        
        self.vars["assoc_m3u"] = tk.BooleanVar(value=self.config.get("assoc_m3u", True))
        ttk.Checkbutton(assoc_frame, text="關聯 .m3u 檔案 (標準播放清單格式)", variable=self.vars["assoc_m3u"]).pack(anchor="w", pady=3)
        
        self.vars["assoc_m3u8"] = tk.BooleanVar(value=self.config.get("assoc_m3u8", True))
        ttk.Checkbutton(assoc_frame, text="關聯 .m3u8 檔案 (UTF-8 播放清單格式)", variable=self.vars["assoc_m3u8"]).pack(anchor="w", pady=3)
        
        self.vars["assoc_pls"] = tk.BooleanVar(value=self.config.get("assoc_pls", False))
        ttk.Checkbutton(assoc_frame, text="關聯 .pls 檔案", variable=self.vars["assoc_pls"]).pack(anchor="w", pady=3)
        
        self.vars["assoc_wpl"] = tk.BooleanVar(value=self.config.get("assoc_wpl", False))
        ttk.Checkbutton(assoc_frame, text="關聯 .wpl 檔案 (Windows Media Player 清單)", variable=self.vars["assoc_wpl"]).pack(anchor="w", pady=3)
        
        other_frame = ttk.LabelFrame(self, text="啟動與提醒設定", padding=15)
        other_frame.pack(fill="x", padx=20, pady=10)
        
        self.vars["ask_association"] = tk.BooleanVar(value=self.config.get("ask_association", True))
        ttk.Checkbutton(other_frame, text="啟動時如果發現未關聯，自動跳出提示詢問", variable=self.vars["ask_association"]).pack(anchor="w", pady=3)
        
        btn_row = ttk.Frame(self)
        btn_row.pack(side="bottom", fill="x", pady=15)
        
        ttk.Button(btn_row, text="儲存 (Save)", command=self.save, width=12).pack(side="right", padx=20)
        ttk.Button(btn_row, text="取消 (Cancel)", command=self.on_close, width=12).pack(side="right")
        
    def save(self):
        # 儲存視窗位置
        self.config.set("window_plg_settings", self.geometry())
        
        for k, var in self.vars.items():
            self.config.set(k, var.get())
        self.config.save()
        
        if self.on_save_callback:
            self.on_save_callback()
            
        self.destroy()

    def on_close(self):
        # 僅儲存視窗位置
        self.config.set("window_plg_settings", self.geometry())
        self.config.save()
        self.destroy()

class PLG_GUI(UniversalApp):
    def __init__(self, root, initial_args=None):
        defaults = {
            "geometry": "1000x750",
            "source": ".",
            "pattern": "*.*",
            "recursive": False,
            "relative": False,
            "sort_order": "N",
            "format": "xspf",
            "use_duration": False,
            "target_duration": "01:30:00",
            "tolerance_duration": "00:05:00",
            "use_count": False,
            "target_count": "20",
            "tolerance_count": "0",
            "assoc_xspf": True,
            "assoc_m3u": True,
            "assoc_m3u8": True,
            "assoc_pls": False,
            "assoc_wpl": False,
            "ask_association": True
        }
        
        super().__init__(root, "Play List Generator (PLG) v1.0", "plg_generator_v1", defaults)
        
        self.scanned_metadata = []
        self.initial_args = initial_args
        self.is_dirty = False
        
        from _lib.UniversalUI import UndoManager
        self.undo_mgr = UndoManager(self.restore_state)
        self.root.bind("<Control-z>", lambda e: self.undo_mgr.undo())
        self.root.bind("<Control-y>", lambda e: self.undo_mgr.redo())
        self.root.bind("<Control-Z>", lambda e: self.undo_mgr.redo())
        
        self.setup_ui()
        
        if self.initial_args:
            self.load_from_args(self.initial_args)
            
        if self.config.get("ask_association", True):
            self.root.after(1000, self.check_and_ask_associations)
            
        self.take_snapshot(set_dirty=False)
        
    def take_snapshot(self, set_dirty=True):
        self.undo_mgr.snapshot({"metadata": list(self.scanned_metadata)})
        if set_dirty:
            self.is_dirty = True

    def restore_state(self, state):
        self.scanned_metadata = list(state["metadata"])
        self.populate_treeview()
        self.is_dirty = True
            
    def setup_ui(self):
        p = 10
        
        # Header
        ttk.Label(self.root, text="PLG - 播放清單生成器", style="Header.TLabel").pack(anchor="w", padx=p, pady=(p, 5))
        
        # Upper Config Panel (2 columns: Left for Paths & Basic, Right for Limits)
        config_frame = ttk.LabelFrame(self.root, text="設定參數", padding=10)
        config_frame.pack(fill="x", padx=p, pady=5)
        
        # Use two sub-frames for two-column configuration
        left_cfg = ttk.Frame(config_frame)
        left_cfg.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        right_cfg = ttk.Frame(config_frame)
        right_cfg.pack(side="right", fill="both", expand=True)
        
        # --- Left Column: Paths & Switches ---
        # Source Path
        src_row = ttk.Frame(left_cfg)
        src_row.pack(fill="x", pady=2)
        ttk.Label(src_row, text="來源資料夾:", width=11, anchor="w").pack(side="left")
        self.source_var = tk.StringVar(value=self.config.get("source"))
        ttk.Entry(src_row, textvariable=self.source_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(src_row, text="瀏覽...", command=self.browse_source, width=8).pack(side="right")
        
        # Target Path
        tgt_row = ttk.Frame(left_cfg)
        tgt_row.pack(fill="x", pady=2)
        ttk.Label(tgt_row, text="儲存清單檔:", width=11, anchor="w").pack(side="left")
        self.target_var = tk.StringVar(value=self.config.get("target", "playlist.xspf"))
        ttk.Entry(tgt_row, textvariable=self.target_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(tgt_row, text="瀏覽...", command=self.browse_target, width=8).pack(side="right")
        
        # File pattern & Format Selection
        fmt_row = ttk.Frame(left_cfg)
        fmt_row.pack(fill="x", pady=2)
        ttk.Label(fmt_row, text="副檔名過濾:", width=11, anchor="w").pack(side="left")
        self.pattern_var = tk.StringVar(value=self.config.get("pattern"))
        ttk.Entry(fmt_row, textvariable=self.pattern_var, width=12).pack(side="left", padx=5)
        
        ttk.Label(fmt_row, text="清單格式:", width=10, anchor="w").pack(side="left", padx=(10, 0))
        self.format_var = tk.StringVar(value=self.config.get("format"))
        formats = ["xspf", "m3u8", "m3u", "pls", "wpl"]
        ttk.Combobox(fmt_row, textvariable=self.format_var, values=formats, state="readonly", width=8).pack(side="left", padx=5)
        
        # Switches: Recursive & Relative Paths
        sw_row = ttk.Frame(left_cfg)
        sw_row.pack(fill="x", pady=5)
        self.recursive_var = tk.BooleanVar(value=self.config.get("recursive"))
        ttk.Checkbutton(sw_row, text="包含子資料夾 (/S)", variable=self.recursive_var).pack(side="left", padx=5)
        
        self.relative_var = tk.BooleanVar(value=self.config.get("relative"))
        ttk.Checkbutton(sw_row, text="使用相對路徑 (/B)", variable=self.relative_var).pack(side="left", padx=15)
        
        # --- Right Column: Sorting & Slicing Limits ---
        # Sorting
        sort_row = ttk.Frame(right_cfg)
        sort_row.pack(fill="x", pady=2)
        ttk.Label(sort_row, text="排列順序 (/O):", width=14, anchor="w").pack(side="left")
        self.sort_var = tk.StringVar(value=self.config.get("sort_order"))
        sort_opts = [
            ("檔名 (Name)", "N"),
            ("檔案大小 (Size)", "S"),
            ("修改日期 (Date)", "D"),
            ("副檔名 (Ext)", "E"),
            ("群組資料夾 (Group)", "G"),
            ("演出者 (Artist)", "A"),
            ("標題 (Title)", "TT"),
            ("音軌名稱 (Track Name)", "TK"),
            ("音軌編號 (Track Number)", "TN")
        ]
        self.sort_combo = ttk.Combobox(sort_row, state="readonly", width=18)
        self.sort_combo['values'] = [opt[0] for opt in sort_opts]
        # set initial
        initial_val = self.config.get("sort_order", "N")
        for i, opt in enumerate(sort_opts):
            if opt[1] == initial_val:
                self.sort_combo.current(i)
                break
        self.sort_combo.pack(side="left", padx=5)
        
        self.sort_reverse_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sort_row, text="反向排序", variable=self.sort_reverse_var).pack(side="left", padx=10)
        
        # Duration limits (/L)
        dur_row = ttk.Frame(right_cfg)
        dur_row.pack(fill="x", pady=2)
        self.use_dur_var = tk.BooleanVar(value=self.config.get("use_duration"))
        ttk.Checkbutton(dur_row, text="限制清單長度 (/L):", variable=self.use_dur_var, command=self.toggle_limit_states).pack(side="left")
        
        self.dur_target_var = tk.StringVar(value=self.config.get("target_duration"))
        self.entry_dur_target = ttk.Entry(dur_row, textvariable=self.dur_target_var, width=10)
        self.entry_dur_target.pack(side="left", padx=5)
        
        ttk.Label(dur_row, text="± 誤差:").pack(side="left")
        self.dur_tol_var = tk.StringVar(value=self.config.get("tolerance_duration"))
        self.entry_dur_tol = ttk.Entry(dur_row, textvariable=self.dur_tol_var, width=10)
        self.entry_dur_tol.pack(side="left", padx=5)
        
        # Count limits (/N)
        cnt_row = ttk.Frame(right_cfg)
        cnt_row.pack(fill="x", pady=2)
        self.use_cnt_var = tk.BooleanVar(value=self.config.get("use_count"))
        ttk.Checkbutton(cnt_row, text="限制歌曲數量 (/N):", variable=self.use_cnt_var, command=self.toggle_limit_states).pack(side="left")
        
        self.cnt_target_var = tk.StringVar(value=self.config.get("target_count"))
        self.entry_cnt_target = ttk.Entry(cnt_row, textvariable=self.cnt_target_var, width=8)
        self.entry_cnt_target.pack(side="left", padx=5)
        
        ttk.Label(cnt_row, text="± 誤差:").pack(side="left")
        self.cnt_tol_var = tk.StringVar(value=self.config.get("tolerance_count"))
        self.entry_cnt_tol = ttk.Entry(cnt_row, textvariable=self.cnt_tol_var, width=6)
        self.entry_cnt_tol.pack(side="left", padx=5)
        
        self.toggle_limit_states()
        
        # --- List and Log Area (Paned UI) ---
        _, self.list_frame, self.bottom_frame = self.create_paned_ui(self.root, list_weight=4, log_weight=1)
        
        # Toolbar inside list_frame
        tb = ttk.Frame(self.list_frame)
        tb.pack(fill="x", pady=(0, 5))

        # 左側：掃描 / 新增 / 刪除
        ttk.Button(tb, text="🔍 掃描資料夾 (Scan)", command=self.scan_files).pack(side="left", padx=5)
        ttk.Button(tb, text="➕ 新增檔案 (Add)",    command=self.add_files).pack(side="left", padx=2)
        ttk.Button(tb, text="🗑 刪除選取 (Del)",   command=self.delete_selected).pack(side="left", padx=2)

        # 右側：生成與設定
        ttk.Button(tb, text="⚙️ 系統設定", command=self.open_settings).pack(side="right", padx=2)
        ttk.Button(tb, text="💾 開始生成清單 (Save)", command=self.generate_playlists).pack(side="right", padx=5)

        self.status_lbl = ttk.Label(tb, text="清單共計 0 首歌曲", foreground="#007acc")
        self.status_lbl.pack(side="left", padx=20)

        # Scanned files list
        cols = ["Track", "Artist", "Duration", "Size", "Path"]
        self.tree = UniversalTreeview(self.list_frame, columns=cols, draggable=True)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.column("Track",    width=200)
        self.tree.column("Artist",   width=150)
        self.tree.column("Duration", width=100, anchor="center")
        self.tree.column("Size",     width=100, anchor="center")
        self.tree.column("Path",     width=350)

        sb = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        # 鍵盤 Delete 鍵也可刪除選取項目
        self.tree.bind("<Delete>", lambda e: self.delete_selected())

        # Hook drag and drop reordering callback
        if hasattr(self.tree, 'drag_helper'):
            self.tree.drag_helper.on_drop_callback = self.on_manual_reorder

        # Output Console log
        self.log_txt = self.create_console_log(self.bottom_frame, height=4)
        
    def log(self, msg):
        self.log_txt.insert(tk.END, f"> {msg}\n")
        self.log_txt.see(tk.END)
        
    def browse_source(self):
        d = filedialog.askdirectory(initialdir=self.source_var.get())
        if d: self.source_var.set(d)

    # ------------------------------------------------------------------
    # 新增個別檔案（跨資料夾多選）
    # ------------------------------------------------------------------
    def add_files(self):
        """開啟多選對話框，將選取的媒體檔案逐一加入清單（自動去重）。"""
        _AUDIO = "*.mp3 *.flac *.m4a *.wav *.ogg *.wma *.aac *.opus *.ape *.aiff"
        _VIDEO = "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.ts *.m2ts *.mts *.vob *.rmvb *.rm"
        chosen = filedialog.askopenfilenames(
            title="選取媒體檔案（可跨資料夾多選）",
            filetypes=[
                ("所有支援格式", f"{_AUDIO} {_VIDEO}"),
                ("音訊檔案",     _AUDIO),
                ("影片檔案",     _VIDEO),
                ("所有檔案",     "*.*"),
            ]
        )
        if not chosen:
            return

        # 去除已在清單中的重複項目
        existing = {m['path'] for m in self.scanned_metadata}
        new_files = [f for f in chosen if f not in existing]
        dup_count  = len(chosen) - len(new_files)

        if not new_files:
            self.log("所選檔案已全部存在於清單中，未新增重複項目。")
            return

        self.log(f"正在讀取 {len(new_files)} 個新增檔案的中繼資料…")
        if dup_count:
            self.log(f"（已略過 {dup_count} 個重複項目）")

        def bg_add():
            new_meta = [plg.get_audio_metadata(f) for f in new_files]
            self.scanned_metadata.extend(new_meta)
            self.root.after(0, self._append_to_treeview, new_meta)
            self.root.after(0, self.take_snapshot)

        threading.Thread(target=bg_add, daemon=True).start()

    def _append_to_treeview(self, new_meta):
        """將新 metadata 列表追加到 Treeview 末尾並更新狀態列。"""
        for m in new_meta:
            size_mb = f"{m['size'] / (1024 * 1024):.2f} MB"
            dur_str = plg.format_time(m['duration']) if m['duration'] > 0 else "---"
            self.tree.insert("", "end", iid=m['path'], values=(
                m['track_name'],
                m['artist'] or "---",
                dur_str,
                size_mb,
                m['path']
            ))
        self.tree.refresh_stripes()
        self._update_status()
        self.log(f"已新增 {len(new_meta)} 個檔案。")

    # ------------------------------------------------------------------
    # 刪除選取項目
    # ------------------------------------------------------------------
    def delete_selected(self):
        """將 Treeview 中選取的列從清單與 metadata 中同步移除。"""
        selected = self.tree.selection()
        if not selected:
            return

        selected_set = set(selected)   # iid 即為檔案絕對路徑
        self.scanned_metadata = [
            m for m in self.scanned_metadata if m['path'] not in selected_set
        ]
        for iid in selected:
            self.tree.delete(iid)

        self.tree.refresh_stripes()
        self._update_status()
        self.log(f"已從清單移除 {len(selected)} 個項目。")
        self.take_snapshot()

    # ------------------------------------------------------------------
    # 共用：更新底部狀態列
    # ------------------------------------------------------------------
    def _update_status(self):
        total_sec = sum(m['duration'] for m in self.scanned_metadata)
        time_str  = plg.format_time(total_sec)
        count     = len(self.scanned_metadata)
        self.status_lbl.config(text=f"清單共計 {count} 首歌曲 ({time_str})")
        
    def browse_target(self):
        fmt = self.format_var.get()
        f = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(f"{fmt.upper()} Playlist", f"*.{fmt}"), ("All Files", "*.*")]
        )
        if f: self.target_var.set(f)
        
    def toggle_limit_states(self):
        # Enable/Disable limit inputs based on checkboxes
        state_dur = "normal" if self.use_dur_var.get() else "disabled"
        self.entry_dur_target.config(state=state_dur)
        self.entry_dur_tol.config(state=state_dur)
        
        state_cnt = "normal" if self.use_cnt_var.get() else "disabled"
        self.entry_cnt_target.config(state=state_cnt)
        self.entry_cnt_tol.config(state=state_cnt)
        
    def get_selected_sort_order(self):
        # Map back combobox choice to sort code
        sort_opts = [
            ("檔名 (Name)", "N"),
            ("檔案大小 (Size)", "S"),
            ("修改日期 (Date)", "D"),
            ("副檔名 (Ext)", "E"),
            ("群組資料夾 (Group)", "G"),
            ("演出者 (Artist)", "A"),
            ("標題 (Title)", "TT"),
            ("音軌名稱 (Track Name)", "TK"),
            ("音軌編號 (Track Number)", "TN")
        ]
        sel = self.sort_combo.get()
        code = "N"
        for opt in sort_opts:
            if opt[0] == sel:
                code = opt[1]
                break
        if self.sort_reverse_var.get():
            code = "-" + code
        return code
        
    def load_from_args(self, args):
        params = plg.parse_arguments(args)
        
        self.source_var.set(params['source'])
        self.pattern_var.set(params['file_pattern'])
        self.target_var.set(params['target'] or "playlist.xspf")
        self.format_var.set(params['format'])
        self.recursive_var.set(params['recursive'])
        self.relative_var.set(params['relative'])
        
        # Sort combo mapping
        sort_val = params['sort_order']
        if sort_val.startswith('-'):
            self.sort_reverse_var.set(True)
            sort_val = sort_val[1:]
        else:
            self.sort_reverse_var.set(False)
            
        sort_opts = [
            ("檔名 (Name)", "N"),
            ("檔案大小 (Size)", "S"),
            ("修改日期 (Date)", "D"),
            ("副檔名 (Ext)", "E"),
            ("群組資料夾 (Group)", "G"),
            ("演出者 (Artist)", "A"),
            ("標題 (Title)", "TT"),
            ("音軌名稱 (Track Name)", "TK"),
            ("音軌編號 (Track Number)", "TN")
        ]
        for i, opt in enumerate(sort_opts):
            if opt[1] == sort_val:
                self.sort_combo.current(i)
                break
                
        # Slicing limits
        if params['duration_limit']:
            self.use_dur_var.set(True)
            self.dur_target_var.set(plg.format_time(params['duration_limit'][0]))
            self.dur_tol_var.set(plg.format_time(params['duration_limit'][1]))
        else:
            self.use_dur_var.set(False)
            
        if params['count_limit']:
            self.use_cnt_var.set(True)
            self.cnt_target_var.set(str(params['count_limit'][0]))
            self.cnt_tol_var.set(str(params['count_limit'][1]))
        else:
            self.use_cnt_var.set(False)
            
        self.toggle_limit_states()
        self.log(f"已從啟動參數載入設定。")
        self.log(f"偵測到命令列參數: {args}")
        
        target = params['target']
        if target:
            target = os.path.abspath(target.strip('"\''))
            
        self.log(f"定位檔案路徑: '{target}' (檔案存在狀態: {os.path.exists(target) if target else False})")
        
        if target and os.path.exists(target) and os.path.isfile(target):
            ext = os.path.splitext(target)[1].lower()
            if ext in ['.xspf', '.m3u', '.m3u8', '.pls', '.wpl']:
                self.load_playlist_file(target)
                return
                
        # Automatically trigger scanning
        self.scan_files()
        
    def load_playlist_file(self, filepath):
        self.tree.delete(*self.tree.get_children())
        self.log(f"正在載入播放清單: {filepath}...")
        
        def bg_load():
            try:
                meta = plg.load_playlist(filepath)
                self.scanned_metadata = meta
                self.root.after(0, self.populate_treeview)
                self.root.after(0, lambda: self.log(f"播放清單載入完成，共計 {len(meta)} 首歌曲。"))
                self.root.after(0, lambda: self.take_snapshot(set_dirty=False))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"載入播放清單失敗: {e}"))
                self.root.after(0, lambda: messagebox.showerror("載入錯誤", f"載入播放清單失敗: {e}"))
                
        threading.Thread(target=bg_load, daemon=True).start()

    def open_settings(self):
        PLGSettingsDialog(self.root, self.config, self.reload_settings)

    def reload_settings(self):
        # 根據設定更新檔案關聯
        for ext in ['.xspf', '.m3u', '.m3u8', '.pls', '.wpl']:
            config_key = f"assoc_{ext.lstrip('.')}"
            should_associate = self.config.get(config_key, False)
            set_association_in_registry(ext, should_associate)
        self.show_toast("設定已儲存並更新檔案關聯！", level="success")

    def check_and_ask_associations(self):
        missing = []
        formats = ['.xspf', '.m3u', '.m3u8']
        for ext in formats:
            config_key = f"assoc_{ext.lstrip('.')}"
            if self.config.get(config_key, True) and not check_association_in_registry(ext):
                missing.append(ext)
                
        if missing:
            ask_win = UniversalToplevel(self.root, "檔案關聯提示")
            ask_win.geometry("380x200")
            ask_win.resizable(False, False)
            ask_win.grab_set()
            
            ask_win.update_idletasks()
            rx = self.root.winfo_x() + (self.root.winfo_width() - ask_win.winfo_width()) // 2
            ry = self.root.winfo_y() + (self.root.winfo_height() - ask_win.winfo_height()) // 2
            ask_win.geometry(f"+{rx}+{ry}")
            
            lbl_msg = ttk.Label(ask_win, text="發現您的播放清單格式尚未關聯到右鍵選單。\n是否要在檔案總管右鍵選單加入「使用 PLG 編輯」？", justify="left")
            lbl_msg.pack(padx=20, pady=20, anchor="w")
            
            chk_var = tk.BooleanVar(value=False)
            chk_dont_ask = ttk.Checkbutton(ask_win, text="不要再問我 (可在設定中變更)", variable=chk_var)
            chk_dont_ask.pack(padx=20, pady=5, anchor="w")
            
            def on_yes():
                for ext in missing:
                    set_association_in_registry(ext, True)
                self.show_toast("右鍵選單關聯建立完成！", level="success")
                if chk_var.get():
                    self.config.set("ask_association", False)
                    self.config.save()
                ask_win.destroy()
                
            def on_no():
                if chk_var.get():
                    self.config.set("ask_association", False)
                    self.config.save()
                ask_win.destroy()
                
            btn_row = ttk.Frame(ask_win)
            btn_row.pack(side="bottom", fill="x", pady=15)
            
            ttk.Button(btn_row, text="是 (Yes)", command=on_yes, width=10).pack(side="right", padx=20)
            ttk.Button(btn_row, text="否 (No)", command=on_no, width=10).pack(side="right")
        
    def scan_files(self):
        self.tree.delete(*self.tree.get_children())
        self.log("正在掃描媒體檔案...")
        
        src = self.source_var.get()
        pat = self.pattern_var.get()
        rec = self.recursive_var.get()
        sort_expr = self.get_selected_sort_order()
        
        # Run scanning in a background thread to prevent UI lock
        def bg_scan():
            files = plg.scan_directory(src, pat, rec)
            if not files:
                self.root.after(0, lambda: self.log("找不到任何相符的媒體檔案。"))
                self.root.after(0, lambda: self.status_lbl.config(text="清單共計 0 首歌曲"))
                return
                
            self.root.after(0, lambda: self.log(f"尋找到 {len(files)} 個檔案，讀取中繼資料..."))
            
            meta = []
            for f in files:
                meta.append(plg.get_audio_metadata(f))
                
            # Sort files
            meta = plg.sort_files(meta, sort_expr)
            self.scanned_metadata = meta
            
            # Load into treeview on main thread
            self.root.after(0, self.populate_treeview)
            self.root.after(0, self.take_snapshot)
            
        threading.Thread(target=bg_scan, daemon=True).start()
        
    def populate_treeview(self):
        self.tree.delete(*self.tree.get_children())
        total_sec = 0.0
        
        for m in self.scanned_metadata:
            size_mb = f"{m['size'] / (1024 * 1024):.2f} MB"
            dur_str = plg.format_time(m['duration']) if m['duration'] > 0 else "---"
            total_sec += m['duration']
            
            # Using absolute path as item IID
            self.tree.insert("", "end", iid=m['path'], values=(
                m['track_name'],
                m['artist'] or "---",
                dur_str,
                size_mb,
                m['path']
            ))
            
        self.tree.refresh_stripes()
        self.log(f"載入 {len(self.scanned_metadata)} 首歌曲成功。")
        
        # Update total time
        time_str = plg.format_time(total_sec)
        self.status_lbl.config(text=f"清單共計 {len(self.scanned_metadata)} 首歌曲 ({time_str})")
        
    def on_manual_reorder(self, source_ids, target_id):
        # source_ids: list of paths, target_id: single path
        if not source_ids or target_id in source_ids: return
        try:
            # Sort source_ids by their current visual order to maintain relative sequence
            source_ids = sorted(source_ids, key=lambda sid: self.tree.index(sid))
            
            for sid in source_ids:
                idx = self.tree.index(target_id)
                sid_idx = self.tree.index(sid)
                if sid_idx < idx:
                    self.tree.move(sid, '', idx - 1)
                else:
                    self.tree.move(sid, '', idx)
                    
            self.tree.refresh_stripes()
            
            # Update self.scanned_metadata array to match new order!
            new_order_paths = self.tree.get_children()
            reordered_meta = []
            for path in new_order_paths:
                m = next((item for item in self.scanned_metadata if item['path'] == path), None)
                if m: reordered_meta.append(m)
            self.scanned_metadata = reordered_meta
            self.log(f"手動調整 {len(source_ids)} 個項目的排列順序。")
            self.take_snapshot()
        except Exception as e:
            print(f"Reorder error: {e}")
            
    def generate_playlists(self):
        if not self.scanned_metadata:
            messagebox.showwarning("警告", "請先掃描或加入媒體檔案。")
            return False
            
        # Compile params
        params = {
            'source': self.source_var.get(),
            'file_pattern': self.pattern_var.get(),
            'recursive': self.recursive_var.get(),
            'sort_order': self.get_selected_sort_order(),
            'target': self.target_var.get(),
            'format': self.format_var.get(),
            'relative': self.relative_var.get(),
            'duration_limit': None,
            'count_limit': None
        }
        
        if self.use_dur_var.get():
            try:
                t = plg.parse_time(self.dur_target_var.get())
                tol = plg.parse_time(self.dur_tol_var.get())
                params['duration_limit'] = (t, tol)
            except Exception as e:
                messagebox.showerror("格式錯誤", f"長度限制格式錯誤 (hh:mm:ss): {e}")
                return False
                
        if self.use_cnt_var.get():
            try:
                t = int(self.cnt_target_var.get())
                tol = int(self.cnt_tol_var.get())
                params['count_limit'] = (t, tol)
            except Exception as e:
                messagebox.showerror("格式錯誤", f"數量限制格式錯誤: {e}")
                return False
                
        # Run Slicing
        try:
            plg.slice_and_generate(self.scanned_metadata, params)
            
            # Save config for persistence
            self.config.set("source", params['source'])
            self.config.set("target", params['target'])
            self.config.set("pattern", params['file_pattern'])
            self.config.set("format", params['format'])
            self.config.set("recursive", params['recursive'])
            self.config.set("relative", params['relative'])
            self.config.set("sort_order", params['sort_order'])
            self.config.set("use_duration", self.use_dur_var.get())
            self.config.set("target_duration", self.dur_target_var.get())
            self.config.set("tolerance_duration", self.dur_tol_var.get())
            self.config.set("use_count", self.use_cnt_var.get())
            self.config.set("target_count", self.cnt_target_var.get())
            self.config.set("tolerance_count", self.cnt_tol_var.get())
            self.config.save()
            
            self.show_toast("播放清單生成完畢！", level="success")
            self.log("所有清單已順利寫入儲存。")
            self.is_dirty = False
            return True
        except Exception as e:
            messagebox.showerror("執行錯誤", f"清單生成失敗: {e}")
            return False
            
    def on_close(self):
        if getattr(self, 'is_dirty', False):
            resp = messagebox.askyesnocancel("未儲存的變更", "播放清單已有變更，是否要在關閉前產生清單？")
            if resp is None:
                return
            if resp is True:
                if not self.generate_playlists():
                    return
        super().on_close()

def main(args=None):
    root = tk.Tk()
    # If launched with /G, strip it out before parsing loaded options
    stripped_args = []
    if args:
        for a in args:
            if not a.upper().startswith('/G'):
                stripped_args.append(a)
                
    app = PLG_GUI(root, initial_args=stripped_args if stripped_args else None)
    root.mainloop()

if __name__ == "__main__":
    main(sys.argv[1:])
