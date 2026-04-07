# UFW OkBoy 使用指南

> 动态防火墙白名单管理工具 — 让授权用户的 IP 变更不再需要手动处理。

---

## 目录

- [这是什么](#这是什么)
- [工作原理](#工作原理)
- [快速开始](#快速开始)
- [服务端部署](#服务端部署)
- [密钥生成与分发](#密钥生成与分发)
- [客户端使用](#客户端使用)
- [日常管理](#日常管理)
- [安全机制](#安全机制)
- [常见问题](#常见问题)

---

## 这是什么

你的服务器上有一些端口（比如管理后台、数据库）只允许特定 IP 访问，通过 UFW 防火墙的白名单来控制。
但现实是：用户的 IP 会变（切换网络、重启路由器、出差换地方），每次变化都要联系管理员手动更新防火墙，非常麻烦。

**UFW OkBoy** 解决的就是这个问题：

- 用户打开一个网页，完成一次认证
- 服务器自动识别用户当前的 IP，更新防火墙白名单
- 只要网页不关，每 30 秒自动"续期"一次
- 用户 IP 变了？下一次续期会自动切换，无需任何操作
- 管理员随时能看到每条防火墙规则对应的是哪个用户

一句话总结：**用户只需要打开网页，防火墙的事交给系统处理。**

## 工作原理

```
用户浏览器 / 客户端脚本
      |
      | HTTPS 请求（携带 HMAC 签名认证）
      v
  Nginx（反向代理，TLS 加密，传递用户真实 IP）
      |
      v
  Flask API 服务（验证身份，获取用户 IP）
      |
      v
  UFW 防火墙（移除旧 IP 规则，添加新 IP 规则）
      |
      v
  状态文件（记录每个用户的当前 IP 和最后活跃时间）
```

**关键机制：**

| 特性 | 说明 |
|------|------|
| 认证方式 | HMAC-SHA256 签名 + 时间戳，密钥永远不在网络上传输 |
| 规则管理 | 每个用户每个端口只保留一条规则，IP 变更时自动替换旧规则 |
| 规则标记 | 每条 UFW 规则带注释 `ufw-okboy:用户名`，`ufw status` 一目了然 |
| 过期清理 | 长时间未活跃的用户规则会被自动清除，防火墙保持干净 |
| 防盗用 | 同一账号只能绑定一个 IP，共享凭证 = 互相踢，自损行为 |

## 快速开始

> 最短路径：5 分钟部署服务端，30 秒完成客户端使用。

### 服务端（管理员操作）

```bash
# 1. 拉取代码
git clone <仓库地址> /opt/ufw-okboy
cd /opt/ufw-okboy

# 2. 创建虚拟环境并安装依赖
python3 -m venv venv
venv/bin/pip install -r server/requirements.txt

# 3. 生成用户密钥
cd server
../venv/bin/python app.py gen-secret alice

# 4. 创建配置文件，填入密钥
cp config.example.yaml config.yaml
nano config.yaml    # 修改 protected_ports 和 users 部分

# 5. 启动服务（测试）
sudo ../venv/bin/python app.py serve --debug
```

### 客户端（用户操作）

1. 用浏览器打开 `https://your-server.com/`
2. 输入管理员给你的**用户名**和**密钥**
3. 点击 **Connect** — 完成！

页面会自动保持连接，每 30 秒刷新一次。关闭页面后再次打开，会自动恢复连接。

---

## 服务端部署

### 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu / Debian（或任何支持 UFW 的 Linux 发行版） |
| Python | 3.8 或更高版本 |
| 防火墙 | UFW 已安装并启用 |
| Web 服务器 | Nginx 已安装，HTTPS 证书已部署 |
| 权限 | 需要 root 权限（UFW 操作需要） |

### 前置条件：UFW 防火墙配置

> **重要**：在部署本工具之前，必须先确保 UFW 的默认策略和基本规则正确。
> 操作不当可能导致你被锁在服务器外面，请务必按顺序执行。

```bash
# 1. 确保 SSH 已放行（防止把自己锁在外面！）
sudo ufw allow 22/tcp

# 2. 确保 HTTPS 端口已放行（客户端通过此端口访问）
sudo ufw allow 443/tcp

# 3. 设置默认策略为拒绝所有入站连接
#    这一步是本工具有意义的前提 — 如果不设置默认拒绝，
#    所有端口对所有人开放，防火墙白名单就没有作用。
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 4. 启用 UFW
sudo ufw enable

# 5. 确认当前状态
sudo ufw status
```

确认输出中至少包含 22/tcp 和 443/tcp 的 ALLOW 规则后，再继续部署。

### 第一步：安装项目文件

```bash
# 将项目文件放到服务器上
git clone <仓库地址> /opt/ufw-okboy
cd /opt/ufw-okboy

# 创建 Python 虚拟环境
python3 -m venv venv
venv/bin/pip install -r server/requirements.txt

# 创建数据目录
mkdir -p /var/lib/ufw-okboy
mkdir -p /var/log/ufw-okboy
```

### 第二步：配置服务

```bash
cd /opt/ufw-okboy/server
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，重点修改以下内容：

```yaml
# 需要保护的端口（用户认证后可以访问这些端口）
protected_ports:
  - 8080        # 改成你实际要保护的端口
  # - 3306      # 可以添加多个端口

# 用户列表（密钥通过 gen-secret 命令生成）
users:
  alice:
    secret: "这里填生成的密钥"
```

> **注意**：`config.yaml` 包含用户密钥，请确保文件权限为 `600`：
> ```bash
> chmod 600 config.yaml
> ```

### 第三步：配置 Nginx 反向代理

将项目中的 Nginx 配置复制到 Nginx 目录：

```bash
cp /opt/ufw-okboy/nginx/ufw-okboy.conf /etc/nginx/sites-available/
ln -s /etc/nginx/sites-available/ufw-okboy.conf /etc/nginx/sites-enabled/
```

编辑 `/etc/nginx/sites-available/ufw-okboy.conf`，修改域名和证书路径：

```nginx
server_name your-server.com;  # ← 改成你的域名

ssl_certificate     /etc/letsencrypt/live/your-server.com/fullchain.pem;  # ← 证书路径
ssl_certificate_key /etc/letsencrypt/live/your-server.com/privkey.pem;    # ← 私钥路径
```

在 Nginx 主配置 `/etc/nginx/nginx.conf` 的 `http` 块中添加限速配置：

```nginx
http {
    # ... 其他配置 ...
    limit_req_zone $binary_remote_addr zone=okboy:10m rate=3r/s;
}
```

测试并重载 Nginx：

```bash
nginx -t && systemctl reload nginx
```

> **关键**：Nginx 必须传递 `X-Real-IP` 头，否则服务端无法获取用户的真实 IP。
> 项目提供的 Nginx 配置已经包含了这个设置，不要删除它。

### 第四步：启动服务

**方式 A — 手动启动（测试用）：**

```bash
cd /opt/ufw-okboy/server
sudo ../venv/bin/python app.py serve --debug
```

**方式 B — Systemd 服务（生产用）：**

```bash
# 安装服务文件
cp /opt/ufw-okboy/deploy/ufw-okboy.service /etc/systemd/system/
cp /opt/ufw-okboy/deploy/ufw-okboy-cleanup.service /etc/systemd/system/
cp /opt/ufw-okboy/deploy/ufw-okboy-cleanup.timer /etc/systemd/system/

# 加载并启动
systemctl daemon-reload
systemctl enable --now ufw-okboy              # API 服务
systemctl enable --now ufw-okboy-cleanup.timer # 每日自动清理过期规则
```

### 第五步：验证部署

```bash
# 检查服务状态
systemctl status ufw-okboy

# 检查健康端点
curl https://your-server.com/health
# 应返回: {"ok": true, "service": "ufw-okboy"}

# 打开浏览器访问 https://your-server.com/
# 应看到登录页面
```

## 密钥生成与分发

### 生成密钥

为每个需要访问的用户生成一个专属密钥：

```bash
cd /opt/ufw-okboy/server
sudo ../venv/bin/python app.py gen-secret alice
```

输出示例：

```
Generated secret for 'alice':

  a1b2c3d4e5f6...（64位随机密钥）

Add to config.yaml:

  users:
    alice:
      secret: "a1b2c3d4e5f6..."
```

将输出的密钥填入 `config.yaml` 的 `users` 部分，然后重启服务：

```bash
systemctl restart ufw-okboy
```

### 分发给用户

用户需要收到两样东西：

| 信息 | 示例 |
|------|------|
| 用户名 | `alice` |
| 密钥 | `a1b2c3d4e5f6...` |

**分发方式（按安全性排序）：**

| 方式 | 安全性 | 说明 |
|------|--------|------|
| 当面告知 | 最高 | 直接当面给用户看密钥，用户现场输入 |
| 加密消息 | 高 | 通过支持端到端加密的工具发送（如 Signal） |
| 分开发送 | 中等 | 用户名通过一个渠道发，密钥通过另一个渠道发 |
| 即时消息 | 一般 | 微信/钉钉直接发送（发完提醒用户删除聊天记录） |

**推荐分发流程：**

```
管理员                                用户
  |                                    |
  |  1. 生成密钥                        |
  |                                    |
  |  2. 发送服务器地址和用户名          |
  |  ──────────────────────────────►   |
  |  （如：微信发送）                    |
  |                                    |
  |  3. 通过另一个渠道发送密钥          |
  |  ──────────────────────────────►   |
  |  （如：短信/电话告知）              |
  |                                    |
  |                 4. 打开网页，输入凭证 |
  |                    勾选"记住凭证"    |
  |                    点击 Connect     |
  |                                    |
  |  5. 确认用户已连接成功              |
  |  （运行 python app.py list 查看）   |
  |                                    |
  |  6. 提醒用户删除聊天中的密钥        |
  |  ──────────────────────────────►   |
```

### 发给用户的模板消息

以下是一段可以直接发给用户的说明文字：

---

> **访问授权信息**
>
> 你的账号已开通，请按以下步骤操作：
>
> 1. 用浏览器打开：`https://your-server.com/`
> 2. 输入用户名：`alice`
> 3. 输入密钥：`（单独发送）`
> 4. 勾选「Remember credentials」后点击「Connect」
>
> 连接成功后页面会显示绿色状态。只要页面不关，访问权限会自动保持。
> 页面关闭后重新打开会自动恢复连接，无需重新输入。
>
> **请在输入完成后删除包含密钥的消息。**

---

### 注意事项

- **一个用户名对应一个密钥**，不要多人共用同一个账号
- **密钥等同于密码**，泄露后应立即更换（修改 config.yaml 中对应的 secret，重启服务）
- 如需撤销某人的访问权限，从 config.yaml 中删除该用户，然后执行清理：
  ```bash
  sudo ../venv/bin/python app.py cleanup --max-age 0
  systemctl restart ufw-okboy
  ```

## 客户端使用

提供三种客户端方式，适应不同使用场景：

| 方式 | 适用场景 | 技术要求 |
|------|----------|----------|
| 网页客户端 | 日常使用，手机/电脑均可 | 只需浏览器 |
| Python 客户端 | 无界面的服务器 | 需要 Python 3 |
| Shell 客户端 | 极简环境 | 只需 curl + openssl |

### 方式一：网页客户端（推荐）

这是最简单的方式，适合所有用户。

**首次使用：**

1. 打开浏览器，访问 `https://your-server.com/`
2. 输入管理员提供的**用户名**和**密钥**
3. 勾选 **Remember credentials**（记住凭证）
4. 点击 **Connect**

连接成功后页面会显示：
- 绿色状态指示灯和「Connected」文字
- 你当前被注册的 IP 地址
- 下次自动续期的倒计时（30 秒）

**之后每次使用：**

直接打开同一个网页地址即可，页面会自动恢复连接，无需重新输入凭证。

**使用提示：**

- 页面保持打开期间，访问权限自动维持
- 切换网络（比如 WiFi 换成手机热点）后，下一个 30 秒周期会自动更新 IP
- 切换到其他标签页也没问题，回来时会立即补一次更新
- 如果要断开连接并清除保存的凭证，点击 **Disconnect**
- 手机浏览器同样适用，建议添加到主屏幕方便使用
- **不要在公共电脑上勾选「Remember credentials」**，凭证会以明文保存在浏览器中

### 方式二：Python 客户端

适合无图形界面的服务器或需要自动化运行的场景。

**安装：**

```bash
# 复制客户端文件到目标机器
scp client/knock.py client/config.example.yaml user@client-machine:~/ufw-okboy/

# 在客户端机器上安装依赖（可选，没有也能运行）
pip install pyyaml
```

**配置：**

```bash
cd ~/ufw-okboy
cp config.example.yaml config.yaml
nano config.yaml
```

```yaml
server_url: "https://your-server.com"
username: "alice"
secret: "你的密钥"
```

```bash
chmod 600 config.yaml  # 保护配置文件
```

**使用：**

```bash
# 单次敲门（注册当前 IP）
python3 knock.py

# 查看当前注册状态
python3 knock.py status

# 持续模式：每 30 秒自动敲门（推荐）
python3 knock.py --watch 30

# 使用自定义配置文件路径
python3 knock.py -c /path/to/config.yaml --watch 30
```

**后台运行（通过 systemd）：**

```bash
# 在客户端机器上安装 systemd 服务
sudo cp deploy/knock.service /etc/systemd/system/
sudo cp deploy/knock.timer /etc/systemd/system/

# 编辑 knock.service，修改 ExecStart 中的路径
sudo nano /etc/systemd/system/knock.service

# 启动
sudo systemctl daemon-reload
sudo systemctl enable --now knock.timer
```

### 方式三：Shell 客户端

零依赖方案，只需要 `curl` 和 `openssl`，几乎所有 Linux 系统都自带。

**安装：**

```bash
# 复制脚本到客户端机器
scp client/knock.sh user@client-machine:/usr/local/bin/ufw-okboy-knock.sh
chmod +x /usr/local/bin/ufw-okboy-knock.sh
```

**配置：**

```bash
mkdir -p ~/.config/ufw-okboy
cat > ~/.config/ufw-okboy/config << 'EOF'
SERVER_URL=https://your-server.com
USERNAME=alice
SECRET=你的密钥
EOF
chmod 600 ~/.config/ufw-okboy/config
```

**使用：**

```bash
# 敲门
ufw-okboy-knock.sh

# 查看状态
ufw-okboy-knock.sh status
```

**设置 cron 定时任务：**

```bash
# 每 2 分钟自动敲门
crontab -e
# 添加以下行：
*/2 * * * * /usr/local/bin/ufw-okboy-knock.sh >/dev/null 2>&1
```

## 日常管理

### 查看当前状态

```bash
cd /opt/ufw-okboy/server
sudo ../venv/bin/python app.py -c config.yaml list
```

输出示例：

```
=== Configured Users ===
  alice                 IP: 203.0.113.42        Last knock: 2025-01-15 14:30:22
  bob                   IP: 198.51.100.7        Last knock: 2025-01-15 14:29:58

=== UFW Rules (managed) ===
  8080/tcp    ALLOW IN    203.0.113.42    # ufw-okboy:alice
  8080/tcp    ALLOW IN    198.51.100.7    # ufw-okboy:bob
```

也可以直接查看 UFW 规则：

```bash
sudo ufw status
```

所有由本工具管理的规则都带有 `# ufw-okboy:用户名` 的注释，一目了然。

### 清理过期规则

长时间未活跃的用户规则会占用防火墙条目。手动清理：

```bash
# 清理超过 7 天未活跃的规则（默认）
sudo ../venv/bin/python app.py -c config.yaml cleanup --max-age 7

# 清理超过 1 天未活跃的规则
sudo ../venv/bin/python app.py -c config.yaml cleanup --max-age 1
```

如果在部署时启用了定时清理服务，系统会每天自动执行清理（默认 7 天阈值）：

```bash
# 查看定时清理状态
systemctl status ufw-okboy-cleanup.timer
```

### 添加新用户

```bash
# 1. 生成密钥
sudo ../venv/bin/python app.py gen-secret 新用户名

# 2. 将密钥添加到 config.yaml
nano config.yaml

# 3. 重启服务使配置生效
systemctl restart ufw-okboy

# 4. 将用户名和密钥分发给用户（参见"密钥生成与分发"章节）
```

### 移除用户

```bash
# 1. 从 config.yaml 中删除该用户
nano config.yaml

# 2. 重启服务（使配置生效）
systemctl restart ufw-okboy

# 3. 清除该用户残留的防火墙规则
#    注意：cleanup --max-age 0 会清除「所有」托管规则（不只是被删除的用户）。
#    其他在线用户会在 30 秒内通过下一次 knock 自动恢复，短暂中断不影响使用。
sudo ../venv/bin/python app.py -c config.yaml cleanup --max-age 0
```

> **提示**：如果不希望影响其他用户，可以手动删除特定规则：
> ```bash
> # 查看当前规则编号
> sudo ufw status numbered
> # 删除指定编号的规则（注意删除后编号会变，从大到小删更安全）
> sudo ufw delete <编号>
> ```

### 更换用户密钥

如果怀疑密钥泄露，立即更换：

```bash
# 1. 生成新密钥
sudo ../venv/bin/python app.py gen-secret 用户名

# 2. 在 config.yaml 中替换旧密钥
nano config.yaml

# 3. 重启服务
systemctl restart ufw-okboy

# 4. 将新密钥通过安全渠道发给用户
# 5. 用户需要在网页上 Disconnect 后用新密钥重新 Connect
```

### 故障排查

**服务无法启动：**
```bash
# 查看详细错误日志
journalctl -u ufw-okboy -n 50 --no-pager
```

**用户反馈连接失败：**
```bash
# 检查 Nginx 是否正常代理
curl -v https://your-server.com/health

# 检查 Flask 是否在运行
curl http://127.0.0.1:5000/health

# 查看应用日志
tail -f /var/log/ufw-okboy/error.log
```

**防火墙规则不生效：**
```bash
# 确认 UFW 已启用
sudo ufw status

# 确认规则是否已添加
sudo ufw status | grep ufw-okboy

# 确认目标端口没有被其他规则覆盖（UFW 按规则顺序匹配）
sudo ufw status numbered
```

---

## 安全机制

### 认证原理

本工具使用 **HMAC-SHA256 + 时间戳** 进行认证：

```
客户端生成签名 = HMAC-SHA256(密钥, "用户名:当前时间戳")
发送请求头: Authorization: HMAC-SHA256 用户名:时间戳:签名
```

**为什么这样设计：**

- **密钥不在网络上传输** — 即使请求被截获，攻击者得到的是签名，不是密钥
- **时间戳防重放** — 签名在 5 分钟后过期，截获的旧请求无法重复使用
- **HTTPS 双重保护** — 整个请求经过 TLS 加密传输

### 防凭证共享

系统通过以下机制防止用户将凭证共享给他人：

**天然防护 — 一个账号只能绑定一个 IP：**

假设 Alice 将凭证分享给了 Bob：
1. Bob 用 Alice 的凭证连接 → 防火墙更新为 Bob 的 IP
2. Alice 立刻失去访问权限（她的 IP 已被替换）
3. Alice 的页面下一次续期 → 又把 Bob 踢掉
4. 两人不断互相踢，谁都无法稳定使用

**结论：共享凭证 = 自损，是一种自我惩罚的行为。**

**主动检测 — IP 变更频率异常报警：**

正常用户的 IP 很少变化（一天变一两次是正常的，比如换网络）。但如果一个账号的 IP 在 1 小时内变更超过 5 次（两人互相踢的典型特征），系统会：

- 在服务端日志中记录详细告警（包含所有相关 IP）
- 在客户端页面上显示异常警告

管理员可以通过以下方式查看异常：

```bash
# 在服务端日志中搜索异常记录
grep "ANOMALY" /var/log/ufw-okboy/error.log
```

### 配置项参考

以下是 `config.yaml` 中所有可调配置项的完整说明：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `protected_ports` | 无（必填） | 需要保护的端口列表 |
| `proto` | `tcp` | 协议类型，可改为 `udp` |
| `listen_host` | `127.0.0.1` | Flask 监听地址 |
| `listen_port` | `5000` | Flask 监听端口 |
| `signature_ttl` | `300` | HMAC 签名有效期（秒）。客户端时钟偏差大时可增大 |
| `rule_prefix` | `ufw-okboy` | UFW 规则注释前缀 |
| `state_file` | `/var/lib/ufw-okboy/state.json` | 状态文件路径 |
| `anomaly_window` | `3600` | 异常检测时间窗口（秒），默认 1 小时 |
| `anomaly_max_changes` | `5` | 窗口内允许的最大 IP 变更次数 |
| `users` | 无（必填） | 用户名和密钥映射 |

> **注意**：所有用户共享同一份端口列表。目前不支持按用户分配不同端口权限。
> 如果需要精细控制，可以部署多个实例，每个实例保护不同的端口组。

### 安全最佳实践

| 建议 | 说明 |
|------|------|
| 一人一号 | 不要多人共用同一个账号，无法追溯且会互相踢 |
| 及时换密钥 | 怀疑泄露时立即更换，参见"更换用户密钥" |
| 保护配置文件 | 服务端 config.yaml 权限设为 600 |
| 启用自动清理 | 让不活跃的规则自动过期，保持防火墙整洁 |
| 监控日志 | 定期检查是否有认证失败或异常告警 |
| HTTPS 必须开启 | 不要在 HTTP 下使用，会导致认证信息被明文传输 |

---

## 常见问题

### 我的 IP 变了怎么办？

什么都不需要做。如果你使用的是网页客户端，页面会在 30 秒内自动检测到 IP 变化并更新防火墙规则。如果使用 Python/Shell 客户端配合定时任务，也会在下一个执行周期自动更新。

### 关掉网页后怎么办？

关掉网页后，你的防火墙规则**不会立即消失**。规则会一直保留到被清理为止（默认 7 天未活跃才会被自动清除）。所以短时间关掉页面不影响正在使用中的连接。

再次打开同一个网址即可恢复自动续期。如果之前勾选了「Remember credentials」，页面会自动恢复连接。如果没有勾选，需要重新输入用户名和密钥。

### 手机上能用吗？

可以。用手机浏览器打开 `https://your-server.com/` 即可，操作方式和电脑完全一样。建议将网页添加到手机主屏幕，方便随时打开。

### 密钥忘了怎么办？

联系管理员重新生成一个新密钥。旧密钥会立即失效。

### 页面显示「Network Error」？

- 检查网络连接是否正常
- 确认服务器地址是否正确
- 可能是服务端暂时不可用，页面会自动重试

### 页面显示「Signature expired」？

你的设备时间与服务器时间相差超过 5 分钟。请同步设备时间（手机一般自动同步，电脑检查时区和 NTP 设置）。

### 页面显示「Warning: Anomaly Detected」？

你的 IP 在短时间内频繁变化。可能原因：
- 网络环境不稳定（正常，可以忽略）
- 有其他人在使用你的凭证（立即联系管理员更换密钥）

### 同时在手机和电脑上打开可以吗？

可以打开，但只有最后一次「敲门」的设备的 IP 会被注册。如果手机和电脑使用同一个网络（同一个公网 IP），没有任何问题。如果使用不同网络，会出现互相覆盖的情况。

### 管理员：如何支持多个端口？

在 `config.yaml` 的 `protected_ports` 列表中添加多个端口：

```yaml
protected_ports:
  - 8080
  - 3306
  - 6379
```

用户认证后会自动获得所有列出端口的访问权限。

### 管理员：如何升级到新版本？

```bash
cd /opt/ufw-okboy
git pull
venv/bin/pip install -r server/requirements.txt  # 更新依赖
systemctl restart ufw-okboy
```

升级不会影响现有的 `config.yaml` 和 `state.json`。

### 管理员：应该备份什么？

最重要的是 **`config.yaml`**（包含所有用户密钥）。`state.json` 丢失可以恢复，但密钥丢失需要重新生成并分发给所有用户。

```bash
cp /opt/ufw-okboy/server/config.yaml /备份路径/config.yaml.bak
```

### 管理员：state.json 丢失了怎么办？

使用同步命令从现有 UFW 规则中恢复状态：

```bash
sudo ../venv/bin/python app.py -c config.yaml sync
```

这会扫描 UFW 中带有 `ufw-okboy:` 注释的规则，重建 state.json。
