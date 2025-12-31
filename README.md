# Passwall2 批量导入工具

OpenWrt Passwall2 批量导入 HTTP 节点的管理工具。

## 功能

- 批量导入 HTTP 代理节点
- 自动生成分流配置
- 自动分配 SOCKS 端口
- 节点在线状态实时检测
- 支持在线更新

## 安装

```bash
# 下载 IPK
wget https://raw.githubusercontent.com/ChunKitGitHub/passwall2-batch/main/passwall2-batch_latest.ipk -O /tmp/passwall2-batch.ipk

# 安装
opkg install /tmp/passwall2-batch.ipk
```

## 访问

- LuCI 菜单：服务 -> Passwall2 批量导入
- 直接访问：http://<路由器IP>:8099

## 版本

当前版本：1.0.0
