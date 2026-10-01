#!/data/data/com.termux/files/usr/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Zeline local dev — nyalain gateway (:8082) + frontend (:5173) sekaligus.
#
#   bash ~/zeline-frontend/start.sh
#
# Gateway  : agent runtime asli, 44 tool, loopback allowlist aktif.
# Frontend : app Zeline + /demo.html (88 label / 12 state / 44 tool).
# ─────────────────────────────────────────────────────────────────────────────
set -u
DIR="/data/data/com.termux/files/home/zeline-frontend"
LOG="$HOME/.zeline"

mkdir -p "$LOG"

stop_old() {
  pkill -f "run_zeline_gateway.py" 2>/dev/null
  pkill -f "python server.py" 2>/dev/null
  sleep 2
}

wait_port() {
  # $1=port  $2=nama  tunggu max 15s
  for _ in $(seq 1 30); do
    if python3 -c "import socket,sys; s=socket.socket(); s.settimeout(.3); sys.exit(0 if s.connect_ex(('127.0.0.1',$1))==0 else 1)" 2>/dev/null; then
      echo "  OK  :$1  $2"
      return 0
    fi
    sleep 0.5
  done
  echo "  FAIL :$1  $2 (cek $LOG/zeline-gateway-8082.log)"
  return 1
}

echo "[zeline] stop instance lama..."
stop_old

echo "[zeline] start gateway :8082 (44 tool, loopback on)..."
cd "$DIR"
ZELINE_ALLOW_LOOPBACK=1 nohup python run_zeline_gateway.py > "$LOG/zeline-gateway-8082.log" 2>&1 &
sleep 1

echo "[zeline] start frontend :5173..."
ZELINE_APP_UPSTREAM=http://127.0.0.1:8082 ZELINE_FE_PORT=5173 \
  nohup python server.py > "$LOG/zeline-fe.log" 2>&1 &
sleep 1

echo "[zeline] tunggu siap..."
wait_port 8082 "gateway"
wait_port 5173 "frontend"

echo ""
echo "[zeline] siap:"
echo "  app     : http://localhost:5173"
echo "  demo    : http://localhost:5173/demo.html"
echo "  gateway : http://127.0.0.1:8082/api/v1/health"
