
# ==============================================================================
# FILM STITCH v1.6
# ==============================================================================
# Powered by UniversalUI
# ==============================================================================

import os
import sys
# Add parent directory to sys.path so we can import the shared _lib
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import threading
import queue
import json
from pathlib import Path
from datetime import datetime
from _lib.UniversalUI import UniversalApp, get_ffmpeg_exe, get_ffprobe_exe

class RedirectText(object):
    def __init__(self, queue, prefix=""):
        self.queue = queue
        self.prefix = prefix
    def write(self, string):
        if string.strip():
            self.queue.put(self.prefix + string.strip())
    def flush(self): pass

class FFmpegWorker:
    def __init__(self, log_queue):
        self.ffmpeg = get_ffmpeg_exe()
        self.ffprobe = get_ffprobe_exe()
        self.log_queue = log_queue
        
    def log(self, msg): self.log_queue.put(msg)

    def get_info(self, path):
        if not self.ffprobe: return None
        try:
            cmd = [self.ffprobe, "-v", "error", "-select_streams", "v:0", 
                   "-show_entries", "stream=width,height,nb_frames,avg_frame_rate", "-of", "json", path]
            si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            dat = json.loads(subprocess.check_output(cmd, startupinfo=si))
            s = dat['streams'][0]
            fps_str = s.get('avg_frame_rate', '30/1')
            n, d = map(int, fps_str.split('/'))
            fps = n/d if d else 30.0
            
            info = {'w': int(s.get('width',0)), 'h': int(s.get('height',0)), 'frames': int(s.get('nb_frames',0)), 'fps': fps}
            
            cmd_a = [self.ffprobe, "-v", "error", "-select_streams", "a:0", 
                   "-show_entries", "stream=codec_type", "-of", "json", path]
            dat_a = json.loads(subprocess.check_output(cmd_a, startupinfo=si))
            info['has_audio'] = len(dat_a.get('streams', [])) > 0
            
            return info
        except Exception as e:
            self.log(f"Probe Error on {Path(path).name}: {e}")
            return None

    def stitch(self, files, out, opts, progress):
        if not self.ffmpeg: raise Exception("FFmpeg missing")
        total = len(files)
        
        info0 = self.get_info(files[0])
        if not info0: raise Exception(f"Start file failed: {files[0]}")
        tw, th = info0['w'], info0['h']
        if tw%2!=0: tw-=1; 
        if th%2!=0: th-=1
        
        mode = opts['mode']
        trim = int(opts['trim'])
        xfade = opts['xfade']
        xfade_dur = float(opts['xfade_dur'])
        keep_audio = opts.get('keep_audio', False)
        
        filters = []
        inputs = []
        
        for i, f in enumerate(files):
            progress((i/total)*30, f"Preparing {i+1}...")
            inputs.extend(["-i", f])
            inf = self.get_info(f)
            if not inf: continue
            
            base = f"[{i}:v]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},setsar=1"
            trim_f = f",trim=start_frame=0:end_frame={max(1, inf['frames']-trim)},setpts=PTS-STARTPTS" if trim>0 else ",setpts=PTS-STARTPTS"
            
            lbl = f"c{i}"
            
            if keep_audio:
                atrim_sec = max(0.001, (inf['frames'] - trim) / inf['fps'])
                if inf.get('has_audio', False):
                    atrim_f = f"[{i}:a]atrim=start=0:end={atrim_sec:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]" if trim>0 else f"[{i}:a]asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]"
                else:
                    atrim_f = f"anullsrc=r=48000:cl=stereo,atrim=start=0:end={atrim_sec:.3f},asetpts=PTS-STARTPTS[a{i}]"
                
                if mode == 'boomerang':
                    v_part = f"{base}{trim_f},split[f{i}][r{i}];[r{i}]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[rr{i}]"
                    a_part = f"{atrim_f};[a{i}]asplit[af{i}][ar{i}];[ar{i}]areverse[arr{i}]"
                    filters.append(f"{v_part};{a_part};[f{i}][af{i}][rr{i}][arr{i}]concat=n=2:v=1:a=1[{lbl}][outa{i}]")
                else:
                    filters.append(f"{base}{trim_f}[{lbl}];{atrim_f}")
            else:
                if mode == 'boomerang':
                    filters.append(f"{base}{trim_f},split[f{i}][r{i}];[r{i}]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[rr{i}];[f{i}][rr{i}]concat=n=2:v=1:a=0[{lbl}]")
                else:
                    filters.append(f"{base}{trim_f}[{lbl}]")

        progress(40, "Calculating joins...")
        map_args = ["-map", "[outv]"]
        if xfade and total > 1:
            join = ""
            current_off = 0.0
            prev = "c0"
            for i in range(1, total):
                prev_f = files[i-1]
                p_inf = self.get_info(prev_f)
                if not p_inf: continue
                frames = p_inf['frames']
                if trim>0: frames=max(1, frames-trim)
                if mode=='boomerang': frames=frames*2-1
                
                dur = frames/p_inf['fps']
                current_off += (dur - xfade_dur)
                next_l = f"x{i}" if i < total-1 else "outv"
                join += f"[{prev}][c{i}]xfade=transition=fade:duration={xfade_dur}:offset={current_off:.3f}[{next_l}];"
                prev = next_l
                
            if keep_audio:
                ajoin = ""
                aprev = "outa0" if mode == 'boomerang' else "a0"
                for i in range(1, total):
                    anext_l = f"ax{i}" if i < total-1 else "outa"
                    next_src = f"outa{i}" if mode == 'boomerang' else f"a{i}"
                    ajoin += f"[{aprev}][{next_src}]acrossfade=d={xfade_dur}:c1=tri:c2=tri[{anext_l}];"
                    aprev = anext_l
                full = ";".join(filters) + ";" + join.strip(";") + ";" + ajoin.strip(";")
                map_args.extend(["-map", "[outa]"])
            else:
                full = ";".join(filters) + ";" + join.strip(";")
        else:
            if keep_audio:
                P = "".join([f"[c{i}][outa{i}]" if mode == 'boomerang' else f"[c{i}][a{i}]" for i in range(total)])
                full = ";".join(filters) + f";{P}concat=n={total}:v=1:a=1[outv][outa]"
                map_args.extend(["-map", "[outa]"])
            else:
                P = "".join([f"[c{i}]" for i in range(total)])
                full = ";".join(filters) + f";{P}concat=n={total}:v=1:a=0[outv]"
            
        progress(50, "Rendering...")
        cmd = [self.ffmpeg, "-y", *inputs, "-filter_complex", full, *map_args, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]
        if keep_audio: cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        cmd.append(out)
        
        si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run(cmd, check=True, startupinfo=si)
        progress(100, "Done!")

class FilmStitchApp(UniversalApp):
    def __init__(self, root):
        defs = {
            "geometry": "900x700",
            "trim_frames": 1, 
            "mode": "standard", 
            "crossfade": False, 
            "xfade_dur": 0.1, 
            "keep_audio": True,
            "last_dir": "", 
            "sort_col": "name", 
            "sort_desc": False
        }
        # Signature: Unique ID for this *type* of application, regardless of filename
        super().__init__(root, "Film Stitch v1.6", "film_stitch_v1", defs)
        
        self.files = []

        self.msg = queue.Queue()
        sys.stdout = RedirectText(self.msg)
        sys.stderr = RedirectText(self.msg, "[ERR] ")
        self.worker = FFmpegWorker(self.msg)
        self.last_sort = self.config.get('sort_col')
        self.sort_desc = self.config.get('sort_desc')
        
        self.setup_ui()
        self.root.after(100, self.poll_log)

    def setup_ui(self):
        p = 10
        bg = "#202124"
        
        # Header (Using TTK Label for auto-font update)
        ttk.Label(self.root, text="Film Stitch", style="Header.TLabel").pack(anchor="w", padx=p, pady=(p, 5))
        
        # Tools
        tb = tk.Frame(self.root, bg=bg)
        tb.pack(fill="x", padx=p, pady=5)
        ttk.Button(tb, text="+ Add Videos", command=self.add).pack(side="left")
        ttk.Button(tb, text="+ Add Folder", command=self.add_folder).pack(side="left", padx=5)
        self.include_sub = tk.BooleanVar(value=True)
        ttk.Checkbutton(tb, text="Include Subfolders", variable=self.include_sub).pack(side="left", padx=(0, 5))
        ttk.Button(tb, text="Clear List", command=self.clear).pack(side="left")
        
        # Config
        sf = ttk.LabelFrame(self.root, text="Configuration", padding=5)
        sf.pack(fill="x", padx=p, pady=5)
        
        self.mode = tk.StringVar(value=self.config.get('mode'))
        ttk.Label(sf, text="Mode:").pack(side="left")
        ttk.Combobox(sf, textvariable=self.mode, values=['standard', 'boomerang'], width=10, state="readonly").pack(side="left", padx=5)
        
        ttk.Label(sf, text="| Trim Frames:").pack(side="left", padx=5)
        self.trim = tk.IntVar(value=self.config.get('trim_frames'))
        ttk.Spinbox(sf, textvariable=self.trim, from_=0, to=10, width=3).pack(side="left")
        
        ttk.Label(sf, text="|").pack(side="left", padx=5)
        self.xfade = tk.BooleanVar(value=self.config.get('crossfade'))
        ttk.Checkbutton(sf, text="Crossfade", variable=self.xfade).pack(side="left")
        
        self.xdur = tk.DoubleVar(value=self.config.get('xfade_dur'))
        ttk.Spinbox(sf, textvariable=self.xdur, from_=0.1, to=2.0, increment=0.1, width=4).pack(side="left", padx=5)
        
        ttk.Label(sf, text="|").pack(side="left", padx=5)
        self.keep_audio = tk.BooleanVar(value=self.config.get('keep_audio', True))
        ttk.Checkbutton(sf, text="Keep Audio", variable=self.keep_audio).pack(side="left")
        
        # Main Area (TTK PanedWindow)
        self.paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        self.paned.pack(fill="both", expand=True, padx=p, pady=5)
        
        # Pane 1: List
        list_frame = tk.Frame(self.paned, bg=bg)
        self.tree = ttk.Treeview(list_frame, columns=("n","d","s"), show="headings")
        self.tree.heading("n", text="Filename", command=lambda: self.sort("name"))
        self.tree.heading("d", text="Date", command=lambda: self.sort("date"))
        self.tree.heading("s", text="Size", command=lambda: self.sort("size"))
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")
        
        self.paned.add(list_frame, weight=3) # Heavy weight -> Grows most
        
        # Pane 2: Log
        log_frame = tk.Frame(self.paned, bg=bg)
        self.prog = ttk.Progressbar(log_frame)
        self.prog.pack(fill="x", pady=(5,5))
        btn_frame = tk.Frame(log_frame, bg=bg)
        btn_frame.pack(fill="x", pady=(0,5))
        ttk.Button(btn_frame, text="START STITCHING", command=self.run).pack(side="left", fill="x", expand=True)
        ttk.Button(btn_frame, text="Save Log", command=self.save_log).pack(side="right", padx=(5,0))
        self.log_txt = tk.Text(log_frame, bg="black", fg="#00ff00") # Font handled by UniversalUI recursive update
        self.log_txt.pack(fill="both", expand=True)
        
        self.paned.add(log_frame, weight=1) # Light weight -> Grows less

        # Restore Sash
        sash = self.config.get('sash_pos')
        if sash:
            # Add small delay to ensure geometry is calculated
            self.root.after(100, lambda: self.paned.sash_place(0, 0, sash))

    def on_close(self):
        self.config.set('mode', self.mode.get())
        self.config.set('trim_frames', self.trim.get())
        self.config.set('crossfade', self.xfade.get())
        self.config.set('xfade_dur', self.xdur.get())
        self.config.set('keep_audio', self.keep_audio.get())
        self.config.set('sort_col', self.last_sort)
        self.config.set('sort_desc', self.sort_desc)
        try: self.config.set('sash_pos', self.paned.sash_coord(0)[1])
        except: pass
        super().on_close()


    def poll_log(self):
        try:
            while True:
                msg = self.msg.get_nowait()
                ts = datetime.now().strftime("[%H:%M:%S]")
                self.log_txt.insert(tk.END, f"{ts} > {msg}\n")
                self.log_txt.see(tk.END)
        except: pass
        self.root.after(200, self.poll_log)

    def add(self):
        d = self.config.get('last_dir') or str(Path.home())
        exts = "*.mp4;*.mov;*.mkv;*.avi;*.wmv;*.flv;*.webm;*.m4v;*.mpeg;*.mpg"
        fs = filedialog.askopenfilenames(initialdir=d, filetypes=[("Video Files", exts), ("All Files", "*.*")])
        if fs:
            self.config.set('last_dir', os.path.dirname(fs[0]))
            for f in fs:
                if Path(f) not in self.files: self.files.append(Path(f))
            self.refresh()

    def add_folder(self):
        d = self.config.get('last_dir') or str(Path.home())
        folder = filedialog.askdirectory(initialdir=d)
        if folder:
            self.config.set('last_dir', folder)
            valid_exts = {'.mp4', '.mov', '.mkv', '.avi', '.wmv', '.flv', '.webm', '.m4v', '.mpeg', '.mpg'}
            if self.include_sub.get():
                for root, _, files in os.walk(folder):
                    for file in files:
                        p = Path(root) / file
                        if p.suffix.lower() in valid_exts and p not in self.files:
                            self.files.append(p)
            else:
                for file in os.listdir(folder):
                    p = Path(folder) / file
                    if p.is_file() and p.suffix.lower() in valid_exts and p not in self.files:
                        self.files.append(p)
            self.refresh()

    def save_log(self):
        txt = self.log_txt.get("1.0", tk.END).strip()
        if not txt: return messagebox.showwarning("Empty", "Log is empty.")
        f = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text File", "*.txt")], initialfile=f"FilmStitch_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        if f:
            with open(f, "w", encoding="utf-8") as out:
                out.write(txt)
            messagebox.showinfo("Saved", "Log saved successfully.")

    def clear(self):
        self.files = []
        self.refresh()

    def sort(self, col):
        if self.last_sort == col: self.sort_desc = not self.sort_desc
        else: self.last_sort = col; self.sort_desc = False
        if col=='name': self.files.sort(key=lambda x:x.name, reverse=self.sort_desc)
        elif col=='date': self.files.sort(key=lambda x:x.stat().st_mtime, reverse=self.sort_desc)
        elif col=='size': self.files.sort(key=lambda x:x.stat().st_size, reverse=self.sort_desc)
        self.refresh()

    def refresh(self):
        for c in self.tree.get_children(): self.tree.delete(c)
        for f in self.files:
            dt = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            sz = f"{f.stat().st_size/1024/1024:.1f} MB"
            self.tree.insert("", "end", values=(f.name, dt, sz))

    def run(self):
        if not self.files: return messagebox.showwarning("Empty", "No files selected.")
        dst = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if not dst: return
        
        opts = {'mode': self.mode.get(), 'trim': self.trim.get(), 'xfade': self.xfade.get(), 'xfade_dur': self.xdur.get(), 'keep_audio': self.keep_audio.get()}
        self.log_txt.delete(1.0, tk.END); self.msg.put("Starting...")
        
        threading.Thread(target=lambda: [
            self.worker.stitch([str(f) for f in self.files], dst, opts, lambda v,m: [self.msg.put(m), self.prog.configure(value=v)]),
            self.msg.put("Finished!"),
            messagebox.showinfo("Done", "Complete!"),
            os.startfile(dst) if os.path.exists(dst) else None
        ], daemon=True).start()

if __name__ == "__main__":
    try: os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except: pass
    
    root = tk.Tk()
    app = FilmStitchApp(root)
    root.mainloop()

