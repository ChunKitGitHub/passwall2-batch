module("luci.controller.passwall2_batch", package.seeall)

function index()
    -- 添加到服务菜单下
    entry({"admin", "services", "passwall2-batch"}, template("passwall2-batch/main"), _("Passwall2 批量导入"), 99)

    -- API 接口
    entry({"admin", "services", "passwall2-batch", "import"}, call("action_import"), nil).leaf = true
    entry({"admin", "services", "passwall2-batch", "get_shunt_rules"}, call("action_get_shunt_rules"), nil).leaf = true
    entry({"admin", "services", "passwall2-batch", "get_nodes"}, call("action_get_nodes"), nil).leaf = true
    entry({"admin", "services", "passwall2-batch", "delete_node"}, call("action_delete_node"), nil).leaf = true
    entry({"admin", "services", "passwall2-batch", "restart"}, call("action_restart"), nil).leaf = true
end

-- 获取分流规则列表
function action_get_shunt_rules()
    local uci = require("luci.model.uci").cursor()
    local http = require("luci.http")
    local rules = {}

    uci:foreach("passwall2", "shunt_rules", function(s)
        if s.remarks then
            table.insert(rules, {
                id = s[".name"],
                remarks = s.remarks
            })
        end
    end)

    http.prepare_content("application/json")
    http.write_json({success = true, rules = rules})
end

-- 获取现有节点列表
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

    -- 获取 socks 配置
    local socks = {}
    uci:foreach("passwall2", "socks", function(s)
        table.insert(socks, {
            id = s[".name"],
            port = s.port,
            node = s.node,
            enabled = s.enabled
        })
    end)

    http.prepare_content("application/json")
    http.write_json({success = true, nodes = nodes, socks = socks})
end

-- 生成随机 ID
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

-- 导入节点
function action_import()
    local http = require("luci.http")
    local uci = require("luci.model.uci").cursor()
    local jsonc = require("luci.jsonc")

    -- 获取 POST 数据
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

        -- 验证节点数据
        if node.ip and node.port and node.username and node.password and node.remarks then
            local http_node_id = generate_id()
            local shunt_node_id = generate_id()
            local socks_id = generate_id()

            -- 1. 创建 HTTP 节点
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

            -- 2. 创建分流节点
            local shunt_config = {
                protocol = "_shunt",
                remarks = "分流:" .. node.remarks,
                type = "sing-box",
                add_mode = "1",
                default_node = http_node_id
            }

            -- 添加分流规则
            for _, rule in ipairs(shunt_rules) do
                shunt_config[rule] = "_direct"
            end

            uci:section("passwall2", "nodes", shunt_node_id, shunt_config)

            -- 3. 创建 SOCKS 配置
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

    -- 保存配置
    uci:commit("passwall2")

    http.prepare_content("application/json")
    http.write_json({
        success = true,
        imported = imported,
        errors = errors,
        message = "成功导入 " .. imported .. " 个节点"
    })
end

-- 删除节点
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

    -- 删除节点
    uci:delete("passwall2", data.node_id)

    -- 如果提供了关联的 socks_id，也删除
    if data.socks_id then
        uci:delete("passwall2", data.socks_id)
    end

    -- 如果提供了关联的 shunt_id，也删除
    if data.shunt_id then
        uci:delete("passwall2", data.shunt_id)
    end

    uci:commit("passwall2")

    http.prepare_content("application/json")
    http.write_json({success = true, message = "节点已删除"})
end

-- 重启 Passwall2 服务
function action_restart()
    local http = require("luci.http")
    local sys = require("luci.sys")

    sys.call("/etc/init.d/passwall2 restart >/dev/null 2>&1 &")

    http.prepare_content("application/json")
    http.write_json({success = true, message = "Passwall2 正在重启"})
end
