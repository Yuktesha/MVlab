
# ==============================================================================
# UNIVERSAL UI LIBRARY v1.2
# ==============================================================================

import tkinter as tk
from tkinter import ttk, messagebox, font
import json
import os
import shutil
import glob
import sys
import copy
import ctypes
import winreg
from pathlib import Path


from pathlib import Path


def get_system_theme():
    """
    Detects Windows System Theme (Dark/Light).
    Returns 'light' or 'dark'.
    """
    try:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value == 1 else "dark"
    except:
        return "dark" # Fallback

def apply_title_bar_theme(window, dark=True):
    """
    Forces Windows Title Bar to Dark (True) or Light (False) mode using DWM API.
    """
    try:
        window.update_idletasks() # Ensure HWND is valid
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 11 / Windows 10 1809+)
        # DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20h1 = 19 (Older Windows 10)
        
        value = ctypes.c_int(2) if dark else ctypes.c_int(0) # 2=True for some versions, 1=True generally. 0=False.
        # Actually value 1 is enabled? Let's check docs.
        # Docs say: BOOL value. TRUE (1) to use dark mode, FALSE (0) to use light.
        # But some reports say use '2' for 'System'.
        # Safest for forced dark is 1. Forced light is 0.
        
        val = ctypes.c_int(1 if dark else 0)
        
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception as e:
        # print(f"DWM Error: {e}")
        pass


class AppConfig:
    def __init__(self, app_name, signature, defaults=None):
        self.app_name = app_name
        self.signature = signature
        # Dynamic Name: [AppName]_cfg.json
        # Dynamic Name: [AppName]_cfg.json
        # Logic:
        # 1. Check legacy: [ScriptDir]/[AppName]_cfg.json
        # 2. Check new:    [ScriptDir]/_cfg/[AppName]_cfg.json
        self.script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.legacy_path = os.path.join(self.script_dir, f"{app_name}_cfg.json")
        
        self.cfg_dir = os.path.join(self.script_dir, "_cfg")
        self.new_path = os.path.join(self.cfg_dir, f"{app_name}_cfg.json")
        
        # Decide which one to use
        if os.path.exists(self.legacy_path):
            self.filename = self.legacy_path
        else:
            self.filename = self.new_path
        
        self.defaults = defaults or {}
        # Embed signature in defaults
        self.defaults["config_signature"] = self.signature
        
        self.data = self.load()

    def load(self):
        # 1. Try Find Exact Match
        if os.path.exists(self.filename):
            return self._read_file(self.filename)
            
        # 2. Smart Scan (If missing)
        return self._scan_and_adopt()

    def _read_file(self, path):
        data = self.defaults.copy()
        try:
            with open(path, 'r') as f:
                saved = json.load(f)
                # Verify Signature if present in saved file
                if saved.get("config_signature") == self.signature:
                    data.update(saved)
                else:
                    # Generic fallback or migration could happen here
                    # For now, if no signature, we assume it's valid legacy or just load it
                    data.update(saved)
        except: pass
        # Ensure signature is set in memory for next save
        data["config_signature"] = self.signature
        return data

    def _scan_and_adopt(self):
        # Look for *_cfg.json files
        candidates = []
        for file in glob.glob("*_cfg.json"):
            if file == self.filename: continue
            try:
                with open(file, 'r') as f:
                    dat = json.load(f)
                    if dat.get("config_signature") == self.signature:
                        candidates.append(file)
            except: pass
            
        if not candidates:
            return self.defaults.copy()
            
        # Found candidates! Ask User.
        return self._ask_user_to_adopt(candidates)

    def _ask_user_to_adopt(self, candidates):
        # We need a root window to show dialog, but AppConfig might run before main UI?
        # UniversalApp creates AppConfig. We can use a temporary hidden root or defer?
        # Simplest: Use a temp hidden root for the dialog.
        
        root = tk.Tk()
        root.withdraw()
        
        # Format msg
        msg = f"Configuration file '{self.filename}' not found.\n\n"
        msg += f"However, I found {len(candidates)} compatible configuration(s) from previous versions or renamed copies:\n\n"
        for c in candidates[:5]: msg += f" - {c}\n"
        if len(candidates) > 5: msg += " ... and more\n"
        msg += "\nWould you like to import settings from the most recent one?"
        
        # Sort by modification time (newest first)
        candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        best = candidates[0]
        
        # Using AskYesNo
        adopt = messagebox.askyesno("Smart Config Recovery", msg, parent=root)
        root.destroy()
        
        if adopt:
            # Copy content
            data = self._read_file(best)
            # Save immediately to new name
            self.data = data
            self.save()
            return data
        else:
            return self.defaults.copy()

    def save(self):
        self.data["config_signature"] = self.signature
        try:
            # If using new path, ensure directory exists
            if self.filename == self.new_path:
                if not os.path.exists(self.cfg_dir):
                    os.makedirs(self.cfg_dir)

            with open(self.filename, 'w') as f:
                json.dump(self.data, f, indent=4)
        except: pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

class UniversalToplevel(tk.Toplevel):
    """
    A auto-themed Toplevel window that inherits the Antigravity theme.
    """
    def __init__(self, parent, title=None, **kwargs):
        super().__init__(parent, **kwargs)
        if title: self.title(title)
        
        # 1. Apply Background from Parent (or default)
        try:
            # We assume parent is themed correctly. 
            # If parent is root, cget('bg') works.
            bg = parent.cget("bg")
            self.configure(bg=bg)
        except:
            # Fallback
            self.configure(bg="#1e1e1e")
            
        # 2. Apply Title Bar Theme
        # We need to determine if dark mode is active.
        # We can try to assume dark unless we know otherwise, 
        # OR we can check if the parent has a 'is_dark' attribute (if it's UniversalApp)
        # OR we can just check the bg color.
        is_dark = True
        try:
             if self.cget("bg").lower() in ("#f0f0f0", "white", "systembuttonface"):
                 is_dark = False
        except: pass
        
        # Apply immediate
        self.after(10, lambda: apply_title_bar_theme(self, is_dark))

        # 3. State Persistence (Geometry)
        self.state_id = kwargs.get("state_id")
        self.app_config = getattr(parent.winfo_toplevel(), "universal_app_config", None)
        
        if self.state_id and self.app_config:
            # Restore
            geo = self.app_config.get(f"window_{self.state_id}")
            if geo:
                try: self.geometry(geo)
                except: pass
        
        # Propagate config to self so children of this Toplevel can find it too
        if self.app_config:
            self.universal_app_config = self.app_config
                
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        if self.state_id and self.app_config:
            # Save
            self.app_config.set(f"window_{self.state_id}", self.geometry())
            self.app_config.save()
        self.destroy()

class UniversalApp:
    def __init__(self, root, title, app_signature, defaults=None):
        self.root = root
        self.title = title
        self.root.title(title)
        
        # Determine App Name from script name (safe against renaming)
        # sys.argv[0] -> "FilmStitch_Pro.py" -> "FilmStitch_Pro"
        script_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]
        
        # Win Protocol
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Config (Smart)
        self.config = AppConfig(script_name, app_signature, defaults)
        
        # Expose config to root for children (UniversalToplevel) to access
        self.root.universal_app_config = self.config

        
        # State
        self.base_font_size = 11
        self.scale_factor = self.config.get("ui_scale", 1.0)
        
        # Initialize Named Fonts (These update automatically!)
        # Use Microsoft JhengHei UI for better CJK coverage on Windows, avoiding weird fallbacks
        self.font_std = font.Font(family="Microsoft JhengHei UI", size=self.base_font_size)
        self.font_bold = font.Font(family="Microsoft JhengHei UI", size=self.base_font_size, weight="bold")
        # Keep font_mono object for reference, though we override Text widgets with tuple for fallback
        self.font_mono = font.Font(family="Consolas", size=self.base_font_size-2)
        self.font_h1 = font.Font(family="Microsoft JhengHei UI", size=int(self.base_font_size*1.6), weight="bold")
        
        self.setup_theme()
        
        # Geometry Restore
        geo = self.config.get("geometry")
        if geo:
            try: self.root.geometry(geo)
            except: pass
            
        # Maximize Restore
        if self.config.get("maximized", False):
            try: self.root.state('zoomed')
            except: pass
            
        # Bind Scaling
        self.root.bind("<Control-plus>", self.increase_scale)
        self.root.bind("<Control-equal>", self.increase_scale)
        self.root.bind("<Control-minus>", self.decrease_scale)
        self.root.bind("<Control-0>", self.reset_scale)
        self.root.bind("<Control-t>", self.toggle_theme)
        self.root.bind("<Control-T>", self.toggle_theme)

    def toggle_theme(self, event=None):
        """Toggles between Dark and Light mode."""
        current = self.config.get("theme", "system")
        if current == "dark":
            new_mode = "light"
        elif current == "light":
            new_mode = "system" # Back to system or switch to dark? Let's cycle dark -> light -> system
        else:
            new_mode = "dark"
            
        self.config.set("theme", new_mode)
        self.setup_theme()
        
        # Show a Toast to notify user
        mode_label = new_mode.capitalize()
        if new_mode == "system":
            mode_label = f"System ({get_system_theme().capitalize()})"
        self.show_toast(f"Theme switched to {mode_label}", level="info")

    def open_settings(self):
        """Opens the generic Universal Settings Dialog."""
        UniversalSettingsDialog(self.root, self.config, self.reload_settings)

    def reload_settings(self):
        """Override this in your app to apply settings when they change."""
        pass

    def setup_theme(self):
        # 1. Determine Mode
        mode = self.config.get("theme", "system")
        if mode == "system":
            effective_theme = get_system_theme()
        else:
            effective_theme = mode
            
        self.is_dark = (effective_theme == "dark")
        
        # 2. Apply Title Bar Theme (DWM)
        self.root.after(10, lambda: apply_title_bar_theme(self.root, self.is_dark))

        style = ttk.Style()
        
        if not self.is_dark:
            # LIGHT MODE: Use Native Windows Theme (vista/xpnative)
            # This looks like standard Windows apps.
            style.theme_use('vista')
            self.root.configure(bg="#f0f0f0") # Standard Windows Bg
            return

        # DARK MODE: Custom Styling (Clam) - Antigravity / VS Code Style
        
        # Palette
        BG_MAIN = "#1e1e1e"   # Deep Editor Grey
        BG_SEC = "#252526"    # Sidebars / Headers
        BG_INPUT = "#3c3c3c"  # Inputs
        FG_MAIN = "#cccccc"   # Readable Light Grey
        FG_SEC = "#858585"    # Dimmed Text
        ACCENT = "#007acc"    # Cyber Blue (VS Code)
        BORDER = "#454545"    # Subtle Border
        
        self.root.configure(bg=BG_MAIN)
        style.theme_use('clam')
        
        # Base
        style.configure(".", background=BG_MAIN, foreground=FG_MAIN, borderwidth=0, font=self.font_std)
        
        # Widgets
        style.configure("TLabel", background=BG_MAIN, foreground=FG_MAIN, font=self.font_std)
        style.configure("Header.TLabel", font=self.font_h1, foreground="white") # Special Header Style
        
        style.configure("TButton", background=BG_INPUT, foreground="white", borderwidth=0, relief="flat", anchor="center", font=self.font_std)
        style.map("TButton", background=[('active', ACCENT), ('pressed', '#005fb8')], foreground=[('disabled', FG_SEC)])
        
        style.configure("TEntry", fieldbackground=BG_INPUT, foreground="white", insertcolor="white", borderwidth=1, bordercolor=BORDER, relief="flat", font=self.font_std)
        style.map("TEntry", bordercolor=[('focus', ACCENT)], lightcolor=[('focus', ACCENT)], darkcolor=[('focus', ACCENT)])
        
        style.configure("TCheckbutton", background=BG_MAIN, foreground=FG_MAIN, font=self.font_std)
        style.map("TCheckbutton", indicatorbackground=[('selected', ACCENT), ('active', BG_INPUT)], background=[('active', BG_MAIN)], indicatorcolor=[('selected', ACCENT)])
        
        style.configure("TRadiobutton", background=BG_MAIN, foreground=FG_MAIN, font=self.font_std)
        style.map("TRadiobutton", indicatorbackground=[('selected', ACCENT), ('active', BG_INPUT)], background=[('active', BG_MAIN)], indicatorcolor=[('selected', ACCENT)])
        
        style.configure("TLabelframe", background=BG_MAIN, foreground=FG_MAIN, bordercolor=BORDER, borderwidth=1)
        style.configure("TLabelframe.Label", background=BG_MAIN, foreground=ACCENT, font=self.font_bold)
        
        # Combobox: Fix hover (active) states for Readonly and Normal modes
        # Clam theme needs explicit state combinations to override defaults
        style.configure("TCombobox", fieldbackground=BG_INPUT, background=BG_INPUT, foreground="white", arrowcolor="white", borderwidth=0)
        style.map("TCombobox", 
                  fieldbackground=[('readonly', 'active', BG_INPUT), ('readonly', BG_INPUT), ('disabled', BG_MAIN)],
                  selectbackground=[('readonly', 'active', BG_INPUT), ('!readonly', 'active', BG_INPUT)],
                  selectforeground=[('readonly', 'white'), ('!readonly', 'white')],
                  background=[('active', BG_INPUT), ('pressed', BG_INPUT)], 
                  foreground=[('readonly', 'active', 'white'), ('active', 'white'), ('disabled', '#5f6368')],
                  arrowcolor=[('active', 'white'), ('disabled', '#5f6368')])
        
        # Spinbox (Needs similar treatment)
        style.configure("TSpinbox", fieldbackground=BG_INPUT, background=BG_INPUT, foreground="white", arrowcolor="white", borderwidth=0)
        style.map("TSpinbox", 
                  fieldbackground=[('readonly', 'active', BG_INPUT), ('readonly', BG_INPUT), ('disabled', BG_MAIN)],
                  selectbackground=[('readonly', 'active', BG_INPUT), ('!readonly', 'active', BG_INPUT)],
                  selectforeground=[('readonly', 'white'), ('!readonly', 'white')],
                  background=[('active', BG_INPUT)],
                  foreground=[('active', 'white'), ('disabled', '#5f6368')],
                  arrowcolor=[('active', 'white'), ('disabled', '#5f6368')])

        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BG_INPUT, borderwidth=0)
        
        # Treeview
        # Note: Treeview heading font must be set via configure
        style.configure("Treeview.Heading", background=BG_INPUT, foreground=FG_MAIN, relief="flat", font=self.font_bold)
        style.map("Treeview.Heading", background=[('active', '#3c4043')])
        style.configure("Treeview", background=BG_SEC, foreground=FG_MAIN, fieldbackground=BG_SEC, borderwidth=0, font=self.font_std)
        style.map("Treeview", background=[('selected', '#2a4a75')], foreground=[('selected', 'white')])
        
        # PanedWindow (TTK)
        style.configure("TPanedwindow", background=BG_MAIN)
        style.configure("Sash", background=BORDER, handlepad=5, handlesize=5) 
        
        # Apply Logic
        self.apply_scaling()

    def apply_scaling(self):
        s = self.scale_factor
        base = self.base_font_size
        
        # Update Named Fonts -> Auto updates TTK widgets
        self.font_std.configure(size=int(base * s))
        self.font_bold.configure(size=int(base * s))
        # Keep font_mono object for reference, though we override Text widgets with tuple for fallback
        self.font_mono.configure(size=int((base-2) * s))

        self.font_h1.configure(size=int((base*1.6) * s))
        
        # Calculate Row Height
        rh = self.font_std.metrics("linespace") + 6
        ttk.Style().configure("Treeview", rowheight=rh)
        
        # Standard TK Options
        self.root.option_add("*Font", self.font_std)
        
        # Recursive fix for TK Text widgets
        self.update_tk_widgets(self.root)
        
        self.config.set("ui_scale", self.scale_factor)
        
    def update_tk_widgets(self, widget):
        if isinstance(widget, tk.Text):
            # Use tuple ("Consolas", size) to ensure correct fallback to thin fonts on Windows
            # NamedFont objects sometimes trigger bold/thick fallbacks for CJK
            s = int((self.base_font_size-2) * self.scale_factor)
            widget.configure(font=("Consolas", s))
        elif isinstance(widget, tk.Label): # Fallback for old tk.Labels
            # If it looks like a header (manual check), use H1? Hard to detect.
            # Best to use ttk.Label in app code. 
            pass
            
        for child in widget.winfo_children():
            self.update_tk_widgets(child)

    def increase_scale(self, event=None):
        self.scale_factor += 0.1
        self.apply_scaling()

    def decrease_scale(self, event=None):
        if self.scale_factor > 0.5:
            self.scale_factor -= 0.1
            self.apply_scaling()

    def reset_scale(self, event=None):
        self.scale_factor = 1.0
        self.apply_scaling()

    def create_paned_ui(self, parent, list_weight=3, log_weight=1):
        """
        Creates a standard vertically PanedWindow with two frames (List and Log).
        Returns: (paned_window, list_frame, log_frame)
        """
        paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        paned.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Pane 1: List Area
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=list_weight)
        
        # Pane 2: Log/Status Area
        log_frame = ttk.Frame(paned)
        paned.add(log_frame, weight=log_weight)
        
        # Restore Sash Position if saved
        sash = self.config.get('sash_pos')
        if sash:
            # Small delay to allow geometry to settle
            self.root.after(100, lambda: paned.sash_place(0, 0, sash))
            
        # Bind close event to save sash (We piggyback or need a way to register hook?)
        # Since UniversalApp.on_close saves config, we can just hook the variable.
        # But we need to know *which* paned to save. 
        # A simple hack: store reference to this paned in self for on_close to check.
        self.main_paned = paned
        
        return paned, list_frame, log_frame
        
    def create_console_log(self, parent, height=5):
        """
        Creates a standard 'Console-like' Text widget with Scrollbar.
        Returns: The Text widget.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        
        # Scrollbar
        sb = ttk.Scrollbar(frame, orient="vertical")
        sb.pack(side="right", fill="y")
        
        # Text Widget
        # matrix-style: black bg, green text
        # Use tuple to ensure Windows Font Linking works (fallback to JhengHei for CJK)
        # instead of the Font object which might force strict fallback to garbage fonts
        s = int((self.base_font_size-2) * self.scale_factor)
        txt = tk.Text(frame, height=height, bg="black", fg="#00ff00", 
                      insertbackground="white", bd=0, 
                      font=("Consolas", s),
                      yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        
        sb.config(command=txt.yview)
        
        return txt

    # IMPORTANT: Need to update on_close to save sash if main_paned exists
    def on_close(self):
        is_zoomed = (self.root.state() == 'zoomed')
        self.config.set("maximized", is_zoomed)
        
        if not is_zoomed:
            self.config.set("geometry", self.root.geometry())
            
        # Save Sash if exists
        try:
            if hasattr(self, 'main_paned'):
                self.config.set('sash_pos', self.main_paned.sash_coord(0)[1])
        except: pass
            
        self.config.save()
        self.root.destroy()

    def show_toast(self, message, level="info", duration=3000):
        """Shows a modern non-blocking notification."""
        UniversalToast(self.root, message, level, duration)


def get_ffmpeg_exe():
    cwd_path = Path.cwd() / "ffmpeg.exe"
    if cwd_path.exists(): return str(cwd_path)
    path_exe = shutil.which("ffmpeg")
    if path_exe: return path_exe
    return None

def get_ffprobe_exe():
    cwd_path = Path.cwd() / "ffprobe.exe"
    if cwd_path.exists(): return str(cwd_path)
    ff = get_ffmpeg_exe()
    if ff and "ffmpeg" in str(ff).lower():
        probe = str(ff).replace("ffmpeg", "ffprobe")
        if os.path.exists(probe): return probe
    return shutil.which("ffprobe")

class DraggableTreeHelper:
    """
    Helper to enable 'Lego-like' visual drag-and-drop reordering/merging for ttk.Treeview.
    """
    def __init__(self, tree, on_drop_callback=None):
        self.tree = tree
        self.root = tree.winfo_toplevel()
        self.on_drop_callback = on_drop_callback
        
        # State
        self._drag_data = {"items": [], "y": 0, "ghost": None, "last_target_id": None, "auto_scroll_id": None}
        
        # Configure drop_target style tag based on current theme
        try:
            self.tree.tag_configure("drop_target", background="#007acc", foreground="white")
        except:
            pass
            
        # Bindings
        self.tree.bind("<ButtonPress-1>", self.on_drag_start, add='+')
        self.tree.bind("<B1-Motion>", self.on_drag_motion, add='+')
        self.tree.bind("<ButtonRelease-1>", self.on_drag_release, add='+')

    def on_drag_start(self, event):
        # Only record coordinate, let Tkinter handle default selection first
        item = self.tree.identify_row(event.y)
        if item:
            self._drag_data["start_item"] = item
            self._drag_data["start_y"] = event.y
            self._drag_data["start_x"] = event.x
            self._drag_data["active"] = False
            self._drag_data["last_target_id"] = None
            
            # Check modifiers
            is_ctrl = (event.state & 0x0004) != 0
            is_shift = (event.state & 0x0001) != 0
            
            if item in self.tree.selection() and not is_ctrl and not is_shift:
                # If clicking on an already selected item, save the full selection and prevent default click
                self._drag_data["items"] = list(self.tree.selection())
                return "break"
            else:
                self._drag_data["items"] = []

    def on_drag_motion(self, event):
        start_item = self._drag_data.get("start_item")
        if not start_item: return
        
        # Check if dragging threshold is met
        if not self._drag_data.get("active"):
            dx = abs(event.x - self._drag_data["start_x"])
            dy = abs(event.y - self._drag_data["start_y"])
            if dx > 5 or dy > 5:
                self._drag_data["active"] = True
                
                # Get current selection
                if not self._drag_data.get("items"):
                    selected = list(self.tree.selection())
                    if start_item not in selected:
                        self.tree.selection_set(start_item)
                        selected = [start_item]
                    self._drag_data["items"] = selected
                else:
                    selected = self._drag_data["items"]
                
                # Create ghost
                count = len(selected)
                if count == 1:
                    vals = self.tree.item(start_item, "values")
                    txt = " | ".join(str(v) for v in vals if v)
                    if len(txt) > 50: txt = txt[:47] + "..."
                else:
                    txt = f"📦 已選取 {count} 個項目"
                
                ghost = tk.Toplevel(self.root)
                ghost.overrideredirect(True)
                ghost.attributes("-alpha", 0.7)
                ghost.attributes("-topmost", True)
                
                bg = "#4a90e2"
                fg = "white"
                
                lbl = tk.Label(ghost, text=txt, bg=bg, fg=fg, padx=10, pady=5, relief="solid", borderwidth=1)
                lbl.pack()
                
                self._drag_data["ghost"] = ghost
                self.tree.configure(cursor="hand2")

        if self._drag_data.get("active"):
            # Move Ghost
            ghost = self._drag_data["ghost"]
            if ghost:
                ghost.geometry(f"+{event.x_root + 15}+{event.y_root + 10}")
                
            target_id = self.tree.identify_row(event.y)
            
            # Clear old drop target tags
            for item in self.tree.get_children():
                tags = list(self.tree.item(item, "tags") or [])
                if "drop_target" in tags:
                    tags.remove("drop_target")
                    self.tree.item(item, tags=tags)
                    
            if target_id and target_id not in self._drag_data["items"]:
                self._drag_data["last_target_id"] = target_id
                tags = list(self.tree.item(target_id, "tags") or [])
                if "drop_target" not in tags:
                    tags.append("drop_target")
                    self.tree.item(target_id, tags=tags)

            # Auto-scroll logic
            self._drag_data["last_y"] = event.y
            tree_h = self.tree.winfo_height()
            margin = 30
            if event.y < margin:
                self._start_auto_scroll(-1)
            elif event.y > tree_h - margin:
                self._start_auto_scroll(1)
            else:
                self._stop_auto_scroll()

    def on_drag_release(self, event):
        # Clear drop target tags
        for item in self.tree.get_children():
            tags = list(self.tree.item(item, "tags") or [])
            if "drop_target" in tags:
                tags.remove("drop_target")
                self.tree.item(item, tags=tags)

        if self._drag_data.get("ghost"):
            self._drag_data["ghost"].destroy()
            self._drag_data["ghost"] = None
        self.tree.configure(cursor="")
        
        self._stop_auto_scroll()
        
        if not self._drag_data.get("active"):
            start_item = self._drag_data.get("start_item")
            if start_item and self._drag_data.get("items"):
                self.tree.selection_set(start_item)
            self._drag_data = {"items": [], "y": 0, "ghost": None, "last_target_id": None, "auto_scroll_id": None}
            return
            
        source_ids = self._drag_data["items"]
        target_id = self._drag_data.get("last_target_id")
        
        self._drag_data = {"items": [], "y": 0, "ghost": None, "last_target_id": None, "auto_scroll_id": None}
        
        if target_id and target_id not in source_ids:
            if self.on_drop_callback:
                self.on_drop_callback(source_ids, target_id)

    def _start_auto_scroll(self, direction):
        if self._drag_data.get("auto_scroll_dir") == direction:
            return
        self._drag_data["auto_scroll_dir"] = direction
        self._auto_scroll_loop()

    def _stop_auto_scroll(self):
        self._drag_data["auto_scroll_dir"] = 0
        if self._drag_data.get("auto_scroll_id"):
            self.root.after_cancel(self._drag_data["auto_scroll_id"])
            self._drag_data["auto_scroll_id"] = None

    def _auto_scroll_loop(self):
        direction = self._drag_data.get("auto_scroll_dir", 0)
        if direction == 0:
            return
        
        self.tree.yview_scroll(direction, "units")
        
        # Update target_id since items have moved
        last_y = self._drag_data.get("last_y")
        if last_y is not None:
            target_id = self.tree.identify_row(last_y)
            for item in self.tree.get_children():
                tags = list(self.tree.item(item, "tags") or [])
                if "drop_target" in tags:
                    tags.remove("drop_target")
                    self.tree.item(item, tags=tags)
                    
            if target_id and target_id not in self._drag_data.get("items", []):
                self._drag_data["last_target_id"] = target_id
                tags = list(self.tree.item(target_id, "tags") or [])
                if "drop_target" not in tags:
                    tags.append("drop_target")
                    self.tree.item(target_id, tags=tags)
                    
        self._drag_data["auto_scroll_id"] = self.root.after(50, self._auto_scroll_loop)

class UndoManager:
    """
    Generic Undo/Redo Manager.
    Maintains a history stack of states.
    """
    def __init__(self, callback_restore, limit=32):
        self.callback_restore = callback_restore
        self.limit = limit
        self.history = []
        self.redo_stack = []
        
    def snapshot(self, state):
        # Deep copy the state to ensure isolation
        try:
            # Using deepcopy is safer involves mutable objects (lists/dicts)
            frozen = copy.deepcopy(state)
            self.history.append(frozen)
            
            # Enforce Limit
            if len(self.history) > self.limit:
                self.history.pop(0)
                
            # Clear redo stack on new branch
            self.redo_stack.clear()
        except Exception as e:
            print(f"UndoManager Snapshot Error: {e}")

    def undo(self, event=None):
        if len(self.history) < 2:
            return # Nothing to undo (need at least current state + 1 prev)
            
        # 1. Pop current state and push to redo
        current = self.history.pop()
        self.redo_stack.append(current)
        
        # 2. Peek previous state (now last in history)
        prev = self.history[-1]
        
        # 3. Restore
        # Note: pass a COPY to the app, so if app mutates it, it doesn't corrupt history record
        self.callback_restore(copy.deepcopy(prev))

    def redo(self, event=None):
        if not self.redo_stack:
            return
            
        # 1. Pop from redo
        next_state = self.redo_stack.pop()
        
        # 2. Push back to history
        self.history.append(next_state)
        
        # 3. Restore
        self.callback_restore(copy.deepcopy(next_state))


class UniversalSettingsDialog:
    """
    Auto-generated Settings Dialog based on AppConfig data.
    """
    def __init__(self, parent, config, on_save_callback=None):
        self.config = config
        self.on_save_callback = on_save_callback
        
        self.win = tk.Toplevel(parent)
        self.win.title("Configuration")
        
        # Restore Geometry if exists
        geo = self.config.get("_settings_geometry")
        if geo:
            try: self.win.geometry(geo)
            except: self.win.geometry("400x500")
        else:
            self.win.geometry("400x500")
            
        self.win.transient(parent)
        self.win.grab_set()
        
        # Style: Match Parent Theme
        bg_color = parent.cget("bg")
        self.win.configure(bg=bg_color)
        
        # Infer Dark Mode from BG color (approximate)
        # Default Windows Light is #f0f0f0 or SystemButtonFace
        is_dark = True
        try:
            # If strictly native light, bg might be named color or #f0f0f0
            if bg_color.lower() in ("#f0f0f0", "systembuttonface", "white"):
                is_dark = False
        except: pass
        
        # Apply Title Bar
        self.win.after(10, lambda: apply_title_bar_theme(self.win, is_dark))
        
        # Bind Close
        self.win.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Buttons (Pack FIRST to ensure they stay at bottom)
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(side="bottom", fill="x", pady=10)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.on_close).pack(side="right")
        
        # Scrollable Canvas
        # Match canvas bg to theme, remove highlight border
        self.canvas = tk.Canvas(self.win, bg=bg_color, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.win, orient="vertical", command=self.canvas.yview)
        
        # Frame inside canvas
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Handle Canvas Resize to resize the inner frame
        self.canvas.bind("<Configure>", self.on_canvas_configure)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self.vars = {}
        self.build_ui()

    def on_canvas_configure(self, event):
        # Force inner frame to match canvas width
        self.canvas.itemconfig(self.canvas_window, width=event.width)


    def build_ui(self):
        # Filter keys: ignore _*, ignore signature
        keys = sorted([k for k in self.config.data.keys() if not k.startswith("_") and k != "config_signature"])
        
        r = 0
        for k in keys:
            val = self.config.data[k]
            v_type = type(val)
            
            lbl = ttk.Label(self.scrollable_frame, text=k + ":")
            lbl.grid(row=r, column=0, sticky="w", padx=10, pady=5)
            
            if v_type == bool:
                var = tk.BooleanVar(value=val)
                ent = ttk.Checkbutton(self.scrollable_frame, variable=var)
                ent.grid(row=r, column=1, sticky="w", padx=10, pady=5)
                self.vars[k] = (var, bool)
            else:
                var = tk.StringVar(value=str(val))
                ent = ttk.Entry(self.scrollable_frame, textvariable=var, width=30)
                ent.grid(row=r, column=1, sticky="w", padx=10, pady=5)
                # Helper for int/float detection
                target_type = int if v_type == int else (float if v_type == float else str)
                self.vars[k] = (var, target_type)
            
            r += 1

    def save_geometry(self):
        self.config.data["_settings_geometry"] = self.win.geometry()

    def on_close(self):
        self.save_geometry()
        # Save config silently to persist geometry even if values weren't saved?
        # Typically yes, window position preference is separate from apply.
        self.config.save() 
        self.win.destroy()

    def save(self):
        self.save_geometry()
        
        for k, (var, t_type) in self.vars.items():
            val = var.get()
            try:
                if t_type == bool:
                    self.config.data[k] = bool(val)
                elif t_type == int:
                    self.config.data[k] = int(val)
                elif t_type == float:
                    self.config.data[k] = float(val)
                else:
                    self.config.data[k] = str(val)
            except:
                # Type conversion failed, keep old or set as str? 
                # Better safe than sorry, ignore error or warn.
                print(f"Failed to convert {k} to {t_type}")
                pass


class ResponsiveFrame(ttk.Frame):
    """
    A Frame that automatically switches its layout from horizontal (row) to vertical (stack)
    when its width falls below a certain threshold.
    """
    def __init__(self, parent, threshold=400, padding=5, **kwargs):
        super().__init__(parent, **kwargs)
        self.threshold = threshold
        self.padding = padding
        self._is_stacked = False
        self._widgets = []
        
        self.bind("<Configure>", self._on_resize)

    def add_widget(self, widget_class, **kwargs):
        """Creates and adds a widget to this frame."""
        w = widget_class(self, **kwargs)
        self._widgets.append(w)
        self._re_layout()
        return w

    def add_existing(self, widget):
        """Adds an existing widget to managed list."""
        widget.master = self # Warning: master change in TK is tricky
        self._widgets.append(widget)
        self._re_layout()

    def _on_resize(self, event):
        should_stack = event.width < self.threshold
        if should_stack != self._is_stacked:
            self._is_stacked = should_stack
            self._re_layout()

    def _re_layout(self):
        for w in self._widgets:
            w.pack_forget()
        
        for w in self._widgets:
            if self._is_stacked:
                w.pack(side="top", fill="x", padx=self.padding, pady=self.padding)
            else:
                w.pack(side="left", fill="both", expand=True, padx=self.padding, pady=self.padding)


class UniversalToast(tk.Toplevel):
    """
    A non-blocking 'Toast' notification window.
    """
    def __init__(self, parent, message, level="info", duration=3000):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0) # Start invisible for fade-in
        
        # Colors based on level
        colors = {
            "info": ("#007acc", "white"),
            "success": ("#28a745", "white"),
            "warning": ("#ffc107", "black"),
            "error": ("#dc3545", "white")
        }
        bg, fg = colors.get(level, colors["info"])
        
        self.configure(bg=bg)
        
        # Icon (Simulated with emoji for now)
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
        icon = icons.get(level, "🔔")
        
        lbl = tk.Label(self, text=f"{icon} {message}", bg=bg, fg=fg, 
                       padx=20, pady=10, font=("Microsoft JhengHei UI", 10, "bold"))
        lbl.pack()
        
        self.update_idletasks()
        
        # Position: Bottom Right of parent or screen
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            
            x = px + pw - self.winfo_width() - 20
            y = py + ph - self.winfo_height() - 20
        except:
            # Fallback to screen bottom right
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = sw - self.winfo_width() - 20
            y = sh - self.winfo_height() - 60
            
        self.geometry(f"+{x}+{y}")
        
        # Fade In
        self._fade_in()
        
        # Auto Close
        self.after(duration, self._fade_out)

    def _fade_in(self):
        alpha = self.attributes("-alpha")
        if alpha < 0.95:
            self.attributes("-alpha", alpha + 0.1)
            self.after(20, self._fade_in)

    def _fade_out(self):
        alpha = self.attributes("-alpha")
        if alpha > 0.05:
            self.attributes("-alpha", alpha - 0.1)
            self.after(20, self._fade_out)
        else:
            self.destroy()
                
class UniversalTreeview(ttk.Treeview):
    """
    A pre-configured Treeview with:
    - Auto-sorting columns
    - Drag & Drop reordering (optional)
    - Alternating row colors
    """
    def __init__(self, parent, columns, draggable=True, **kwargs):
        super().__init__(parent, columns=columns, show="headings", **kwargs)
        
        self.columns = columns
        self.draggable = draggable
        
        # Setup Columns
        for col in columns:
            self.heading(col, text=col, command=lambda c=col: self.sort_by(c, False))
            self.column(col, width=100) # Default width, can be overridden
            
        # Alternating Colors (Try to get from style or hardcode decent dark defaults)
        self.tag_configure('odd', background='#252526')
        self.tag_configure('even', background='#1e1e1e')

        # Drag & Drop
        if self.draggable:
            self.drag_helper = DraggableTreeHelper(self, self.on_drag_drop_complete)

        
    def sort_by(self, col, descending):
        """Sort tree contents when a column header is clicked."""
        data = [(self.set(child, col), child) for child in self.get_children('')]
        
        # Detect if numeric (simple check)
        try:
            # Try converting first item to size string or float? 
            # This is a bit risky if mixed. Let's try to parse "KB/MB" or dates?
            # For now, simplistic string sort is safer unless we separate value from display.
            # But let's try a heuristic for "Size" column or just string.
            if col == "Size":
                 # Helper to parse size string "1.2 MB", "500 KB"
                 def parse_size(s):
                     s = s.upper()
                     if "MB" in s: return float(s.replace("MB", "").strip()) * 1024 * 1024
                     if "KB" in s: return float(s.replace("KB", "").strip()) * 1024
                     if "BYTES" in s: return float(s.replace("BYTES", "").strip())
                     return 0
                 data.sort(key=lambda t: parse_size(t[0]), reverse=descending)
            else:
                 data.sort(key=lambda t: t[0].lower(), reverse=descending)
        except:
            data.sort(key=lambda t: t[0].lower(), reverse=descending)
            
        for index, (val, child) in enumerate(data):
            self.move(child, '', index)
            
        # Switch sort direction
        self.heading(col, command=lambda: self.sort_by(col, not descending))
        
        self.refresh_stripes()

    def on_drag_drop_complete(self, source_ids, target_id):
        """Called by DraggableTreeHelper when a drop happens."""
        # Default behavior: Move source to index of target
        if not source_ids or target_id in source_ids: return
        
        try:
            # We want to drop insert "before" the target usually
            target_index = self.index(target_id)
            for i, sid in enumerate(source_ids):
                self.move(sid, '', target_index + i)
            self.refresh_stripes()
        except: pass
        
    def refresh_stripes(self):
        for i, item in enumerate(self.get_children()):
            tag = 'even' if i % 2 == 0 else 'odd'
            # Preserve existing tags? Treeview mostly allows list of tags.
            # We overwrite for now, assuming only striping is used. 
            # Or append? 'odd'/'even' usually sufficient.
            self.item(item, tags=(tag,))

    def get_all_items(self):
        """Returns list of children IIDs."""
        return self.get_children()
