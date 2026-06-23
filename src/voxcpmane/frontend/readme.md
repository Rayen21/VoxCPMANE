# VoxCPMANE 完整安装指南

> 适用：macOS（Apple Silicon，M1/M2/M3/M4），使用 Conda 管理 Python 环境  
> 目标：在本地跑起 `VoxCPM2 TTS`（CoreML / Apple Neural Engine 加速）

---

## 0. 系统要求

- macOS 12+（Apple Silicon，ARM64）
- 已装 Xcode Command Line Tools（`xcode-select --install`）
- 磁盘 ≥ 10 GB（CoreML 模型下载）
- 内存 ≥ 16 GB（推理时峰值）
- 网络：能访问 Hugging Face / ModelScope

---

## 1. 路径 A：已经装了 Conda

跳过这一步，直接看「3. 安装项目」。

## 1. 路径 B：还没装 Conda

### 1.1 推荐：Miniforge3（最轻，Apple Silicon 原生）

```bash
# ARM64 Mac 用这个
curl -L -o /tmp/miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh
bash /tmp/miniforge.sh -b -p "$HOME/miniforge3"
# 写入 shell 初始化（zsh 是 macOS 默认）
"$HOME/miniforge3/bin/conda" init zsh
# 让当前 shell 生效
source ~/.zshrc
# 验证
conda --version
```

### 1.2 备选：Miniconda

```bash
curl -L -o /tmp/miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh
bash /tmp/miniconda.sh -b -p "$HOME/miniconda3"
"$HOME/miniconda3/bin/conda" init zsh
source ~/.zshrc
conda --version
```

---

## 2. 创建 Conda 虚拟环境

```bash
# 创建名为 voxcpmane 的环境，Python 3.11（CoreML 工具链兼容性最佳）
conda create -n voxcpmane python=3.11 -y
conda activate voxcpmane
```

确认激活成功（终端提示前面应出现 `(voxcpmane)`）。

---

## 2.5 M1 Max 用户必看 ⚠️

原作者在 0.1.3b1 之前的版本对 **M1 Max** 推理有 ANE/CoreML 路径 bug，必须装 beta 版：

```bash
conda activate voxcpmane
conda install -y -c conda-forge "python>=3.10,<3.13" numpy=2.4 scipy=1.17
pip install --prerelease allow -U -r requirements_m1max.txt
```

注意：
- `--prerelease allow` 必带，否则 pip 默认跳过 beta 版
- 用专门的 `requirements_m1max.txt`（不是通用的 `requirements.txt`），里面把 `voxcpmane2` 锁死成 `0.1.3b1`
- 验证：`pip show voxcpmane2` 应显示 `Version: 0.1.3b1`

不是 M1 Max 的用户请用通用的 `requirements.txt`（即下文的第 3 节）。

---

## 3. 安装项目依赖

### 3.1 先装系统级科学计算包（conda-forge，coremltools 编译更稳）

```bash
conda install -y -c conda-forge numpy=2.4 scipy=1.17
```

### 3.2 装 PyTorch（CPU 即可，CoreML 跑在 ANE 上）

```bash
pip install torch==2.12.1 torchaudio==2.11.0 torch-complex==0.4.4
```

### 3.3 装 CoreML 工具链

```bash
pip install coremltools==9.0
```

### 3.4 装 Hugging Face / ModelScope / FunASR

```bash
pip install huggingface_hub==1.19.0 modelscope==1.37.1 funasr==1.3.11
```

### 3.5 装后端 + 代理服务需要的 web 框架

```bash
pip install fastapi==0.137.0 uvicorn==0.49.0 httpx==0.28.1
```

### 3.6 装音频处理

```bash
pip install soundfile==0.14.0 librosa==0.11.0
```

### 3.7 装 VoxCPMANE 包本体

```bash
pip install voxcpmane
# 这会装好 server.py + 一键 CLI：voxcpmmane2-server
```

---

## 4. requirements.txt（保存为 `voxcpmane_requirements.txt`）

```text
# Python 3.11
# Core scientific stack (建议从 conda-forge 装，pip 装的也行)
numpy==2.4.6
scipy==1.17.1

# PyTorch (CPU build, CoreML 跑在 ANE)
torch==2.12.1
torchaudio==2.11.0
torch-complex==0.4.4

# CoreML toolchain
coremltools==9.0

# Hugging Face / ModelScope / FunASR
huggingface_hub==1.19.0
modelscope==1.37.1
funasr==1.3.11

# Web framework（后端 + 代理）
fastapi==0.137.0
uvicorn==0.49.0
httpx==0.28.1

# Audio I/O
soundfile==0.14.0
librosa==0.11.0

# VoxCPMANE 本体（pip install voxcpmane）
voxcpmane
```

### 4.1 一键安装方式（推荐）

保存上面内容为 `voxcpmane_requirements.txt`，然后：

```bash
conda activate voxcpmane

# 1) conda 优先装这两个
conda install -y -c conda-forge numpy=2.4 scipy=1.17

# 2) pip 装剩下的
pip install -r voxcpmane_requirements.txt
```

---

## 5. 启动项目

```bash
conda activate voxcpmane

# 后端（:8000）
voxcpmmane2-server --split-base-lm

# 另开一个终端：代理（:8001）+ 服务前端
conda activate voxcpmane
cd /path/to/proxy/dir    # 一般是 site-packages/voxcpmane/frontend
python proxy_server.py
```

打开浏览器：`http://127.0.0.1:8001/`

---

## 6. 一键启动脚本（推荐用这个，不用每次手敲）

把 [voxcpmane_start.sh] 和 [voxcpmane_stop.sh] 放到 `~/Desktop/`，chmod +x 后双击或在终端跑。

> 脚本内容见仓库 `scripts/` 目录或对话里我给你写过的版本。

---

## 7. 故障排查

### 7.1 `conda activate voxcpmane` 失败
```bash
conda env list    # 确认 env 存在
# 如果不存在，重做第 2 步
```

### 7.2 `voxcpmmane2-server: command not found`
说明 voxcpmane 没装到当前 env：
```bash
conda activate voxcpmane
pip show voxcpmane     # 确认装了
# 没装的话：
pip install voxcpmane
```

### 7.3 FunASR 转录失败：`[Errno 2] No such file or directory: 'ffmpeg'`
- 终极克隆模式下需要 ffmpeg 解码 m4a/mp3
- 解决 A：上传 wav 文件（推荐）
- 解决 B：`brew install ffmpeg`

### 7.4 后端启动报 "scikit-learn version not supported"
正常 warning，不影响使用。`coremltools` 的 sklearn 转换 API 被禁用，但 CoreML 推理本身不受影响。

### 7.5 浏览器打开是 `file://` 而不是 `http://127.0.0.1:8001/`
代理没在跑或 `proxy_server.py` 没加 `serve_index` 路由。检查 `proxy_server.py` 是否有：
```python
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
```

### 7.6 端口 8000 / 8001 被占用
```bash
lsof -ti:8000 | xargs kill -9
lsof -ti:8001 | xargs kill -9
```

---

## 8. 升级

```bash
conda activate voxcpmane
pip install --upgrade voxcpmane
# 看 release notes 决定要不要升其它依赖
```

---

## 9. 卸载

```bash
conda deactivate
conda env remove -n voxcpmane
# 删模型缓存（可选，省 5GB+）
rm -rf ~/.cache/huggingface/hub/models--seba--*
```
