import os
import sys
from PIL import Image, ImageDraw

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

# Check if render_bridge is available
try:
    from render_bridge import RenderEngine
except ImportError:
    print("Error: render_bridge.py not found in path.")
    sys.exit(1)

def create_dummy_image(path):
    img = Image.new('RGB', (1920, 1080), color = 'red')
    d = ImageDraw.Draw(img)
    d.text((10,10), "Hello World", fill=(255,255,0))
    img.save(path)
    print(f"Created dummy image at {path}")

def run_test():
    engine = RenderEngine(project_root)
    
    # Define a test directory for outputs
    test_dir = project_root # Or a specific subdirectory like os.path.join(project_root, "test_output")
    
    # Create valid dummy image
    test_img = os.path.join(project_root, "test_image.jpg")
    create_dummy_image(test_img)
    
    # 1. Preprocess
    processed = engine.preprocess_media([test_img])
    print(f"Processed media: {processed}")
    
    # 2. Generate Props
    print("2. Generating props...")
    theme_config = {
        "theme": "Slideshow",
        "duration": 2.0,
        "transition": 0.5
    }
    props_path = engine.generate_props(processed, "Integration Test Video", theme_config)
    print(f"Props generated at: {props_path}")
    
    # 3. Test Smart Conversion Logic (ConverterEngine)
    print("3. Testing ConverterEngine...")
    try:
        from MediaConverter_Pro import ConverterEngine
        converter = ConverterEngine()
        
        # Test detection
        if converter.is_supported(test_img):
            print(f"Converter incorrectly flagged JPG as supported/needing conversion.")
        
        # Create a dummy TIFF to test conversion
        tiff_path = os.path.join(test_dir, "test.tiff")
        try:
            from PIL import Image
            img = Image.new('RGB', (100, 100), color = 'blue')
            img.save(tiff_path)
            
            if converter.is_supported(tiff_path):
                print("Converter correctly identified TIFF.")
                target = converter.get_target_path(tiff_path, test_dir)
                success, msg = converter.convert_file(tiff_path, target)
                if success and os.path.exists(target):
                     print(f"Converter successfully converted TIFF to {target}")
                else:
                     print(f"Converter failed: {msg}")
            else:
                print("Converter failed to identify TIFF.")
        except ImportError:
            print("Skipping TIFF test (Pillow not installed)")

    except ImportError:
        print("Could not import MediaConverter_Pro. Is it in the path?")

    # 4. Render (Existing logic)
    print("4. Rendering...")
    output_path = os.path.join(test_dir, "output_test_video.mp4")
    result = engine.render("Slideshow", output_path)

    if result:
        print(f"SUCCESS! Video rendered to: {result}")
        # Build props path again just to show where it is
        props_path = os.path.join(test_dir, "_engine", "input_props.json")
        print(f"Check {props_path} to see the relative paths.")
    else:
        print("FAILURE: Rendering failed.")

if __name__ == "__main__":
    run_test()
