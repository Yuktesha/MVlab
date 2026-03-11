import os
import subprocess
import sys
import re
import shutil
from typing import List, Dict, Any, Optional

class FFmpegEngine:
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.output_dir = os.path.join(project_root, "outputs")
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Verify FFmpeg availability
        self.ffmpeg_exe = shutil.which("ffmpeg")
        if not self.ffmpeg_exe:
            # Fallback check common paths or alert
            # For now, we assume it's in PATH as per plan
            print("[FFmpegEngine] Warning: 'ffmpeg' not found in PATH.")

    def render(self, 
               media_list: List[str], 
               output_path: str, 
               theme_config: Dict[str, Any], 
               overlay_image: Optional[str] = None,
               callback=None):
        """
        Renders the video using FFmpeg.
        
        Args:
            media_list: List of absolute paths to media files.
            output_path: Destination path.
            theme_config: Dict containing 'width', 'height', 'duration', 'transition', 'fitMode'.
            overlay_image: Optional path to a PNG overlay.
            callback: Function to call with progress lines.
        """
        
        if not self.ffmpeg_exe and not shutil.which("ffmpeg"):
             if callback: callback("Error: FFmpeg not found in system PATH.")
             return None

        # 1. Parse Config
        width = int(theme_config.get("width", 1920))
        height = int(theme_config.get("height", 1080))
        slide_duration = float(theme_config.get("duration", 3.0))
        transition_duration = float(theme_config.get("transition", 1.0))
        result_duration = slide_duration + transition_duration # Total time per clip before next starts? 
        # Actually logic:
        # Clip A plays for (Duration). Transition starts at (Duration - Transition).
        # So useful "static" time is (Duration - Transition).
        # Total video length ~ N * (Duration - Transition) + Transition
        
        fit_mode = theme_config.get("fitMode", "cover") # cover, contain, contain-blur

        # 2. Build Input Args
        input_args = []
        filter_complex = []
        
        # We need to handle images vs videos differently
        # Images need looping. Videos need to be trimmed or padded? 
        # For this version, we assume primarily IMAGES or treat videos as "play once then hold?".
        # Let's stick to standard behavior: 
        # Images: Loop for `slide_duration`.
        # Videos: Play. If shorter than slide_duration, hold last frame? Or Loop? 
        # For simplicity in V1: We'll force everything to be an image loop logic for now 
        # BUT user might want video.
        # IMPROVED LOGIC:
        # -i image: -loop 1 -t <slide_duration>
        # -i video: -t <slide_duration> (cut) or match length?
        # Let's enforce the "Slide Duration" strictly for now.
        
        for idx, media_path in enumerate(media_list):
            ext = os.path.splitext(media_path)[1].lower()
            is_video = ext in ['.mp4', '.mov', '.avi', '.mkv']
            
            if is_video:
                 # TODO: improved video handling (loop or scale duration)
                 # Current: Just take the first `slide_duration` seconds, or pad?
                 # FFMpeg tricky: -stream_loop?
                 # We will use -t to limit.
                 input_args.extend(["-t", str(slide_duration), "-i", media_path])
            else:
                 input_args.extend(["-loop", "1", "-t", str(slide_duration), "-i", media_path])

        # Add Overlay Input (Last Index)
        if overlay_image:
            input_args.extend(["-i", overlay_image])
            overlay_idx = len(media_list)
        
        # 3. Build Filter Chains
        video_nodes = []
        
        for i in range(len(media_list)):
            # Normalize Input [i] -> [v{i}] (Scaled/Padded/Blurred)
            input_node = f"{i}:v"
            out_node = f"v{i}"
            
            # --- Scale/Fit Logic ---
            if fit_mode == "contain-blur":
                # Split -> BG (Blur) + FG (Keep)
                split_node = f"split_{i}"
                bg_node = f"bg_{i}"
                fg_node = f"fg_{i}"
                
                # Split
                filter_complex.append(f"[{input_node}]split[bg_{i}][fg_{i}]")
                
                # BG: Scale to Cover -> Crop -> Blur
                # Scale logic: force_original_aspect_ratio=increase checks which dim is smaller and scales it to match target, 
                # ensuring the other dim is larger. Then crop centers it.
                filter_complex.append(
                    f"[bg_{i}]scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},"
                    f"boxblur=20:10,"
                    f"setsar=1[bg_proc_{i}]"
                )
                
                # FG: Scale to Fit
                filter_complex.append(
                    f"[fg_{i}]scale={width}:{height}:force_original_aspect_ratio=decrease[fg_proc_{i}]"
                )
                
                # Overlay FG on BG
                filter_complex.append(
                    f"[bg_proc_{i}][fg_proc_{i}]overlay=(W-w)/2:(H-h)/2:format=auto,"
                    f"setsar=1[{out_node}]"
                )
                
            elif fit_mode == "contain":
                # Scale to fit, pad with black
                filter_complex.append(
                    f"[{input_node}]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"setsar=1[{out_node}]"
                )
                
            else: # Cover
                filter_complex.append(
                    f"[{input_node}]scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},"
                    f"setsar=1[{out_node}]"
                )
            
            video_nodes.append(out_node)

        # 4. Transition Chain (XFade)
        # Sequence: v0 --(xfade)--> v1 --(xfade)--> v2 ...
        
        # Calculate Offsets
        # Slide 0 starts at 0. Ends at D.
        # Slide 1 starts at D - T.
        # Slide 2 starts at 2*(D-T).
        
        # We need a meaningful duration where the slide is "fully inputs".
        # If D=3, T=1.
        # S0: 0-3.
        # S1: Starts at 2. (Overlap 2-3).
        # Offset = idx * (slide_duration - transition_duration)
        
        offset_step = slide_duration - transition_duration
        if offset_step < 0: offset_step = 0 # Safety
        
        # 5. Apply Title Overlay (if any) - ONLY on the first slide (v0)
        # Done BEFORE the transition chain so it fades out with the first slide.
        if overlay_image:
             # Scale overlay to fit (preserve aspect ratio)
             # boxblur? No, title should be sharp.
             overlay_input_node = f"{overlay_idx}:v"
             scaled_overlay_node = "ov_scaled"
             
             filter_complex.append(
                 f"[{overlay_input_node}]scale={width}:{height}:force_original_aspect_ratio=decrease[ov_scaled]"
             )
             
             # Apply overlay to v0
             # (W-w)/2:(H-h)/2 centers it
             v0_node = video_nodes[0]
             v0_with_title = "v0_title"
             
             filter_complex.append(
                 f"[{v0_node}][{scaled_overlay_node}]overlay=(W-w)/2:(H-h)/2:format=auto[{v0_with_title}]"
             )
             
             # Replace v0 in the list with the titled version
             video_nodes[0] = v0_with_title

        curr_node = video_nodes[0]
        
        for i in range(1, len(video_nodes)):
            next_node = video_nodes[i]
            mix_node = f"m{i}"
            offset = i * offset_step
            
            # XFade
            filter_complex.append(
                f"[{curr_node}][{next_node}]xfade=transition=fade:duration={transition_duration}:offset={offset}[{mix_node}]"
            )
            curr_node = mix_node
            
        final_video_node = curr_node
        
        # Map final output

        # Map final output
        # Also, for audio, we currently map nothing (silent) or we need -f lavfi -i anullsrc?
        # If we don't map audio, FFmpeg might pick audio from first video input or produce silent video.
        # Let's explicitely produce silent video if no audio (we aren't handling audio mixing yet).
        # Actually xfade handles video only. Audio needs 'acrossfade'.
        # For this version (MVP reliability), let's ignore audio to prevent sync issues unless requested.
        # User said: "matching static cards (images) with audio"
        # If input has audio (video file), it will be lost with just video xfade.
        # We will focus on VIDEO ONLY for now as per "static cards" use case.
        
        # Final Command Construction
        filter_script_content = ";".join(filter_complex)
        
        # Write filter script to file to avoid char limit
        script_path = os.path.join(self.output_dir, "filter_script.txt")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(filter_script_content)
            
        cmd = ["ffmpeg", "-y"]
        cmd.extend(input_args)
        cmd.extend(["-filter_complex_script", script_path])
        cmd.extend(["-map", f"[{final_video_node}]"])
        
        # Encoding Settings for Compatibility
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium"])
        cmd.extend([output_path])
        
        # Print command for debugging
        full_cmd_str = " ".join(cmd)
        print(f"[FFmpeg] Command: {full_cmd_str}")
        if callback: callback(f"Starting Encode...")

        # Run
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, 
                universal_newlines=True,
                encoding='utf-8',
                errors='replace' # Handle potential encoding issues in logs
            )
            
            # Progress Parsing
            # frame=  123 fps=0.0 q=0.0 size=       0kB time=00:00:05.12 bitrate=   0.0kbits/s speed=10.2x
            duration_sec = len(media_list) * offset_step + transition_duration
            
            for line in process.stdout:
                line = line.strip()
                if not line: continue
                # print(f"[FFmpeg Log] {line}") # Verbose
                
                if "frame=" in line and "time=" in line:
                    # Extract time
                    match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d+)", line)
                    if match:
                        h, m, s = map(float, match.groups())
                        current_sec = h*3600 + m*60 + s
                        percent = min(100, (current_sec / duration_sec) * 100)
                        if callback: callback(f"Progress: {percent:.1f}%")
                elif "Error" in line or "Invalid" in line:
                     print(f"[FFmpeg Error] {line}")
                     if callback: callback(f"Error: {line}")
            
            process.wait()
            
            if process.returncode == 0:
                if callback: callback("Render Complete!")
                return output_path
            else:
                if callback: callback("Render Failed. Check console.")
                return None
                
        except Exception as e:
            print(f"Exception: {e}")
            if callback: callback(f"Exception: {e}")
            return None
