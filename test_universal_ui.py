
import tkinter as tk
from tkinter import ttk
import sys
import os

# Add parent directory to sys.path so we can import the shared _lib
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from _lib.UniversalUI import UniversalApp, ResponsiveFrame

def main():
    root = tk.Tk()
    root.geometry("600x500")
    
    app = UniversalApp(root, "UniversalUI Enhancement Demo", "ui_demo_v1")
    
    # Header
    ttk.Label(root, text="UniversalUI Professional Enhancements", font=app.font_h1).pack(pady=20)
    
    # 1. Toast Demo
    btn_frame = ttk.Frame(root)
    btn_frame.pack(pady=10)
    
    ttk.Button(btn_frame, text="Show Info Toast", command=lambda: app.show_toast("This is an info toast!")).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Show Success Toast", command=lambda: app.show_toast("Action successful!", level="success")).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Show Error Toast", command=lambda: app.show_toast("An error occurred!", level="error")).pack(side="left", padx=5)
    
    # 2. Theme Toggle Info
    ttk.Label(root, text="Press Ctrl+T to toggle Dark/Light/System modes.", foreground="#007acc").pack(pady=10)
    
    # 3. Responsive Frame Demo
    lbl_frame = ttk.LabelFrame(root, text="Responsive Layout (Try resizing window width)")
    lbl_frame.pack(fill="both", expand=True, padx=20, pady=20)
    
    resp = ResponsiveFrame(lbl_frame, threshold=400)
    resp.pack(fill="both", expand=True)
    
    # Add some widgets to responsive frame
    # Note: add_widget helper makes it easy
    resp.add_widget(ttk.Button, text="Button A")
    resp.add_widget(ttk.Button, text="Button B")
    resp.add_widget(ttk.Button, text="Button C")
    
    root.mainloop()

if __name__ == "__main__":
    main()
