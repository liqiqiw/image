# 人像照片智能裁剪工具 - 打包说明

## 功能说明

这是一个带 GUI 界面的人像照片智能裁剪工具，支持：

- 选择输入/输出文件夹
- 自定义上下左右留白参数（百分比）
- 实时显示处理日志
- 支持中断处理
- 使用 MediaPipe 进行人体检测，智能裁剪为 1200x1600 竖版照片

## 在 Windows 上打包成 exe

### 方法一：使用命令行

1. 确保在 Windows 环境下
2. 安装依赖：
   ```bash
   uv sync
   ```

3. 运行打包命令：
   ```bash
   uv run pyinstaller build_exe.spec --clean
   ```

4. 打包完成后，exe 文件在 `dist/人像照片智能裁剪工具.exe`

### 方法二：使用打包脚本

在 Windows 的 Git Bash 或 WSL 中运行：
```bash
bash build_windows.sh
```

## 文件说明

- `crop_portrait_gui.py` - GUI 主程序
- `crop_portrait.py` - 命令行版本（原始版本）
- `pose_landmarker.task` - MediaPipe 人体检测模型（必需）
- `build_exe.spec` - PyInstaller 打包配置
- `build_windows.sh` - 自动打包脚本

## 使用说明

### GUI 版本

直接运行：
```bash
uv run python crop_portrait_gui.py
```

或双击打包后的 exe 文件。

### 命令行版本

```bash
uv run python crop_portrait.py
```

## 注意事项

1. 打包必须在 Windows 环境下进行（Windows exe 只能在 Windows 上打包）
2. 确保 `pose_landmarker.task` 模型文件存在
3. 首次打包可能需要较长时间下载依赖
4. 打包后的 exe 文件较大（约 100-200MB），因为包含了完整的 Python 运行时和所有依赖库

## 跨平台打包

- Windows exe: 必须在 Windows 上打包
- macOS app: 必须在 macOS 上打包
- Linux binary: 必须在 Linux 上打包

当前你在 macOS 上，如果需要 Windows exe，需要：
1. 在 Windows 虚拟机中运行
2. 使用 Windows 物理机
3. 使用 GitHub Actions 等 CI/CD 服务自动打包
