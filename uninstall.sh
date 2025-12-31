#!/bin/sh

echo "=========================================="
echo "  Passwall2 批量导入插件 - 卸载"
echo "=========================================="

# 删除文件
rm -f /usr/lib/lua/luci/controller/passwall2_batch.lua
rm -rf /usr/lib/lua/luci/view/passwall2-batch

# 清除缓存
rm -rf /tmp/luci-modulecache
rm -rf /tmp/luci-indexcache

echo "卸载完成！"
echo "请执行: /etc/init.d/uhttpd restart"
