import os
import urllib.request
import sys

def download_model():
    model_dir = "models"
    model_name = "nomic-embed-text-v1.5.Q4_K_M.gguf"
    model_path = os.path.join(model_dir, model_name)
    
    # 使用国内镜像加速下载
    url = f"https://hf-mirror.com/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/{model_name}"

    if not os.path.exists(model_dir):
        os.makedirs(model_dir)
        print(f"[系统] 已创建 {model_dir}/ 文件夹")

    if os.path.exists(model_path):
        print(f"[系统] 模型 {model_name} 已存在，跳过下载。")
        return

    print(f"============================================================")
    print(f"正在从 HF 镜像下载向量模型 (约 90 MB)，请耐心等待...")
    print(f"下载链接: {url}")
    print(f"保存路径: {model_path}")
    print(f"============================================================")

    try:
        def reporthook(blocknum, blocksize, totalsize):
            readsofar = blocknum * blocksize
            if totalsize > 0:
                percent = readsofar * 100 / totalsize
                s = f"\r下载进度: {percent:5.1f}% [{readsofar / (1024*1024):.2f} MB / {totalsize / (1024*1024):.2f} MB]"
                sys.stdout.write(s)
                if readsofar >= totalsize:
                    sys.stdout.write("\n")
            else:
                sys.stdout.write(f"\r已下载: {readsofar / (1024*1024):.2f} MB")
                
        urllib.request.urlretrieve(url, model_path, reporthook)
        print(f"\n[成功] 模型下载完成，已存入 {model_path}")
    except Exception as e:
        print(f"\n[失败] 下载过程中发生错误: {e}")
        print("请手动前往浏览器下载，并放入 models 文件夹下：")
        print("https://hf-mirror.com/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q4_K_M.gguf")

if __name__ == "__main__":
    download_model()
