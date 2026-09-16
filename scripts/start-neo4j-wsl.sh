#!/usr/bin/env bash
# 启动 WSL Ubuntu 里的原生 Neo4j（脱离 Docker 开发环境），并把 WSL 虚拟机 IP 同步到根目录 .env
#
# 背景：Windows 的 WSL localhost 转发在本机不可靠，后端直接连 WSL 虚拟机 IP。
# WSL 每次重启后 VM IP 会变化，本脚本自动检测并更新 .env 的 NEO4J_URI。
# 改完 .env 后需要重启后端进程（uvicorn 不热载 .env）。
#
# 用法（git-bash / 任意 bash）：
#   bash scripts/start-neo4j-wsl.sh
set -e

ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"

echo "==> 检查 Neo4j 是否已在 WSL 中运行..."
if wsl -d Ubuntu -- bash -c 'ss -tln 2>/dev/null | grep -q ":7687"' 2>/dev/null; then
  echo "    Neo4j 已在运行"
else
  echo "    Neo4j 未运行，正在启动（JAVA_HOME=~/jdk-21.0.2）..."
  nohup wsl -d Ubuntu -- bash -c 'export JAVA_HOME=$HOME/jdk-21.0.2; exec $HOME/neo4j-srv/usr/share/neo4j/bin/neo4j console' \
    > "$(dirname "$0")/neo4j-wsl.log" 2>&1 &
  echo "    等待 Neo4j 启动（约 30s）..."
  for i in $(seq 1 30); do
    sleep 3
    wsl -d Ubuntu -- bash -c 'ss -tln 2>/dev/null | grep -q ":7687"' 2>/dev/null && break
  done
  wsl -d Ubuntu -- bash -c 'ss -tln 2>/dev/null | grep -q ":7687"' \
    && echo "    Neo4j 启动成功" || { echo "    Neo4j 启动失败，见 scripts/neo4j-wsl.log"; exit 1; }
fi

VM_IP=$(wsl -d Ubuntu -- hostname -I | tr -d ' \r\n' | cut -d' ' -f1)
if [ -z "$VM_IP" ]; then
  echo "!! 无法获取 WSL 虚拟机 IP"
  exit 1
fi

echo "==> WSL 虚拟机 IP: $VM_IP"
if grep -q "^NEO4J_URI=bolt://$VM_IP:7687" "$ENV_FILE"; then
  echo "    .env 已是最新，无需修改"
else
  sed -i "s|^NEO4J_URI=.*|NEO4J_URI=bolt://$VM_IP:7687|" "$ENV_FILE"
  echo "    .env NEO4J_URI 已更新为 bolt://$VM_IP:7687 —— 请重启后端进程使其生效"
fi
