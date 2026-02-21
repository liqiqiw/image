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


class CropPortraitGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("人像照片智能裁剪工具")
        self.root.geometry("700x680")
        self.worker_proc = None
        self.is_running = False
        self.log_file = None
        self.log_pos = 0
        self.src_dir = tk.StringVar(value=str(Path.home() / "Desktop" / "imageSrc"))
        self.out_dir = tk.StringVar(value=str(Path.home() / "Desktop" / "imageOut"))
        self.padding_top = tk.StringVar(value="10")
        self.padding_bottom = tk.StringVar(value="2")
        self.padding_left = tk.StringVar(value="0")
        self.padding_right = tk.StringVar(value="0")
        self.auto_level = tk.BooleanVar(value=False)
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
        tk.Checkbutton(f_opt, text="启用水平矫正（基于图像直线检测自动校正倾斜）",
                       variable=self.auto_level, font=('Arial', 10)).pack(anchor='w')

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
        self.log_text = scrolledtext.ScrolledText(f5, height=16, width=80, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)

    def browse_src(self):
        d = filedialog.askdirectory(title="选择输入文件夹")
        if d:
            self.src_dir.set(d)

    def browse_out(self):
        d = filedialog.askdirectory(title="选择输出文件夹")
        if d:
            self.out_dir.set(d)

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

        params = json.dumps({
            "src_dir": src, "out_dir": self.out_dir.get(),
            "pad_top": pt, "pad_bottom": pb, "pad_left": pl, "pad_right": pr,
            "auto_level": self.auto_level.get(),
        })

        # 关键：打包后用 exe 自身 + --worker 参数启动子进程
        # 开发时用 python + crop_worker.py
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

    def finish_processing(self):
        self.is_running = False
        self.worker_proc = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        if self.log_file and os.path.exists(self.log_file):
            try:
                os.remove(self.log_file)
            except OSError:
                pass


def main_gui():
    root = tk.Tk()
    app = CropPortraitGUI(root)
    root.mainloop()


if __name__ == "__main__":
    # 打包后通过 --worker 参数区分 GUI 模式和 Worker 模式
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        # Worker 模式: 参数为 --worker <log_file> <params_json>
        sys.argv = [sys.argv[0]] + sys.argv[2:]  # 去掉 --worker，让 worker 的 argv[1] argv[2] 正确
        from crop_worker import main as worker_main
        worker_main()
    else:
        main_gui()
