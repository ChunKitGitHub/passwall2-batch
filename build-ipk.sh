#!/bin/bash

# 打包 ipk 脚本 - 独立 Web 应用版本
# 参考 OpenWrt 官方 ipkg-build 脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PKG_NAME="passwall2-batch"
PKG_VERSION="1.0.0"
PKG_RELEASE="2"
PKG_ARCH="all"
OUTPUT_FILE="${PKG_NAME}_${PKG_VERSION}-${PKG_RELEASE}_${PKG_ARCH}.ipk"

echo "=== 开始构建 ${OUTPUT_FILE} ==="

# 创建输出目录
mkdir -p output

# 创建临时构建目录
BUILD_DIR=$(mktemp -d)
echo "临时目录: $BUILD_DIR"

# 清理函数
cleanup() {
    rm -rf "$BUILD_DIR"
}
trap cleanup EXIT

# 创建包目录结构
PKG_DIR="$BUILD_DIR/pkg"
mkdir -p "$PKG_DIR/CONTROL"

# 复制所有文件
echo "复制文件..."
cp -r root/* "$PKG_DIR/"

# 创建 LuCI 菜单入口 (controller)
mkdir -p "$PKG_DIR/usr/lib/lua/luci/controller"
cat > "$PKG_DIR/usr/lib/lua/luci/controller/passwall2_batch.lua" << 'LUAEOF'
module("luci.controller.passwall2_batch", package.seeall)

function index()
    entry({"admin", "services", "passwall2_batch"},
          template("passwall2_batch/main"),
          _("Passwall2 批量导入"), 90)
end
LUAEOF

# 创建 LuCI 视图 (跳转页面)
mkdir -p "$PKG_DIR/usr/lib/lua/luci/view/passwall2_batch"
cat > "$PKG_DIR/usr/lib/lua/luci/view/passwall2_batch/main.htm" << 'HTMEOF'
<%+header%>
<style>
.pw-redirect-box {
    max-width: 600px;
    margin: 50px auto;
    padding: 40px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 15px;
    text-align: center;
    color: white;
    box-shadow: 0 10px 40px rgba(0,0,0,0.3);
}
.pw-redirect-box h2 {
    margin: 0 0 20px 0;
    font-size: 24px;
}
.pw-redirect-box p {
    margin: 0 0 30px 0;
    opacity: 0.9;
}
.pw-redirect-btn {
    display: inline-block;
    padding: 15px 40px;
    background: white;
    color: #667eea;
    text-decoration: none;
    border-radius: 8px;
    font-weight: bold;
    font-size: 16px;
    transition: transform 0.3s, box-shadow 0.3s;
}
.pw-redirect-btn:hover {
    transform: translateY(-3px);
    box-shadow: 0 5px 20px rgba(0,0,0,0.3);
    color: #764ba2;
}
.pw-info {
    margin-top: 20px;
    font-size: 14px;
    opacity: 0.8;
}
</style>

<div class="pw-redirect-box">
    <h2>Passwall2 批量导入工具</h2>
    <p>批量导入 HTTP 节点，自动生成分流配置和 SOCKS 端口</p>
    <a href="http://<%= luci.http.getenv("HTTP_HOST"):gsub(":.*", "") %>:8099"
       target="_blank" class="pw-redirect-btn">
        打开批量导入工具
    </a>
    <div class="pw-info">
        独立端口: 8099 | 将在新窗口打开
    </div>
</div>

<%+footer%>
HTMEOF

# 设置正确的权限
echo "设置权限..."
chmod 755 "$PKG_DIR/etc/init.d/passwall2-batch"
chmod 755 "$PKG_DIR/www/passwall2-batch"
chmod 644 "$PKG_DIR/www/passwall2-batch/index.html"
chmod 755 "$PKG_DIR/www/passwall2-batch/api.cgi"
chmod 644 "$PKG_DIR/usr/lib/lua/luci/controller/passwall2_batch.lua"
chmod 644 "$PKG_DIR/usr/lib/lua/luci/view/passwall2_batch/main.htm"

# 创建 cgi-bin 目录和入口脚本
mkdir -p "$PKG_DIR/www/passwall2-batch/cgi-bin"
cat > "$PKG_DIR/www/passwall2-batch/cgi-bin/passwall2-batch" << 'CGIEOF'
#!/bin/sh
exec /www/passwall2-batch/api.cgi
CGIEOF
chmod 755 "$PKG_DIR/www/passwall2-batch/cgi-bin/passwall2-batch"

# 创建 control 文件
cat > "$PKG_DIR/CONTROL/control" << EOF
Package: ${PKG_NAME}
Version: ${PKG_VERSION}-${PKG_RELEASE}
Depends: libc, uhttpd, luci-base
Section: luci
Architecture: ${PKG_ARCH}
Installed-Size: 0
Maintainer: OpenWrt Developer
Description: Passwall2 Batch Import Tool
 批量导入 HTTP 节点，自动配置分流和 SOCKS 端口
 LuCI 菜单: 服务 -> Passwall2 批量导入
 独立访问: http://<路由器IP>:8099
EOF

# 创建 postinst 脚本
cat > "$PKG_DIR/CONTROL/postinst" << 'EOF'
#!/bin/sh
[ "${IPKG_NO_SCRIPT}" = "1" ] && exit 0

# 清除 LuCI 缓存
rm -rf /tmp/luci-modulecache /tmp/luci-indexcache 2>/dev/null

# 启用服务
/etc/init.d/passwall2-batch enable 2>/dev/null

# 启动服务
/etc/init.d/passwall2-batch start 2>/dev/null

exit 0
EOF
chmod 755 "$PKG_DIR/CONTROL/postinst"

# 创建 prerm 脚本
cat > "$PKG_DIR/CONTROL/prerm" << 'EOF'
#!/bin/sh
[ "${IPKG_NO_SCRIPT}" = "1" ] && exit 0

# 停止服务
/etc/init.d/passwall2-batch stop 2>/dev/null

# 禁用服务
/etc/init.d/passwall2-batch disable 2>/dev/null

exit 0
EOF
chmod 755 "$PKG_DIR/CONTROL/prerm"

# 创建 postrm 脚本 (卸载后清理)
cat > "$PKG_DIR/CONTROL/postrm" << 'EOF'
#!/bin/sh
# 清除 LuCI 缓存
rm -rf /tmp/luci-modulecache /tmp/luci-indexcache 2>/dev/null
exit 0
EOF
chmod 755 "$PKG_DIR/CONTROL/postrm"

# 进入临时目录
TMP_DIR="$BUILD_DIR/tmp"
mkdir -p "$TMP_DIR"

# 创建 data.tar.gz (排除 CONTROL 目录)
echo "创建 data.tar.gz..."
cd "$PKG_DIR"
tar -czf "$TMP_DIR/data.tar.gz" --exclude='CONTROL' .

# 更新 Installed-Size
INSTALLED_SIZE=$(gzip -dc "$TMP_DIR/data.tar.gz" | wc -c | tr -d ' ')
sed -i.bak "s/^Installed-Size: .*/Installed-Size: $INSTALLED_SIZE/" "$PKG_DIR/CONTROL/control"
rm -f "$PKG_DIR/CONTROL/control.bak"

# 创建 control.tar.gz
echo "创建 control.tar.gz..."
cd "$PKG_DIR/CONTROL"
tar -czf "$TMP_DIR/control.tar.gz" .

# 创建 debian-binary
echo "2.0" > "$TMP_DIR/debian-binary"

# 创建最终的 ipk 文件
echo "创建 ipk 文件..."
cd "$TMP_DIR"
tar -czf "$SCRIPT_DIR/output/$OUTPUT_FILE" ./debian-binary ./data.tar.gz ./control.tar.gz

echo ""
echo "=== 打包完成 ==="
ls -la "$SCRIPT_DIR/output/$OUTPUT_FILE"
echo ""
echo "=== 安装方法 ==="
echo "1. 上传: scp output/$OUTPUT_FILE root@<路由器IP>:/tmp/"
echo "2. 安装: opkg install /tmp/$OUTPUT_FILE"
echo ""
echo "=== 访问方式 ==="
echo "方式1: LuCI 菜单 -> 服务 -> Passwall2 批量导入"
echo "方式2: 直接访问 http://<路由器IP>:8099"
