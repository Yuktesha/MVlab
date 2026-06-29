
# ==============================================================================
# CHRONOSTRETCH v1.4
# ==============================================================================
# Powered by UniversalUI
# ==============================================================================

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import threading
import queue
from pathlib import Path

# Add parent directory to sys.path so we can import the shared _lib
import os
import sys
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from _lib.UniversalUI import UniversalApp, get_ffmpeg_exe, get_ffprobe_exe
import _lib.UniversalUI as UniversalUI

# Try importing TkinterDnD
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

class FFmpegWorker:
    def __init__(self, log_queue):
        self.ffmpeg = get_ffmpeg_exe()
        self.ffprobe = get_ffprobe_exe()
        self.log_queue = log_queue

    def log(self, msg):
        self.log_queue.put(msg)
        
    def get_duration(self, path):
        if not self.ffprobe: return 0.0
        try:
            cmd = [self.ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
            si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return float(subprocess.check_output(cmd, startupinfo=si).strip())
        except: return 0.0

    def process_pair(self, vid, aud, out, upscale_mode):
        if not self.ffmpeg: raise Exception("FFmpeg missing")
        dur_v = self.get_duration(vid)
        dur_a = self.get_duration(aud)
        if dur_v <= 0 or dur_a <= 0: raise Exception("Invalid duration")
        
        pts_factor = dur_a / dur_v
        filters = [f"setpts={pts_factor:.6f}*PTS"]
        
        if upscale_mode != "off":
            dim = 1920 if upscale_mode == "1080p" else 3840
            filters.append(f"scale='if(gt(iw,ih),{dim},-2)':'if(gt(iw,ih),-2,{dim})':flags=lanczos")
            filters.append("unsharp=5:5:1.0:5:5:0.0")
            
        cmd = [
            self.ffmpeg, "-y", "-i", vid, "-i", aud,
            "-filter_complex", f"[0:v]{','.join(filters)}[v]",
            "-map", "[v]", "-map", "1:a", "-t", str(dur_a),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", out
        ]
        
        si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run(cmd, check=True, startupinfo=si)

class ChronoApp(UniversalApp):
    def __init__(self, root, file_args=None):
        defaults = {
            "geometry": "1100x800",
            "upscale_mode": "1080p",
            "name_source": "video",
            "last_dir": "",
            "undo_limit": 32
        }
        super().__init__(root, "ChronoStretch v1.4", "chrono_stretch_v1", defaults)
        
        self.msg_queue = queue.Queue()
        self.worker = FFmpegWorker(self.msg_queue)
        
        # Data Model: List of dicts
        # { 'id': str, 'v': Path|None, 'a': Path|None, 'status': str, 'v_dur': float, 'a_dur': float }
        self.jobs = [] 
        
        self.setup_ui()
        self.root.after(100, self.poll_log)
        
        # Undo Manager Setup
        limit = int(self.config.get("undo_limit", 32))
        self.undo_mgr = UniversalUI.UndoManager(self.restore_state, limit=limit)
        self.undo_mgr.snapshot(self.jobs) # Initial state
        
        self.root.bind("<Control-z>", self.undo_mgr.undo)
        self.root.bind("<Control-r>", self.undo_mgr.redo)
        
        # Log Config Hint
        self.root.after(200, lambda: self.worker.log(f"Config loaded: {self.config.filename}"))
        self.root.after(250, lambda: self.worker.log(f"(Hint: Click 'Config' button to change settings)"))
        
        # Handle Drag & Drop Args
        if file_args:
            self.root.after(500, lambda: self.process_incoming_files(file_args))
            
        # Hook Drag & Drop if available
        if HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.on_drop)

        # Internal Drag & Drop (Row to Row) via UniversalUI
        self.dragger = UniversalUI.DraggableTreeHelper(self.tree, self.on_row_dropped)

    def on_row_dropped(self, src_id, tgt_id):
        self.undo_mgr.snapshot(self.jobs)
        self.merge_jobs(src_id, tgt_id)

    def merge_jobs(self, src_id, tgt_id):
        # Find jobs
        src_job = next((j for j in self.jobs if j['id'] == src_id), None)
        tgt_job = next((j for j in self.jobs if j['id'] == tgt_id), None)
        
        if not src_job or not tgt_job: return
        
        updates = False
        
        # Transfer Video
        if src_job['v']:
             # If target has no video, or we decide to overwrite (user intention is usually fix)
             # Let's overwrite/fill.
             tgt_job['v'] = src_job['v']
             tgt_job['v_dur'] = src_job['v_dur']
             src_job['v'] = None
             src_job['v_dur'] = 0
             updates = True
             
        # Transfer Audio
        if src_job['a']:
             tgt_job['a'] = src_job['a']
             tgt_job['a_dur'] = src_job['a_dur']
             src_job['a'] = None
             src_job['a_dur'] = 0
             updates = True
             
        if updates:
            # Refresh Target
            self.check_job_status(tgt_job)
            self.refresh_list_item(tgt_job)
            
            # Check Source
            if not src_job['v'] and not src_job['a']:
                # Empty, remove
                self.jobs.remove(src_job)
                self.tree.delete(src_id)
            else:
                self.check_job_status(src_job)
                self.refresh_list_item(src_job)
                
            self.worker.log(f"Merged row manually.")


    def on_drop(self, event):
        try:
            files = self.root.tk.splitlist(event.data)
            
            # Use global mouse position for reliability
            mx, my = self.root.winfo_pointerxy()
            
            # Check if drop is inside the Treeview widget
            tx = self.tree.winfo_rootx()
            ty = self.tree.winfo_rooty()
            tw = self.tree.winfo_width()
            th = self.tree.winfo_height()
            
            if tx <= mx <= tx+tw and ty <= my <= ty+th:
                # Calculate Y relative to the tree widget
                local_y = my - ty
                row_id = self.tree.identify_row(local_y)
                
                if row_id:
                    self.handle_row_drop(row_id, files)
                    return
            
            # Default: General Add
            self.process_incoming_files(files)
            
        except Exception as e:
            print(f"DnD Error: {e}")
            self.worker.log(f"DnD Error: {e}")

    def handle_row_drop(self, row_id, files):
        self.undo_mgr.snapshot(self.jobs)
        # Find job
        job = next((j for j in self.jobs if j['id'] == row_id), None)
        if not job: return
        
        vid_exts = {'.mp4', '.mov', '.mkv', '.avi'}
        aud_exts = {'.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg'}
        
        updates = 0
        for f in files:
            p = Path(f)
            if p.suffix.lower() in vid_exts:
                job['v'] = p
                job['v_dur'] = 0 # Reset duration
                updates += 1
            elif p.suffix.lower() in aud_exts:
                job['a'] = p
                job['a_dur'] = 0
                updates += 1
        
        if updates > 0:
            self.check_job_status(job)
            self.refresh_list_item(job)
            self.worker.log(f"Manually updated pair: {job['v'].name if job['v'] else '---'} + {job['a'].name if job['a'] else '---'}")
            # Trigger duration check for new files
            threading.Thread(target=self.scan_durations, args=([job],), daemon=True).start()

    def setup_ui(self):
        p = 10
        
        # Header
        ttk.Label(self.root, text="ChronoStretch", style="Header.TLabel").pack(anchor="w", padx=p, pady=(p, 5))
        
        # Settings
        cf = ttk.LabelFrame(self.root, text="Settings", padding=10)
        cf.pack(fill="x", padx=p, pady=5)
        
        ttk.Label(cf, text="Upscale:").pack(side="left")
        self.upscale_var = tk.StringVar(value=self.config.get("upscale_mode"))
        cb = ttk.Combobox(cf, textvariable=self.upscale_var, values=["1080p", "4k", "off"], state="readonly", width=10)
        cb.pack(side="left", padx=5)
        
        ttk.Label(cf, text="| Name Source:").pack(side="left", padx=10)
        self.name_src_var = tk.StringVar(value=self.config.get("name_source"))
        ttk.Radiobutton(cf, text="Video", variable=self.name_src_var, value="video").pack(side="left")
        ttk.Radiobutton(cf, text="Audio", variable=self.name_src_var, value="audio").pack(side="left")

        # Config Button (Gear)
        ttk.Button(cf, text="Config", width=8, command=self.open_settings).pack(side="right", padx=5)

        # Auto Match Button
        ttk.Button(cf, text="Auto-Match by Duration", command=self.auto_match_by_duration).pack(side="right", padx=5)

        # List & Log
        _, self.list_frame, self.log_frame = self.create_paned_ui(self.root)
        
        # Toolbar
        tb = ttk.Frame(self.list_frame)
        tb.pack(fill="x", pady=(0,5))
        ttk.Button(tb, text="+ Add Files", command=self.add_files).pack(side="left")
        ttk.Button(tb, text="Clear All", command=self.clear_all).pack(side="right")
        
        self.tree = ttk.Treeview(self.list_frame, columns=("v","a","dur","s"), show="headings", selectmode="extended")
        self.tree.heading("v", text="Video"); self.tree.column("v", width=250)
        self.tree.heading("a", text="Audio"); self.tree.column("a", width=250)
        self.tree.heading("dur", text="Durations (V / A)"); self.tree.column("dur", width=150)
        self.tree.heading("s", text="Status"); self.tree.column("s", width=100)
        
        sb = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        # Action Area
        self.prog = ttk.Progressbar(self.log_frame, mode="determinate")
        self.prog.pack(fill="x", pady=(5,5))
        
        self.btn = ttk.Button(self.log_frame, text="START MERGE", command=self.start)
        self.btn.pack(fill="x", pady=(0,5))
        
        self.log_txt = self.create_console_log(self.log_frame)

    def on_close(self):
        self.config.set("upscale_mode", self.upscale_var.get())
        self.config.set("name_source", self.name_src_var.get())
        super().on_close()

    def poll_log(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self.log_txt.insert(tk.END, f"> {msg}\n")
                self.log_txt.see(tk.END)
        except queue.Empty: pass
        self.root.after(200, self.poll_log)

    def add_files(self):
        init = self.config.get("last_dir") or str(Path.home())
        files = filedialog.askopenfilenames(initialdir=init, title="Select Files")
        if files:
            self.config.set("last_dir", os.path.dirname(files[0]))
            self.process_incoming_files(files)
            
    def clear_all(self):
        self.undo_mgr.snapshot(self.jobs)
        self.jobs = []
        for c in self.tree.get_children(): self.tree.delete(c)

    def process_incoming_files(self, paths):
        self.undo_mgr.snapshot(self.jobs)
        vid_exts = {'.mp4', '.mov', '.mkv', '.avi'}
        aud_exts = {'.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg'}
        
        # Recursion
        files = []
        for p in paths:
            po = Path(p)
            if po.is_dir():
                for c in po.rglob('*'):
                    if c.is_file(): files.append(c)
            else:
                files.append(po)
        
        new_vids = []
        new_auds = []
        
        for p in files:
            if p.suffix.lower() in vid_exts: new_vids.append(p)
            elif p.suffix.lower() in aud_exts: new_auds.append(p)
            
        # 1. Try to fill existing orphans first
        for job in self.jobs:
            if not job['v'] and new_vids:
                # Try Name Match
                match = next((v for v in new_vids if v.stem == job['a'].stem), None)
                if match: 
                    job['v'] = match
                    new_vids.remove(match)
                # Else take first? No, wait for explicit or duration match
            
            if not job['a'] and new_auds:
                match = next((a for a in new_auds if a.stem == job['v'].stem), None)
                if match:
                    job['a'] = match
                    new_auds.remove(match)
                    
        # 2. Pair up remaining new V and new A by name
        new_jobs = []
        for v in list(new_vids):
            match = next((a for a in new_auds if a.stem == v.stem), None)
            if match:
                new_jobs.append(self.create_job(v, match))
                new_vids.remove(v)
                new_auds.remove(match)
                
        # 3. Add remaining as orphans
        for v in new_vids: new_jobs.append(self.create_job(v, None))
        for a in new_auds: new_jobs.append(self.create_job(None, a))
        
        self.jobs.extend(new_jobs)
        self.refresh_whole_tree()
        
        # Trigger Duration Scan for ALL incomplete or unprobed items
        threading.Thread(target=self.scan_durations, args=(self.jobs,), daemon=True).start()

    def create_job(self, v, a):
        jid = str(len(self.jobs) + 1 + int.from_bytes(os.urandom(4), 'big')) # Unique ID
        return {'id': jid, 'v': v, 'a': a, 'status': 'Pending', 'v_dur': 0, 'a_dur': 0}

    def check_job_status(self, job):
        if job['v'] and job['a']:
            job['status'] = "Ready" 
        elif job['v']:
            job['status'] = "Missing Audio"
        elif job['a']:
            job['status'] = "Missing Video"
        else:
            job['status'] = "Empty"

    def refresh_whole_tree(self):
        self.tree.delete(*self.tree.get_children())
        for j in self.jobs:
            self.check_job_status(j)
            self.insert_tree_item(j)
            
    def insert_tree_item(self, job):
        v = job['v'].name if job['v'] else "---"
        a = job['a'].name if job['a'] else "---"
        dur = f"{job['v_dur']:.1f}s / {job['a_dur']:.1f}s"
        self.tree.insert("", "end", iid=job['id'], values=(v, a, dur, job['status']))
        
    def refresh_list_item(self, job):
        if self.tree.exists(job['id']):
            v = job['v'].name if job['v'] else "---"
            a = job['a'].name if job['a'] else "---"
            dur = f"{job['v_dur']:.1f}s / {job['a_dur']:.1f}s"
            self.tree.item(job['id'], values=(v, a, dur, job['status']))

    def scan_durations(self, job_list):
        # Background thread
        for job in job_list:
            updated = False
            if job['v'] and job['v_dur'] == 0:
                job['v_dur'] = self.worker.get_duration(str(job['v']))
                updated = True
            if job['a'] and job['a_dur'] == 0:
                job['a_dur'] = self.worker.get_duration(str(job['a']))
                updated = True
                
            if updated:
                self.root.after(0, lambda j=job: self.refresh_list_item(j))
                
    def auto_match_by_duration(self):
        self.undo_mgr.snapshot(self.jobs)
        # Strategy: Greedy matching based on user criteria
        # Criteria: Video is usually >= 60% of Audio length. (Audio is ~1.0x to 1.66x Video)
        # We'll use a range of Audio/Video ratio: [0.9, 1.7] to allow for slight margin.
        # Priority: Closest to ratio 1.0 (assuming "same length" is the strongest signal), 
        # but valid matches within the range are accepted.
        
        orph_v = [j for j in self.jobs if j['v'] and not j['a']]
        orph_a = [j for j in self.jobs if j['a'] and not j['v']]
        
        # Scanned check
        if any(j['v_dur'] == 0 for j in orph_v) or any(j['a_dur'] == 0 for j in orph_a):
            messagebox.showinfo("Info", "Scanning file durations... Please wait a moment and try again.")
            return

        potential_matches = []
        
        for jv in orph_v:
            vd = jv['v_dur']
            if vd <= 0: continue
            
            for ja in orph_a:
                ad = ja['a_dur']
                if ad <= 0: continue
                
                ratio = ad / vd
                
                # Check User's Range: Audio is roughly 1.0 to 1.66 times longer than video
                # We allow 0.9 to 1.8 for tolerance
                if 0.9 <= ratio <= 1.8:
                    # Score: how close is it to 1.0? (Or just treat all as valid? 
                    # Usually closest duration is best match if multiple candidates exist)
                    diff = abs(ad - vd)
                    potential_matches.append({
                        'v': jv, 'a': ja, 'diff': diff, 'ratio': ratio
                    })
        
        # Sort by difference (closest duration first) allows 1:1 matches to grab first
        # Then maybe sort by ratio?
        # Let's sort by 'diff' ascending
        potential_matches.sort(key=lambda x: x['diff'])
        
        matches = 0
        used_v = set()
        used_a = set()
        
        for m in potential_matches:
            jv = m['v']
            ja = m['a']
            
            if jv['id'] in used_v or ja['id'] in used_a:
                continue
                
            # Perform Match
            jv['a'] = ja['a']
            jv['a_dur'] = ja['a_dur']
            
            # Mark for removal/cleanup
            used_v.add(jv['id'])
            used_a.add(ja['id'])
            
            # Remove the audio job from main list (since it's merged into video job)
            if ja in self.jobs:
                self.jobs.remove(ja)
            
            self.check_job_status(jv)
            matches += 1
            
        if matches > 0:
            self.refresh_whole_tree()
            messagebox.showinfo("Auto Pattern", f"Matched {matches} pairs based on duration ratio (0.9x - 1.8x).")
        else:
            messagebox.showinfo("Auto Pattern", "No matches found within likely duration criteria (Audio 0.9x ~ 1.8x Video).")

    def restore_state(self, state):
        self.jobs = state
        self.refresh_whole_tree()
        self.worker.log("Undo/Redo applied.")

    def reload_settings(self):
        # Update Undo Limit
        new_limit = int(self.config.get("undo_limit", 32))
        self.undo_mgr.limit = new_limit
        
        # Update other vars if needed
        # (Comboboxes usually bound to vars, so just update vars?)
        # self.upscale_var.set(self.config.get("upscale_mode"))
        # But if config changed underlying data, we might need to refresh widgets if they don't auto-update
        # Actually vars are independent. 
        self.worker.log(f"Settings reloaded. Undo limit: {new_limit}")

    def start(self):
        valid_jobs = [j for j in self.jobs if j['status'] == "Ready"]
        if not valid_jobs:
            messagebox.showwarning("Warning", "No ready pairs to process.")
            return
            
        dst = filedialog.askdirectory()
        if not dst: return
        
        self.btn.config(state="disabled")
        self.prog['value'] = 0
        self.log_txt.delete(1.0, tk.END)
        
        opts = {'upscale': self.upscale_var.get(), 'dst': dst}
        threading.Thread(target=self.run_batch, args=(opts, valid_jobs), daemon=True).start()

    def run_batch(self, opts, jobs):
        total = len(jobs)
        upscale = opts['upscale']
        dst = Path(opts['dst'])
        
        for i, p in enumerate(jobs):
            self.worker.log(f"Processing {i+1}/{total}...")
            try:
                src_name = self.name_src_var.get()
                base = p['a'].stem if src_name=='audio' else p['v'].stem
                
                suffix = "_merged"
                if upscale == "1080p": suffix = "_1080P"
                elif upscale == "4k": suffix = "_4K"
                elif upscale == "off": suffix = "_off"
                
                out = dst / f"{base}{suffix}.mp4"
                
                self.worker.process_pair(str(p['v']), str(p['a']), str(out), upscale)
                p['status'] = "Done"
                self.worker.log(f"Saved: {out.name}")
            except Exception as e:
                p['status'] = "Error"
                self.worker.log(f"Error: {e}")
            
            self.root.after(0, lambda j=p: self.refresh_list_item(j))
            self.root.after(0, lambda val=(i+1)/total*100: self.prog.configure(value=val))
            
        self.worker.log("Done.")
        messagebox.showinfo("Success", "Batch Complete")
        self.root.after(0, lambda: self.btn.config(state="normal"))
        if os.name=='nt': os.startfile(dst)

if __name__ == "__main__":
    try: os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except: pass
    
    # Select Root Class
    if HAS_DND:
        RootClass = TkinterDnD.Tk
        title_suffix = "" # UniversalUI handles title but we can append if we want, but simpler is better
    else:
        RootClass = tk.Tk
        title_suffix = " [DnD Disabled]"

    root = RootClass()
    
    # Handle Drag & Drop args (sys.argv)
    files = sys.argv[1:] if len(sys.argv) > 1 else None
    
    app = ChronoApp(root, files)
    if not HAS_DND:
        root.title(root.title() + title_suffix)
    
    root.mainloop()
