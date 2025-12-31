#!/bin/sh

# 快速安装脚本 - 无需编译
# 直接将文件复制到 OpenWrt 对应目录

INSTALL_DIR="/tmp/luci-app-passwall2-batch"

echo "=========================================="
echo "  Passwall2 批量导入插件 - 快速安装"
echo "=========================================="

# 创建目录
mkdir -p /usr/lib/lua/luci/controller
mkdir -p /usr/lib/lua/luci/view/passwall2-batch

# 复制控制器
cat > /usr/lib/lua/luci/controller/passwall2_batch.lua << 'LUAEOF'
module("luci.controller.passwall2_batch", package.seeall)

function index()
    entry({"admin", "services", "passwall2-batch"}, template("passwall2-batch/main"), _("Passwall2 批量导入"), 99)
    entry({"admin", "services", "passwall2-batch", "import"}, call("action_import"), nil).leaf = true
    entry({"admin", "services", "passwall2-batch", "get_shunt_rules"}, call("action_get_shunt_rules"), nil).leaf = true
    entry({"admin", "services", "passwall2-batch", "get_nodes"}, call("action_get_nodes"), nil).leaf = true
    entry({"admin", "services", "passwall2-batch", "delete_node"}, call("action_delete_node"), nil).leaf = true
    entry({"admin", "services", "passwall2-batch", "restart"}, call("action_restart"), nil).leaf = true
end

function action_get_shunt_rules()
    local uci = require("luci.model.uci").cursor()
    local http = require("luci.http")
    local rules = {}
    uci:foreach("passwall2", "shunt_rules", function(s)
        if s.remarks then
            table.insert(rules, {id = s[".name"], remarks = s.remarks})
        end
    end)
    http.prepare_content("application/json")
    http.write_json({success = true, rules = rules})
end

function action_get_nodes()
    local uci = require("luci.model.uci").cursor()
    local http = require("luci.http")
    local nodes = {}
    uci:foreach("passwall2", "nodes", function(s)
        if s.remarks and s.protocol then
            table.insert(nodes, {
                id = s[".name"],
                remarks = s.remarks,
                protocol = s.protocol,
                address = s.address or "",
                port = s.port or ""
            })
        end
    end)
    local socks = {}
    uci:foreach("passwall2", "socks", function(s)
        table.insert(socks, {id = s[".name"], port = s.port, node = s.node, enabled = s.enabled})
    end)
    http.prepare_content("application/json")
    http.write_json({success = true, nodes = nodes, socks = socks})
end

local function generate_id()
    local chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    local id = ""
    math.randomseed(os.time() + math.random())
    for i = 1, 8 do
        local idx = math.random(1, #chars)
        id = id .. chars:sub(idx, idx)
    end
    return id
end

function action_import()
    local http = require("luci.http")
    local uci = require("luci.model.uci").cursor()
    local jsonc = require("luci.jsonc")
    local content = http.content()
    local data = jsonc.parse(content)
    if not data or not data.nodes then
        http.prepare_content("application/json")
        http.write_json({success = false, message = "无效的请求数据"})
        return
    end
    local nodes = data.nodes
    local start_port = tonumber(data.start_port) or 1081
    local group_name = data.group_name or "批量导入"
    local shunt_rules = data.shunt_rules or {"ImageDirect"}
    local imported = 0
    local errors = {}
    for i, node in ipairs(nodes) do
        local current_port = start_port + i - 1
        if node.ip and node.port and node.username and node.password and node.remarks then
            local http_node_id = generate_id()
            local shunt_node_id = generate_id()
            local socks_id = generate_id()
            uci:section("passwall2", "nodes", http_node_id, {
                remarks = node.remarks,
                group = group_name,
                type = "sing-box",
                protocol = "http",
                address = node.ip,
                port = node.port,
                username = node.username,
                password = node.password,
                tls = "0"
            })
            local shunt_config = {
                protocol = "_shunt",
                remarks = "分流:" .. node.remarks,
                type = "sing-box",
                add_mode = "1",
                default_node = http_node_id
            }
            for _, rule in ipairs(shunt_rules) do
                shunt_config[rule] = "_direct"
            end
            uci:section("passwall2", "nodes", shunt_node_id, shunt_config)
            uci:section("passwall2", "socks", socks_id, {
                enabled = "1",
                port = tostring(current_port),
                http_port = "0",
                node = shunt_node_id,
                log = "1",
                enable_autoswitch = "0"
            })
            imported = imported + 1
        else
            table.insert(errors, "节点 " .. i .. " 数据不完整")
        end
    end
    uci:commit("passwall2")
    http.prepare_content("application/json")
    http.write_json({success = true, imported = imported, errors = errors, message = "成功导入 " .. imported .. " 个节点"})
end

function action_delete_node()
    local http = require("luci.http")
    local uci = require("luci.model.uci").cursor()
    local jsonc = require("luci.jsonc")
    local content = http.content()
    local data = jsonc.parse(content)
    if not data or not data.node_id then
        http.prepare_content("application/json")
        http.write_json({success = false, message = "无效的节点 ID"})
        return
    end
    uci:delete("passwall2", data.node_id)
    if data.socks_id then uci:delete("passwall2", data.socks_id) end
    if data.shunt_id then uci:delete("passwall2", data.shunt_id) end
    uci:commit("passwall2")
    http.prepare_content("application/json")
    http.write_json({success = true, message = "节点已删除"})
end

function action_restart()
    local http = require("luci.http")
    local sys = require("luci.sys")
    sys.call("/etc/init.d/passwall2 restart >/dev/null 2>&1 &")
    http.prepare_content("application/json")
    http.write_json({success = true, message = "Passwall2 正在重启"})
end
LUAEOF

echo "[1/3] 控制器已安装"

# 复制视图模板
cat > /usr/lib/lua/luci/view/passwall2-batch/main.htm << 'HTMEOF'
<%+header%>
<style>
.pw-batch-container{max-width:1200px;margin:0 auto}
.pw-batch-header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:20px;border-radius:10px;margin-bottom:20px}
.pw-batch-header h2{margin:0 0 5px 0}
.pw-batch-header p{margin:0;opacity:.9}
.pw-batch-section{background:#fff;border:1px solid #ddd;border-radius:8px;padding:20px;margin-bottom:20px}
.pw-batch-section h3{margin-top:0;padding-bottom:10px;border-bottom:2px solid #667eea;color:#333}
.pw-batch-stats{display:flex;gap:15px;margin-bottom:20px}
.pw-batch-stat{background:#f8f9fa;padding:15px 25px;border-radius:8px;text-align:center;flex:1}
.pw-batch-stat .number{font-size:28px;font-weight:700;color:#667eea}
.pw-batch-stat .label{color:#666;font-size:14px}
.pw-batch-form-group{margin-bottom:15px}
.pw-batch-form-group label{display:block;margin-bottom:5px;font-weight:700;color:#333}
.pw-batch-form-group input,.pw-batch-form-group textarea,.pw-batch-form-group select{width:100%;padding:10px;border:1px solid #ddd;border-radius:5px;font-size:14px}
.pw-batch-form-group textarea{height:200px;font-family:monospace}
.pw-batch-form-group select[multiple]{height:120px}
.pw-batch-row{display:flex;gap:20px}
.pw-batch-row .pw-batch-form-group{flex:1}
.pw-batch-help{background:#e7f3ff;border-left:4px solid #667eea;padding:10px 15px;margin-bottom:15px;font-size:13px;color:#555}
.pw-batch-help code{background:#fff;padding:2px 6px;border-radius:3px;color:#667eea}
.pw-batch-btn{display:inline-block;padding:10px 25px;border:none;border-radius:5px;cursor:pointer;font-size:14px;font-weight:700;transition:all .3s}
.pw-batch-btn-primary{background:#667eea;color:#fff}
.pw-batch-btn-primary:hover{background:#5a6fd6}
.pw-batch-btn-secondary{background:#6c757d;color:#fff}
.pw-batch-btn-secondary:hover{background:#5a6268}
.pw-batch-btn-success{background:#28a745;color:#fff}
.pw-batch-btn-success:hover{background:#218838}
.pw-batch-btn-danger{background:#dc3545;color:#fff}
.pw-batch-btn-danger:hover{background:#c82333}
.pw-batch-btn-group{display:flex;gap:10px;margin-top:15px}
.pw-batch-table{width:100%;border-collapse:collapse;margin-top:15px}
.pw-batch-table th,.pw-batch-table td{padding:10px;text-align:left;border-bottom:1px solid #ddd}
.pw-batch-table th{background:#f8f9fa;font-weight:700;color:#333}
.pw-batch-table tr:hover{background:#f8f9fa}
.pw-batch-tag{display:inline-block;padding:3px 10px;border-radius:3px;font-size:12px;background:#667eea;color:#fff}
.pw-batch-message{padding:10px 15px;border-radius:5px;margin-bottom:15px;display:none}
.pw-batch-message.success{background:#d4edda;color:#155724;display:block}
.pw-batch-message.error{background:#f8d7da;color:#721c24;display:block}
</style>
<div class="pw-batch-container">
<div class="pw-batch-header"><h2>Passwall2 批量导入</h2><p>批量导入 HTTP 节点，自动生成分流配置和 SOCKS 端口</p></div>
<div id="message" class="pw-batch-message"></div>
<div class="pw-batch-stats">
<div class="pw-batch-stat"><div class="number" id="nodeCount">0</div><div class="label">待导入节点</div></div>
<div class="pw-batch-stat"><div class="number" id="portRange">-</div><div class="label">SOCKS 端口范围</div></div>
<div class="pw-batch-stat"><div class="number" id="existingNodes">0</div><div class="label">现有节点</div></div>
</div>
<div class="pw-batch-section">
<h3>1. 输入节点列表</h3>
<div class="pw-batch-help">格式：<code>IP:端口:用户名:密码:备注</code>，每行一个节点<br>示例：<code>183.146.16.165:28012:h8280:password123:宜春</code></div>
<div class="pw-batch-form-group"><textarea id="nodeInput" placeholder="183.146.16.165:28012:h8280:password123:宜春
183.146.16.131:49053:h8280:password456:周口"></textarea></div>
</div>
<div class="pw-batch-section">
<h3>2. 配置选项</h3>
<div class="pw-batch-row">
<div class="pw-batch-form-group"><label>SOCKS 起始端口</label><input type="number" id="startPort" value="1081"></div>
<div class="pw-batch-form-group"><label>节点分组名</label><input type="text" id="groupName" value="批量导入"></div>
</div>
<div class="pw-batch-form-group">
<label>分流规则（选择哪些规则走直连）</label>
<select id="shuntRules" multiple></select>
<small style="color:#888">按住 Ctrl 可多选</small>
</div>
</div>
<div class="pw-batch-section">
<h3>3. 导入节点</h3>
<div class="pw-batch-btn-group">
<button class="pw-batch-btn pw-batch-btn-secondary" onclick="parseNodes()">解析预览</button>
<button class="pw-batch-btn pw-batch-btn-primary" onclick="importNodes()">导入节点</button>
<button class="pw-batch-btn pw-batch-btn-success" onclick="restartPasswall()">重启 Passwall2</button>
</div>
</div>
<div class="pw-batch-section" id="parseSection" style="display:none">
<h3>解析预览</h3>
<table class="pw-batch-table"><thead><tr><th>#</th><th>备注</th><th>地址</th><th>端口</th><th>用户名</th><th>SOCKS端口</th></tr></thead><tbody id="parseResult"></tbody></table>
</div>
<div class="pw-batch-section">
<h3>现有节点列表</h3>
<div class="pw-batch-btn-group" style="margin-bottom:15px"><button class="pw-batch-btn pw-batch-btn-secondary" onclick="loadExistingNodes()">刷新列表</button></div>
<table class="pw-batch-table"><thead><tr><th>备注</th><th>协议</th><th>地址</th><th>端口</th><th>操作</th></tr></thead><tbody id="existingNodesList"></tbody></table>
</div>
</div>
<script>
let parsedNodes=[];
document.addEventListener('DOMContentLoaded',function(){loadShuntRules();loadExistingNodes()});
function showMessage(msg,type){const el=document.getElementById('message');el.textContent=msg;el.className='pw-batch-message '+type;setTimeout(()=>{el.className='pw-batch-message'},5000)}
function loadShuntRules(){fetch('<%=url("admin/services/passwall2-batch/get_shunt_rules")%>').then(r=>r.json()).then(data=>{if(data.success){const select=document.getElementById('shuntRules');select.innerHTML=data.rules.map(rule=>'<option value="'+rule.id+'"'+(rule.id==='ImageDirect'?' selected':'')+'>'+rule.remarks+'</option>').join('')}}).catch(err=>console.error('加载分流规则失败:',err))}
function loadExistingNodes(){fetch('<%=url("admin/services/passwall2-batch/get_nodes")%>').then(r=>r.json()).then(data=>{if(data.success){document.getElementById('existingNodes').textContent=data.nodes.length;const tbody=document.getElementById('existingNodesList');tbody.innerHTML=data.nodes.map(node=>'<tr><td><span class="pw-batch-tag">'+node.remarks+'</span></td><td>'+node.protocol+'</td><td>'+node.address+'</td><td>'+node.port+'</td><td><button class="pw-batch-btn pw-batch-btn-danger" style="padding:5px 10px;font-size:12px" onclick="deleteNode(\''+node.id+'\')">删除</button></td></tr>').join('')}}).catch(err=>console.error('加载节点失败:',err))}
function parseNodes(){const input=document.getElementById('nodeInput').value.trim();const startPort=parseInt(document.getElementById('startPort').value);const lines=input.split('\n').filter(line=>line.trim());parsedNodes=[];let currentPort=startPort;for(const line of lines){const parts=line.trim().split(':');if(parts.length>=5){parsedNodes.push({ip:parts[0],port:parts[1],username:parts[2],password:parts[3],remarks:parts.slice(4).join(':'),socksPort:currentPort++})}}document.getElementById('nodeCount').textContent=parsedNodes.length;if(parsedNodes.length>0){const endPort=startPort+parsedNodes.length-1;document.getElementById('portRange').textContent=startPort+'-'+endPort}const tbody=document.getElementById('parseResult');tbody.innerHTML=parsedNodes.map((node,i)=>'<tr><td>'+(i+1)+'</td><td><span class="pw-batch-tag">'+node.remarks+'</span></td><td>'+node.ip+'</td><td>'+node.port+'</td><td>'+node.username+'</td><td>'+node.socksPort+'</td></tr>').join('');document.getElementById('parseSection').style.display='block';if(parsedNodes.length===0){showMessage('没有解析到有效节点，请检查格式','error')}else{showMessage('解析成功，共 '+parsedNodes.length+' 个节点','success')}}
function importNodes(){if(parsedNodes.length===0){parseNodes()}if(parsedNodes.length===0){showMessage('没有可导入的节点','error');return}const startPort=parseInt(document.getElementById('startPort').value);const groupName=document.getElementById('groupName').value||'批量导入';const shuntSelect=document.getElementById('shuntRules');const selectedShunts=Array.from(shuntSelect.selectedOptions).map(opt=>opt.value);const data={nodes:parsedNodes,start_port:startPort,group_name:groupName,shunt_rules:selectedShunts};fetch('<%=url("admin/services/passwall2-batch/import")%>',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json()).then(result=>{if(result.success){showMessage(result.message,'success');loadExistingNodes();document.getElementById('nodeInput').value='';parsedNodes=[];document.getElementById('nodeCount').textContent='0';document.getElementById('portRange').textContent='-';document.getElementById('parseSection').style.display='none'}else{showMessage(result.message||'导入失败','error')}}).catch(err=>{showMessage('导入失败: '+err.message,'error')})}
function deleteNode(nodeId){if(!confirm('确定要删除这个节点吗？')){return}fetch('<%=url("admin/services/passwall2-batch/delete_node")%>',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({node_id:nodeId})}).then(r=>r.json()).then(result=>{if(result.success){showMessage('节点已删除','success');loadExistingNodes()}else{showMessage(result.message||'删除失败','error')}}).catch(err=>{showMessage('删除失败: '+err.message,'error')})}
function restartPasswall(){if(!confirm('确定要重启 Passwall2 服务吗？')){return}fetch('<%=url("admin/services/passwall2-batch/restart")%>',{method:'POST'}).then(r=>r.json()).then(result=>{if(result.success){showMessage('Passwall2 正在重启...','success')}else{showMessage(result.message||'重启失败','error')}}).catch(err=>{showMessage('重启失败: '+err.message,'error')})}
</script>
<%+footer%>
HTMEOF

echo "[2/3] 视图模板已安装"

# 清除 LuCI 缓存
rm -rf /tmp/luci-modulecache
rm -rf /tmp/luci-indexcache

echo "[3/3] 缓存已清除"

echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "请访问: 服务 -> Passwall2 批量导入"
echo ""
echo "如果菜单没有出现，请执行: /etc/init.d/uhttpd restart"
echo ""
