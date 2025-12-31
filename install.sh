#!/bin/sh
# Passwall2 批量导入工具 - 一键安装脚本

echo "====================================="
echo "Passwall2 批量导入工具 - 一键安装"
echo "====================================="

# 下载 IPK
echo "正在下载安装包..."
wget -q --show-progress -O /tmp/passwall2-batch.ipk "https://cdn.jsdelivr.net/gh/ChunKitGitHub/passwall2-batch@main/passwall2-batch_latest.ipk"

if [ ! -f /tmp/passwall2-batch.ipk ]; then
    echo "下载失败，请检查网络连接"
    exit 1
fi

# 安装
echo "正在安装..."
opkg install --force-reinstall /tmp/passwall2-batch.ipk

if [ $? -eq 0 ]; then
    echo ""
    echo "====================================="
    echo "安装成功！"
    echo "====================================="
    echo ""
    echo "访问方式："
    echo "  1. LuCI 菜单: 服务 -> Passwall2 批量导入"
    echo "  2. 直接访问: http://$(uci get network.lan.ipaddr 2>/dev/null || echo '路由器IP'):8099"
    echo ""
else
    echo "安装失败"
    exit 1
fi

# 清理
rm -f /tmp/passwall2-batch.ipk
