import sys
import subprocess
import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import time

# -----------------------------------------------------------------------------
# Core Logic
# -----------------------------------------------------------------------------

def get_duration(file_path):
    """Get the duration of a media file using ffprobe."""
    if not file_path or not os.path.exists(file_path):
        return 0.0
        
    cmd = [
        'ffprobe', 
        '-v', 'error', 
        '-show_entries', 'format=duration', 
        '-of', 'default=noprint_wrappers=1:nokey=1', 
        file_path
    ]
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Error reading duration: {e}")
        return 0.0

def process_media(video_path, audio_path, target_duration, upscale=False, output_dir=None, log_func=print):
    """
    Retime video to match target_duration and merge with audio.
    """
    try:
        vid_duration = get_duration(video_path)
        if vid_duration == 0:
            raise Exception("Could not determine video duration")

        # Calculate Factors
        speed_factor = vid_duration / target_duration
        pts_factor = 1.0 / speed_factor
        
        log_func(f"Processing: {os.path.basename(video_path)}")
        log_func(f"  Target: {target_duration:.2f}s (Speed x{speed_factor:.2f})")

        # Determine Output Filename
        base_name = os.path.basename(video_path)
        if output_dir:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            output_filename = os.path.join(output_dir, f"synced_{base_name}")
        else:
            output_filename = f"synced_{base_name}"
            # Avoid overwrite collision if in same folder
            if os.path.exists(output_filename):
                base, ext = os.path.splitext(output_filename)
                output_filename = f"{base}_{int(time.time())}{ext}"

        # Build Video Filter Chain
        vf_chain = [f"setpts={pts_factor:.6f}*(PTS-STARTPTS)"]
        
        if upscale:
            log_func("  Applying Smart Upscale (1080p + Sharpen)...")
            vf_chain.append("scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)':flags=lanczos")
            vf_chain.append("unsharp=5:5:1.0:5:5:0.0")
            
        vf_string = ",".join(vf_chain)

        cmd = []
        
        # Construct FFmpeg Command
        if audio_path:
            # Video Retime + Replace Audio
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-filter_complex', f'[0:v]{vf_string}[v]',
                '-map', '[v]',
                '-map', '1:a',
                '-t', str(target_duration),
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                output_filename
            ]
        else:
            # Video Retime + Audio Pitch Shift
            audio_filter_chain = ""
            remaining = speed_factor
            filters = []
            
            while remaining > 2.0:
                filters.append("atempo=2.0")
                remaining /= 2.0
            while remaining < 0.5:
                filters.append("atempo=0.5")
                remaining /= 0.5
            filters.append(f"atempo={remaining}")
            
            audio_filter_str = ",".join(filters)
            
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-filter_complex', f'[0:v]{vf_string}[v];[0:a]{audio_filter_str}[a]',
                '-map', '[v]',
                '-map', '[a]',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                output_filename
            ]

        # Run FFmpeg
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        subprocess.run(cmd, startupinfo=startupinfo, check=True)
        log_func(f"  Success: Saved to {os.path.basename(output_filename)}\n")
        return True, output_filename
            
    except Exception as e:
        log_func(f"  Error: {str(e)}\n")
        return False, str(e)

# -----------------------------------------------------------------------------
# GUI Implementation
# -----------------------------------------------------------------------------

class ChronoGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ChronoStretch Tool v2.1")
        self.root.geometry("700x800")
        self.root.resizable(True, True)
        
        # Styles for HiDPI
        style = ttk.Style()
        style.configure("TButton", font=('Segoe UI', 12, 'bold'), padding=10)
        style.configure("TLabel", font=('Segoe UI', 12), padding=5)
        style.configure("TEntry", padding=5, font=('Segoe UI', 11))
        style.configure("TRadiobutton", font=('Segoe UI', 12))
        style.configure("TCheckbutton", font=('Segoe UI', 12))
        style.configure("TNotebook.Tab", font=('Segoe UI', 12, 'bold'), padding=[15, 8])
        style.configure("TLabelframe.Label", font=('Segoe UI', 12, 'bold'))
        
        # Main Notebook (Tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # --- TAB 1: SINGLE MODE ---
        self.tab_single = ttk.Frame(self.notebook, padding=25)
        self.notebook.add(self.tab_single, text="  Single File  ")
        self.init_single_tab()
        
        # --- TAB 2: BATCH MODE ---
        self.tab_batch = ttk.Frame(self.notebook, padding=25)
        self.notebook.add(self.tab_batch, text="  Batch Folder  ")
        self.init_batch_tab()

    # -------------------------------------------------------------------------
    # Single Tab Logic
    # -------------------------------------------------------------------------
    def init_single_tab(self):
        # Vars
        self.s_video_path = tk.StringVar()
        self.s_audio_path = tk.StringVar()
        self.s_mode_var = tk.StringVar(value="audio")
        self.s_custom_var = tk.StringVar()
        self.s_upscale_var = tk.BooleanVar(value=True)
        self.s_v_dur = 0.0
        self.s_a_dur = 0.0

        # UI
        ttk.Label(self.tab_single, text="Video File:", font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        frame_v = ttk.Frame(self.tab_single)
        frame_v.pack(fill=tk.X, pady=(0, 5))
        ttk.Entry(frame_v, textvariable=self.s_video_path, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(frame_v, text="Browse...", command=self.browse_single_video).pack(side=tk.RIGHT)
        self.lbl_v_dur = ttk.Label(self.tab_single, text="Duration: -", foreground="#666", font=('Segoe UI', 11))
        self.lbl_v_dur.pack(anchor='w', pady=(0, 25))

        ttk.Label(self.tab_single, text="Audio File (Optional):", font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        frame_a = ttk.Frame(self.tab_single)
        frame_a.pack(fill=tk.X, pady=(0, 5))
        ttk.Entry(frame_a, textvariable=self.s_audio_path, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(frame_a, text="Browse...", command=self.browse_single_audio).pack(side=tk.RIGHT)
        self.lbl_a_dur = ttk.Label(self.tab_single, text="Duration: -", foreground="#666", font=('Segoe UI', 11))
        self.lbl_a_dur.pack(anchor='w', pady=(0, 25))

        # Settings Group
        lf = ttk.LabelFrame(self.tab_single, text="Target Settings", padding=20)
        lf.pack(fill=tk.X, pady=10)
        
        self.rb_s_audio = ttk.Radiobutton(lf, text="Match Audio Length", variable=self.s_mode_var, value="audio", command=self.update_single_ui)
        self.rb_s_audio.pack(anchor='w', pady=5)
        
        f_cust = ttk.Frame(lf)
        f_cust.pack(fill=tk.X, pady=5)
        ttk.Radiobutton(f_cust, text="Custom Length (sec):", variable=self.s_mode_var, value="custom", command=self.update_single_ui).pack(side=tk.LEFT)
        self.ent_s_custom = ttk.Entry(f_cust, textvariable=self.s_custom_var, width=12)
        self.ent_s_custom.pack(side=tk.LEFT, padx=10)

        ttk.Separator(lf, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        ttk.Checkbutton(lf, text="Smart Upscale (HD 1080p + Sharpen)", variable=self.s_upscale_var).pack(anchor='w')
        ttk.Label(lf, text="(Recommended for AI-generated clips)", font=('Segoe UI', 10), foreground="#666").pack(anchor='w', padx=28)

        # Action
        self.lbl_s_status = ttk.Label(self.tab_single, text="Ready", foreground="blue", font=('Segoe UI', 12, 'bold'))
        self.lbl_s_status.pack(pady=(25, 5))
        self.btn_s_run = ttk.Button(self.tab_single, text="START PROCESSING", command=self.run_single)
        self.btn_s_run.pack(fill=tk.X, ipady=8)
        
        self.update_single_ui()

    def browse_single_video(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv *.webm")])
        if f:
            self.s_video_path.set(f)
            self.s_v_dur = get_duration(f)
            self.lbl_v_dur.config(text=f"Duration: {self.s_v_dur:.2f}s")
            self.update_single_ui()

    def browse_single_audio(self):
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.aac *.m4a *.flac")])
        if f:
            self.s_audio_path.set(f)
            self.s_a_dur = get_duration(f)
            self.lbl_a_dur.config(text=f"Duration: {self.s_a_dur:.2f}s")
            self.s_mode_var.set("audio")
            self.update_single_ui()

    def update_single_ui(self):
        if self.s_mode_var.get() == "custom":
            self.ent_s_custom.config(state='normal')
        else:
            self.ent_s_custom.config(state='disabled')
        
        if not self.s_audio_path.get():
            self.rb_s_audio.config(state='disabled')
            if self.s_mode_var.get() == "audio":
                self.s_mode_var.set("custom")
                self.ent_s_custom.config(state='normal')
        else:
            self.rb_s_audio.config(state='normal')

    def run_single(self):
        v = self.s_video_path.get()
        a = self.s_audio_path.get()
        if not v:
            messagebox.showerror("Error", "Select a video first.")
            return
        
        target = 0.0
        if self.s_mode_var.get() == "audio":
            if not a: return
            target = self.s_a_dur
        else:
            try:
                target = float(self.s_custom_var.get())
            except:
                messagebox.showerror("Error", "Invalid custom duration.")
                return

        self.btn_s_run.config(state='disabled')
        self.lbl_s_status.config(text="Processing...", foreground="blue")
        
        def thread_task():
            success, msg = process_media(v, a, target, self.s_upscale_var.get())
            self.root.after(0, lambda: self.finish_single(success, msg))
            
        threading.Thread(target=thread_task).start()

    def finish_single(self, success, msg):
        self.btn_s_run.config(state='normal')
        if success:
            self.lbl_s_status.config(text="Done!", foreground="green")
            messagebox.showinfo("Success", f"File saved: {os.path.basename(msg)}")
        else:
            self.lbl_s_status.config(text="Failed", foreground="red")
            messagebox.showerror("Error", msg)


    # -------------------------------------------------------------------------
    # Batch Tab Logic
    # -------------------------------------------------------------------------
    def init_batch_tab(self):
        self.b_folder_path = tk.StringVar()
        self.b_upscale = tk.BooleanVar(value=True)

        # Instructions
        info = (
            "Batch Mode auto-matches Video and Audio files with the SAME filename.\n"
            "Example: 'Scene01.mp4' will automatically pair with 'Scene01.wav'.\n"
            "Files without a matching audio pair will be skipped."
        )
        lbl_info = ttk.Label(self.tab_batch, text=info, foreground="#555", justify=tk.LEFT, font=('Segoe UI', 11))
        lbl_info.pack(anchor='w', pady=(0, 25))

        # Folder Selection
        ttk.Label(self.tab_batch, text="Source Folder:", font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        frame_f = ttk.Frame(self.tab_batch)
        frame_f.pack(fill=tk.X, pady=(0, 15))
        ttk.Entry(frame_f, textvariable=self.b_folder_path, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(frame_f, text="Select Folder...", command=self.browse_batch_folder).pack(side=tk.RIGHT)

        # Settings
        ttk.Checkbutton(self.tab_batch, text="Smart Upscale (HD 1080p + Sharpen)", variable=self.b_upscale).pack(anchor='w', pady=15)

        # Action
        self.btn_b_run = ttk.Button(self.tab_batch, text="START BATCH PROCESS", command=self.run_batch)
        self.btn_b_run.pack(fill=tk.X, ipady=8, pady=10)

        # Progress
        self.progress = ttk.Progressbar(self.tab_batch, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress.pack(fill=tk.X, pady=10)
        
        # Log Area
        ttk.Label(self.tab_batch, text="Process Log:", font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(10,0))
        self.log_text = tk.Text(self.tab_batch, height=12, font=('Consolas', 10), state='disabled', bg="#f0f0f0")
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)

    def browse_batch_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.b_folder_path.set(d)
            self.log_msg(f"Selected: {d}")

    def log_msg(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def run_batch(self):
        folder = self.b_folder_path.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return

        self.log_msg("--- Starting Batch Scan ---")
        self.btn_b_run.config(state='disabled')
        
        threading.Thread(target=self.batch_worker, args=(folder, self.b_upscale.get())).start()

    def batch_worker(self, folder, upscale):
        # 1. Scan
        vid_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
        aud_exts = {'.mp3', '.wav', '.aac', '.m4a', '.flac'}
        
        pairs = [] # (vid_path, aud_path, target_dur)
        
        files = os.listdir(folder)
        videos = [f for f in files if os.path.splitext(f)[1].lower() in vid_exts]
        
        for v_file in videos:
            base_name = os.path.splitext(v_file)[0]
            v_path = os.path.join(folder, v_file)
            
            # Find matching audio
            found_audio = None
            for f in files:
                if f == v_file: continue
                name, ext = os.path.splitext(f)
                if name == base_name and ext.lower() in aud_exts:
                    found_audio = os.path.join(folder, f)
                    break
            
            if found_audio:
                # Calculate duration immediately to ensure validity
                a_dur = get_duration(found_audio)
                if a_dur > 0:
                    pairs.append((v_path, found_audio, a_dur))
                    self.root.after(0, lambda m=f"Found pair: {v_file} + {os.path.basename(found_audio)}": self.log_msg(m))
            else:
                self.root.after(0, lambda m=f"Skipping {v_file} (No matching audio)": self.log_msg(m))

        count = len(pairs)
        self.root.after(0, lambda: self.log_msg(f"--- Found {count} pairs to process ---"))
        
        if count == 0:
            self.root.after(0, lambda: self.finish_batch())
            return

        # 2. Process
        output_dir = os.path.join(folder, "_Output")
        
        for i, (v_path, a_path, duration) in enumerate(pairs):
            self.root.after(0, lambda val=(i/count)*100: self.progress.configure(value=val))
            
            # Wrapper for thread-safe logging
            def safe_log(txt):
                if txt.strip():
                    self.root.after(0, lambda t=txt: self.log_msg(t))
            
            process_media(v_path, a_path, duration, upscale, output_dir, safe_log)
        
        self.root.after(0, lambda: self.progress.configure(value=100))
        self.root.after(0, lambda: self.finish_batch())

    def finish_batch(self):
        self.btn_b_run.config(state='normal')
        self.log_msg("--- Batch Complete ---")
        messagebox.showinfo("Done", "Batch processing finished check _Output folder.")

# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------

def main():
    if not shutil.which("ffmpeg"):
        root = tk.Tk()
        root.withdraw() 
        messagebox.showerror("FFmpeg Missing", "FFmpeg not found in PATH.")
        return

    # CLI / Drag-n-Drop Mode
    if len(sys.argv) > 1:
        files = sys.argv[1:]
        
        # Determine if it's a file list or a folder drag
        if len(files) == 1 and os.path.isdir(files[0]):
            # Dragged a Folder -> Run Headless Batch
            folder = files[0]
            print(f"Detected Folder Drag: {folder}")
            print("Scanning for pairs...")
            
            vid_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
            aud_exts = {'.mp3', '.wav', '.aac', '.m4a', '.flac'}
            
            files_in_dir = os.listdir(folder)
            videos = [f for f in files_in_dir if os.path.splitext(f)[1].lower() in vid_exts]
            output_dir = os.path.join(folder, "_Output")
            
            for v_file in videos:
                base = os.path.splitext(v_file)[0]
                v_path = os.path.join(folder, v_file)
                # find audio
                a_path = None
                for f in files_in_dir:
                    if f == v_file: continue
                    if os.path.splitext(f)[0] == base and os.path.splitext(f)[1].lower() in aud_exts:
                        a_path = os.path.join(folder, f)
                        break
                
                if a_path:
                    dur = get_duration(a_path)
                    print(f"Processing Pair: {v_file}")
                    process_media(v_path, a_path, dur, upscale=True, output_dir=output_dir)
            
            print("Batch Done!")
            import time
            time.sleep(3)
            return

        # Regular File Drag
        video_file = None
        audio_file = None
        video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
        audio_exts = {'.mp3', '.wav', '.aac', '.m4a', '.flac'}

        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in video_exts:
                video_file = f
            elif ext in audio_exts:
                audio_file = f
        
        if not video_file:
            print("No video file detected.")
            input("Press Enter...")
            return

        v_dur = get_duration(video_file)
        target_dur = v_dur
        if audio_file:
            target_dur = get_duration(audio_file)
        else:
            try:
                target_dur = float(input(f"Enter target duration (current {v_dur}s): "))
            except:
                pass

        print("Auto-enabling Smart Upscale...")
        process_media(video_file, audio_file, target_dur, upscale=True)
        import time
        time.sleep(1)

    else:
        # GUI Mode
        root = tk.Tk()
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
        app = ChronoGUI(root)
        root.mainloop()

if __name__ == "__main__":
    main()
