
# Grok Loop Weaver - Pro Edition (Version 3.4 - Total Recall)
#
# ==============================================================================
# UNIVERSAL APP DEVELOPMENT PROTOCOL (Grok Standard v1.0)
# ==============================================================================
# 1. PATH SAFETY:
#    Always execute: os.chdir(os.path.dirname(os.path.abspath(__file__)))
#    This prevents "File Not Found" errors when users double-click the script.
#
# 2. ZERO-DEPENDENCY:
#    Do not assume FFMPEG is in PATH. Auto-detect "ffmpeg.exe" in the script's folder.
#
# 3. UI/UX STANDARDS:
#    - Text-Flow Input: Use ScrolledText for file lists (Paste/Edit friendly).
#    - Persistence: Save Window Geometry & User Settings to JSON on exit.
#    - Lazy UX: Auto-open output files/folders using os.startfile().
#
# 4. PROCESSING STABILITY (3-Stage Pipeline):
#    - Stage 1: Normalize (Fix FPS/Resolution/ColorSpace to intermediate file).
#    - Stage 2: Sequence/Effect (Apply Reverse/Weave logic).
#    - Stage 3: Merge (Concat or Crossfade).
#    - Always use -pix_fmt yuv420p for WMP compatibility.
# ==============================================================================

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import subprocess
import os
import sys
import shutil
import threading
import json
import time

CONFIG_FILE = "grok_config.json"

class GrokLoopWeaver:
    def __init__(self, root):
        self.root = root
        self.root.title("Grok Loop Weaver (Pro v3.4)")
        self.root.configure(bg="#0d1117")
        
        # Load Config (Geometry + Settings)
        self.config = self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.ffmpeg_cmd = "ffmpeg" 
        self.ffprobe_cmd = "ffprobe"
        
        self.setup_ui()
        self.root.after(100, self.ensure_ffmpeg)

    def load_config(self):
        default = {
            "geometry": "750x900",
            "out_mode": "Merge (Stitch All)",
            "seq_mode": "Weave (Original+Reverse)",
            "trans_type": "Crossfade (Overlap)",
            "overlap": 1
        }
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    saved = json.load(f)
                    # Merge saved with default to handle missing keys
                    default.update(saved)
                    self.root.geometry(default["geometry"])
            else:
                self.root.geometry(default["geometry"])
        except:
            self.root.geometry(default["geometry"])
        return default

    def on_close(self):
        try:
            # Save current state
            cfg = {
                "geometry": self.root.geometry(),
                "out_mode": self.out_mode.get(),
                "seq_mode": self.seq_mode.get(),
                "trans_type": self.trans_type.get(),
                "overlap": self.overlap_var.get()
            }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(cfg, f)
        except:
            pass
        self.root.destroy()

    def ensure_ffmpeg(self):
        local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg.exe")
        local_ffprobe = os.path.join(os.getcwd(), "ffprobe.exe")
        
        if os.path.exists(local_ffmpeg):
            self.ffmpeg_cmd = local_ffmpeg
            if os.path.exists(local_ffprobe): self.ffprobe_cmd = local_ffprobe
            return

        if not self.detect_cmd("ffmpeg") or not self.detect_cmd("ffprobe"):
            ans = messagebox.askyesno("FFmpeg Required", 
                "FFmpeg/FFprobe not found.\nPlease select ffmpeg.exe manually.")
            if ans:
                path = filedialog.askopenfilename(title="Select ffmpeg.exe", filetypes=[("Executable", "*.exe")])
                if path and os.path.exists(path):
                    self.ffmpeg_cmd = path
                    probe = path.replace("ffmpeg", "ffprobe")
                    if os.path.exists(probe): self.ffprobe_cmd = probe
                    return
            messagebox.showerror("Error", "FFmpeg is required.")
            self.root.destroy()

    def detect_cmd(self, name):
        if shutil.which(name): return True
        if os.name == 'nt' and shutil.which(name + ".exe"): return True
        return False

    def get_si(self):
        si = subprocess.STARTUPINFO() if os.name=='nt' else None
        if si: si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return si

    def setup_ui(self):
        bg="#0d1117"; bg2="#161b22"; fg="#c9d1d9"; acc="#238636"
        
        tk.Label(self.root, text="Grok Loop Weaver", font=("Segoe UI", 18, "bold"), bg=bg, fg="white").pack(pady=(15,0))
        tk.Label(self.root, text="Engine v3.4: Total Recall Edition", font=("Segoe UI", 9), bg=bg, fg="#8b949e").pack(pady=(0,10))

        main = tk.Frame(self.root, bg=bg, padx=15)
        main.pack(fill="both", expand=True)

        # Settings
        s_frame = tk.LabelFrame(main, text="Processing Configuration", bg=bg2, fg=fg, padx=10, pady=10, bd=0)
        s_frame.pack(fill="x", pady=5)

        # Mode
        r1 = tk.Frame(s_frame, bg=bg2); r1.pack(fill="x", pady=2)
        tk.Label(r1, text="Output Mode:", bg=bg2, fg=fg, width=12, anchor="w").pack(side="left")
        self.out_mode = ttk.Combobox(r1, values=["Merge (Stitch All)", "Batch (Individual Files)"], state="readonly", width=25)
        self.out_mode.set(self.config["out_mode"])
        self.out_mode.pack(side="left")
        
        tk.Label(r1, text="Pattern:", bg=bg2, fg=fg, width=10, anchor="e").pack(side="left", padx=10)
        self.seq_mode = ttk.Combobox(r1, values=["Weave (Original+Reverse)", "Forward Only", "Reverse Only"], state="readonly", width=25)
        self.seq_mode.set(self.config["seq_mode"])
        self.seq_mode.pack(side="left")

        # Transitions
        r2 = tk.Frame(s_frame, bg=bg2); r2.pack(fill="x", pady=2)
        tk.Label(r2, text="Transition:", bg=bg2, fg=fg, width=12, anchor="w").pack(side="left")
        self.trans_type = ttk.Combobox(r2, values=["None (Direct Cut)", "Crossfade (Overlap)"], state="readonly", width=25)
        self.trans_type.set(self.config["trans_type"])
        self.trans_type.pack(side="left")

        tk.Label(r2, text="Overlap(s):", bg=bg2, fg=fg, width=10, anchor="e").pack(side="left", padx=10)
        self.overlap_var = tk.DoubleVar(value=self.config["overlap"]); 
        tk.Entry(r2, textvariable=self.overlap_var, bg=bg, fg="white", insertbackground="white", width=8).pack(side="left")

        # File Input Area (Text Flow)
        l_frame = tk.Frame(main, bg=bg); l_frame.pack(fill="both", expand=True, pady=10)
        
        # Toolbar
        tb = tk.Frame(l_frame, bg=bg); tb.pack(fill="x", pady=5)
        tk.Label(tb, text="Input Videos (Paste paths, one per line):", bg=bg, fg=fg, font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(tb, text="Clear", command=self.clear_text, bg="#da3633", fg="white", bd=0, padx=10, pady=2).pack(side="right")
        tk.Button(tb, text="+ Append Files", command=self.add_videos, bg="#1f6feb", fg="white", bd=0, padx=10, pady=2).pack(side="right", padx=5)

        # ScrolledText for flexible input
        self.text_area = scrolledtext.ScrolledText(l_frame, bg=bg2, fg=fg, insertbackground="white", bd=0, height=10, font=("Consolas", 9))
        self.text_area.pack(fill="both", expand=True)
        
        # Go
        self.process_btn = tk.Button(self.root, text="Start Processing", command=self.start_processing, bg=acc, fg="white", font=("bold", 12), bd=0, pady=12)
        self.process_btn.pack(fill="x", padx=20, pady=(10,20))
        self.status_var = tk.StringVar(value="Ready"); tk.Label(self.root, textvariable=self.status_var, bg=bg, fg="#8b949e").pack(pady=5)

    def add_videos(self):
        files = filedialog.askopenfilenames(filetypes=[("Videos", "*.mp4 *.mov *.webm *.mkv")])
        if files:
            current = self.text_area.get("1.0", tk.END).strip()
            if current: self.text_area.insert(tk.END, "\n")
            for f in files:
                # Use standardized paths with forward slashes for consistency
                clean_path = f.replace("/", "\\")
                self.text_area.insert(tk.END, clean_path + "\n")
            self.text_area.see(tk.END)

    def clear_text(self):
        self.text_area.delete("1.0", tk.END)

    def get_valid_files(self):
        raw = self.text_area.get("1.0", tk.END).splitlines()
        valid = []
        for line in raw:
            # Remove quotes if user copied as path
            clean = line.strip().strip('"').strip("'")
            if clean and os.path.exists(clean):
                valid.append({"path": clean, "name": os.path.basename(clean)})
        return valid

    def get_video_info(self, path):
        try:
            cmd = [self.ffprobe_cmd, "-v", "error", "-select_streams", "v:0", 
                   "-show_entries", "stream=width,height", "-of", "json", path]
            out = subprocess.check_output(cmd, startupinfo=self.get_si()).decode().strip()
            data = json.loads(out)
            s = data['streams'][0]
            return int(s.get('width', 0)), int(s.get('height', 0))
        except: return 1280, 720

    def get_duration(self, path):
        try:
            cmd = [self.ffprobe_cmd, "-v", "error", "-show_entries", "format=duration", 
                   "-of", "default=noprint_wrappers=1:nokey=1", path]
            return float(subprocess.check_output(cmd, startupinfo=self.get_si()).decode().strip())
        except: return 0.0

    def start_processing(self):
        videos = self.get_valid_files()
        if not videos: return messagebox.showwarning("Empty", "No valid video paths found in the text area.")
        
        mode = self.out_mode.get()
        target_path = ""
        
        if "Batch" in mode:
            target_path = filedialog.askdirectory(title="Select Output Folder")
            if not target_path: return
        else:
            target_path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
            if not target_path: return
        
        self.process_btn.config(state="disabled")
        threading.Thread(target=self.run_engine, args=(videos, target_path, mode), daemon=True).start()

    def run_engine(self, video_list, target, mode_str):
        temp_files_to_clean = []
        try:
            is_merge = "Merge" in mode_str
            seq_type = self.seq_mode.get()
            trans_type = self.trans_type.get()
            overlap = self.overlap_var.get()

            # --- STEP 1: Max Resolution ---
            self.status_var.set("Analyzing video dimensions...")
            max_w, max_h = 0, 0
            for v in video_list:
                w, h = self.get_video_info(v["path"])
                if w > max_w: max_w = w
                if h > max_h: max_h = h
            if max_w == 0: max_w, max_h = 1280, 720
            
            # Ensure dimensions are even
            if max_w % 2 != 0: max_w += 1
            if max_h % 2 != 0: max_h += 1

            processed_parts = []

            # --- MAIN LOOP ---
            for i, vid in enumerate(video_list):
                self.status_var.set(f"Processing clip {i+1}/{len(video_list)}: {vid['name']}...")
                
                # STAGE 1: NORMALIZE
                temp_norm = f"temp_norm_{i}.mp4"
                temp_files_to_clean.append(temp_norm)
                
                # Use scale to fill (increase aspect ratio) then crop to fit exact dims
                norm_filter = (
                    f"scale={max_w}:{max_h}:force_original_aspect_ratio=increase,"
                    f"crop={max_w}:{max_h},"
                    f"setsar=1,fps=30,format=yuv420p"
                )
                
                subprocess.run([
                    self.ffmpeg_cmd, "-y", "-i", vid["path"],
                    "-vf", norm_filter,
                    "-c:v", "libx264", "-preset", "ultrafast", "-an",
                    temp_norm
                ], check=True, startupinfo=self.get_si())

                # STAGE 2: SEQUENCE
                temp_seq = f"temp_seq_{i}.mp4"
                temp_files_to_clean.append(temp_seq)

                if "Weave" in seq_type:
                    # Robust Split -> Reverse -> Concat
                    subprocess.run([
                        self.ffmpeg_cmd, "-y", "-i", temp_norm,
                        "-filter_complex", "[0:v]split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0[out]",
                        "-map", "[out]",
                        "-c:v", "libx264", "-preset", "ultrafast", "-an",
                        temp_seq
                    ], check=True, startupinfo=self.get_si())
                elif "Reverse" in seq_type:
                    subprocess.run([
                        self.ffmpeg_cmd, "-y", "-i", temp_norm,
                        "-vf", "reverse",
                        "-c:v", "libx264", "-preset", "ultrafast", "-an",
                        temp_seq
                    ], check=True, startupinfo=self.get_si())
                else: 
                    # Forward Only (Direct Copy)
                    shutil.copy(temp_norm, temp_seq)
                
                if os.path.exists(temp_norm): os.remove(temp_norm)

                # STAGE 3: OUTPUT COLLECTION
                if not is_merge:
                    # Batch Mode: Move to final folder immediately
                    base_name = "".join([c for c in os.path.splitext(vid["name"])[0] if c.isalnum() or c in (' ','_','-')]).strip()
                    final_path = os.path.join(target, f"{base_name}_loop.mp4")
                    shutil.move(temp_seq, final_path)
                else:
                    processed_parts.append(temp_seq)

            # --- STAGE 4: FINAL MERGE ---
            if is_merge and processed_parts:
                self.status_var.set("Finalizing Merge...")
                
                if "Crossfade" in trans_type and len(processed_parts) > 1 and overlap > 0:
                    durs = [self.get_duration(p) for p in processed_parts]
                    inputs = []
                    for p in processed_parts: inputs.extend(["-i", p])
                    
                    filter_chain = ""
                    curr_offset = 0
                    prev_label = "0"
                    
                    for i in range(1, len(processed_parts)):
                        d_prev = durs[i-1]
                        curr_offset += (d_prev - overlap)
                        
                        next_label = f"{i}"
                        out_label = f"v{i}" if i < len(processed_parts)-1 else "out"
                        
                        filter_chain += f"[{prev_label}][{next_label}]xfade=transition=fade:duration={overlap}:offset={curr_offset:.3f}[{out_label}];"
                        prev_label = out_label
                    
                    filter_chain = filter_chain.strip(";")
                    
                    subprocess.run([
                        self.ffmpeg_cmd, "-y", *inputs,
                        "-filter_complex", filter_chain,
                        "-map", f"[{prev_label}]",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                        "-pix_fmt", "yuv420p",
                        target
                    ], check=True, startupinfo=self.get_si())
                    
                else:
                    # Direct Concat (No Trans)
                    list_f = "list.txt"
                    with open(list_f, "w") as f:
                        for p in processed_parts: f.write(f"file '{os.path.abspath(p).replace(os.sep, '/')}'\n")
                    
                    subprocess.run([
                        self.ffmpeg_cmd, "-y", "-f", "concat", "-safe", "0", 
                        "-i", list_f, "-c", "copy", target
                    ], check=True, startupinfo=self.get_si())
                    os.remove(list_f)

            # Cleanup
            for p in temp_files_to_clean:
                if os.path.exists(p): os.remove(p)

            self.status_var.set("Done!"); messagebox.showinfo("Success", "Processing Complete!")
            # Lazy UX: Auto-open result
            if os.name=='nt': os.startfile(target)

        except Exception as e:
            self.status_var.set("Error"); messagebox.showerror("Error", f"{e}")
            print(e)
            for p in temp_files_to_clean:
                if os.path.exists(p): os.remove(p)
        finally:
            self.root.after(0, lambda: self.process_btn.config(state="normal"))

if __name__ == "__main__":
    try:
        # PATH ANCHORING
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except:
        pass
        
    root = tk.Tk()
    app = GrokLoopWeaver(root)
    root.mainloop()
