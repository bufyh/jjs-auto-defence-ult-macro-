import os
import sys
import time
import ctypes
import winsound
import numpy as np
import cv2
from mss import mss
import customtkinter as ctk
import pydirectinput
from pynput import keyboard


def resource_path(p):
    return os.path.join(getattr(sys, '_MEIPASS', os.path.abspath(".")), p)


if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class status_overlay(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry("8x8+20+20")
        self.configure(fg_color="#ffffff")
        self.withdraw()


class hotkey_btn(ctk.CTkButton):
    def __init__(self, master, hotkey="f2", **kw):
        super().__init__(master, text=hotkey, fg_color="#222", hover_color="#333", **kw)
        self.hotkey = hotkey.lower()
        self.configure(command=self.listen)
        self.listening = False
        self.keys = []

    def listen(self):
        if self.listening: return
        self.listening = True
        self.keys = []
        self.configure(text="...", fg_color="#444", hover_color="#555")
        self.focus_set()
        self.bind("<Key>", self.press)
        self.bind("<KeyRelease>", self.release)
        self.bind("<Button-1>", lambda e: self.stop(True), add="+")

    def press(self, e):
        if not self.listening: return
        ks = e.keysym.lower()
        if ks == "escape": return self.stop(True)

        m = {"control_l": "ctrl", "control_r": "ctrl", "shift_l": "shift", "shift_r": "shift",
             "alt_l": "alt", "alt_r": "alt", "super_l": "win", "super_r": "win", "return": "enter"}
        c = m.get(ks, ks if len(ks) == 1 or ks.startswith("f") else ks)

        if c not in self.keys: self.keys.append(c)
        mods = [k for k in ["ctrl", "shift", "alt", "win"] if k in self.keys]
        self.hotkey = "+".join(mods + [k for k in self.keys if k not in mods])
        self.configure(text=self.hotkey)

    def release(self, e):
        if self.listening and self.hotkey: self.stop()

    def stop(self, cancel=False):
        self.unbind("<Key>")
        self.unbind("<KeyRelease>")
        self.listening = False
        self.configure(text=self.hotkey, fg_color="#222", hover_color="#333")


class region_selector(ctk.CTkToplevel):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.attributes("-fullscreen", True, "-alpha", 0.3)
        self.configure(fg_color="black")
        self.overrideredirect(True)
        self.grab_set()
        self.start_x = self.start_y = None
        self.canvas = ctk.CTkCanvas(self, cursor="cross", highlightthickness=0, bg="black")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)

    def press(self, e): self.start_x, self.start_y = e.x, e.y

    def drag(self, e):
        self.canvas.delete("box")
        self.canvas.create_rectangle(self.start_x, self.start_y, e.x, e.y, outline="#ffffff", width=1, tag="box")

    def release(self, e):
        self.destroy()
        self.callback((min(self.start_x, e.x), min(self.start_y, e.y), max(self.start_x, e.x), max(self.start_y, e.y)))


class app(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("macro")
        self.geometry("380x510")
        self.resizable(False, False)
        self.configure(fg_color="#0a0a0a")

        try:
            self.iconbitmap(resource_path("favicon.ico"))
        except:
            pass

        self.running = False
        self.sct = mss()
        self.overlay = status_overlay(self)
        self.show_overlay = ctk.BooleanVar(value=True)
        self.templates = {}

        for img, key in {"imageA.png": "a", "imageD.png": "d", "imageW.png": "w"}.items():
            im = cv2.imread(resource_path(img), cv2.IMREAD_GRAYSCALE)
            if im is not None: self.templates[img] = {"img": im, "key": key}

        self.cooldown = ctk.StringVar(value="0.05")
        self.confidence = ctk.StringVar(value="0.65")
        self.x1, self.y1, self.x2, self.y2 = (ctk.StringVar(value=v) for v in ["936", "810", "987", "870"])

        self.setup_ui()
        self.listener = None
        self.bind_keys()

    def setup_ui(self):
        opts = {"fg_color": "transparent"}

        hk_frame = ctk.CTkFrame(self, fg_color="#121212", corner_radius=6)
        hk_frame.pack(fill="x", padx=16, pady=(16, 8))

        r1 = ctk.CTkFrame(hk_frame, **opts);
        r1.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(r1, text="toggle:").pack(side="left")
        self.btn_toggle = hotkey_btn(r1, "f2", width=80, height=24);
        self.btn_toggle.pack(side="right")

        r2 = ctk.CTkFrame(hk_frame, **opts);
        r2.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(r2, text="hide:").pack(side="left")
        self.btn_hide = hotkey_btn(r2, "f3", width=80, height=24);
        self.btn_hide.pack(side="right")

        ctk.CTkButton(hk_frame, text="apply", height=24, fg_color="#222", hover_color="#333",
                      command=self.bind_keys).pack(fill="x", padx=12, pady=(4, 12))

        set_frame = ctk.CTkFrame(self, fg_color="#121212", corner_radius=6)
        set_frame.pack(fill="x", padx=16, pady=8)

        s1 = ctk.CTkFrame(set_frame, **opts);
        s1.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(s1, text="cooldown:").pack(side="left")
        ctk.CTkEntry(s1, textvariable=self.cooldown, width=50, height=24, fg_color="#1a1a1a", border_width=0).pack(
            side="right")

        s2 = ctk.CTkFrame(set_frame, **opts);
        s2.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(s2, text="confidence:").pack(side="left")
        ctk.CTkEntry(s2, textvariable=self.confidence, width=50, height=24, fg_color="#1a1a1a", border_width=0).pack(
            side="right")

        s3 = ctk.CTkFrame(set_frame, **opts);
        s3.pack(fill="x", padx=12, pady=(4, 12))
        ctk.CTkLabel(s3, text="overlay:").pack(side="left")
        ctk.CTkSwitch(s3, text="", variable=self.show_overlay, command=self.toggle_overlay, width=40).pack(side="right")

        reg_frame = ctk.CTkFrame(self, fg_color="#121212", corner_radius=6)
        reg_frame.pack(fill="x", padx=16, pady=8)

        c_row = ctk.CTkFrame(reg_frame, **opts)
        c_row.pack(fill="x", padx=12, pady=(12, 0))
        for lbl, var in zip(["x1", "y1", "x2", "y2"], [self.x1, self.y1, self.x2, self.y2]):
            ctk.CTkLabel(c_row, text=lbl, text_color="#777").pack(side="left", padx=(0, 4))
            ctk.CTkEntry(c_row, textvariable=var, width=42, height=24, fg_color="#1a1a1a", border_width=0).pack(
                side="left", padx=(0, 6))

        ctk.CTkButton(reg_frame, text="select area", height=24, fg_color="#222", hover_color="#333",
                      command=self.select_area).pack(fill="x", padx=12, pady=12)

        self.btn_main = ctk.CTkButton(self, text="start", height=32, fg_color="#ededed",
                                      text_color="#0a0a0a", hover_color="#ffffff", command=self.toggle_macro)
        self.btn_main.pack(fill="x", padx=16, pady=(12, 0))

        self.status_lbl = ctk.CTkLabel(self, text="ready.", text_color="#555")
        self.status_lbl.pack(pady=8)

    def toggle_overlay(self):
        if self.running and self.show_overlay.get():
            self.overlay.deiconify()
        else:
            self.overlay.withdraw()

    def bind_keys(self):
        if self.listener:
            try:
                self.listener.stop()
            except:
                pass

        def format_key(hk):
            m = {"ctrl": "<ctrl>", "alt": "<alt>", "shift": "<shift>", "win": "<cmd>"}
            return "+".join([m.get(p, f"<{p}>" if len(p) > 1 else p) for p in hk.split("+")])

        try:
            self.listener = keyboard.GlobalHotKeys({
                format_key(self.btn_toggle.hotkey): lambda: self.after(0, self.toggle_macro),
                format_key(self.btn_hide.hotkey): lambda: self.after(0, self.toggle_window)
            })
            self.listener.start()
            self.status_lbl.configure(text="hotkeys applied.")
        except:
            self.status_lbl.configure(text="error binding.")

    def toggle_window(self):
        try:
            winsound.Beep(750, 80)
        except:
            pass
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.deiconify(); self.lift(); self.focus_force()

    def select_area(self):
        if self.running: self.toggle_macro()
        region_selector(lambda c: [v.set(str(n)) for v, n in zip([self.x1, self.y1, self.x2, self.y2], c)])

    def toggle_macro(self):
        self.running = not self.running
        if self.running:
            try:
                winsound.Beep(1200, 100)
            except:
                pass
            if self.show_overlay.get(): self.overlay.deiconify()
            self.btn_main.configure(text="stop", fg_color="#333", text_color="#fff")
            self.status_lbl.configure(text="running.")
            self.scan()
        else:
            try:
                winsound.Beep(500, 100)
            except:
                pass
            self.overlay.withdraw()
            self.btn_main.configure(text="start", fg_color="#ededed", text_color="#0a0a0a")
            self.status_lbl.configure(text="stopped.")

    def scan(self):
        if not self.running: return
        try:
            x, y, x2, y2 = int(self.x1.get()), int(self.y1.get()), int(self.x2.get()), int(self.y2.get())
            w, h = x2 - x, y2 - y
            th = float(self.confidence.get())
            cd = int(float(self.cooldown.get()) * 1000)

            if w > 0 and h > 0:
                frm = cv2.cvtColor(np.array(self.sct.grab({"left": x, "top": y, "width": w, "height": h})),
                                   cv2.COLOR_BGRA2GRAY)
                for d in self.templates.values():
                    t = d["img"]
                    if frm.shape[0] < t.shape[0] or frm.shape[1] < t.shape[1]: continue
                    _, val, _, _ = cv2.minMaxLoc(cv2.matchTemplate(frm, t, cv2.TM_CCOEFF_NORMED))
                    if val >= th:
                        k = d["key"]
                        pydirectinput.keyDown(k)
                        self.after(50, lambda: pydirectinput.keyUp(k))
                        self.after(cd, self.scan)
                        return
        except:
            pass
        self.after(1, self.scan)


if __name__ == "__main__":
    app().mainloop()