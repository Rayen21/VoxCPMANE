#!/bin/zsh
# ============================================
# VoxCPMANE 一键启动 — 前台版
#   行为：激活 conda → 后端后台跑 → 代理前台跑
#   退出：Ctrl+C 或关终端 → 全部清理掉
# ============================================

# 1. 激活 conda（绝对路径，不依赖 PATH）
source /Users/hanqingren/miniforge3/etc/profile.d/conda.sh
conda activate voxcpmane
if [ $? -ne 0 ]; then
  echo "conda activate failed"
  exit 1
fi
echo "[ok] conda activated, python: $(which python)"

# 2. 退出清理
cleanup() {
  echo ""
  echo "[stop] closing services..."
  [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
  sleep 1
  for p in 8000 8001; do
    pid=$(lsof -ti:$p 2>/dev/null)
    [ -n "$pid" ] && kill -9 $pid 2>/dev/null
  done
  echo "[stopped]"
}
trap cleanup EXIT INT TERM HUP

# 3. 启动后端（后台，日志直接打印到当前终端）
echo ""
echo "[start] backend (:8000) ..."
voxcpmane2-server --split-base-lm &
BACKEND_PID=$!
echo "  backend PID=$BACKEND_PID"

# 4. 等后端 ready
echo "[wait] backend health check..."
for i in {1..60}; do
  if curl -s -o /dev/null http://127.0.0.1:8000/health 2>/dev/null; then
    echo "  [ok] backend ready (${i}s)"
    break
  fi
  sleep 1
done

# 5. 启动代理（前台阻塞，看到的实时日志就是它）
PROXY_DIR="/Users/hanqingren/miniforge3/envs/voxcpmane/lib/python3.11/site-packages/voxcpmane/frontend"
cd "$PROXY_DIR"
echo ""
echo "[start] proxy (:8001) ..."
echo "============================================"
echo "Services ready. Opening index.html ..."
echo "Press Ctrl+C to stop everything."
echo "============================================"
# 自动打开前端（走代理，地址栏显示 http://127.0.0.1:8001/ 而不是 file://）
sleep 1  # 等代理完全就绪
open "http://127.0.0.1:8001/" 2>/dev/null || echo "[warn] failed to open browser"
python proxy_server.py
