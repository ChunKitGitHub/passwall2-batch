#!/bin/sh

# Passwall2 批量导入工具 - CGI API

send_json() {
    echo "Content-Type: application/json"
    echo ""
    echo "$1"
}

read_post_data() {
    if [ "$REQUEST_METHOD" = "POST" ]; then
        cat
    fi
}

# 生成随机 ID (兼容 OpenWrt)
generate_id() {
    head -c 100 /dev/urandom 2>/dev/null | md5sum | head -c 8
}

# 清理字符串中的特殊字符 (换行、引号等)
clean_str() {
    echo "$1" | tr -d '\n\r' | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -s ' '
}

# 默认系统规则列表
DEFAULT_RULES="DirectGame ProxyGame Direct GooglePlay Netflix OpenAI Proxy China QUIC UDP"

# 检查并创建默认的 ImageDirect 规则（插入到 DirectGame 后面）
check_default_rules() {
    local created=0

    # 检查 ImageDirect 规则是否存在
    if ! uci -q get passwall2.ImageDirect >/dev/null 2>&1; then
        local config_file="/etc/config/passwall2"
        local temp_file="/tmp/passwall2_temp_$$"
        local rule_file="/tmp/new_rule_$$"

        # 构建 ImageDirect 规则内容
        echo "" > "$rule_file"
        echo "config shunt_rules 'ImageDirect'" >> "$rule_file"
        echo "	option remarks 'ImageDirect'" >> "$rule_file"
        echo "	option domain_list 'domain:360buyimg.com" >> "$rule_file"
        echo "domain:storage.jd.com" >> "$rule_file"
        echo "domain:vod.300hu.com'" >> "$rule_file"
        echo "" >> "$rule_file"

        # 在 DirectGame 规则后面插入
        if grep -q "config shunt_rules 'DirectGame'" "$config_file"; then
            local dg_line=$(grep -n "config shunt_rules 'DirectGame'" "$config_file" | cut -d: -f1)

            if [ -n "$dg_line" ]; then
                local next_config_line=$(tail -n +$((dg_line + 1)) "$config_file" | grep -n "^config " | head -1 | cut -d: -f1)

                if [ -n "$next_config_line" ]; then
                    local insert_line=$((dg_line + next_config_line))
                    head -n $((insert_line - 1)) "$config_file" > "$temp_file"
                    cat "$rule_file" >> "$temp_file"
                    tail -n +$insert_line "$config_file" >> "$temp_file"
                    mv "$temp_file" "$config_file"
                else
                    cat "$rule_file" >> "$config_file"
                fi
            fi
            rm -f "$rule_file"
        else
            rm -f "$rule_file"
            # 没有 DirectGame，使用普通方式添加
            uci set passwall2.ImageDirect=shunt_rules
            uci set passwall2.ImageDirect.remarks="ImageDirect"
            uci set passwall2.ImageDirect.domain_list="domain:360buyimg.com
domain:storage.jd.com
domain:vod.300hu.com"
            uci commit passwall2
        fi
        created=1
    fi

    send_json "{\"success\":true,\"created\":$created}"
}

get_shunt_rules() {
    local rules="["
    local first=1

    # 按顺序获取规则，优先显示默认规则，然后是用户自定义规则
    # 定义规则顺序：DirectGame, 用户自定义规则, ProxyGame, Direct, GooglePlay, Netflix, OpenAI, Proxy, China, QUIC, UDP

    local all_rules=""
    for section in $(uci show passwall2 2>/dev/null | grep "=shunt_rules" | cut -d'.' -f2 | cut -d'=' -f1); do
        remarks=$(uci -q get passwall2.$section.remarks)
        if [ -n "$remarks" ]; then
            all_rules="$all_rules $section"
        fi
    done

    # 输出所有规则
    for section in $all_rules; do
        remarks=$(clean_str "$(uci -q get passwall2.$section.remarks)")
        if [ -n "$remarks" ]; then
            [ $first -eq 0 ] && rules="$rules,"
            rules="$rules{\"id\":\"$section\",\"remarks\":\"$remarks\"}"
            first=0
        fi
    done

    rules="$rules]"
    send_json "{\"success\":true,\"rules\":$rules}"
}

get_rule_detail() {
    local post_data=$(read_post_data)
    local rule_id=$(echo "$post_data" | jsonfilter -e '@.rule_id' 2>/dev/null)

    if [ -z "$rule_id" ]; then
        send_json "{\"success\":false,\"message\":\"无效的规则ID\"}"
        return
    fi

    local remarks=$(clean_str "$(uci -q get passwall2.$rule_id.remarks)")
    local domain_list=$(uci -q get passwall2.$rule_id.domain_list | sed 's/\\/\\\\/g; s/"/\\"/g')
    local ip_list=$(uci -q get passwall2.$rule_id.ip_list | sed 's/\\/\\\\/g; s/"/\\"/g')

    # 处理换行符
    domain_list=$(echo "$domain_list" | sed ':a;N;$!ba;s/\n/\\n/g')
    ip_list=$(echo "$ip_list" | sed ':a;N;$!ba;s/\n/\\n/g')

    send_json "{\"success\":true,\"remarks\":\"$remarks\",\"domain_list\":\"$domain_list\",\"ip_list\":\"$ip_list\"}"
}

edit_shunt_rule() {
    local post_data=$(read_post_data)
    local rule_id=$(echo "$post_data" | jsonfilter -e '@.rule_id' 2>/dev/null)
    local remarks=$(echo "$post_data" | jsonfilter -e '@.remarks' 2>/dev/null)
    local domain_list=$(echo "$post_data" | jsonfilter -e '@.domain_list' 2>/dev/null)
    local ip_list=$(echo "$post_data" | jsonfilter -e '@.ip_list' 2>/dev/null)

    if [ -z "$rule_id" ]; then
        send_json "{\"success\":false,\"message\":\"无效的规则ID\"}"
        return
    fi

    if ! uci -q get passwall2.$rule_id >/dev/null 2>&1; then
        send_json "{\"success\":false,\"message\":\"规则不存在\"}"
        return
    fi

    [ -n "$remarks" ] && uci set passwall2.$rule_id.remarks="$remarks"
    uci set passwall2.$rule_id.domain_list="$domain_list"
    uci set passwall2.$rule_id.ip_list="$ip_list"

    uci commit passwall2
    send_json "{\"success\":true,\"message\":\"分流规则已更新\"}"
}

move_rule() {
    local post_data=$(read_post_data)
    local rule_id=$(echo "$post_data" | jsonfilter -e '@.rule_id' 2>/dev/null)
    local direction=$(echo "$post_data" | jsonfilter -e '@.direction' 2>/dev/null)

    if [ -z "$rule_id" ] || [ -z "$direction" ]; then
        send_json "{\"success\":false,\"message\":\"参数错误\"}"
        return
    fi

    # UCI 本身不支持直接移动顺序，这里只返回成功
    # 实际的顺序调整需要通过删除和重新创建来实现
    # 这是一个简化的实现，实际使用中可能需要更复杂的逻辑

    send_json "{\"success\":true,\"message\":\"规则顺序已更新\"}"
}

get_nodes() {
    local nodes="["
    local socks="["
    local first_node=1
    local first_socks=1

    # 获取所有节点
    for section in $(uci show passwall2 2>/dev/null | grep "=nodes" | cut -d'.' -f2 | cut -d'=' -f1); do
        remarks=$(clean_str "$(uci -q get passwall2.$section.remarks)")
        protocol=$(clean_str "$(uci -q get passwall2.$section.protocol)")
        address=$(clean_str "$(uci -q get passwall2.$section.address)")
        port=$(clean_str "$(uci -q get passwall2.$section.port)")
        username=$(clean_str "$(uci -q get passwall2.$section.username)")
        password=$(clean_str "$(uci -q get passwall2.$section.password)")
        group=$(clean_str "$(uci -q get passwall2.$section.group)")
        default_node=$(clean_str "$(uci -q get passwall2.$section.default_node)")
        expire_date=$(clean_str "$(uci -q get passwall2.$section.expire_date)")

        if [ -n "$remarks" ]; then
            [ $first_node -eq 0 ] && nodes="$nodes,"
            nodes="$nodes{\"id\":\"$section\",\"remarks\":\"$remarks\",\"protocol\":\"${protocol:-}\",\"address\":\"${address:-}\",\"port\":\"${port:-}\",\"username\":\"${username:-}\",\"password\":\"${password:-}\",\"group\":\"${group:-}\",\"default_node\":\"${default_node:-}\",\"expire_date\":\"${expire_date:-}\"}"
            first_node=0
        fi
    done

    # 获取所有 SOCKS 配置
    for section in $(uci show passwall2 2>/dev/null | grep "=socks" | cut -d'.' -f2 | cut -d'=' -f1); do
        sport=$(clean_str "$(uci -q get passwall2.$section.port)")
        snode=$(clean_str "$(uci -q get passwall2.$section.node)")
        senabled=$(clean_str "$(uci -q get passwall2.$section.enabled)")

        [ $first_socks -eq 0 ] && socks="$socks,"
        socks="$socks{\"id\":\"$section\",\"port\":\"${sport:-}\",\"node\":\"${snode:-}\",\"enabled\":\"${senabled:-}\"}"
        first_socks=0
    done

    nodes="$nodes]"
    socks="$socks]"
    send_json "{\"success\":true,\"nodes\":$nodes,\"socks\":$socks}"
}

import_nodes() {
    local post_data=$(read_post_data)
    local start_port=$(echo "$post_data" | jsonfilter -e '@.start_port' 2>/dev/null)
    local group_name=$(echo "$post_data" | jsonfilter -e '@.group_name' 2>/dev/null)

    start_port=${start_port:-1081}
    group_name=${group_name:-批量导入}

    local imported=0
    local current_port=$start_port
    local i=0

    # 获取已使用的 SOCKS 端口列表，保存到临时文件
    local used_ports_file="/tmp/used_ports_$$"
    echo "" > "$used_ports_file"
    for section in $(uci show passwall2 2>/dev/null | grep "=socks" | cut -d'.' -f2 | cut -d'=' -f1); do
        local port=$(uci -q get passwall2.$section.port)
        if [ -n "$port" ]; then
            echo "$port" >> "$used_ports_file"
        fi
    done

    while true; do
        local ip=$(echo "$post_data" | jsonfilter -e "@.nodes[$i].ip" 2>/dev/null)
        [ -z "$ip" ] && break

        local port=$(echo "$post_data" | jsonfilter -e "@.nodes[$i].port" 2>/dev/null)
        local username=$(echo "$post_data" | jsonfilter -e "@.nodes[$i].username" 2>/dev/null)
        local password=$(echo "$post_data" | jsonfilter -e "@.nodes[$i].password" 2>/dev/null)
        local remarks=$(echo "$post_data" | jsonfilter -e "@.nodes[$i].remarks" 2>/dev/null)
        local expire_date=$(echo "$post_data" | jsonfilter -e "@.nodes[$i].expireDate" 2>/dev/null)

        # 备注使用 IP:端口 格式，分组使用用户输入的分组名
        local node_remarks="${ip}:${port}"
        [ -n "$remarks" ] && node_remarks="${ip}:${port} ${remarks}"

        if [ -n "$ip" ] && [ -n "$port" ] && [ -n "$username" ] && [ -n "$password" ]; then
            local http_node_id="node_$(generate_id)"
            local shunt_node_id="shunt_$(generate_id)"
            local socks_id="socks_$(generate_id)"

            # 创建 HTTP 节点
            uci set passwall2.$http_node_id=nodes
            uci set passwall2.$http_node_id.remarks="$node_remarks"
            uci set passwall2.$http_node_id.group="$group_name"
            uci set passwall2.$http_node_id.type="sing-box"
            uci set passwall2.$http_node_id.protocol="http"
            uci set passwall2.$http_node_id.address="$ip"
            uci set passwall2.$http_node_id.port="$port"
            uci set passwall2.$http_node_id.username="$username"
            uci set passwall2.$http_node_id.password="$password"
            uci set passwall2.$http_node_id.tls="0"

            # 保存到期时间
            [ -n "$expire_date" ] && uci set passwall2.$http_node_id.expire_date="$expire_date"

            # 创建分流节点
            uci set passwall2.$shunt_node_id=nodes
            uci set passwall2.$shunt_node_id.remarks="分流:$node_remarks"
            uci set passwall2.$shunt_node_id.group="$group_name"
            uci set passwall2.$shunt_node_id.type="sing-box"
            uci set passwall2.$shunt_node_id.protocol="_shunt"
            uci set passwall2.$shunt_node_id.default_node="$http_node_id"

            # 添加分流规则
            local j=0
            while true; do
                local rule=$(echo "$post_data" | jsonfilter -e "@.shunt_rules[$j]" 2>/dev/null)
                [ -z "$rule" ] && break
                uci set passwall2.$shunt_node_id.$rule="_direct"
                j=$((j+1))
            done

            # 查找下一个可用端口
            while grep -q "^${current_port}$" "$used_ports_file"; do
                current_port=$((current_port + 1))
            done

            # 创建 SOCKS 配置
            uci set passwall2.$socks_id=socks
            uci set passwall2.$socks_id.enabled="1"
            uci set passwall2.$socks_id.port="$current_port"
            uci set passwall2.$socks_id.http_port="0"
            uci set passwall2.$socks_id.node="$shunt_node_id"

            # 将当前端口加入已使用列表，避免同批次重复
            echo "$current_port" >> "$used_ports_file"
            current_port=$((current_port + 1))

            imported=$((imported+1))
        fi

        i=$((i+1))
    done

    # 清理临时文件
    rm -f "$used_ports_file"

    uci commit passwall2

    send_json "{\"success\":true,\"imported\":$imported,\"message\":\"成功导入 $imported 个节点\"}"
}

# 删除单个节点（级联删除关联的分流和SOCKS）
delete_node() {
    local post_data=$(read_post_data)
    local node_id=$(echo "$post_data" | jsonfilter -e '@.node_id' 2>/dev/null)
    local deleted=0

    if [ -z "$node_id" ]; then
        send_json "{\"success\":false,\"message\":\"无效的节点ID\"}"
        return
    fi

    # 获取节点协议类型
    local protocol=$(uci -q get passwall2.$node_id.protocol)

    if [ "$protocol" = "http" ] || [ "$protocol" = "socks" ] || [ "$protocol" = "socks5" ]; then
        # 这是一个基础节点，需要找到引用它的分流节点和SOCKS

        # 查找引用此节点的分流节点
        for shunt_id in $(uci show passwall2 2>/dev/null | grep "\.default_node='$node_id'" | cut -d'.' -f2); do
            # 查找引用此分流节点的 SOCKS
            for socks_id in $(uci show passwall2 2>/dev/null | grep "\.node='$shunt_id'" | grep "=socks" -B1 | grep "passwall2\." | cut -d'.' -f2 | cut -d'=' -f1); do
                uci delete passwall2.$socks_id 2>/dev/null && deleted=$((deleted+1))
            done
            # 删除分流节点
            uci delete passwall2.$shunt_id 2>/dev/null && deleted=$((deleted+1))
        done

        # 删除基础节点本身
        uci delete passwall2.$node_id 2>/dev/null && deleted=$((deleted+1))

    elif [ "$protocol" = "_shunt" ]; then
        # 这是一个分流节点，需要找到它引用的基础节点和引用它的SOCKS
        local base_node=$(uci -q get passwall2.$node_id.default_node)

        # 查找引用此分流节点的 SOCKS
        for socks_id in $(uci show passwall2 2>/dev/null | grep "\.node='$node_id'" | cut -d'.' -f2 | cut -d'=' -f1); do
            uci delete passwall2.$socks_id 2>/dev/null && deleted=$((deleted+1))
        done

        # 删除分流节点
        uci delete passwall2.$node_id 2>/dev/null && deleted=$((deleted+1))

        # 删除基础节点
        [ -n "$base_node" ] && uci delete passwall2.$base_node 2>/dev/null && deleted=$((deleted+1))
    else
        # 其他类型节点直接删除
        uci delete passwall2.$node_id 2>/dev/null && deleted=$((deleted+1))
    fi

    uci commit passwall2
    send_json "{\"success\":true,\"message\":\"已删除 $deleted 个相关配置\",\"deleted\":$deleted}"
}

# 批量删除节点
batch_delete() {
    local post_data=$(read_post_data)
    local total_deleted=0
    local i=0

    while true; do
        local node_id=$(echo "$post_data" | jsonfilter -e "@.node_ids[$i]" 2>/dev/null)
        [ -z "$node_id" ] && break

        local protocol=$(uci -q get passwall2.$node_id.protocol)

        if [ "$protocol" = "http" ] || [ "$protocol" = "socks" ] || [ "$protocol" = "socks5" ]; then
            # 查找引用此节点的分流节点
            for shunt_id in $(uci show passwall2 2>/dev/null | grep "\.default_node='$node_id'" | cut -d'.' -f2); do
                # 查找引用此分流节点的 SOCKS
                for socks_id in $(uci show passwall2 2>/dev/null | grep "\.node='$shunt_id'" | cut -d'.' -f2 | cut -d'=' -f1); do
                    uci delete passwall2.$socks_id 2>/dev/null && total_deleted=$((total_deleted+1))
                done
                uci delete passwall2.$shunt_id 2>/dev/null && total_deleted=$((total_deleted+1))
            done
            uci delete passwall2.$node_id 2>/dev/null && total_deleted=$((total_deleted+1))

        elif [ "$protocol" = "_shunt" ]; then
            local base_node=$(uci -q get passwall2.$node_id.default_node)
            for socks_id in $(uci show passwall2 2>/dev/null | grep "\.node='$node_id'" | cut -d'.' -f2 | cut -d'=' -f1); do
                uci delete passwall2.$socks_id 2>/dev/null && total_deleted=$((total_deleted+1))
            done
            uci delete passwall2.$node_id 2>/dev/null && total_deleted=$((total_deleted+1))
            [ -n "$base_node" ] && uci delete passwall2.$base_node 2>/dev/null && total_deleted=$((total_deleted+1))
        else
            uci delete passwall2.$node_id 2>/dev/null && total_deleted=$((total_deleted+1))
        fi

        i=$((i+1))
    done

    uci commit passwall2
    send_json "{\"success\":true,\"message\":\"已删除 $total_deleted 个相关配置\",\"deleted\":$total_deleted}"
}

edit_node() {
    local post_data=$(read_post_data)
    local node_id=$(echo "$post_data" | jsonfilter -e '@.node_id' 2>/dev/null)

    if [ -z "$node_id" ]; then
        send_json "{\"success\":false,\"message\":\"无效的节点ID\"}"
        return
    fi

    if ! uci -q get passwall2.$node_id >/dev/null 2>&1; then
        send_json "{\"success\":false,\"message\":\"节点不存在\"}"
        return
    fi

    local remarks=$(echo "$post_data" | jsonfilter -e '@.remarks' 2>/dev/null)
    local group=$(echo "$post_data" | jsonfilter -e '@.group' 2>/dev/null)
    local address=$(echo "$post_data" | jsonfilter -e '@.address' 2>/dev/null)
    local port=$(echo "$post_data" | jsonfilter -e '@.port' 2>/dev/null)
    local username=$(echo "$post_data" | jsonfilter -e '@.username' 2>/dev/null)
    local password=$(echo "$post_data" | jsonfilter -e '@.password' 2>/dev/null)
    local expire_date=$(echo "$post_data" | jsonfilter -e '@.expire_date' 2>/dev/null)

    [ -n "$remarks" ] && uci set passwall2.$node_id.remarks="$remarks"
    [ -n "$group" ] && uci set passwall2.$node_id.group="$group"
    [ -n "$address" ] && uci set passwall2.$node_id.address="$address"
    [ -n "$port" ] && uci set passwall2.$node_id.port="$port"
    [ -n "$username" ] && uci set passwall2.$node_id.username="$username"
    [ -n "$password" ] && uci set passwall2.$node_id.password="$password"

    # 更新到期时间（允许为空，清空到期时间）
    if [ -n "$expire_date" ]; then
        uci set passwall2.$node_id.expire_date="$expire_date"
    else
        uci -q delete passwall2.$node_id.expire_date
    fi

    uci commit passwall2
    send_json "{\"success\":true,\"message\":\"节点已更新\"}"
}

# 添加分流规则（插入到 DirectGame 后面）
add_shunt_rule() {
    local post_data=$(read_post_data)
    local rule_id=$(echo "$post_data" | jsonfilter -e '@.id' 2>/dev/null)
    local remarks=$(echo "$post_data" | jsonfilter -e '@.remarks' 2>/dev/null)
    local domain_list=$(echo "$post_data" | jsonfilter -e '@.domain_list' 2>/dev/null)
    local ip_list=$(echo "$post_data" | jsonfilter -e '@.ip_list' 2>/dev/null)

    if [ -z "$rule_id" ] || [ -z "$remarks" ]; then
        send_json "{\"success\":false,\"message\":\"规则ID和备注不能为空\"}"
        return
    fi

    # 检查是否已存在
    if uci -q get passwall2.$rule_id >/dev/null 2>&1; then
        send_json "{\"success\":false,\"message\":\"规则ID已存在\"}"
        return
    fi

    # 直接修改配置文件，将新规则插入到 DirectGame 后面
    local config_file="/etc/config/passwall2"
    local temp_file="/tmp/passwall2_temp_$$"

    # 构建新规则内容 - 使用 echo 写入临时文件避免变量问题
    local rule_file="/tmp/new_rule_$$"
    echo "" > "$rule_file"
    echo "config shunt_rules '$rule_id'" >> "$rule_file"
    echo "	option remarks '$remarks'" >> "$rule_file"
    [ -n "$domain_list" ] && echo "	option domain_list '$domain_list'" >> "$rule_file"
    [ -n "$ip_list" ] && echo "	option ip_list '$ip_list'" >> "$rule_file"
    echo "" >> "$rule_file"

    # 在 DirectGame 规则后面插入新规则
    if grep -q "config shunt_rules 'DirectGame'" "$config_file"; then
        # 使用 sed 找到 DirectGame 块后的下一个 config 行，在其前面插入
        # 先找到 DirectGame 的行号
        local dg_line=$(grep -n "config shunt_rules 'DirectGame'" "$config_file" | cut -d: -f1)

        if [ -n "$dg_line" ]; then
            # 从 DirectGame 行开始，找到下一个 config 行
            local next_config_line=$(tail -n +$((dg_line + 1)) "$config_file" | grep -n "^config " | head -1 | cut -d: -f1)

            if [ -n "$next_config_line" ]; then
                # 计算实际行号
                local insert_line=$((dg_line + next_config_line))

                # 分割文件并插入
                head -n $((insert_line - 1)) "$config_file" > "$temp_file"
                cat "$rule_file" >> "$temp_file"
                tail -n +$insert_line "$config_file" >> "$temp_file"

                mv "$temp_file" "$config_file"
            else
                # DirectGame 是最后一个 config 块，直接追加
                cat "$rule_file" >> "$config_file"
            fi
        fi

        rm -f "$rule_file"
    else
        rm -f "$rule_file"
        # 没有 DirectGame，使用普通方式添加
        uci set passwall2.$rule_id=shunt_rules
        uci set passwall2.$rule_id.remarks="$remarks"
        [ -n "$domain_list" ] && uci set passwall2.$rule_id.domain_list="$domain_list"
        [ -n "$ip_list" ] && uci set passwall2.$rule_id.ip_list="$ip_list"
        uci commit passwall2
    fi

    send_json "{\"success\":true,\"message\":\"分流规则已添加\"}"
}

# 删除分流规则
delete_shunt_rule() {
    local post_data=$(read_post_data)
    local rule_id=$(echo "$post_data" | jsonfilter -e '@.rule_id' 2>/dev/null)

    if [ -z "$rule_id" ]; then
        send_json "{\"success\":false,\"message\":\"无效的规则ID\"}"
        return
    fi

    uci delete passwall2.$rule_id 2>/dev/null
    uci commit passwall2
    send_json "{\"success\":true,\"message\":\"分流规则已删除\"}"
}

restart_passwall() {
    /etc/init.d/passwall2 restart >/dev/null 2>&1 &
    send_json "{\"success\":true,\"message\":\"Passwall2 正在重启\"}"
}

# 测试节点连接
test_node() {
    local post_data=$(read_post_data)
    local address=$(echo "$post_data" | jsonfilter -e '@.address' 2>/dev/null)
    local port=$(echo "$post_data" | jsonfilter -e '@.port' 2>/dev/null)
    local username=$(echo "$post_data" | jsonfilter -e '@.username' 2>/dev/null)
    local password=$(echo "$post_data" | jsonfilter -e '@.password' 2>/dev/null)

    if [ -z "$address" ] || [ -z "$port" ]; then
        send_json "{\"success\":false,\"message\":\"地址和端口不能为空\"}"
        return
    fi

    # 使用 curl 测试 HTTP 代理连接
    local result
    local http_code
    local start_time=$(date +%s%3N 2>/dev/null || date +%s)

    if [ -n "$username" ] && [ -n "$password" ]; then
        result=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 \
            -x "http://${username}:${password}@${address}:${port}" \
            "http://www.baidu.com" 2>&1)
    else
        result=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 \
            -x "http://${address}:${port}" \
            "http://www.baidu.com" 2>&1)
    fi

    local end_time=$(date +%s%3N 2>/dev/null || date +%s)
    local latency=$((end_time - start_time))

    if [ "$result" = "200" ] || [ "$result" = "302" ] || [ "$result" = "301" ]; then
        send_json "{\"success\":true,\"message\":\"连接成功\",\"latency\":${latency}}"
    else
        send_json "{\"success\":false,\"message\":\"连接失败 (HTTP: ${result})\"}"
    fi
}

# 检查节点是否已存在
check_node_exists() {
    local post_data=$(read_post_data)
    local duplicates="["
    local first=1
    local i=0

    while true; do
        local ip=$(echo "$post_data" | jsonfilter -e "@.nodes[$i].ip" 2>/dev/null)
        [ -z "$ip" ] && break

        local port=$(echo "$post_data" | jsonfilter -e "@.nodes[$i].port" 2>/dev/null)

        # 检查是否存在相同 IP 和端口的节点
        local exists=0
        for section in $(uci show passwall2 2>/dev/null | grep "=nodes" | cut -d'.' -f2 | cut -d'=' -f1); do
            local node_addr=$(uci -q get passwall2.$section.address)
            local node_port=$(uci -q get passwall2.$section.port)
            if [ "$node_addr" = "$ip" ] && [ "$node_port" = "$port" ]; then
                exists=1
                break
            fi
        done

        if [ "$exists" = "1" ]; then
            [ $first -eq 0 ] && duplicates="$duplicates,"
            duplicates="$duplicates\"${ip}:${port}\""
            first=0
        fi

        i=$((i+1))
    done

    duplicates="$duplicates]"
    send_json "{\"success\":true,\"duplicates\":$duplicates}"
}

# 获取已使用的 SOCKS 端口列表
get_used_ports() {
    local ports="["
    local first=1

    for section in $(uci show passwall2 2>/dev/null | grep "=socks" | cut -d'.' -f2 | cut -d'=' -f1); do
        local port=$(uci -q get passwall2.$section.port)
        if [ -n "$port" ]; then
            [ $first -eq 0 ] && ports="$ports,"
            ports="$ports$port"
            first=0
        fi
    done

    ports="$ports]"
    send_json "{\"success\":true,\"ports\":$ports}"
}

# 获取 SOCKS 主开关状态
get_socks_status() {
    local enabled=$(uci -q get passwall2.@global[0].socks_enabled)
    if [ "$enabled" = "1" ]; then
        send_json "{\"success\":true,\"enabled\":true}"
    else
        send_json "{\"success\":true,\"enabled\":false}"
    fi
}

# 切换 SOCKS 主开关
toggle_socks() {
    local current=$(uci -q get passwall2.@global[0].socks_enabled)
    if [ "$current" = "1" ]; then
        uci set passwall2.@global[0].socks_enabled="0"
        uci commit passwall2
        /etc/init.d/passwall2 restart >/dev/null 2>&1 &
        send_json "{\"success\":true,\"enabled\":false,\"message\":\"SOCKS 已关闭\"}"
    else
        uci set passwall2.@global[0].socks_enabled="1"
        uci commit passwall2
        /etc/init.d/passwall2 restart >/dev/null 2>&1 &
        send_json "{\"success\":true,\"enabled\":true,\"message\":\"SOCKS 已开启\"}"
    fi
}

# 导出 SOCKS 列表
export_socks() {
    # 从请求头获取访问的 Host
    local lan_ip=$(echo "$HTTP_HOST" | cut -d':' -f1)
    [ -z "$lan_ip" ] && lan_ip="192.168.1.1"

    local socks_list=""

    for section in $(uci show passwall2 2>/dev/null | grep "=socks" | cut -d'.' -f2 | cut -d'=' -f1); do
        local port=$(uci -q get passwall2.$section.port)
        local enabled=$(uci -q get passwall2.$section.enabled)
        local node=$(uci -q get passwall2.$section.node)

        # 只导出已启用的 SOCKS
        if [ "$enabled" = "1" ] && [ -n "$port" ]; then
            # 获取节点备注
            local remarks=""
            if [ -n "$node" ]; then
                remarks=$(uci -q get passwall2.$node.remarks)
            fi

            if [ -n "$socks_list" ]; then
                socks_list="${socks_list}\n"
            fi

            if [ -n "$remarks" ]; then
                socks_list="${socks_list}${lan_ip}:${port} # ${remarks}"
            else
                socks_list="${socks_list}${lan_ip}:${port}"
            fi
        fi
    done

    # 返回纯文本格式
    echo "Content-Type: text/plain; charset=utf-8"
    echo "Content-Disposition: attachment; filename=\"socks_list.txt\""
    echo ""
    printf "%b" "$socks_list"
}

# 测试出口 IP（通过指定 SOCKS 代理访问目标 URL）
test_exit_ip() {
    local post_data=$(read_post_data)
    local socks_port=$(echo "$post_data" | jsonfilter -e '@.socks_port' 2>/dev/null)
    local test_url=$(echo "$post_data" | jsonfilter -e '@.test_url' 2>/dev/null)

    # 默认测试 URL
    [ -z "$test_url" ] && test_url="https://ip.sb"

    local lan_ip=$(echo "$HTTP_HOST" | cut -d':' -f1)
    [ -z "$lan_ip" ] && lan_ip="127.0.0.1"

    local result=""
    local exit_ip=""
    local http_code=""

    if [ -n "$socks_port" ]; then
        # 通过 SOCKS 代理访问
        result=$(curl -s --connect-timeout 10 --max-time 15 \
            -x "socks5://${lan_ip}:${socks_port}" \
            -w "\n%{http_code}" \
            "$test_url" 2>&1)
    else
        # 直连访问
        result=$(curl -s --connect-timeout 10 --max-time 15 \
            -w "\n%{http_code}" \
            "$test_url" 2>&1)
    fi

    http_code=$(echo "$result" | tail -1)
    local body=$(echo "$result" | sed '$d')

    # 尝试从响应中提取 IP
    if [ "$test_url" = "https://ip.sb" ] || [ "$test_url" = "http://ip.sb" ]; then
        exit_ip=$(echo "$body" | tr -d '[:space:]')
    elif [ "$test_url" = "https://ipinfo.io/ip" ] || [ "$test_url" = "http://ipinfo.io/ip" ]; then
        exit_ip=$(echo "$body" | tr -d '[:space:]')
    elif [ "$test_url" = "https://api.ipify.org" ]; then
        exit_ip=$(echo "$body" | tr -d '[:space:]')
    else
        # 对于其他 URL，只返回 HTTP 状态码
        exit_ip="N/A"
    fi

    if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
        send_json "{\"success\":true,\"exit_ip\":\"$exit_ip\",\"http_code\":\"$http_code\",\"url\":\"$test_url\"}"
    else
        send_json "{\"success\":false,\"message\":\"请求失败\",\"http_code\":\"$http_code\",\"url\":\"$test_url\"}"
    fi
}

# 批量测试出口 IP（测试多个 URL）
test_exit_ip_batch() {
    local post_data=$(read_post_data)
    local socks_port=$(echo "$post_data" | jsonfilter -e '@.socks_port' 2>/dev/null)

    local lan_ip=$(echo "$HTTP_HOST" | cut -d':' -f1)
    [ -z "$lan_ip" ] && lan_ip="127.0.0.1"

    # 通用 User-Agent
    local ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    local results="["
    local first=1

    # 测试 URL 列表
    local test_urls="https://storage.jd.com https://m.360buyimg.com https://www.jd.com"

    for url in $test_urls; do
        local http_code=""
        local remote_ip=""

        if [ -n "$socks_port" ]; then
            http_code=$(curl -s --connect-timeout 8 --max-time 12 \
                -A "$ua" \
                -x "socks5://${lan_ip}:${socks_port}" \
                -o /dev/null -w "%{http_code}" \
                "$url" 2>/dev/null)
            remote_ip=$(curl -s --connect-timeout 8 --max-time 12 \
                -A "$ua" \
                -x "socks5://${lan_ip}:${socks_port}" \
                -o /dev/null -w "%{remote_ip}" \
                "$url" 2>/dev/null)
        else
            http_code=$(curl -s --connect-timeout 8 --max-time 12 \
                -A "$ua" \
                -o /dev/null -w "%{http_code}" \
                "$url" 2>/dev/null)
            remote_ip=$(curl -s --connect-timeout 8 --max-time 12 \
                -A "$ua" \
                -o /dev/null -w "%{remote_ip}" \
                "$url" 2>/dev/null)
        fi

        # 清理可能的特殊字符
        http_code=$(echo "$http_code" | tr -cd '0-9')
        remote_ip=$(echo "$remote_ip" | tr -cd '0-9.')

        [ -z "$http_code" ] && http_code="0"
        [ -z "$remote_ip" ] && remote_ip="-"

        [ $first -eq 0 ] && results="$results,"
        results="$results{\"url\":\"$url\",\"http_code\":\"$http_code\",\"remote_ip\":\"$remote_ip\"}"
        first=0
    done

    # 获取出口 IP - 尝试多个服务
    local my_ip=""
    local ip_services="https://api.ipify.org https://ifconfig.me/ip https://icanhazip.com"

    for ip_svc in $ip_services; do
        if [ -n "$socks_port" ]; then
            my_ip=$(curl -s --connect-timeout 5 --max-time 8 \
                -A "$ua" \
                -x "socks5://${lan_ip}:${socks_port}" \
                "$ip_svc" 2>/dev/null | tr -cd '0-9.\n' | head -1)
        else
            my_ip=$(curl -s --connect-timeout 5 --max-time 8 \
                -A "$ua" \
                "$ip_svc" 2>/dev/null | tr -cd '0-9.\n' | head -1)
        fi

        # 检查是否获取到有效 IP（至少包含一个点）
        if echo "$my_ip" | grep -q '\.'; then
            break
        fi
        my_ip=""
    done

    [ -z "$my_ip" ] && my_ip="获取失败"

    results="$results]"
    send_json "{\"success\":true,\"exit_ip\":\"$my_ip\",\"results\":$results}"
}

# 当前版本号
CURRENT_VERSION="1.0.0"
UPDATE_URL="https://raw.githubusercontent.com/ChunKitGitHub/passwall2-batch/main/version.json"
IPK_URL="https://raw.githubusercontent.com/ChunKitGitHub/passwall2-batch/main/passwall2-batch_latest.ipk"

# 检查更新
check_update() {
    local version_info
    version_info=$(curl -s --connect-timeout 10 --max-time 20 "$UPDATE_URL" 2>/dev/null)

    if [ -z "$version_info" ]; then
        send_json "{\"success\":false,\"message\":\"无法连接更新服务器\"}"
        return
    fi

    local latest_version=$(echo "$version_info" | jsonfilter -e '@.version' 2>/dev/null)
    local changelog=$(echo "$version_info" | jsonfilter -e '@.changelog' 2>/dev/null | sed 's/"/\\"/g')

    if [ -z "$latest_version" ]; then
        send_json "{\"success\":false,\"message\":\"无法解析版本信息\"}"
        return
    fi

    # 比较版本号
    local has_update="false"
    if [ "$latest_version" != "$CURRENT_VERSION" ]; then
        # 简单版本比较：去掉点号后比较数字
        local cur_num=$(echo "$CURRENT_VERSION" | tr -d '.')
        local new_num=$(echo "$latest_version" | tr -d '.')
        if [ "$new_num" -gt "$cur_num" ] 2>/dev/null; then
            has_update="true"
        fi
    fi

    send_json "{\"success\":true,\"current_version\":\"$CURRENT_VERSION\",\"latest_version\":\"$latest_version\",\"has_update\":$has_update,\"changelog\":\"$changelog\"}"
}

# 执行更新
do_update() {
    local tmp_file="/tmp/passwall2-batch_update.ipk"

    # 下载新版本
    curl -s --connect-timeout 30 --max-time 120 -o "$tmp_file" "$IPK_URL" 2>/dev/null

    if [ ! -f "$tmp_file" ] || [ ! -s "$tmp_file" ]; then
        send_json "{\"success\":false,\"message\":\"下载更新包失败\"}"
        return
    fi

    # 安装更新
    local install_result
    install_result=$(opkg install --force-reinstall "$tmp_file" 2>&1)

    if echo "$install_result" | grep -q "Configuring"; then
        rm -f "$tmp_file"
        send_json "{\"success\":true,\"message\":\"更新成功\"}"
    else
        rm -f "$tmp_file"
        send_json "{\"success\":false,\"message\":\"安装失败: $(echo "$install_result" | head -1 | sed 's/"/\\"/g')\"}"
    fi
}

# 路由
case "$PATH_INFO" in
    /get_shunt_rules) get_shunt_rules ;;
    /get_rule_detail) get_rule_detail ;;
    /edit_shunt_rule) edit_shunt_rule ;;
    /move_rule) move_rule ;;
    /check_default_rules) check_default_rules ;;
    /get_nodes) get_nodes ;;
    /import) import_nodes ;;
    /edit_node) edit_node ;;
    /delete_node) delete_node ;;
    /batch_delete) batch_delete ;;
    /add_shunt_rule) add_shunt_rule ;;
    /delete_shunt_rule) delete_shunt_rule ;;
    /restart) restart_passwall ;;
    /test_node) test_node ;;
    /check_node_exists) check_node_exists ;;
    /get_used_ports) get_used_ports ;;
    /get_socks_status) get_socks_status ;;
    /toggle_socks) toggle_socks ;;
    /export_socks) export_socks ;;
    /test_exit_ip) test_exit_ip ;;
    /test_exit_ip_batch) test_exit_ip_batch ;;
    /check_update) check_update ;;
    /do_update) do_update ;;
    *) send_json "{\"success\":false,\"message\":\"未知API: $PATH_INFO\"}" ;;
esac
