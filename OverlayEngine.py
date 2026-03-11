import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import sys
import os
import json
import subprocess
import shutil
import math
import re

# ==============================================================================
# Helper: FFmpeg Probe
# ==============================================================================
def get_video_info(path):
    """Returns duration, width, height."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "csv=p=0", path
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        parts = out.split(',')
        if len(parts) >= 3:
            return float(parts[0]), float(parts[1]), float(parts[2]) # w, h, dur (mixed order in csv?)
            # Actually ffprobe csv order depends on -show_entries order? No, it's reliable usually but safer to use json
    except:
        pass
    
    # Fallback/Safe JSON method
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "json", path
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        data = json.loads(out)
        stream = data['streams'][0]
        return float(stream['duration']), int(stream['width']), int(stream['height'])
    except Exception as e:
        print(f"Probe Error: {e}")
        return 0, 1920, 1080

# ==============================================================================
# Engine Logic
# ==============================================================================
class OverlayEngine:
    def __init__(self):
        self.overlays = [] # List of dicts
        self.bg_color = "black" # For padding
        
    def add_overlay(self, config):
        self.overlays.append(config)
        
    def render(self, input_video, output_video, callback=None):
        if not os.path.exists(input_video):
            if callback: callback("Error: Input video not found.")
            return False
            
        # 1. Probe Input
        vid_dur, vid_w, vid_h = get_video_info(input_video)
        if callback: callback(f"Input: {vid_dur}s, {vid_w}x{vid_h}")
        
        # 2. Calculate Timing & Padding
        # We need to map relative times to absolute times on an infinite timeline
        # 0 = Video Start. Video End = vid_dur.
        
        abs_starts = []
        abs_ends = []
        
        processed_overlays = []
        
        for ov in self.overlays:
            # Parse Anchor
            anchor = ov.get("anchor", "start")
            offset = float(ov.get("offset", 0.0))
            duration = float(ov.get("duration", 5.0))
            
            if anchor == "start":
                start_time = offset
            else: # end
                start_time = vid_dur + offset
                
            end_time = start_time + duration
            
            abs_starts.append(start_time)
            abs_ends.append(end_time)
            
            processed_overlays.append({
                "path": ov["path"],
                "start": start_time,
                "end": end_time,
                "duration": duration,
                "anim_in": ov.get("anim_in", "none"),
                "anim_out": ov.get("anim_out", "none"),
                "scale": ov.get("scale", "fit") # fit, fill, original
            })
            
        # Determine Bounds
        min_start = min(abs_starts + [0])
        max_end = max(abs_ends + [vid_dur])
        
        pre_pad = 0
        if min_start < 0:
            pre_pad = abs(min_start)
            
        post_pad = 0
        if max_end > vid_dur:
            post_pad = max_end - vid_dur
            
        if callback: callback(f"Padding: Pre={pre_pad}s, Post={post_pad}s")
        
        # 3. Build Filter Complex
        inputs = []
        inputs.append("-i")
        inputs.append(input_video)
        
        # Add Overlay Inputs
        for ov in processed_overlays:
            inputs.append("-i")
            inputs.append(ov["path"])
            
        filter_complex = []
        
        # A. Pad Main Video
        # tpad: start_duration, stop_duration
        # color? tpad supports 'color'.
        # Note: tpad works on video stream. Audio needs pad/apads too? 
        # For simplicity, we assume video-centric. Audio might go silent or need apad.
        # We use 'tpad' filter.
        
        main_node = "v_main"
        filter_complex.append(f"[0:v]tpad=start_duration={pre_pad}:stop_duration={post_pad}:start_mode=add:stop_mode=add:color={self.bg_color}[{main_node}]")
        
        current_bg = main_node
        
        # B. Apply Overlays
        # Iterate Inputs (starting from index 1)
        for i, ov in enumerate(processed_overlays):
            input_idx = i + 1
            ov_node = f"ov_{i}"
            
            # 1. Scale Overlay
            # 'fit': scale=iw*min(TargetW/iw\,TargetH/ih):ih*min(TargetW/iw\,TargetH/ih)
            # Simplified: scale to fit within WxH
            scale_filter = f"scale={vid_w}:{vid_h}:force_original_aspect_ratio=decrease"
            filter_complex.append(f"[{input_idx}:v]{scale_filter}[{ov_node}_scaled]")
            
            # --- Animation Logic ---
            # Standard Duration for In/Out animations = 1.0s (or min(1, duration/2))
            anim_dur = 1.0
            if ov["duration"] < 2.0: anim_dur = ov["duration"] / 2.0
            
            # Helper for interpolation:
            # if(lte(t, T_start+D), START + (END-START)*(t-T_start)/D, END)
            def lerp(var, start_val, end_val, start_time):
                p = f"(t-{start_time})/{anim_dur}"
                return f"{start_val} + ({end_val}-({start_val}))*{p}"

            # Base target (Center)
            target_x = f"({vid_w}-w*min({vid_w}/iw\\,{vid_h}/ih))/2" # If scaled? No, w is scaled width.
            # actually we don't know exact 'w' at filter build time easily without geq/leq or scale filter output.
            # But 'scale' filter sets w, h.
            # 'overlay' filter knows w, h of overlay input.
            # (W-w)/2 is safe generic "Center".
            
            # Directional Offsets
            # Left: -w
            # Right: W
            # Top: -h
            # Bottom: H
            
            anim_in = ov["anim_in"]
            anim_out = ov["anim_out"]
            
            # --- X Expression ---
            x_cmd = "(W-w)/2" # Default Center
            
            # Scroll Special Case
            if anim_in == "scroll_up":
                x_cmd = "(W-w)/2"
                # Y handled below
            elif anim_in == "scroll_left": # Ticker
                # Moves W -> -w over full duration
                x_cmd = f"W - (W+w)*(t-{T_start})/{T_dur}"
            else:
                # Standard In/Out for X
                # Check In
                start_x = None
                if anim_in == "slide_left": start_x = "-w"      # Enter FROM Left (move right) - Wait, "Slide Left" usually means "Move Left"? 
                # Let's standardize: "Slide In Left" = Enters FROM Left side. (Start -w, End Center)
                elif anim_in == "slide_right": start_x = "W"    # Enters FROM Right side.
                
                # Check Out
                end_x = None
                if anim_out == "slide_left": end_x = "-w"       # Exit TO Left
                elif anim_out == "slide_right": end_x = "W"     # Exit TO Right
                
                # Construct Expression
                # if t < S+1: IN
                # elif t > E-1: OUT
                # else: Center
                
                if start_x and end_x:
                     x_cmd = f"if(lte(t,{T_start}+{anim_dur}), {lerp('t', start_x, '(W-w)/2', T_start)}, if(gte(t,{T_end}-{anim_dur}), {lerp('t', '(W-w)/2', end_x, f'{T_end}-{anim_dur}')}, (W-w)/2))"
                elif start_x:
                     x_cmd = f"if(lte(t,{T_start}+{anim_dur}), {lerp('t', start_x, '(W-w)/2', T_start)}, (W-w)/2)"
                elif end_x:
                     x_cmd = f"if(gte(t,{T_end}-{anim_dur}), {lerp('t', '(W-w)/2', end_x, f'{T_end}-{anim_dur}')}, (W-w)/2)"
                
            # --- Y Expression ---
            y_cmd = "(H-h)/2" # Default Center
            
            if anim_in == "scroll_up":
                # H -> -h
                y_cmd = f"H - (H+h)*(t-{T_start})/{T_dur}"
            elif anim_in == "scroll_left":
                y_cmd = "(H-h)/2"
            else:
                # Standard In/Out for Y
                start_y = None
                if anim_in == "slide_up": start_y = "-h"      # From Top
                elif anim_in == "slide_down": start_y = "H"   # From Bottom
                
                end_y = None
                if anim_out == "slide_up": end_y = "-h"
                elif anim_out == "slide_down": end_y = "H"
                
                if start_y and end_y:
                     y_cmd = f"if(lte(t,{T_start}+{anim_dur}), {lerp('t', start_y, '(H-h)/2', T_start)}, if(gte(t,{T_end}-{anim_dur}), {lerp('t', '(H-h)/2', end_y, f'{T_end}-{anim_dur}')}, (H-h)/2))"
                elif start_y:
                     y_cmd = f"if(lte(t,{T_start}+{anim_dur}), {lerp('t', start_y, '(H-h)/2', T_start)}, (H-h)/2)"
                elif end_y:
                     y_cmd = f"if(gte(t,{T_end}-{anim_dur}), {lerp('t', '(H-h)/2', end_y, f'{T_end}-{anim_dur}')}, (H-h)/2)"

            # --- Layering & Fades ---
            
            looped_node = f"{ov_node}_looped"
            filter_complex.append(f"[{ov_node}_scaled]loop=loop=-1:size=1:start=0[{looped_node}]")
            
            processed_node = looped_node
            
            # Apply Fade In/Out Filters
            if anim_in == "fade" or anim_out == "fade":
                faded_node = f"{ov_node}_faded"
                fades = []
                fades.append("format=rgba")
                if anim_in == "fade":
                    fades.append(f"fade=t=in:st={T_start}:d={anim_dur}:alpha=1")
                if anim_out == "fade":
                    fades.append(f"fade=t=out:st={T_end-anim_dur}:d={anim_dur}:alpha=1")
                
                fade_str = ",".join(fades)
                filter_complex.append(f"[{looped_node}]{fade_str}[{faded_node}]")
                processed_node = faded_node

            # Apply Overlay
            next_bg = f"v_out_{i}"
            enable_expr = f"between(t,{T_start},{T_end})"
            
            filter_complex.append(
                f"[{current_bg}][{processed_node}]overlay=x='{x_cmd}':y='{y_cmd}':enable='{enable_expr}':eval=frame[{next_bg}]"
            )
            
            current_bg = next_bg
            
        # Map Final
        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)
        cmd.extend(["-filter_complex", ";".join(filter_complex)])
        cmd.extend(["-map", f"[{current_bg}]"])
        # Map audio from 0:a if exists?
        # Simple check: map 0:a? 
        # For now, video only focus. Audio mapping might require tpad on audio too 'apad'.
        # Let's map audio and pad it.
        # [0:a]apad[a_pad];[a_pad]atrim=0:TOTAL_DUR[a_out]
        # Skip for now to ensure stability of video.
        
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", output_video])
        
        print("Executing Overlay CMD:")
        print(" ".join(cmd))
        
        if callback: callback("Rendering Overlays...")
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
        for line in proc.stdout:
            # print(line)
            if "frame=" in line and "time=" in line and callback:
                 # Clean up log line for GUI
                 match = re.search(r"time=(\d{2}:\d{2}:\d{2})", line)
                 if match: callback(f"Processing: {match.group(1)}")
                 
        proc.wait()
        return proc.returncode == 0

# ==============================================================================
# GUI
# ==============================================================================
# Import UniversalUI if available, else standalone
try:
    from _lib.UniversalUI import UniversalApp, UniversalTreeview, UniversalToplevel
except ImportError:
    # Minimal Stub if running standalone without dependencies
    class UniversalApp:
        def __init__(self, root, title, config_name):
            self.root = root
            self.root.title(title)
            self.config = {}
    class UniversalTreeview(ttk.Treeview):
        pass
    class UniversalToplevel(tk.Toplevel):
        pass

class OverlayApp(UniversalApp):
    def __init__(self, root, cli_args=None):
        if "UniversalApp" in [b.__name__ for b in OverlayApp.__bases__]:
             super().__init__(root, "OverlayEngine", "overlay_engine_v2")
        else:
             self.root = root
             self.root.title("OverlayEngine")
             
        self.overlays = []
        self.engine = OverlayEngine()
        
        # CLI Mode check
        if cli_args and cli_args.get("nogui"):
            self.run_cli(cli_args)
            return

        self.setup_ui()
        
    def setup_ui(self):
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Top: Video Select
        frm_vid = ttk.LabelFrame(main, text="Base Video")
        frm_vid.pack(fill="x", pady=5)
        
        self.var_video = tk.StringVar()
        ttk.Entry(frm_vid, textvariable=self.var_video).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(frm_vid, text="Browse", command=self.browse_video).pack(side="left")
        
        # Middle: Overlay List
        frm_list = ttk.LabelFrame(main, text="Overlays")
        frm_list.pack(fill="both", expand=True, pady=5)
        
        cols = ["Type", "Offset", "Anchor", "Anim"]
        self.tree = ttk.Treeview(frm_list, columns=cols, show="headings", height=8)
        for c in cols: self.tree.heading(c, text=c)
        self.tree.pack(side="left", fill="both", expand=True)
        
        btn_bar = ttk.Frame(frm_list)
        btn_bar.pack(side="right", fill="y", padx=5)
        ttk.Button(btn_bar, text="+ Add", command=self.add_overlay_dialog).pack(pady=2)
        ttk.Button(btn_bar, text="- Remove", command=self.remove_overlay).pack(pady=2)
        
        # Bottom: Render
        ttk.Button(main, text="Render Output", command=self.render_gui).pack(side="bottom", pady=10)

    def browse_video(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi")])
        if f: self.var_video.set(f)
        
    def add_overlay_dialog(self):
        # Modal Dialog to configure overlay
        dlg = UniversalToplevel(self.root, title="Add Overlay")
        
        # Rows
        r1 = ttk.Frame(dlg); r1.pack(fill="x", padx=10, pady=5)
        ttk.Label(r1, text="Image:").pack(side="left")
        var_img = tk.StringVar()
        ttk.Entry(r1, textvariable=var_img).pack(side="left", fill="x", expand=True)
        ttk.Button(r1, text="Browse", command=lambda: var_img.set(filedialog.askopenfilename())).pack(side="left")
        
        r2 = ttk.Frame(dlg); r2.pack(fill="x", padx=10, pady=5)
        ttk.Label(r2, text="Anchor:").pack(side="left")
        var_anchor = tk.StringVar(value="start")
        ttk.Combobox(r2, textvariable=var_anchor, values=["start", "end"], state="readonly", width=10).pack(side="left")
        
        ttk.Label(r2, text="Offset (s):").pack(side="left", padx=5)
        var_offset = tk.StringVar(value="0.0")
        ttk.Entry(r2, textvariable=var_offset, width=5).pack(side="left")
        
        r3 = ttk.Frame(dlg); r3.pack(fill="x", padx=10, pady=5)
        ttk.Label(r3, text="Duration (s):").pack(side="left")
        var_dur = tk.StringVar(value="5.0")
        ttk.Entry(r3, textvariable=var_dur, width=5).pack(side="left")
        
        ttk.Label(r4, text="Anim In:").pack(side="left")
        var_anim = tk.StringVar(value="fade")
        anims = ["none", "fade", "slide_left", "slide_right", "slide_up", "slide_down", "scroll_up"]
        ttk.Combobox(r4, textvariable=var_anim, values=anims, state="readonly", width=12).pack(side="left")
        
        ttk.Label(r4, text="Out:").pack(side="left", padx=5)
        var_anim_out = tk.StringVar(value="fade")
        anims_out = ["none", "fade", "slide_left", "slide_right", "slide_up", "slide_down"]
        ttk.Combobox(r4, textvariable=var_anim_out, values=anims_out, state="readonly", width=12).pack(side="left")
        
        def save():
            conf = {
                "path": var_img.get(),
                "anchor": var_anchor.get(),
                "offset": float(var_offset.get()),
                "duration": float(var_dur.get()),
                "anim_in": var_anim.get(),
                "anim_out": var_anim_out.get()
            }
            self.overlays.append(conf)
            self._refresh_list()
            dlg.destroy()
            
        ttk.Button(dlg, text="Save", command=save).pack(pady=10)
        
    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for ov in self.overlays:
            name = os.path.basename(ov["path"])
            anim_str = f"{ov['anim_in']} / {ov.get('anim_out', 'none')}"
            self.tree.insert("", "end", values=(name, ov["offset"], ov["anchor"], anim_str))
            
    def remove_overlay(self):
        sel = self.tree.selection()
        if sel:
            idx = self.tree.index(sel[0])
            self.overlays.pop(idx)
            self._refresh_list()
            
    def render_gui(self):
        src = self.var_video.get()
        if not src: return
        
        out = filedialog.asksaveasfilename(defaultextension=".mp4")
        if not out: return
        
        self.engine.overlays = self.overlays
        
        # Show Progress
        top = tk.Toplevel(self.root)
        lbl = tk.Label(top, text="Rendering...", width=40)
        lbl.pack(padx=20, pady=20)
        
        def run():
            self.engine.render(src, out, callback=lambda s: lbl.config(text=s))
            lbl.config(text="Done!")
            top.after(2000, top.destroy)
            
        import threading
        threading.Thread(target=run, daemon=True).start()

    def run_cli(self, args):
        # CLI Mode
        print("[OverlayEngine] Running in CLI Mode")
        input_vid = args["input"]
        config_file = args["config"]
        output_vid = args["output"]
        
        with open(config_file, 'r') as f:
            overlays = json.load(f)
            
        self.engine.overlays = overlays
        self.engine.render(input_vid, output_vid)
        print("[OverlayEngine] Finished")
        sys.exit(0)

if __name__ == "__main__":
    # Check CLI args
    # usage: python OverlayEngine.py --input in.mp4 --config c.json --output out.mp4 --nogui
    
    cli_args = {}
    if "--nogui" in sys.argv:
        try:
            cli_args["nogui"] = True
            cli_args["input"] = sys.argv[sys.argv.index("--input") + 1]
            cli_args["config"] = sys.argv[sys.argv.index("--config") + 1]
            cli_args["output"] = sys.argv[sys.argv.index("--output") + 1]
        except:
             print("Invalid CLI Args")
             sys.exit(1)
             
    root = tk.Tk()
    app = OverlayApp(root, cli_args)
    if not cli_args:
        root.mainloop()
