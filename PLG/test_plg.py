import os
import sys
import re
import shutil
import tempfile
import time
import subprocess
import xml.etree.ElementTree as ET
import mutagen
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

# Add parent directory to sys.path so we can import plg
parent_dir = os.path.dirname(os.path.abspath(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import plg

def create_dummy_file(filepath):
    """建立零位元組的假媒體檔（僅用於掃描測試）。"""
    open(filepath, 'wb').close()

def mock_get_audio_metadata(filepath):
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    mapping = {
        "songA.mp3": ("Artist Alpha", "Title A", 1, 120),
        "songB.mp3": ("Artist Beta",  "Title B", 2, 180),
        "songC.mp3": ("Artist Alpha", "Title C", 3, 240),
        "songD.mp3": ("Artist Gamma", "Title D", 4, 300),
        "songE.mp3": ("Artist Beta",  "Title E", 5,  60),
        "videoA.mp4": ("", "Video A", 0, 600),
        "videoB.mkv": ("", "Video B", 0, 720),
    }
    if filename in mapping:
        artist, title, num, dur = mapping[filename]
        return {
            'artist': artist, 'title': title, 'track_name': title,
            'track_number': num, 'duration': float(dur), 'size': 1000,
            'name': filename, 'path': filepath,
            'mtime': os.path.getmtime(filepath) if os.path.exists(filepath) else time.time(),
            'ext': ext
        }
    return {
        'artist': '', 'title': '', 'track_name': filename, 'track_number': 0,
        'duration': 0.0, 'size': 0, 'name': filename, 'path': filepath,
        'mtime': time.time(), 'ext': ext
    }

plg.get_audio_metadata = mock_get_audio_metadata

def run_tests():
    print("Initializing PLG Unit Tests...")
    
    # 1. Create temporary directory with media files
    temp_dir = tempfile.mkdtemp(prefix="plg_test_")
    print(f"Created temp directory: {temp_dir}")
    
    try:
        audio_files = [
            "songA.mp3", "songB.mp3", "songC.mp3", "songD.mp3", "songE.mp3",
        ]
        video_files = ["videoA.mp4", "videoB.mkv"]
        all_media = audio_files + video_files

        for name in all_media:
            filepath = os.path.join(temp_dir, name)
            create_dummy_file(filepath)
            time.sleep(0.05)  # 確保修改時間各異

        print(f"Created {len(all_media)} dummy media files (audio + video).")
        
        # 2. Test Custom Argument Parsing
        print("\nTesting Custom CLI Parsing...")
        args = [temp_dir, "*.mp3", os.path.join(temp_dir, "test.xspf"), "/S", "/O:N", "/F:xspf", "/B"]
        params = plg.parse_arguments(args)
        assert params['source'] == temp_dir
        assert params['file_pattern'] == "*.mp3"
        assert params['target'] == os.path.join(temp_dir, "test.xspf")
        assert params['recursive'] is True
        assert params['relative'] is True
        assert params['sort_order'] == "N"
        assert params['format'] == "xspf"
        print("Argument Parsing PASS")
        
        # 3. Test Scanning (音訊 + 影片)
        print("\nTesting Directory Scanning...")
        # 指定 *.mp3 → 只掃音訊
        scanned_mp3 = plg.scan_directory(temp_dir, "*.mp3", False)
        assert len(scanned_mp3) == 5, f"Expected 5 MP3 files, got {len(scanned_mp3)}"

        # 不指定格式 → 掃描所有支援的媒體（5 音訊 + 2 影片）
        scanned_all = plg.scan_directory(temp_dir, "*.*", False)
        assert len(scanned_all) == 7, f"Expected 7 media files, got {len(scanned_all)}"

        # 確認影片副檔名出現在結果中
        exts = {os.path.splitext(f)[1].lower() for f in scanned_all}
        assert '.mp4' in exts, ".mp4 should be scanned"
        assert '.mkv' in exts, ".mkv should be scanned"
        print("Directory Scanning PASS (audio + video)")

        scanned = scanned_mp3  # 後續排序/切分測試只用 MP3
        
        # 4. Test Sorting
        print("\nTesting Sorting Algorithm...")
        # 直接使用已 mock 的 get_audio_metadata 建立 meta 列表
        meta = [mock_get_audio_metadata(f) for f in scanned]
            
        # Sort by Name (Alphabetical)
        sorted_meta = plg.sort_files(list(meta), "N")
        assert sorted_meta[0]['name'] == "songA.mp3"
        assert sorted_meta[-1]['name'] == "songE.mp3"
        
        # Sort by Track Number (TN)
        sorted_meta = plg.sort_files(list(meta), "TN")
        assert sorted_meta[0]['track_number'] == 1
        assert sorted_meta[-1]['track_number'] == 5
        print("Sorting Algorithm PASS")
        
        # 5. Test Slicing and Generation
        print("\nTesting Slicing and Playlist Generation...")
        # Target: 5 minutes (300 sec), tolerance: 1 minute (60 sec)
        # Playlist 1 should contain:
        # songA (120s) + songB (180s) = 300s (Matches target exactly)
        # Playlist 2 should contain:
        # songC (240s) + songD (300s) -> wait, songC is 240s, next is songD (300s). 
        # Adding songD makes it 540s (exceeds max target 360s). 
        # So Playlist 2 should stop and write songC (240s).
        # Playlist 3 should contain:
        # songD (300s) = 300s
        # Playlist 4 should contain:
        # songE (60s) = 60s (remainder)
        
        params['duration_limit'] = (300, 60)
        plg.slice_and_generate(sorted_meta, params)
        
        # Verify slice files exist
        expected_files = [
            os.path.join(temp_dir, "test[-001].xspf"),
            os.path.join(temp_dir, "test[-002].xspf"),
            os.path.join(temp_dir, "test[-003].xspf"),
            os.path.join(temp_dir, "test[-004].xspf"),
        ]
        
        for f in expected_files:
            assert os.path.exists(f), f"Expected playlist slice missing: {f}"
            
        # Read test[-001].xspf and verify content
        tree = ET.parse(expected_files[0])
        root = tree.getroot()
        tracks = root.findall(".//{http://xspf.org/ns/0/}track")
        assert len(tracks) == 2, f"Expected 2 tracks in first playlist, got {len(tracks)}"
        print("Slicing & Playlist Generation PASS")
        
        # 6. Test Update Mode (/U) — 應跳過子清單，只更新根清單
        print("\nTesting Update Mode...")
        old_cwd = os.getcwd()
        os.chdir(temp_dir)
        try:
            plg.run_update_mode()

            # 根清單（test.xspf）沒有 PLG_PARAMS，但切分子清單有 → 子清單應被跳過
            # 在 /U 執行後，不應產生雙層後綴的檔案（如 test[-001][-001].xspf）
            nested = [f for f in os.listdir(temp_dir)
                      if re.search(r'\[-\d{3}\].*\[-\d{3}\]', f)]
            assert len(nested) == 0, f"Nested split files found: {nested}"

            # 原始切分子清單應依然存在（已被直接覆蓋更新）
            for f in expected_files:
                assert os.path.exists(f), f"Expected split file missing after /U: {f}"

            print("Update Mode PASS (no nested splits)")
        finally:
            os.chdir(old_cwd)
            
        print("\nAll PLG core tests PASSED successfully!")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print(f"\nCleaned up temp directory: {temp_dir}")

if __name__ == "__main__":
    run_tests()
