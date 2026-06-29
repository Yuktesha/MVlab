import os
import sys
# Add parent directory to sys.path so we can import the shared _lib
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import subprocess
import random
import threading
import time
import shutil
import datetime
from PIL import Image
from _lib.UniversalUI import UniversalApp, UniversalTreeview, UniversalToplevel

# ==============================================================================
# ==============================================================================
# QMotion - Bootstrapper & Main
# ==============================================================================
# This script is designed to run from the project root (e.g., C:/_MVlab/)
# It expects a data directory named 'QMotion' in the same folder, 
# containing dependencies like 'render_bridge.py' and assets.

# 1. Setup Paths
current_dir = os.path.dirname(os.path.abspath(__file__))
data_dir_name = "QMotion"
data_dir = os.path.join(current_dir, data_dir_name)

# Ensure Data Directory Exists
if not os.path.exists(data_dir):
    messagebox.showerror("Configuration Error", 
        f"Critical folder '{data_dir_name}' not found!\n\n"
        f"Please ensure '{data_dir_name}' is in the same directory as this script.")
    sys.exit(1)

# 2. UniversalUI Self-Healing & Portability Logic (Disabled/Removed for _lib structure)
# We now rely on _lib being present.
sys.path.append(current_dir) # Add root to path
sys.path.append(data_dir)    # Add data dir to path (for backup UI and other modules)

# ==============================================================================
# QMotion
# ==============================================================================

class QMotionApp(UniversalApp):
    def __init__(self, root):
        super().__init__(root, "QMotion", "qmotion_v2")
        
        # Load Config
        # Config is now loaded by UniversalApp from _cfg (in root or subfolder?), 
        # UniversalApp logic looks for _cfg relative to script. 
        # Since script is in root, it looks in c:/_MVlab/_cfg. This is desired.
        
        self.last_dir = self.config.get("last_dir", os.path.expanduser("~"))
        # Output defaults to internal folder for portability, or user choice
        self.output_dir = self.config.get("output_dir", os.path.join(data_dir, "outputs"))
        
        self.setup_ui()
        
        # Check for smart conversion session
        self.check_smart_conversion_session()
        
    def check_smart_conversion_session(self):
         # Placeholder if logic needed on startup (e.g. resume conversion)
         pass

    def setup_ui(self):
        # Main Layout
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # TOP: Media List
        list_frame = ttk.LabelFrame(main_frame, text="Media Sequence")
        list_frame.pack(side="top", fill="both", expand=True, pady=5)
        
        # Treeview for Media
        cols = ["Name", "Date", "Size"]
        self.media_list = UniversalTreeview(list_frame, columns=cols, height=10)
        self.media_list.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        # Column Config
        self.media_list.column("Name", width=300)
        self.media_list.column("Date", width=120)
        self.media_list.column("Size", width=80)
        
        # Scrollbar
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.media_list.yview)
        sb.pack(side="right", fill="y")
        self.media_list.configure(yscrollcommand=sb.set)
        
        # File Controls
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=5)
        
        ttk.Button(btn_frame, text="+ Add Media", command=self.add_media).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="- Remove", command=self.remove_media).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_media).pack(side="left", padx=5)
        
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=10)
        
        ttk.Button(btn_frame, text="Move Up", command=self.move_up).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Move Down", command=self.move_down).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Shuffle", command=self.shuffle_media).pack(side="left", padx=5)
 
        # MIDDLE: Settings
        settings_frame = ttk.LabelFrame(main_frame, text="Composition Settings")
        settings_frame.pack(fill="x", pady=5)
        
        # Row 1: Title & Theme
        r1 = ttk.Frame(settings_frame)
        r1.pack(fill="x", padx=5, pady=5)
        
        # Row 1: Overlays Button (Replacing simple Title Image)
        ttk.Label(r1, text="Overlays:").pack(side="left")
        self.overlay_config = [] # Store list of overlay dicts
        ttk.Button(r1, text="Manage Titles / Credits...", command=self.open_overlay_manager).pack(side="left", padx=5)
        self.overlay_status = ttk.Label(r1, text="(0 items)")
        self.overlay_status.pack(side="left")
        
        ttk.Label(r1, text="Theme:").pack(side="left", padx=10)
        self.selected_theme = tk.StringVar(value=self.config.get("last_theme", "Slideshow"))
        themes = ["Slideshow", "DynamicOverlay (WIP)", "AutoEdit (WIP)"]
        ttk.Combobox(r1, textvariable=self.selected_theme, values=themes, state="readonly", width=15).pack(side="left")

        # Row 2: Visuals (Aspect, Fit)
        r2 = ttk.Frame(settings_frame)
        r2.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(r2, text="Resolution:").pack(side="left")
        self.selected_aspect = tk.StringVar(value=self.config.get("last_aspect", "1920x1080 (16:9 FHD)"))
        resolutions = [
            "Auto (自動匹配第一張圖)",
            "--- 16:9 (橫向 Landscape) ---",
            "3840x2160 (16:9 4K)",
            "1920x1080 (16:9 FHD)",
            "1280x720 (16:9 HD)",
            "--- 4:3 (橫向 Landscape) ---",
            "1440x1080 (4:3)",
            "--- 1:1 (方形 Square) ---",
            "2160x2160 (1:1 4K)",
            "1080x1080 (1:1 FHD)",
            "720x720 (1:1 HD)",
            "--- 3:4 (直向 Portrait) ---",
            "1080x1440 (3:4)",
            "--- 9:16 (直向 Portrait) ---",
            "2160x3840 (9:16 4K)",
            "1080x1920 (9:16 FHD)",
            "720x1280 (9:16 HD)",
        ]
        ttk.Combobox(r2, textvariable=self.selected_aspect, values=resolutions, state="readonly", width=30).pack(side="left", padx=5)
        
        ttk.Label(r2, text="Image Fit:").pack(side="left", padx=10)
        self.selected_fit = tk.StringVar(value=self.config.get("last_fit", "Cover"))
        fit_modes = ["Cover", "Contain", "Contain (Blur)"]
        ttk.Combobox(r2, textvariable=self.selected_fit, values=fit_modes, state="readonly", width=15).pack(side="left", padx=5)

        # Row 3: Timing
        r3 = ttk.Frame(settings_frame)
        r3.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(r3, text="Slide Duration (s):").pack(side="left")
        self.duration_entry = ttk.Entry(r3, width=5)
        self.duration_entry.insert(0, str(self.config.get("duration", 4.0)))
        self.duration_entry.pack(side="left", padx=5)
        
        ttk.Label(r3, text="Transition (s):").pack(side="left", padx=10)
        self.transition_entry = ttk.Entry(r3, width=5)
        self.transition_entry.insert(0, str(self.config.get("transition", 1.0)))
        self.transition_entry.pack(side="left", padx=5)

        # BOTTOM: Output & Action
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill="x", pady=10)
        
        ttk.Label(action_frame, text="Output:").pack(side="left")
        self.output_entry = ttk.Entry(action_frame)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(action_frame, text="Browse...", command=self.browse_output).pack(side="left")
        
        self.generate_btn = ttk.Button(action_frame, text="Generate Video", command=self.generate_video)
        self.generate_btn.pack(side="right", padx=10)

    def open_overlay_manager(self):
        # We can implement a mini-dialog here OR launch the standalone OverlayEngine in a mode?
        # Better: Implement a mini-manager dialog here that saves to self.overlay_config
        
        # Better: Implement a mini-manager dialog here that saves to self.overlay_config
        
        
        dlg = UniversalToplevel(self.root, title="Manage Overlays", state_id="overlay_manager")
        dlg.geometry("500x350")
        
        # Layout: Buttons at Bottom, Tip at Top, Tree in Middle
        btn_fr = ttk.Frame(dlg)
        btn_fr.pack(side="bottom", fill="x", padx=5, pady=5)
        
        ttk.Label(dlg, text="💡 Tip: Drag & Drop PNG files here to add them quickly.", foreground="#888").pack(side="top", pady=5)
        
        # List
        cols = ["Image", "Anchor", "Offset", "Anim"]
        tree = ttk.Treeview(dlg, columns=cols, show="headings")
        for c in cols: tree.heading(c, text=c)
        tree.pack(side="top", fill="both", expand=True, padx=5)
        
        # DND Support
        try:
            def on_drop(event):
                files = self.root.tk.splitlist(event.data)
                for f in files:
                    if f.lower().endswith('.png'):
                        # Default Item
                        item = {
                            "path": f,
                            "anchor": "start",
                            "offset": 0.0,
                            "duration": 5.0,
                            "anim_in": "fade",
                            "anim_out": "fade"
                        }
                        self.overlay_config.append(item)
                        tree.insert("", "end", values=(os.path.basename(f), item["anchor"], item["offset"], "fade / fade"))
                self.overlay_status.config(text=f"({len(self.overlay_config)} items)")

            tree.drop_target_register(DND_FILES)
            tree.dnd_bind('<<Drop>>', on_drop)
        except Exception as e:
            print(f"DND Setup Failed: {e}")
        
        # Populate
        for ov in self.overlay_config:
            name = os.path.basename(ov["path"])
            anim_str = f"{ov['anim_in']} / {ov.get('anim_out', 'none')}"
            tree.insert("", "end", values=(name, ov["anchor"], ov["offset"], anim_str))
            
        def add():
            # Mini add dialog
            d2 = UniversalToplevel(dlg, title="Add Item", state_id="add_overlay_item")
            
            ttk.Label(d2, text="Image:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
            v_path = tk.StringVar()
            ttk.Entry(d2, textvariable=v_path, width=30).grid(row=0, column=1, padx=5, pady=5)
            ttk.Button(d2, text="...", command=lambda: v_path.set(filedialog.askopenfilename()), width=3).grid(row=0, column=2, padx=5)
            
            ttk.Label(d2, text="Anchor:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
            v_anchor = tk.StringVar(value="start")
            ttk.Combobox(d2, textvariable=v_anchor, values=["start", "end"], state="readonly").grid(row=1, column=1, sticky="w", padx=5)

            ttk.Label(d2, text="Offset (s):").grid(row=2, column=0, sticky="e", padx=5, pady=5)
            v_off = tk.StringVar(value="0.0")
            ttk.Entry(d2, textvariable=v_off).grid(row=2, column=1, sticky="w", padx=5)
            
            ttk.Label(d2, text="Duration (s):").grid(row=3, column=0, sticky="e", padx=5, pady=5)
            v_dur = tk.StringVar(value="5.0")
            ttk.Entry(d2, textvariable=v_dur).grid(row=3, column=1, sticky="w", padx=5)
            
            ttk.Label(d2, text="Anim In:").grid(row=4, column=0, sticky="e", padx=5, pady=5)
            v_anim = tk.StringVar(value="fade")
            anims = ["none", "fade", "slide_left", "slide_right", "slide_up", "slide_down", "scroll_up"]
            ttk.Combobox(d2, textvariable=v_anim, values=anims, state="readonly").grid(row=4, column=1, sticky="w", padx=5)
            
            ttk.Label(d2, text="Anim Out:").grid(row=5, column=0, sticky="e", padx=5, pady=5)
            v_anim_out = tk.StringVar(value="fade")
            anims_out = ["none", "fade", "slide_left", "slide_right", "slide_up", "slide_down"]
            ttk.Combobox(d2, textvariable=v_anim_out, values=anims_out, state="readonly").grid(row=5, column=1, sticky="w", padx=5)
            
            def save_item():
                item = {
                    "path": v_path.get(),
                    "anchor": v_anchor.get(),
                    "offset": float(v_off.get() or 0),
                    "duration": float(v_dur.get() or 5),
                    "anim_in": v_anim.get(),
                    "anim_out": v_anim_out.get()
                }
                anim_str = f"{item['anim_in']} / {item['anim_out']}"
                self.overlay_config.append(item)
                tree.insert("", "end", values=(os.path.basename(item["path"]), item["anchor"], item["offset"], anim_str))
                self.overlay_status.config(text=f"({len(self.overlay_config)} items)")
                d2.destroy()
            
            # Button Frame for Add Dialog
            bf = ttk.Frame(d2)
            bf.grid(row=6, column=0, columnspan=3, pady=10)
            ttk.Button(bf, text="Add", command=save_item).pack()
            
        def delete():
            sel = tree.selection()
            if sel:
                idx = tree.index(sel[0])
                self.overlay_config.pop(idx)
                tree.delete(sel[0])
                self.overlay_status.config(text=f"({len(self.overlay_config)} items)")

        # Buttons (Already packed at bottom)
        ttk.Button(btn_fr, text="Add Item", command=add).pack(side="left")
        ttk.Button(btn_fr, text="Remove", command=delete).pack(side="left")
        ttk.Button(btn_fr, text="Close", command=dlg.destroy).pack(side="right")

    def browse_overlay(self):
        f = filedialog.askopenfilename(
            title="Select Overlay Image (PNG)",
            filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")]
        )
        if f:
             self.overlay_path_var.set(f)

    def add_media(self):
        files = filedialog.askopenfilenames(
            initialdir=self.last_dir,
            title="Select Images/Videos",
            filetypes=[("Media Files", "*.jpg *.jpeg *.png *.mp4 *.mov *.avi *.mkv *.tiff *.tif *.webp *.pdf *.heic")]
        )
        if not files: return
        
        self.last_dir = os.path.dirname(files[0])
        self.config.set("last_dir", self.last_dir)
        self.config.save()
        
        # Identify unsupported
        unsupported = []
        valid_extensions = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.mkv', '.webp'}
        
        to_add = []
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in valid_extensions and ext in {'.tiff', '.tif', '.pdf', '.heic'}:
                unsupported.append(f)
            else:
                to_add.append(f)
                
        # Handle unsupported
        if unsupported:
             self._run_smart_conversion(files, unsupported, None)
             return

        # Add to Treeview
        for f in to_add:
            self._insert_file_to_tree(f)
            
    def _insert_file_to_tree(self, filepath):
        # Gather Stats
        try:
            stats = os.stat(filepath)
            size_mb = stats.st_size / (1024 * 1024)
            size_str = f"{size_mb:.2f} MB"
            mtime = datetime.datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
        except:
            size_str = "?"
            mtime = "?"
            
        name = os.path.basename(filepath)
        
        if not self.media_list.exists(filepath):
            self.media_list.insert('', 'end', iid=filepath, values=(name, mtime, size_str))

    def remove_media(self):
        selected = self.media_list.selection()
        for item in selected:
            self.media_list.delete(item)
            
    def clear_media(self):
         self.media_list.delete(*self.media_list.get_children())

    def move_up(self):
        selected = self.media_list.selection()
        if not selected: return
        rows = [(self.media_list.index(item), item) for item in selected]
        rows.sort()
        for idx, item in rows:
            if idx > 0:
                self.media_list.move(item, '', idx - 1)
        self.media_list.refresh_stripes()

    def move_down(self):
        selected = self.media_list.selection()
        if not selected: return
        rows = [(self.media_list.index(item), item) for item in selected]
        rows.sort(reverse=True)
        last_idx = len(self.media_list.get_children()) - 1
        for idx, item in rows:
            if idx < last_idx:
                self.media_list.move(item, '', idx + 1)
        self.media_list.refresh_stripes()

    def shuffle_media(self):
        items = list(self.media_list.get_children())
        random.shuffle(items)
        for i, item in enumerate(items):
            self.media_list.move(item, '', i)
        self.media_list.refresh_stripes()

    def browse_output(self):
        f = filedialog.asksaveasfilename(
            title="Save Video As",
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4")],
            initialfile="MyVideo.mp4"
        )
        if f:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, f)

    def generate_video(self):
        # Get Media Files from Treeview (in order)
        media_files = self.media_list.get_children() # These are IIDs which are full paths
        
        if not media_files:
            messagebox.showwarning("No Media", "Please add at least one image or video.")
            return

        # Gather Inputs
        overlay_image = None
             
        theme = self.selected_theme.get()
        
        try:
            duration = float(self.duration_entry.get())
            transition = float(self.transition_entry.get())
            if duration <= 0 or transition < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Input", "Duration and Transition must be positive numbers.")
            return
            
        # Parse Advanced Settings
        res_str = self.selected_aspect.get()
        
        # Backward compatibility for old config values
        aspect_map = {
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "1:1": (1080, 1080),
            "4:3": (1440, 1080),
            "3:4": (1080, 1440)
        }
        
        if res_str.startswith("Auto"):
            first_media = media_files[0]
            try:
                with Image.open(first_media) as img:
                    width, height = img.size
                # Round to even dimensions (FFmpeg requires even for some codecs)
                width = width - (width % 2)
                height = height - (height % 2)
            except Exception as e:
                # Fallback if unreadable or video
                try:
                    # Try using OpenCV/ffprobe indirectly or just fallback
                    # Since we don't readily have cv2 imported, fallback to 1080p
                    width, height = 1920, 1080
                    print(f"Auto-res failed for {first_media}, defaulting to 1920x1080 ({e})")
                except:
                    width, height = 1920, 1080

        elif res_str in aspect_map:
            width, height = aspect_map[res_str]
        elif res_str.startswith("---"):
            messagebox.showwarning("Invalid Resolution", "請選擇有效的影片解析度。 (Please select a valid resolution.)")
            return
        else:
            try:
                # Extract width and height from "1920x1080 ..."
                dims = res_str.split(" ")[0].split("x")
                width = int(dims[0])
                height = int(dims[1])
            except Exception:
                width, height = 1920, 1080
        
        aspect = res_str  # For config saving
        
        fit_raw = self.selected_fit.get()
        fit_mode = "cover"
        if fit_raw == "Contain": fit_mode = "contain"
        elif fit_raw == "Contain (Blur)": fit_mode = "contain-blur"
        
        # Save Config
        self.config.set("last_theme", theme)
        self.config.set("last_aspect", aspect)
        self.config.set("last_fit", fit_raw)
        self.config.save()
        
        # Auto-Generate Filename with Prefix
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        current_out_path = self.output_entry.get()
        
        # Determine Directory and Prefix
        if os.path.isdir(current_out_path):
            output_dir = current_out_path
            user_prefix = "Video"
        else:
            output_dir = os.path.dirname(current_out_path)
            # If empty dir (e.g. just filename "MyVideo.mp4"), use default dir
            if not output_dir:
                 output_dir = os.path.join(data_dir, "outputs")
                 
            # Extract filename part as prefix
            base = os.path.basename(current_out_path)
            user_prefix, _ = os.path.splitext(base)
            if not user_prefix: user_prefix = "Video"

        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except:
                output_dir = os.path.join(data_dir, "outputs")
                os.makedirs(output_dir, exist_ok=True)
        
        # Filename Format: [Name]_[Timestamp]_[Theme]_[FitMode]_[WxH].mp4
        # Clean fit_mode string for filename
        fit_str = fit_raw.replace(" ", "").replace("(", "").replace(")", "")
        filename = f"{user_prefix}_{timestamp}_{theme}_{fit_str}_{width}x{height}.mp4"
        output_path = os.path.join(output_dir, filename)
        
        self.output_entry.delete(0, tk.END)
        self.output_entry.insert(0, output_path)

        theme_config = {
            "theme": theme,
            "duration": duration,
            "transition": transition,
            "width": width,
            "height": height,
            "fitMode": fit_mode
        }

        # Start Render Thread
        threading.Thread(target=self._run_render, args=(media_files, output_path, theme_config, overlay_image), daemon=True).start()
        
    def _run_render(self, media_files, output_path, theme_config, overlay_image):
        # Convert tuple to list
        media_files_list = list(media_files)
        
        self.root.after(0, lambda: self._show_progress_window("Starting Engine..."))
        
        try:
            # Initialize Engine
            project_root = data_dir 
            
            # Check for FFmpeg Engine
            try:
                from render_engine_ffmpeg import FFmpegEngine
            except ImportError:
                if project_root not in sys.path:
                    sys.path.append(project_root)
                from render_engine_ffmpeg import FFmpegEngine
                
            engine = FFmpegEngine(project_root)
            
            # Render
            self.root.after(0, lambda: self.progress_label.config(text=f"Rendering Video..."))
            self.root.after(0, lambda: self.progress_bar.configure(value=10))
            
            def render_callback(line):
                print(f"[Render] {line}")
                # Update label
                if "Progress:" in line:
                     self.root.after(0, lambda l=line: self.progress_label.config(text=l))
                elif "Error" in line:
                     self.root.after(0, lambda l=line: self.progress_label.config(text=l))
            
            # Call Render (Base Video)
            # Create temp output for base
            import tempfile
            base_output = output_path.replace(".mp4", "_base.mp4")
            
            result_base = engine.render(
                media_list=media_files_list, 
                output_path=base_output, 
                theme_config=theme_config, 
                overlay_image=None, # Deprecated single overlay
                callback=render_callback
            )
            
            if result_base and os.path.exists(result_base):
                # 3. Post-Process with OverlayEngine if overlays exist
                if self.overlay_config:
                    self.root.after(0, lambda: self.progress_label.config(text="Applying Overlays & Credits..."))
                    
                    # Dump config to temp json
                    cfg_path = os.path.join(data_dir, "temp_overlays.json")
                    with open(cfg_path, "w") as f:
                        json.dump(self.overlay_config, f)
                        
                    # Call CLI
                    # python OverlayEngine_Pro.py --input base --config cfg --output final --nogui
                    overlay_script = os.path.join(data_dir, "../OverlayEngine_Pro.py")
                    if not os.path.exists(overlay_script):
                         # Try current dir
                         overlay_script = os.path.join(current_dir, "OverlayEngine_Pro.py")

                    cmd = [
                        sys.executable,
                        overlay_script,
                        "--input", base_output,
                        "--config", cfg_path,
                        "--output", output_path,
                        "--nogui"
                    ]
                    
                    print(f"Running Overlay CLI: {cmd}")
                    subprocess.check_call(cmd)
                    
                    # Cleanup base
                    try:
                        os.remove(base_output)
                    except: pass
                    
                    result = output_path
                else:
                    # No overlays, just rename base to final
                    if os.path.exists(output_path): os.remove(output_path)
                    os.rename(base_output, output_path)
                    result = output_path
            else:
                result = None
            
            self.root.after(0, lambda: self.progress_bar.configure(value=100))
            
            if result:
                self.root.after(0, lambda: self.progress_label.config(text="Render Complete! Opening Video..."))
                try:
                    os.startfile(result)
                except Exception as e:
                    print(f"Could not open file: {e}")
            else:
                 self.root.after(0, lambda: self.progress_label.config(text="Render Failed."))
                 messagebox.showerror("Error", "Render Failed. Check console logs.")

            # Close progress window after delay
            self.root.after(2000, self._close_progress_window)
            
        except Exception as e:
            self.root.after(0, self._close_progress_window)
            messagebox.showerror("Render Error", f"An error occurred:\n{str(e)}")
            print(e)

    def restart_application(self):
        """Restarts the current application to free up GDI/GPU resources."""
        try:
            print("Restarting application...")
            # Use subprocess to start a new instance
            subprocess.Popen([sys.executable] + sys.argv)
            # Exit this instance
            self.root.quit()
        except Exception as e:
            print(f"Failed to restart: {e}")
            messagebox.showerror("Error", f"Failed to restart: {e}")
            
        except Exception as e:
            self.root.after(0, self._close_progress_window)
            messagebox.showerror("Render Error", f"An error occurred:\n{str(e)}")
            print(e)
            
    def _show_progress_window(self, message):
        self.progress_win = tk.Toplevel(self.root)
        self.progress_win.title("Processing")
        
        # Load saved geometry or default to center
        saved_geo = self.config.get("progress_geometry", "")
        if saved_geo:
            self.progress_win.geometry(saved_geo)
        else:
            self.progress_win.geometry("400x150")
            # Center window
            self.progress_win.update_idletasks() # Ensure sizes are known
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 75
            self.progress_win.geometry(f"+{x}+{y}")
            
        self.progress_win.resizable(True, True)
        
        # Bind close event to save geometry (in case user clicks X)
        self.progress_win.protocol("WM_DELETE_WINDOW", self._close_progress_window)
        
        tk.Label(self.progress_win, text=message, wraplength=380).pack(pady=20, fill=tk.BOTH, expand=True)
        self.progress_bar = ttk.Progressbar(self.progress_win, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, padx=20, pady=10)
        self.progress_bar.start(10)
        
        self.progress_label = tk.Label(self.progress_win, text="Please wait...")
        self.progress_label.pack(pady=5)

    def _close_progress_window(self):
        if hasattr(self, 'progress_win') and self.progress_win.winfo_exists():
            # Save Geometry
            geo = self.progress_win.geometry()
            self.config.set("progress_geometry", geo)
            self.config.save()
            self.progress_win.destroy()

    def _run_smart_conversion(self, all_files, unsupported_files, engine):
        # 1. Ask for Output Dir
        last_dir = self.config.get("last_converted_folder", "")
        if not last_dir:
            last_dir = os.path.dirname(all_files[0])
            
        target_dir = filedialog.askdirectory(title="Select Folder for Converted Files", initialdir=last_dir)
        if not target_dir: return

        self.config.set("last_converted_folder", target_dir)
        self.config.save()
        
        self._show_progress_window("Converting media...")
        
        def worker():
            converted_map = {}
            # Ensure ConverterEngine is available
            try:
                from _lib.MediaConverter import ConverterEngine
                local_engine = ConverterEngine()
            except ImportError:
                self.root.after(0, lambda: messagebox.showerror("Error", "MediaConverter not found."))
                self.root.after(0, self._close_progress_window)
                return

            session_overwrite = None
            
            for src in unsupported_files:
                target = local_engine.get_target_path(src, target_dir)
                self.root.after(0, lambda t=os.path.basename(src): self.progress_label.config(text=f"Processing: {t}"))
                
                # Overwrite Check
                if os.path.exists(target):
                    should_overwrite = False
                    if session_overwrite is not None:
                        should_overwrite = session_overwrite
                    else:
                        response = [None]
                        self.root.after(0, lambda: self._ask_overwrite(target, response))
                        while response[0] is None:
                            time.sleep(0.1)
                        res = response[0]
                        if res == "cancel": break
                        if res == "yes_all": session_overwrite = True; should_overwrite = True
                        elif res == "no_all": session_overwrite = False; should_overwrite = False
                        elif res == "yes": should_overwrite = True
                        else: should_overwrite = False
                    
                    if not should_overwrite:
                        converted_map[src] = target
                        continue

                success, msg = local_engine.convert_file(src, target)
                if success:
                    converted_map[src] = target
                else:
                    print(f"Failed to convert {src}: {msg}")

            # Re-assemble list
            final_files = []
            for f in all_files:
                if f in converted_map:
                    final_files.append(converted_map[f])
                elif f not in unsupported_files:
                    final_files.append(f)
            
            self.root.after(0, self._close_progress_window)
            self.root.after(0, lambda: self._add_converted_files(final_files))

        threading.Thread(target=worker, daemon=True).start()

    def _ask_overwrite(self, path, container):
        dialog = tk.Toplevel(self.root)
        dialog.title("File Exists")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text=f"File already exists:\n{os.path.basename(path)}\nOverwrite?", wraplength=380).pack(pady=10)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        def set_res(val):
            container[0] = val
            dialog.destroy()
            
        ttk.Button(btn_frame, text="Yes", width=8, command=lambda: set_res("yes")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Yes to All", width=10, command=lambda: set_res("yes_all")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Skip", width=8, command=lambda: set_res("no")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Skip All", width=10, command=lambda: set_res("no_all")).pack(side=tk.LEFT, padx=5)
        
        dialog.protocol("WM_DELETE_WINDOW", lambda: set_res("cancel"))

    def _add_converted_files(self, files):
        # Clear/Add? Or Append?
        # Logic says we were adding, so let's append.
        for f in files:
            self._insert_file_to_tree(f)

if __name__ == "__main__":
    root = tk.Tk()
    app = QMotionApp(root)
    root.mainloop()
