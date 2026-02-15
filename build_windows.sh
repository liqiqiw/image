#!/bin/bash
# Windows 打包脚本（需要在 Windows 环境下运行）

echo "开始打包 Windows 可执行文件..."

# 确保模型文件存在
if [ ! -f "pose_landmarker.task" ]; then
    echo "错误: 找不到 pose_landmarker.task 模型文件"
    exit 1
fi

# 使用 PyInstaller 打包
uv run pyinstaller build_exe.spec --clean

if [ $? -eq 0 ]; then
    echo ""
    echo "打包完成!"
    echo "可执行文件位置: dist/人像照片智能裁剪工具.exe"
else
    echo "打包失败"
    exit 1
fi
