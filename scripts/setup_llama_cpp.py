import os
import subprocess
import sys

def get_gpu_vendor():
    try:
        cmd = 'powershell -NoProfile -Command "Get-CimInstance -ClassName Win32_VideoController | Select-Object -ExpandProperty Name"'
        output = subprocess.check_output(cmd, shell=True, universal_newlines=True)
        print(f"[硬件信息] {output.strip()}")
        output_lower = output.lower()
        if "nvidia" in output_lower:
            return "nvidia"
        elif "amd" in output_lower or "radeon" in output_lower:
            return "amd"
        elif "intel" in output_lower:
            return "intel"
    except Exception as e:
        print(f"检测显卡失败: {e}")
    return "unknown"

def main():
    print("=" * 60)
    print("自动检测并安装 llama-cpp-python (GPU 加速版)")
    print("=" * 60)
    
    vendor = get_gpu_vendor()
    
    env = os.environ.copy()
    
    if vendor == "nvidia":
        print("-> 为 NVIDIA 显卡配置 CUDA 编译标志 (-DGGML_CUDA=on)")
        env["CMAKE_ARGS"] = "-DGGML_CUDA=on"
    elif vendor == "amd":
        print("-> 为 AMD 显卡配置 Vulkan 编译标志 (-DGGML_VULKAN=on)")
        env["CMAKE_ARGS"] = "-DGGML_VULKAN=on"
    elif vendor == "intel":
        print("-> 为 Intel 显卡配置 Vulkan 编译标志 (-DGGML_VULKAN=on)")
        env["CMAKE_ARGS"] = "-DGGML_VULKAN=on"
    else:
        print("-> 未识别到特定显卡，默认尝试使用 Vulkan 编译标志")
        env["CMAKE_ARGS"] = "-DGGML_VULKAN=on"
    
    print("\n[开始编译安装] 正在调用 pip 安装，可能需要数分钟时间，请耐心等待...")
    
    cmd = [
        sys.executable, "-m", "pip", "install", "llama-cpp-python",
        "--upgrade", "--force-reinstall", "--no-cache-dir"
    ]
    
    try:
        # 使用 Popen 来实时输出日志
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace"
        )
        for line in process.stdout:
            print(line, end="")
        process.wait()
        if process.returncode == 0:
            print("\n[成功] llama-cpp-python (GPU 加速版) 安装完成！")
        else:
            print(f"\n[失败] 安装返回非零状态码: {process.returncode}")
            print("提示：如果编译失败，请确保您的电脑上已安装 'CMake' 以及 'Visual Studio C++ 生成工具'。")
            if vendor == "nvidia":
                print("并且已安装 'CUDA Toolkit'。")
            else:
                print("并且已安装 'Vulkan SDK'。")
    except Exception as e:
        print(f"\n[异常] 安装过程中发生错误: {e}")

if __name__ == "__main__":
    main()
