"""
VoxCPM2 代理服务器 (proxy_server.py) - 终极修复版
- 彻底修复了 status 0 (浏览器解析崩溃) 的问题
- 清理了所有导致浏览器解码错误的响应头 (content-encoding, transfer-encoding 等)
"""

from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, FileResponse
import httpx
import io
import os
import tempfile
import uuid

# ===== 配置 =====
ORIGINAL_BACKEND = "http://localhost:8000"
PROXY_PORT = 8001

app = FastAPI(title="VoxCPM2 Proxy Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ 直接把前端 index.html 当作 / 返回，浏览器地址栏就会显示 http://... 而不是 file://
FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(FRONTEND_DIR, "index.html")

@app.get("/")
async def serve_index():
    return FileResponse(INDEX_HTML, media_type="text/html")

# ===== 1. 初始化 FunASR =====
asr_model = None
postprocess_func = None

def load_asr_model():
    global asr_model, postprocess_func
    if asr_model is not None: return True
    try:
        print("⏳ 正在加载 FunASR SenseVoiceSmall 模型...")
        from funasr import AutoModel
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        import torch
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        asr_model = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=True, vad_model="fsmn-vad", vad_kwargs={"max_single_segment_time": 30000}, device=device)
        postprocess_func = rich_transcription_postprocess
        print(f"✅ FunASR 模型加载成功 (运行在 {device.upper()})")
        return True
    except Exception as e:
        print(f"❌ FunASR 加载失败: {e}")
        return False

# ===== 2. 音频转文字 =====
@app.post("/v1/audio/transcribe")
async def transcribe_audio_endpoint(file: UploadFile = File(...)):
    if not load_asr_model(): raise HTTPException(status_code=500, detail="ASR 模型未加载成功")
    temp_path = None
    try:
        temp_path = os.path.join(tempfile.gettempdir(), f"trans_{uuid.uuid4()}.wav")
        with open(temp_path, "wb") as f: f.write(await file.read())
        res = asr_model.generate(input=temp_path, language="auto", use_itn=True)
        text = postprocess_func(res[0]["text"]).strip()
        print(f"✅ 转写成功：{text[:30]}...")
        return {"text": text, "status": "success"}
    except Exception as e:
        print(f"❌ 转录失败: {e}")
        raise HTTPException(status_code=500, detail=f"转录失败: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path): os.remove(temp_path)

# ===== 3. 文件上传 =====
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "voxcpm_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ✅ 早拒绝后端不可读的音频格式（m4a / mp3 / aac 等需要 ffmpeg）
# 用 soundfile 直接试读字节流；读不动就 400 拦下，避免污染后端导致流中断
_UNSUPPORTED_HINT = (
    "不支持的音频格式：{ext}。VoxCPM 后端依赖 libsndfile，仅支持 "
    "WAV / FLAC / OGG / AIFF。M4A / MP3 / AAC 需要系统安装 ffmpeg 才能转码，"
    "请把文件转成 WAV 后再上传。"
)

@app.post("/v1/audio/upload")
async def upload_audio(file: UploadFile = File(...)):
    try:
        content = await file.read()
        # ✅ 用 soundfile 试读：libsndfile 能直接解的就放行，否则 400
        try:
            import soundfile as _sf
            _sf.info(io.BytesIO(content))
        except Exception as _e:
            file_ext = os.path.splitext(file.filename)[1] or ""
            print(f"❌ 拒绝上传（格式不支持）: {file.filename} ({_e})")
            raise HTTPException(status_code=400, detail=_UNSUPPORTED_HINT.format(ext=file_ext or "未知"))

        file_ext = os.path.splitext(file.filename)[1] or ".wav"
        file_path = os.path.join(UPLOAD_DIR, f"ref_{uuid.uuid4()}{file_ext}")
        with open(file_path, "wb") as f: f.write(content)
        print(f"📁 文件已上传至: {file_path}")
        return {"status": "success", "file_path": file_path, "filename": file.filename}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

# ===== 4. 核心代理逻辑 (终极修复版) =====
# 定义需要清理的“有毒”响应头
BAD_RESPONSE_HEADERS = [
    "content-length",       # 让 FastAPI 自动重新计算
    "content-encoding",     # ✅ 核心修复：防止浏览器尝试解压明文数据导致 status 0
    "transfer-encoding",    # ✅ 核心修复：防止分块传输冲突
    "connection",           # hop-by-hop 头
    "keep-alive",           # hop-by-hop 头
]

async def proxy_request(request: Request, method: str):
    url = f"{ORIGINAL_BACKEND}{request.url.path}"
    headers = dict(request.headers)
    # 清理请求头
    for h in ["host", "content-length", "transfer-encoding", "connection", "keep-alive", "accept-encoding"]:
        headers.pop(h, None)
    
    body = await request.body() if method in ["POST", "PUT", "PATCH"] else None

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.request(method, url, params=dict(request.query_params), headers=headers, content=body)
            
            # ✅ 彻底清理响应头，防止浏览器解析崩溃
            resp_headers = dict(response.headers)
            for h in BAD_RESPONSE_HEADERS:
                resp_headers.pop(h, None)
                
            return response.status_code, resp_headers, response.content
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"无法连接到官方后端 ({ORIGINAL_BACKEND})")

# 转发普通 TTS 请求
@app.api_route("/v1/audio/speech", methods=["POST"])
async def proxy_speech(request: Request):
    status, headers, content = await proxy_request(request, "POST")
    return Response(content=content, status_code=status, headers=headers)

# 转发取消请求
@app.api_route("/v1/audio/speech/cancel", methods=["POST"])
async def proxy_cancel(request: Request):
    status, headers, content = await proxy_request(request, "POST")
    return Response(content=content, status_code=status, headers=headers)

# 转发健康检查
@app.get("/health")
async def proxy_health():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{ORIGINAL_BACKEND}/health")
            data = res.json()
            data["proxy_status"] = "active"
            data["asr_available"] = asr_model is not None
            return data
    except:
        return {"status": "degraded", "proxy_status": "active", "backend": "unreachable"}

# 转发流式 TTS 请求
@app.api_route("/v1/audio/speech/stream", methods=["POST"])
async def proxy_speech_stream(request: Request):
    url = f"{ORIGINAL_BACKEND}{request.url.path}"
    headers = dict(request.headers)
    for h in ["host", "content-length", "transfer-encoding", "connection", "keep-alive", "accept-encoding"]:
        headers.pop(h, None)
    
    body = await request.body()
    client = httpx.AsyncClient(timeout=None)
    
    try:
        req = client.build_request("POST", url, content=body, headers=headers)
        response = await client.send(req, stream=True)
        
        if response.status_code != 200:
            error_content = await response.aread()
            await response.aclose()
            await client.aclose()
            return Response(content=error_content, status_code=response.status_code, media_type="application/json")
        
        async def stream_generator():
            try:
                async for chunk in response.aiter_bytes(): yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        # ✅ 同样清理流式响应的有毒头部
        resp_headers = {k: v for k, v in response.headers.items() if k.lower() not in BAD_RESPONSE_HEADERS}
        
        return StreamingResponse(
            stream_generator(),
            status_code=200,
            media_type=response.headers.get("content-type", "audio/pcm"),
            headers=resp_headers
        )
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=500, detail=f"代理流式请求失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("="*50)
    print("🚀 VoxCPM2 代理服务器启动准备中...")
    print(f"🎯 目标官方后端: {ORIGINAL_BACKEND}")
    print(f"📍 代理监听端口: http://localhost:{PROXY_PORT}")
    print("="*50)
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT)
