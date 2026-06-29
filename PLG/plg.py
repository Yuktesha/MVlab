import os
import sys
import fnmatch
import re
import urllib.parse
import xml.etree.ElementTree as ET
import subprocess
import mutagen

# Add parent directory to sys.path so we can import the shared _lib
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# ==============================================================================
# Helper Functions
# ==============================================================================
def parse_time(time_str):
    """Converts hh:mm:ss to seconds."""
    time_str = time_str.strip().lstrip('+').lstrip('-')
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    return 0

def format_time(seconds):
    """Converts seconds to hh:mm:ss."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def get_audio_duration_ffprobe(filepath):
    """Fallback to read duration using ffprobe."""
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
        si = None
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        out = subprocess.check_output(cmd, startupinfo=si).strip()
        return float(out)
    except:
        return 0.0

# 支援的媒體副檔名（音訊 + 影片）
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.wav', '.ogg', '.wma', '.aac', '.opus', '.ape', '.aiff'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts', '.mts', '.vob', '.rmvb', '.rm'}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

def get_audio_metadata(filepath):
    """Extract media metadata using mutagen (audio) or ffprobe (video) as fallback."""
    ext = os.path.splitext(filepath)[1].lower()
    metadata = {
        'artist': '',
        'title': '',
        'track_name': '',
        'track_number': 0,
        'duration': 0.0,
        'size': os.path.getsize(filepath),
        'name': os.path.basename(filepath),
        'path': filepath,
        'mtime': os.path.getmtime(filepath),
        'ext': ext
    }

    # 對音訊檔：優先用 mutagen 讀取完整標籤
    if ext in AUDIO_EXTENSIONS:
        try:
            audio = mutagen.File(filepath)
            if audio is not None:
                if audio.info:
                    metadata['duration'] = getattr(audio.info, 'length', 0.0)

                tags = audio.tags
                if tags:
                    artist = ""
                    title = ""
                    track_num = 0

                    # Artist Keys
                    for key in ['artist', 'ARTIST', 'Artist', 'author', 'Author', 'TP1', 'TPE1']:
                        if key in tags:
                            val = tags[key]
                            artist = val[0] if isinstance(val, list) else str(val)
                            break

                    # Title Keys
                    for key in ['title', 'TITLE', 'Title', 'name', 'Name', 'TT2', 'TIT2']:
                        if key in tags:
                            val = tags[key]
                            title = val[0] if isinstance(val, list) else str(val)
                            break

                    # Track Number Keys
                    for key in ['tracknumber', 'TRACKNUMBER', 'TrackNumber', 'track', 'Track', 'TRK', 'TRCK']:
                        if key in tags:
                            val = tags[key]
                            track_val = val[0] if isinstance(val, list) else str(val)
                            if '/' in track_val:
                                track_val = track_val.split('/')[0]
                            try:
                                track_num = int(track_val)
                            except:
                                pass
                            break

                    metadata['artist'] = artist
                    metadata['title'] = title
                    metadata['track_name'] = title or os.path.splitext(os.path.basename(filepath))[0]
                    metadata['track_number'] = track_num
        except Exception:
            pass

    # 對影片檔或 duration 仍為 0：用 ffprobe 補齊時長
    if metadata['duration'] <= 0.0:
        metadata['duration'] = get_audio_duration_ffprobe(filepath)

    if not metadata['track_name']:
        metadata['track_name'] = os.path.splitext(os.path.basename(filepath))[0]

    return metadata

# ==============================================================================
# Parsing, Scanning & Sorting
# ==============================================================================
def scan_directory(source_dir, file_pattern, recursive):
    matched_files = []

    if recursive:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if file_pattern and file_pattern != '*.*':
                    if fnmatch.fnmatch(file, file_pattern):
                        matched_files.append(os.path.join(root, file))
                else:
                    if ext in MEDIA_EXTENSIONS:
                        matched_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(source_dir):
            filepath = os.path.join(source_dir, file)
            if os.path.isfile(filepath):
                ext = os.path.splitext(file)[1].lower()
                if file_pattern and file_pattern != '*.*':
                    if fnmatch.fnmatch(file, file_pattern):
                        matched_files.append(filepath)
                else:
                    if ext in MEDIA_EXTENSIONS:
                        matched_files.append(filepath)

    return matched_files

def sort_files(files_metadata, sort_expr):
    if not sort_expr:
        return files_metadata
        
    reverse = False
    if sort_expr.startswith('-'):
        reverse = True
        sort_expr = sort_expr[1:]
        
    group_dirs = False
    if 'G' in sort_expr:
        group_dirs = True
        sort_expr = sort_expr.replace('G', '')
        
    key_func = lambda m: m['name'].lower()
    
    if sort_expr == 'N':
        key_func = lambda m: m['name'].lower()
    elif sort_expr == 'S':
        key_func = lambda m: m['size']
    elif sort_expr == 'E':
        key_func = lambda m: m['ext'].lower()
    elif sort_expr == 'D':
        key_func = lambda m: m['mtime']
        reverse = not reverse  # default D is newest first, reverse switches it
    elif sort_expr == 'A':
        key_func = lambda m: m['artist'].lower()
    elif sort_expr == 'TT':
        key_func = lambda m: m['title'].lower()
    elif sort_expr == 'TK':
        key_func = lambda m: m['track_name'].lower()
    elif sort_expr == 'TN':
        key_func = lambda m: m['track_number']
        
    if group_dirs:
        files_metadata.sort(key=lambda m: (os.path.dirname(m['path']).lower(), key_func(m)), reverse=reverse)
    else:
        files_metadata.sort(key=key_func, reverse=reverse)
        
    return files_metadata

def load_playlist(filepath):
    """
    Parses an existing playlist file and returns a list of audio metadata dicts.
    Supports: .xspf, .m3u, .m3u8, .pls, .wpl
    """
    ext = os.path.splitext(filepath)[1].lower()
    paths = []
    
    if ext == '.xspf':
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            # Remove namespace if present
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"
            
            for loc in root.findall(f".//{ns}location"):
                text = loc.text
                if text and text.startswith("file:///"):
                    # Decode URL format
                    p = urllib.parse.unquote(text[8:])
                    paths.append(p)
                elif text:
                    paths.append(text)
        except Exception as e:
            print(f"Error parsing XSPF: {e}")
            
    elif ext in ['.m3u', '.m3u8']:
        try:
            content = ""
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(filepath, 'r', encoding='cp950', errors='ignore') as f:
                    content = f.read()
                    
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    paths.append(line)
        except Exception as e:
            print(f"Error parsing M3U: {e}")
            
    elif ext == '.pls':
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.lower().startswith('file'):
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            paths.append(parts[1].strip())
        except Exception as e:
            print(f"Error parsing PLS: {e}")
            
    elif ext == '.wpl':
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            for media in root.findall(".//media"):
                src = media.get('src')
                if src:
                    paths.append(src)
        except Exception as e:
            print(f"Error parsing WPL: {e}")
            
    # Resolve paths relative to the playlist directory if needed
    playlist_dir = os.path.dirname(os.path.abspath(filepath))
    resolved_metadata = []
    
    for p in paths:
        # If relative path, join with playlist dir
        if not os.path.isabs(p) and not p.startswith("file://"):
            p = os.path.abspath(os.path.join(playlist_dir, p))
        
        # Check if file exists, then retrieve metadata
        if os.path.exists(p):
            resolved_metadata.append(get_audio_metadata(p))
        else:
            # Fallback if file does not exist locally
            resolved_metadata.append({
                'artist': '',
                'title': '',
                'track_name': os.path.splitext(os.path.basename(p))[0],
                'track_number': 0,
                'duration': 0.0,
                'size': 0,
                'name': os.path.basename(p),
                'path': p,
                'mtime': 0.0,
                'ext': os.path.splitext(p)[1].lower()
            })
            
    return resolved_metadata

# ==============================================================================
# CLI Argument Parser
# ==============================================================================
def parse_arguments(args):
    params = {
        'source': '.',
        'file_pattern': '*.*',
        'recursive': False,
        'sort_order': '',
        'target': '',
        'format': '',
        'relative': False,
        'duration_limit': None,  # (target_sec, tolerance_sec)
        'count_limit': None,     # (target_count, tolerance_count)
        'update_mode': False,
        'gui_confirm': False,
        'original_args': " ".join(args)
    }
    
    positionals = []
    
    for arg in args:
        if arg.startswith('/'):
            # Parse switch
            switch = arg[1:].upper()
            if switch == 'S':
                params['recursive'] = True
            elif switch == 'B':
                params['relative'] = True
            elif switch == 'U':
                params['update_mode'] = True
            elif switch == 'G':
                params['gui_confirm'] = True
            elif switch.startswith('O'):
                # Sort order
                val = arg[2:]
                if val.startswith(':'):
                    val = val[1:]
                params['sort_order'] = val
            elif switch.startswith('F'):
                # Playlist format
                val = arg[2:]
                if val.startswith(':'):
                    val = val[1:]
                params['format'] = val.lower()
            elif switch.startswith('L'):
                # Duration Limit
                val = arg[2:]
                if val.startswith(':'):
                    val = val[1:]
                # Split target and tolerance
                parts = val.split(',')
                target_sec = parse_time(parts[0])
                tolerance_sec = parse_time(parts[1]) if len(parts) > 1 else 300 # default 5m
                params['duration_limit'] = (target_sec, tolerance_sec)
            elif switch.startswith('N'):
                # Count Limit
                val = arg[2:]
                if val.startswith(':'):
                    val = val[1:]
                parts = val.split(',')
                target_count = int(parts[0])
                tolerance_count = int(parts[1]) if len(parts) > 1 else 0
                params['count_limit'] = (target_count, tolerance_count)
        else:
            positionals.append(arg)
            
    # Map positionals
    if len(positionals) >= 3:
        params['source'] = positionals[0]
        params['file_pattern'] = positionals[1]
        params['target'] = positionals[2]
    elif len(positionals) == 2:
        params['source'] = positionals[0]
        # Check if second looks like a pattern or a file
        if '*' in positionals[1] or '?' in positionals[1]:
            params['file_pattern'] = positionals[1]
        else:
            params['target'] = positionals[1]
    elif len(positionals) == 1:
        # If update mode, it could be just target or source
        if params['update_mode']:
            params['source'] = positionals[0]
        else:
            params['target'] = positionals[0]
            
    # Default format from target extension if not specified
    if not params['format'] and params['target']:
        ext = os.path.splitext(params['target'])[1].lower().lstrip('.')
        if ext in ['xspf', 'm3u8', 'm3u', 'pls', 'wpl']:
            params['format'] = ext
            
    if not params['format']:
        params['format'] = 'xspf'  # Spec default
        
    return params

# ==============================================================================
# Playlist Writers
# ==============================================================================
def write_playlist(filepath, files_metadata, params, part_num=None, total_parts=None):
    # Adjust filename if in multi-part mode
    if part_num is not None:
        base, ext = os.path.splitext(filepath)
        filepath = f"{base}[-{part_num:03d}]{ext}"
        
    fmt = params['format']
    cwd = os.getcwd()
    
    # Generate metadata string to save as comment
    arg_sig = f"PLG_PARAMS: source={params['source']} pattern={params['file_pattern']} r={params['recursive']} o={params['sort_order']} relative={params['relative']} format={params['format']}"
    if params['duration_limit']:
        arg_sig += f" L={format_time(params['duration_limit'][0])},{format_time(params['duration_limit'][1])}"
    if params['count_limit']:
        arg_sig += f" N={params['count_limit'][0]},{params['count_limit'][1]}"
        
    os.makedirs(os.path.dirname(os.path.abspath(filepath)) or '.', exist_ok=True)
    
    # Helper to resolve paths (relative or absolute)
    def resolve_path(p):
        if params['relative']:
            return os.path.relpath(p, cwd)
        return os.path.abspath(p)

    if fmt == 'xspf':
        # Write XSPF
        root = ET.Element("playlist", version="1", xmlns="http://xspf.org/ns/0/")
        title = ET.SubElement(root, "title")
        title.text = os.path.splitext(os.path.basename(filepath))[0]
        
        annotation = ET.SubElement(root, "annotation")
        annotation.text = arg_sig
        
        trackList = ET.SubElement(root, "trackList")
        for m in files_metadata:
            track = ET.SubElement(trackList, "track")
            loc = ET.SubElement(track, "location")
            # Convert file path to file:/// URL format
            resolved_p = resolve_path(m['path']).replace('\\', '/')
            loc.text = "file:///" + urllib.parse.quote(resolved_p)
            
            if m['title']:
                t = ET.SubElement(track, "title")
                t.text = m['title']
            if m['artist']:
                c = ET.SubElement(track, "creator")
                c.text = m['artist']
            if m['duration'] > 0:
                d = ET.SubElement(track, "duration")
                d.text = str(int(m['duration'] * 1000)) # in milliseconds
                
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        # Write to file with utf-8 header and comment
        with open(filepath, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(f"<!-- {arg_sig} -->\n".encode('utf-8'))
            tree.write(f, encoding='utf-8', xml_declaration=False)
            
    elif fmt in ['m3u8', 'm3u']:
        # Write M3U/M3U8
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write(f"# {arg_sig}\n")
            for m in files_metadata:
                dur = int(m['duration']) if m['duration'] > 0 else -1
                artist_title = f"{m['artist']} - {m['track_name']}" if m['artist'] else m['track_name']
                f.write(f"#EXTINF:{dur},{artist_title}\n")
                f.write(f"{resolve_path(m['path'])}\n")
                
    elif fmt == 'pls':
        # Write PLS
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("[playlist]\n")
            f.write(f"; {arg_sig}\n")
            f.write(f"NumberOfEntries={len(files_metadata)}\n")
            for i, m in enumerate(files_metadata, 1):
                f.write(f"File{i}={resolve_path(m['path'])}\n")
                title = f"{m['artist']} - {m['track_name']}" if m['artist'] else m['track_name']
                f.write(f"Title{i}={title}\n")
                f.write(f"Length{i}={int(m['duration']) if m['duration'] > 0 else -1}\n")
            f.write("Version=2\n")
            
    elif fmt == 'wpl':
        # Write WPL
        root = ET.Element("smil")
        head = ET.SubElement(root, "head")
        meta_gen = ET.SubElement(head, "meta", name="Generator", content="PLG")
        meta_sig = ET.SubElement(head, "meta", name="PLG_PARAMS", content=arg_sig)
        title = ET.SubElement(head, "title")
        title.text = os.path.splitext(os.path.basename(filepath))[0]
        
        body = ET.SubElement(root, "body")
        seq = ET.SubElement(body, "seq")
        
        for m in files_metadata:
            ET.SubElement(seq, "media", src=resolve_path(m['path']))
            
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        with open(filepath, 'wb') as f:
            f.write(b'<?wpl version="1.0"?>\n')
            f.write(f"<!-- {arg_sig} -->\n".encode('utf-8'))
            tree.write(f, encoding='utf-8', xml_declaration=False)
            
    print(f"Generated playlist: {filepath} ({len(files_metadata)} tracks)")
    return filepath

# ==============================================================================
# Slicing Engine
# ==============================================================================
def slice_and_generate(files_metadata, params):
    target_file = params['target']
    if not target_file:
        target_file = "playlist.xspf"
        params['target'] = target_file
        
    duration_limit = params['duration_limit']
    count_limit = params['count_limit']
    
    # If no limits are set, write all in a single playlist
    if not duration_limit and not count_limit:
        write_playlist(target_file, files_metadata, params)
        return
        
    remaining_pool = list(files_metadata)
    part_num = 1
    
    while remaining_pool:
        current_slice = []
        current_dur = 0.0
        current_count = 0
        
        # Slicing criteria
        if duration_limit:
            target_sec, tolerance_sec = duration_limit
            min_target = target_sec - tolerance_sec
            max_target = target_sec + tolerance_sec
            
            while remaining_pool:
                m = remaining_pool[0]
                dur = m['duration'] if m['duration'] > 0 else 180.0 # fallback 3m
                
                # Check if adding this goes beyond the max tolerance
                if current_dur + dur > max_target:
                    # Choose closest to target
                    dist_without = abs(target_sec - current_dur)
                    dist_with = abs(target_sec - (current_dur + dur))
                    
                    if dist_with < dist_without and (current_dur + dur) <= max_target:
                        current_slice.append(remaining_pool.pop(0))
                        current_dur += dur
                    break
                else:
                    current_slice.append(remaining_pool.pop(0))
                    current_dur += dur
                    
                    # If we reached the target range, we can stop
                    if current_dur >= min_target and current_dur <= max_target:
                        break
                        
        elif count_limit:
            target_count, tolerance_count = count_limit
            min_count = target_count - tolerance_count
            max_count = target_count + tolerance_count
            
            while remaining_pool and len(current_slice) < max_count:
                current_slice.append(remaining_pool.pop(0))
                if len(current_slice) >= min_count:
                    break
                    
        # Check if we have anything to write
        if current_slice:
            # If this is the last chunk, and it falls short of the minimum target duration,
            # we still write it as the final playlist (remnant handling)
            write_playlist(target_file, current_slice, params, part_num=part_num)
            part_num += 1
        else:
            break

# ==============================================================================
# Update Mode (/U)
# ==============================================================================
def parse_params_from_file(filepath):
    """Parses PLG_PARAMS signature from a playlist file comment."""
    sig = None
    try:
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ['.xspf', '.wpl']:
            # Parse XML comments or annotations
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            match = re.search(r"PLG_PARAMS:\s*(.*?)\s*-->", content)
            if match:
                sig = match.group(1)
            else:
                # Check annotation
                match = re.search(r"<annotation>PLG_PARAMS:\s*(.*?)\s*</annotation>", content)
                if match:
                    sig = match.group(1)
        elif ext in ['.m3u8', '.m3u', '.pls']:
            # Parse text lines
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if "PLG_PARAMS:" in line:
                        sig = line.split("PLG_PARAMS:")[-1].strip()
                        break
    except Exception as e:
        print(f"Error parsing signature from {filepath}: {e}")
    return sig

def rebuild_args_from_sig(sig):
    """Converts key=value signature back to sys.argv list."""
    args = []
    # E.g. source=. pattern=*.* r=True o=N relative=False format=xspf L=01:30:00,00:05:00
    parts = re.findall(r'(\w+)=([^\s]+)', sig)
    params = dict(parts)
    
    if 'source' in params:
        args.append(params['source'])
    if 'pattern' in params:
        args.append(params['pattern'])
    # Target file
    # We will reuse the original file as target
    
    if params.get('r') == 'True':
        args.append('/S')
    if params.get('relative') == 'True':
        args.append('/B')
    if params.get('o'):
        args.append(f"/O:{params['o']}")
    if params.get('format'):
        args.append(f"/F:{params['format']}")
    if params.get('L'):
        args.append(f"/L:{params['L']}")
    if params.get('N'):
        args.append(f"/N:{params['N']}")
        
    return args

# 偵測切分子清單的後綴樣式，例如 playlist[-001].xspf
_SPLIT_SUFFIX_RE = re.compile(r'\[-(\d{3})\](?:\.[^.]+)?$')

def run_update_mode():
    """更新模式：掃描當前目錄的根清單（跳過切分子清單），
    依嵌入簽名重新生成整批清單以取代舊版本。"""
    print("Running in Update Mode (/U)...")
    cwd = os.getcwd()
    playlist_exts = ['*.xspf', '*.m3u8', '*.m3u', '*.pls', '*.wpl']
    playlists = []
    for ext in playlist_exts:
        playlists.extend(fnmatch.filter(os.listdir(cwd), ext))

    if not playlists:
        print("No existing playlists found in the startup folder.")
        return

    for pl in playlists:
        # 跳過切分子清單（檔名含 [-NNN] 後綴）；
        # 根清單才帶有完整的 PLG_PARAMS 簽名。
        base = os.path.splitext(pl)[0]
        if _SPLIT_SUFFIX_RE.search(base):
            print(f"Skipped split playlist: {pl}")
            continue

        filepath = os.path.abspath(pl)
        sig = parse_params_from_file(filepath)
        if sig:
            print(f"Found signature in {pl}: {sig}")
            rebuilt_args = rebuild_args_from_sig(sig)
            rebuilt_args.append(filepath)  # 以根清單本身為輸出目標

            # 執行重新生成
            params = parse_arguments(rebuilt_args)
            files = scan_directory(params['source'], params['file_pattern'], params['recursive'])
            if files:
                meta = [get_audio_metadata(f) for f in files]
                meta = sort_files(meta, params['sort_order'])
                slice_and_generate(meta, params)
            else:
                print(f"No media files found for updated {pl}")
        else:
            print(f"Skipped {pl}: No PLG signature found.")

# ==============================================================================
# CLI Entry Point
# ==============================================================================
def run_cli(args):
    params = parse_arguments(args)
    
    if params['update_mode']:
        run_update_mode()
        return
        
    print(f"Scanning source directory: {params['source']}")
    files = scan_directory(params['source'], params['file_pattern'], params['recursive'])
    print(f"Found {len(files)} matching media files.")
    
    if not files:
        print("No matching files found. Playlist not generated.")
        return
        
    # Read metadata
    print("Reading media metadata/tags...")
    files_metadata = [get_audio_metadata(f) for f in files]
    
    # Sort
    if params['sort_order']:
        print(f"Sorting files by order: {params['sort_order']}")
        files_metadata = sort_files(files_metadata, params['sort_order'])
        
    # Generate
    slice_and_generate(files_metadata, params)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # GUI Mode
        import plg_gui
        plg_gui.main()
    else:
        # Check /G parameter
        args = sys.argv[1:]
        if '/G' in [a.upper() for a in args] or '/G:' in [a.upper()[:3] for a in args]:
            import plg_gui
            plg_gui.main(args)
        else:
            run_cli(args)
