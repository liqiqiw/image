"""
人像照片智能裁剪工具 - GUI 版本
通过临时日志文件与 worker 子进程通信，避免 stdout 被 MediaPipe 污染。
打包后通过 --worker 参数让 exe 以 worker 模式启动子进程。
"""

import os
import sys
import json
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from pathlib import Path
from PIL import Image, ImageTk, ImageOps


class PreviewWindow:
    """预览窗口：显示原图 + 可拖动/缩放的裁剪框"""

    MAX_DISPLAY = 800  # 预览窗口最大尺寸

    EDGE_THRESHOLD = 12  # 像素，鼠标距边缘多近算"在边上"

    def __init__(self, parent, filepath, crop_box, img_w, img_h, on_confirm, on_skip, target_ratio=0.75):
        self.on_confirm = on_confirm
        self.on_skip = on_skip
        self.img_w = img_w
        self.img_h = img_h
        self.crop_box = list(crop_box)  # [left, top, right, bottom]
        self.target_ratio = target_ratio  # w/h ratio
        self.drag_mode = None  # 'move' or 'edge_l/r/t/b'
        self.drag_start = None

        # 加载图片
        img = Image.open(filepath)
        img = ImageOps.exif_transpose(img).convert("RGB")

        # 计算缩放比例
        self.scale = min(self.MAX_DISPLAY / img_w, self.MAX_DISPLAY / img_h, 1.0)
        disp_w = int(img_w * self.scale)
        disp_h = int(img_h * self.scale)
        self.disp_img = img.resize((disp_w, disp_h), Image.LANCZOS)

        # 创建窗口
        self.win = tk.Toplevel(parent)
        self.win.title(f"预览 - {os.path.basename(filepath)}")
        self.win.grab_set()

        self.canvas = tk.Canvas(self.win, width=disp_w, height=disp_h)
        self.canvas.pack()

        self.tk_img = ImageTk.PhotoImage(self.disp_img)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)

        # 画裁剪框
        self.rect_id = self.canvas.create_rectangle(
            *self._box_to_display(), outline='red', width=2)

        # 三等分构图辅助线
        self.grid_lines = []
        for i in range(1, 3):
            self.grid_lines.append(self.canvas.create_line(0, 0, 0, 0, fill='#FFD700', width=1, dash=(4, 4)))  # 横线
            self.grid_lines.append(self.canvas.create_line(0, 0, 0, 0, fill='#FFD700', width=1, dash=(4, 4)))  # 竖线
        self._update_grid()

        # 按钮
        bf = tk.Frame(self.win, pady=8)
        bf.pack()
        tk.Button(bf, text="确认裁剪", command=self._confirm,
                  bg='#4CAF50', fg='white', font=('Arial', 10, 'bold'),
                  width=12, height=2).pack(side=tk.LEFT, padx=10)
        tk.Button(bf, text="跳过", command=self._skip,
                  bg='#999', fg='white', font=('Arial', 10, 'bold'),
                  width=12, height=2).pack(side=tk.LEFT, padx=10)

        # 提示
        tk.Label(self.win, text="拖动中间移动 | 拖动边缘缩放（保持3:4比例）",
                 font=('Arial', 9), fg='#666').pack(pady=2)

        # 鼠标事件
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def _box_to_display(self):
        """原图坐标 -> 显示坐标"""
        l, t, r, b = self.crop_box
        return l * self.scale, t * self.scale, r * self.scale, b * self.scale

    def _update_rect(self):
        self.canvas.coords(self.rect_id, *self._box_to_display())
        self._update_grid()

    def _update_grid(self):
        """更新三等分构图辅助线"""
        dl, dt, dr, db = self._box_to_display()
        w, h = dr - dl, db - dt
        idx = 0
        for i in range(1, 3):
            # 横线
            y = dt + h * i / 3
            self.canvas.coords(self.grid_lines[idx], dl, y, dr, y)
            idx += 1
            # 竖线
            x = dl + w * i / 3
            self.canvas.coords(self.grid_lines[idx], x, dt, x, db)
            idx += 1

    def _clamp_box(self):
        """确保裁剪框不超出图片边界"""
        l, t, r, b = self.crop_box
        w, h = r - l, b - t
        if l < 0:
            l, r = 0, w
        if t < 0:
            t, b = 0, h
        if r > self.img_w:
            l, r = self.img_w - w, self.img_w
        if b > self.img_h:
            t, b = self.img_h - h, self.img_h
        self.crop_box = [max(0, l), max(0, t), min(self.img_w, r), min(self.img_h, b)]

    def _hit_test(self, mx, my):
        """判断鼠标在裁剪框的哪个部分：边缘还是内部"""
        dl, dt, dr, db = self._box_to_display()
        th = self.EDGE_THRESHOLD
        on_left = abs(mx - dl) < th and dt - th < my < db + th
        on_right = abs(mx - dr) < th and dt - th < my < db + th
        on_top = abs(my - dt) < th and dl - th < mx < dr + th
        on_bottom = abs(my - db) < th and dl - th < mx < dr + th
        if on_left:
            return 'edge_l'
        if on_right:
            return 'edge_r'
        if on_top:
            return 'edge_t'
        if on_bottom:
            return 'edge_b'
        if dl < mx < dr and dt < my < db:
            return 'move'
        return None

    def _on_motion(self, event):
        """鼠标移动时更新光标样式"""
        hit = self._hit_test(event.x, event.y)
        if hit in ('edge_l', 'edge_r'):
            self.canvas.config(cursor="sb_h_double_arrow")
        elif hit in ('edge_t', 'edge_b'):
            self.canvas.config(cursor="sb_v_double_arrow")
        elif hit == 'move':
            self.canvas.config(cursor="fleur")
        else:
            self.canvas.config(cursor="arrow")

    def _on_press(self, event):
        self.drag_mode = self._hit_test(event.x, event.y)
        self.drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self.drag_start is None or self.drag_mode is None:
            return
        dx = (event.x - self.drag_start[0]) / self.scale
        dy = (event.y - self.drag_start[1]) / self.scale

        if self.drag_mode == 'move':
            self.crop_box[0] += dx
            self.crop_box[1] += dy
            self.crop_box[2] += dx
            self.crop_box[3] += dy
            self._clamp_box()
        elif self.drag_mode.startswith('edge_'):
            self._resize_edge(self.drag_mode, dx, dy)

        self._update_rect()
        self.drag_start = (event.x, event.y)

    def _on_release(self, event):
        self.drag_mode = None
        self.drag_start = None

    def _resize_edge(self, edge, dx, dy):
        """拖动边缘缩放，保持目标比例"""
        l, t, r, b = self.crop_box
        ratio = self.target_ratio
        w, h = r - l, b - t
        cx, cy = (l + r) / 2, (t + b) / 2

        if edge == 'edge_r':
            w = max(200, w + dx)
        elif edge == 'edge_l':
            w = max(200, w - dx)
        elif edge == 'edge_b':
            h = max(200 / ratio, h + dy)
            w = h * ratio
        elif edge == 'edge_t':
            h = max(200 / ratio, h - dy)
            w = h * ratio

        # 保持比例
        if edge in ('edge_l', 'edge_r'):
            h = w / ratio

        w = max(200, min(w, self.img_w))
        h = max(200 / ratio, min(h, self.img_h))
        if w / h > ratio:
            w = h * ratio
        else:
            h = w / ratio

        self.crop_box = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
        self._clamp_box()
        self._update_rect()

    def _confirm(self):
        box = [int(v) for v in self.crop_box]
        self.win.destroy()
        self.on_confirm(box)

    def _skip(self):
        self.win.destroy()
        self.on_skip()


class CropPortraitGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("人像照片智能裁剪工具")
        self.root.geometry("700x720")
        self.worker_proc = None
        self.is_running = False
        self.log_file = None
        self.log_pos = 0
        self.response_file = None
        self.src_dir = tk.StringVar(value=str(Path.home() / "Desktop" / "imageSrc"))
        self.out_dir = tk.StringVar(value=str(Path.home() / "Desktop" / "imageOut"))
        self.padding_top = tk.StringVar(value="10")
        self.padding_bottom = tk.StringVar(value="2")
        self.padding_left = tk.StringVar(value="0")
        self.padding_right = tk.StringVar(value="0")
        self.auto_level = tk.BooleanVar(value=False)
        self.knee_foot_mode = tk.BooleanVar(value=False)
        self.crop_ratio = tk.StringVar(value="3:4")  # "3:4" = 1200x1600, "1:1" = 1600x1600
        self.status_var = tk.StringVar(value="就绪")
        self.setup_ui()

    def setup_ui(self):
        f1 = tk.Frame(self.root, padx=10, pady=5)
        f1.pack(fill=tk.X)
        tk.Label(f1, text="输入文件夹:", width=12, anchor='w').pack(side=tk.LEFT)
        tk.Entry(f1, textvariable=self.src_dir, width=50).pack(side=tk.LEFT, padx=5)
        tk.Button(f1, text="浏览...", command=self.browse_src).pack(side=tk.LEFT)

        f2 = tk.Frame(self.root, padx=10, pady=5)
        f2.pack(fill=tk.X)
        tk.Label(f2, text="输出文件夹:", width=12, anchor='w').pack(side=tk.LEFT)
        tk.Entry(f2, textvariable=self.out_dir, width=50).pack(side=tk.LEFT, padx=5)
        tk.Button(f2, text="浏览...", command=self.browse_out).pack(side=tk.LEFT)

        f3 = tk.Frame(self.root, padx=10, pady=10)
        f3.pack(fill=tk.X)
        tk.Label(f3, text="留白参数 (%):", font=('Arial', 10, 'bold')).pack(anchor='w')
        pf = tk.Frame(f3)
        pf.pack(fill=tk.X, pady=5)
        for i, (label, var) in enumerate([
            ("上:", self.padding_top), ("下:", self.padding_bottom),
            ("左:", self.padding_left), ("右:", self.padding_right),
        ]):
            row, col = divmod(i, 2)
            tk.Label(pf, text=label, width=6).grid(row=row, column=col * 2)
            tk.Entry(pf, textvariable=var, width=8).grid(row=row, column=col * 2 + 1, padx=5, pady=2)

        f_opt = tk.Frame(self.root, padx=10, pady=5)
        f_opt.pack(fill=tk.X)
        tk.Checkbutton(f_opt, text="启用水平矫正（基于人体中轴线自动校正倾斜）",
                       variable=self.auto_level, font=('Arial', 10)).pack(anchor='w')
        tk.Checkbutton(f_opt, text="膝盖到脚模式（以膝盖到脚部区域为画面中心）",
                       variable=self.knee_foot_mode, font=('Arial', 10),
                       command=self._toggle_ratio).pack(anchor='w')

        f_ratio = tk.Frame(f_opt, padx=20)
        f_ratio.pack(anchor='w')
        self.lbl_ratio = tk.Label(f_ratio, text="输出比例:", font=('Arial', 10))
        self.lbl_ratio.pack(side=tk.LEFT)
        self.rb_34 = tk.Radiobutton(f_ratio, text="1200×1600 (3:4)", variable=self.crop_ratio,
                                    value="3:4", font=('Arial', 10))
        self.rb_34.pack(side=tk.LEFT, padx=5)
        self.rb_11 = tk.Radiobutton(f_ratio, text="1600×1600 (1:1)", variable=self.crop_ratio,
                                    value="1:1", font=('Arial', 10))
        self.rb_11.pack(side=tk.LEFT, padx=5)
        # 默认置灰
        self._toggle_ratio()

        f4 = tk.Frame(self.root, padx=10, pady=10)
        f4.pack(fill=tk.X)
        self.btn_start = tk.Button(
            f4, text="开始处理", command=self.start_processing,
            bg='#4CAF50', fg='white', font=('Arial', 10, 'bold'), width=15, height=2)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = tk.Button(
            f4, text="中断", command=self.stop_processing,
            bg='#f44336', fg='white', font=('Arial', 10, 'bold'), width=15, height=2, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        sf = tk.Frame(self.root, padx=10)
        sf.pack(fill=tk.X)
        tk.Label(sf, textvariable=self.status_var, font=('Arial', 10), fg='#333', anchor='w').pack(fill=tk.X)

        f5 = tk.Frame(self.root, padx=10, pady=5)
        f5.pack(fill=tk.BOTH, expand=True)
        tk.Label(f5, text="执行日志:", font=('Arial', 10, 'bold')).pack(anchor='w')
        self.log_text = scrolledtext.ScrolledText(f5, height=15, width=80, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)

    def browse_src(self):
        d = filedialog.askdirectory(title="选择输入文件夹")
        if d:
            self.src_dir.set(d)

    def browse_out(self):
        d = filedialog.askdirectory(title="选择输出文件夹")
        if d:
            self.out_dir.set(d)

    def _toggle_ratio(self):
        """膝盖到脚模式开启时才能选比例，否则置灰并重置为 3:4"""
        if self.knee_foot_mode.get():
            self.rb_34.config(state=tk.NORMAL)
            self.rb_11.config(state=tk.NORMAL)
            self.lbl_ratio.config(fg='#000')
        else:
            self.crop_ratio.set("3:4")
            self.rb_34.config(state=tk.DISABLED)
            self.rb_11.config(state=tk.DISABLED)
            self.lbl_ratio.config(fg='#999')

    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def start_processing(self):
        if self.is_running:
            return
        try:
            pt = float(self.padding_top.get()) / 100
            pb = float(self.padding_bottom.get()) / 100
            pl = float(self.padding_left.get()) / 100
            pr = float(self.padding_right.get()) / 100
        except ValueError:
            messagebox.showerror("错误", "留白参数必须是数字")
            return
        src = self.src_dir.get()
        if not os.path.exists(src):
            messagebox.showerror("错误", f"输入文件夹不存在: {src}")
            return

        self.is_running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.status_var.set("正在启动...")
        self.log("启动处理...")

        fd, self.log_file = tempfile.mkstemp(suffix='.jsonl', prefix='crop_log_')
        os.close(fd)
        self.log_pos = 0

        # 膝盖到脚模式需要响应文件用于预览交互
        if self.knee_foot_mode.get():
            fd2, self.response_file = tempfile.mkstemp(suffix='.json', prefix='crop_resp_')
            os.close(fd2)
            os.remove(self.response_file)  # 先删除，worker 会轮询它的出现
        else:
            self.response_file = None

        params = json.dumps({
            "src_dir": src, "out_dir": self.out_dir.get(),
            "pad_top": pt, "pad_bottom": pb, "pad_left": pl, "pad_right": pr,
            "auto_level": self.auto_level.get(),
            "knee_foot_mode": self.knee_foot_mode.get(),
            "crop_ratio": self.crop_ratio.get(),
            "response_file": self.response_file,
        })

        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, "--worker", self.log_file, params]
        else:
            py = sys.executable
            worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crop_worker.py")
            cmd = [py, worker, self.log_file, params]

        self.worker_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.poll_log_file()

    def poll_log_file(self):
        if not self.is_running:
            return
        done = False
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                f.seek(self.log_pos)
                new_data = f.read()
                self.log_pos = f.tell()
            if new_data:
                for line in new_data.strip().split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        t = msg.get("type", "")
                        if t == "log":
                            self.log(msg["msg"])
                        elif t == "progress":
                            c, tot = msg["current"], msg["total"]
                            fn, st = msg["filename"], msg["status"]
                            self.log(f"[{c}/{tot}] {fn} - {st}")
                            self.status_var.set(f"处理中: {c}/{tot} - {fn}")
                        elif t == "preview_request":
                            self._show_preview(
                                msg["filepath"], msg["crop_box"],
                                msg["img_w"], msg["img_h"])
                        elif t == "done":
                            s = msg.get('success', 0)
                            tot = msg.get('total', 0)
                            self.status_var.set(f"完成! 成功 {s}/{tot} 张")
                            done = True
                    except json.JSONDecodeError:
                        pass
        except FileNotFoundError:
            pass

        if done:
            self.finish_processing()
            return

        if self.worker_proc and self.worker_proc.poll() is not None:
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    f.seek(self.log_pos)
                    rest = f.read()
                for line in rest.strip().split('\n'):
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.strip())
                        t = msg.get("type", "")
                        if t == "log":
                            self.log(msg["msg"])
                        elif t == "progress":
                            self.log(f"[{msg['current']}/{msg['total']}] {msg['filename']} - {msg['status']}")
                        elif t == "done":
                            s = msg.get('success', 0)
                            tot = msg.get('total', 0)
                            self.status_var.set(f"完成! 成功 {s}/{tot} 张")
                    except json.JSONDecodeError:
                        pass
            except FileNotFoundError:
                pass
            self.finish_processing()
            return

        self.root.after(200, self.poll_log_file)

    def stop_processing(self):
        if self.worker_proc and self.worker_proc.poll() is None:
            self.worker_proc.terminate()
            self.log("已中断")
            self.status_var.set("已中断")
            self.finish_processing()

    def _show_preview(self, filepath, crop_box, img_w, img_h):
        """弹出预览窗口让用户调整裁剪框"""
        self.status_var.set(f"预览: {os.path.basename(filepath)} - 请调整裁剪框")
        ratio = 1.0 if self.crop_ratio.get() == "1:1" else 1200 / 1600
        PreviewWindow(
            self.root, filepath, crop_box, img_w, img_h,
            on_confirm=lambda box: self._send_response("confirm", box),
            on_skip=lambda: self._send_response("skip", None),
            target_ratio=ratio,
        )

    def _send_response(self, action, crop_box):
        """写响应文件通知 worker"""
        if self.response_file:
            resp = {"action": action}
            if crop_box is not None:
                resp["crop_box"] = crop_box
            with open(self.response_file, 'w', encoding='utf-8') as f:
                json.dump(resp, f)

    def finish_processing(self):
        self.is_running = False
        self.worker_proc = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        for f in [self.log_file, self.response_file]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass


def main_gui():
    root = tk.Tk()
    app = CropPortraitGUI(root)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from crop_worker import main as worker_main
        worker_main()
    else:
        main_gui()
