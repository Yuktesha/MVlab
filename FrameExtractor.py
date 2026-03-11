import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import time
from pathlib import Path
import shutil
import _lib.UniversalUI as UniversalUI
import sys
import re

# Try importing TkinterDnD
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
    RootClass = TkinterDnD.Tk
except ImportError as e:
    HAS_DND = False
    RootClass = tk.Tk
    print(f"Warning: tkinterdnd2 not found. Drag & Drop disabled.")
    print(f"Error: {e}")
    print(f"Current Python: {sys.executable}")
except Exception as e:
    HAS_DND = False
    RootClass = tk.Tk
    print(f"Warning: Unexpected error importing tkinterdnd2.")
    print(f"Error: {e}")
    print(f"Current Python: {sys.executable}")

# ==============================================================================
# CONFIG & CONSTANTS
# ==============================================================================
SUPPORTED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.wmv'}
CHECK_INTERVAL_MS = 2000  # Check watch folder every 2 seconds

class FrameExtractorApp:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        
        # State Variables
        self.is_monitoring = False
        self.processed_files = set()
        self.monitor_thread = None
        self.stop_event = threading.Event()
        
        # Config Defaults
        default_downloads = str(Path.home() / "Downloads")
        self.watch_dir_var = tk.StringVar(value=self.app.config.get("watch_dir", default_downloads))
        self.auto_rename_var = tk.BooleanVar(value=self.app.config.get("auto_rename", False))
        self.rename_prefix_var = tk.StringVar(value=self.app.config.get("rename_prefix", "Grok"))
        self.rename_counter = self.app.config.get("rename_counter", 1)
        
        self.auto_copy_var = tk.BooleanVar(value=self.app.config.get("auto_copy", False))
        
        self.setup_ui()
        
        # Drag & Drop Hook
        if HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.on_drop)
        
        # Validation
        if not self.check_ffmpeg():
             messagebox.showwarning("FFmpeg Missing", "Could not find 'ffmpeg' command.\nPlease ensure FFmpeg is installed and in your PATH.")

        # Hook Close Event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_custom)

    def check_ffmpeg(self):
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=self.get_startup_info())
            return True
        except:
            return False

    def get_startup_info(self):
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return si
        return None

    def setup_ui(self):
        # --- 1. Monitoring Control ---
        monitor_frame = ttk.LabelFrame(self.root, text="Watch Folder Settings", padding=10)
        monitor_frame.pack(fill="x", padx=10, pady=5)
        
        # Directory Selection
        dir_box = ttk.Frame(monitor_frame)
        dir_box.pack(fill="x", pady=5)
        
        ttk.Label(dir_box, text="Monitor Folder:").pack(side="left")
        self.entry_dir = ttk.Entry(dir_box, textvariable=self.watch_dir_var)
        self.entry_dir.pack(side="left", fill="x", expand=True, padx=5)
        
        btn_browse = ttk.Button(dir_box, text="Browse...", command=self.browse_dir)
        btn_browse.pack(side="left")
        
        # Options
        opts_box = ttk.Frame(monitor_frame)
        opts_box.pack(fill="x", pady=5)
        
        # Monitor Toggle
        self.btn_toggle = ttk.Button(opts_box, text="START Monitoring", command=self.toggle_monitoring)
        self.btn_toggle.pack(side="left", padx=(0, 20))
        
        # Auto Rename
        ttk.Checkbutton(opts_box, text="Auto-Rename Files", variable=self.auto_rename_var).pack(side="left", padx=5)
        ttk.Label(opts_box, text="Prefix:").pack(side="left")
        ttk.Entry(opts_box, textvariable=self.rename_prefix_var, width=10).pack(side="left", padx=(2, 5))
        
        # Reset Counter Button
        btn_reset = ttk.Button(opts_box, text="↺", width=2, command=self.reset_counter)
        btn_reset.pack(side="left", padx=(0, 15))
        
        # Auto Copy
        ttk.Checkbutton(opts_box, text="Auto-Copy Image", variable=self.auto_copy_var).pack(side="left")
        
        # --- 2. Action Log ---
        log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # DND Hint
        hint_text = "Activity Log (Drag & Drop Videos Here!)" if HAS_DND else "Activity Log"
        log_frame.configure(text=hint_text)
        
        columns = ("time", "event", "file")
        self.tree = ttk.Treeview(log_frame, columns=columns, show="headings", height=10)
        self.tree.heading("time", text="Time")
        self.tree.heading("event", text="Event")
        self.tree.heading("file", text="File / Status")
        
        self.tree.column("time", width=80)
        self.tree.column("event", width=100)
        self.tree.column("file", width=400)
        
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # --- 3. Manual Actions ---
        manual_frame = ttk.Frame(self.root, padding=10)
        manual_frame.pack(fill="x", side="bottom")
        
        ttk.Label(manual_frame, text="Manual Mode:").pack(side="left")
        ttk.Button(manual_frame, text="Select File to Extract", command=self.manual_select).pack(side="left", padx=10)
        
        self.lbl_status = ttk.Label(manual_frame, text="Ready", foreground="#8ab4f8")
        self.lbl_status.pack(side="right")

    def log(self, event, filename):
        t_str = time.strftime("%H:%M:%S")
        self.tree.insert("", 0, values=(t_str, event, filename))
        if len(self.tree.get_children()) > 100:
            self.tree.delete(self.tree.get_children()[-1])

    def browse_dir(self):
        d = filedialog.askdirectory()
        if d: self.watch_dir_var.set(d)
        
    def reset_counter(self):
        if messagebox.askyesno("Reset Counter", f"Reset numbering counter to 1 (Next: {self.rename_prefix_var.get()}_001)?"):
            self.rename_counter = 1
            self.app.config.set("rename_counter", 1)
            self.app.config.save()
            self.log("Info", "Counter reset to 001")

    def on_close_custom(self):
        # Save App Settings before closing
        self.save_settings()
        # Call UniversalApp cleanup (saves geometry)
        self.app.on_close()

    def save_settings(self):
        try:
            self.app.config.set("watch_dir", self.watch_dir_var.get())
            self.app.config.set("auto_rename", self.auto_rename_var.get())
            self.app.config.set("rename_prefix", self.rename_prefix_var.get())
            self.app.config.set("auto_copy", self.auto_copy_var.get())
            self.app.config.save()
            print("Settings saved.")
        except Exception as e:
            print(f"Error saving settings: {e}")

    def toggle_monitoring(self):
        if self.is_monitoring:
            # Stop
            self.is_monitoring = False
            self.stop_event.set()
            self.btn_toggle.configure(text="START Monitoring", style="TButton")
            self.lbl_status.configure(text="Monitoring Stopped")
            self.entry_dir.configure(state="normal")
            
            # Save settings on Stop as well
            self.save_settings()
        else:
            # Start
            path = self.watch_dir_var.get()
            if not os.path.exists(path):
                messagebox.showerror("Error", "Watch directory does not exist!")
                return
            
            self.save_settings()
            
            # Reset processed_files to snapshot of now, to ignore old files
            # But ensure we are case-insensitive if needed? For now simple set str.
            self.processed_files = set(os.listdir(path))
            
            self.is_monitoring = True
            self.stop_event.clear()
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
            
            self.btn_toggle.configure(text="STOP Monitoring", style="TButton")
            self.lbl_status.configure(text=f"Monitoring: {path}")
            self.entry_dir.configure(state="disabled")

    def monitor_loop(self):
        watch_path = Path(self.watch_dir_var.get())
        
        while not self.stop_event.is_set():
            try:
                # 1. Snapshot Disk State
                current_on_disk = set(os.listdir(watch_path))
                
                # 2. Calculate New Files
                new_files = current_on_disk - self.processed_files
                
                # 3. Process
                # We work on a copy of current_on_disk that we will update if we rename things
                updated_state = current_on_disk.copy()
                
                for f in new_files:
                    if self.stop_event.is_set(): break
                    
                    full_path = watch_path / f
                    
                    # Ignore active downloads or temps
                    if f.endswith('.tmp') or f.endswith('.crdownload'):
                        continue
                        
                    # Check extension
                    if full_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                        if self.wait_for_file_ready(full_path):
                            # Process and get final name (which might be renamed)
                            processed_name = self.process_file(full_path, allow_rename=True)
                                                            
                            # Add to tracking
                            updated_state.add(f)
                            if processed_name:
                                updated_state.add(processed_name)

                # 4. Update state for next loop
                self.processed_files = updated_state
                
            except Exception as e:
                print(f"Monitor Error: {e}")
                
            time.sleep(CHECK_INTERVAL_MS / 1000)

    def wait_for_file_ready(self, filepath, timeout=30):
        last_size = -1
        stable_count = 0
        
        for _ in range(timeout):
            if self.stop_event.is_set(): return False
            try:
                if not filepath.exists(): return False 
                
                size = filepath.stat().st_size
                if size == last_size and size > 0:
                    stable_count += 1
                else:
                    stable_count = 0
                
                last_size = size
                
                if stable_count >= 2: # ~1 sec stability
                    return True
                    
                time.sleep(0.5)
            except:
                return False
        return False

    def process_file(self, vid_path, allow_rename=True):
        """
        Returns the filename of the processed file (new name if renamed, or original).
        """
        final_path = vid_path
        
        # 1. Rename Logic
        if self.auto_rename_var.get() and allow_rename:
            try:
                prefix = self.rename_prefix_var.get()
                current_name = vid_path.name
                
                # SAFETY CHECK: Does it ALREADY match Prefix_XXX?
                # Case-insensitive check
                safe_prefix = re.escape(prefix)
                pattern = f"^{safe_prefix}_\\d{{3}}.*"
                if re.match(pattern, current_name, re.IGNORECASE):
                     self.root.after(0, self.log, "Skip Rename", f"Already numbered: {current_name}")
                else:
                    # Find next number
                    while True:
                        new_name = f"{prefix}_{self.rename_counter:03d}{vid_path.suffix}"
                        if new_name.lower() == current_name.lower(): 
                            final_path = vid_path
                            break
                            
                        new_path = vid_path.parent / new_name
                        if not new_path.exists():
                            # Perform Rename
                            vid_path.rename(new_path)
                            final_path = new_path
                            
                            self.rename_counter += 1
                            self.app.config.set("rename_counter", self.rename_counter)
                            
                            self.root.after(0, self.log, "Renamed", f"{current_name} -> {new_name}")
                            break
                        
                        self.rename_counter += 1
                    
                    self.app.config.save()
                
            except Exception as e:
                self.root.after(0, self.log, "Rename Fail", str(e))
                # If rename fails, we continue with original file 'final_path' (vid_path)

        # CRITICAL: Add to processed set logic is handled by caller (monitor), 
        # but also here for safety if called manually? 
        # Actually safe to add to self.processed_files here too to be double sure.
        self.processed_files.add(final_path.name)
        
        # 2. Extract Frame
        self.root.after(0, self.log, "Extracting", final_path.name)
        
        # Save directly in the same folder (User preference)
        output_dir = final_path.parent
        output_png = output_dir / f"{final_path.stem}.png"
        
        success = self.extract_last_frame(final_path, output_png)
        
        if success:
             self.root.after(0, self.on_extraction_success, output_png)
             
        return final_path.name

    def extract_last_frame(self, input_path, output_path):
        # -sseof -0.5 should get last half-second.
        cmd = [
            "ffmpeg", "-y",
            "-sseof", "-0.5", 
            "-i", str(input_path),
            "-update", "1", 
            "-q:v", "2", 
            str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=self.get_startup_info())
            return True
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore')
            print(f"FFmpeg failed: {err_msg}")
            self.root.after(0, self.log, "Error", "FFmpeg Extract Failed")
            return False
        except Exception as e:
            print(f"Generic Error: {e}")
            self.root.after(0, self.log, "Error", str(e))
            return False

    def on_extraction_success(self, png_path):
        self.log("Success", f"Created {png_path.name}")
        
        if self.auto_copy_var.get():
            self.copy_image_to_clipboard(png_path)
            self.log("Action", "Copied to Clipboard")
            
        self.reveal_in_explorer(png_path)
        self.root.bell()

    def copy_image_to_clipboard(self, path):
        # Use single quotes for path in PowerShell to avoid some char issues
        ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile('{str(path)}'))"
        cmd = ["powershell", "-c", ps_cmd]
        try:
            subprocess.run(cmd, startupinfo=self.get_startup_info())
        except: pass

    def reveal_in_explorer(self, path):
        p = str(path).replace("/", "\\")
        cmd = f'explorer /select,"{p}"'
        try:
            subprocess.Popen(cmd, startupinfo=self.get_startup_info())
        except: pass

    def on_drop(self, event):
        try:
            self.log("DnD Event", f"Received drop data: {event.data[:50]}...") # truncate for display
            
            # Robust split (handle {} path wrapping by TkinterDnD)
            files = self.root.tk.splitlist(event.data)
            
            count = 0
            for f in files:
                path = Path(f)
                if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                     # Disable Rename for Drag & Drop
                     threading.Thread(target=self.process_file, args=(path, False), daemon=True).start()
                     count += 1
                else:
                     self.log("Ignored", "Not a video file")
            
            if count == 0:
                self.log("DnD Info", "No valid video files found in drop.")
                
        except Exception as e:
            self.log("DnD Error", str(e))
            print(f"DnD Error: {e}")

    def manual_select(self):
        f = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.mov;*.avi;*.mkv;*.webm")])
        if f:
            # Disable Rename for Manual Select
            threading.Thread(target=self.process_file, args=(Path(f), False), daemon=True).start()

if __name__ == "__main__":
    # Use TkinterDnD.Tk if available
    root = RootClass()
    
    title_suffix = " [DnD Ready]" if HAS_DND else " [DnD Disabled]"
    
    app_wrapper = UniversalUI.UniversalApp(
        root,
        "FrameExtractor" + title_suffix,
        "frame_extractor_v1",
        defaults={"geometry": "650x550", "watch_dir": str(Path.home() / "Downloads")}
    )
    app = FrameExtractorApp(app_wrapper)
    root.mainloop()
