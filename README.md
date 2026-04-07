# UFW OkBoy

**动态防火墙白名单管理工具** — 授权用户认证后自动将其 IP 注册到 UFW，IP 变化时无缝切换，保持防火墙规则整洁可追溯。

[English](README.en.md) | 中文

<p align="center">
  <img src="docs/web-client.png" alt="Web 客户端界面" width="380">
</p>

---

## 为什么需要它

服务器上的敏感端口（管理后台、数据库、API）通过 UFW 防火墙白名单限制访问。但客户端 IP 会变——切换 WiFi、出差、重启路由器——每次都要找管理员手动改规则。

**UFW OkBoy 让这件事自动化**：用户打开网页认证一次，服务器自动更新防火墙；IP 变了，下一个心跳周期无感切换。

## 工作流程

```
客户端（浏览器 / Python / Shell）
    |
    | HTTPS + HMAC-SHA256 签名认证
    v
Nginx（反向代理，TLS 加密，传递真实 IP）
    |
    v
Flask API（验证身份，提取客户端 IP）
    |
    v
UFW（移除旧规则 → 添加新规则 → 注释：ufw-okboy:<用户名>）
```

## 核心特性

| 特性 | 说明 |
|------|------|
| **网页客户端** | 浏览器打开即用，每 30 秒自动续期，关闭后重开自动恢复。手机适用 |
| **规则整洁** | 每用户每端口仅一条规则，IP 变更时自动替换，不留残余 |
| **规则可追溯** | UFW 规则带注释 `ufw-okboy:<用户名>`，`ufw status` 直观可查 |
| **防凭证共享** | 同一账号只能绑定一个 IP，共享即互踢；异常 IP 切换自动告警 |
| **自动过期清理** | 7 天未活跃的规则由每日定时任务自动清除 |
| **认证安全** | HMAC-SHA256 + 时间戳，密钥不上线，全程 HTTPS |
| **三种客户端** | Web UI / Python 脚本 / Shell 脚本（curl + openssl，零依赖） |

## 快速开始

**服务端（管理员）：**

```bash
git clone https://github.com/lvusyy/UFW-OkBoy.git /opt/ufw-okboy
cd /opt/ufw-okboy
python3 -m venv venv && venv/bin/pip install -r server/requirements.txt
cd server
../venv/bin/python app.py gen-secret alice    # 生成用户密钥
cp config.example.yaml config.yaml            # 编辑：填入端口和密钥
sudo ../venv/bin/python app.py serve --debug   # 启动（开发模式）
```

**客户端（用户）：**

浏览器打开 `https://your-server.com/` → 输入用户名和密钥 → 点击 **Connect** → 完成。

## 完整文档

详见 **[GUIDE.md](GUIDE.md)**（中文），包含：

- 服务端部署（UFW 前置配置、Nginx、Systemd）
- 密钥生成与安全分发流程（含发给用户的模板消息）
- 客户端使用说明（Web / Python / Shell）
- 日常管理（用户增删、规则清理、故障排查）
- 安全机制与最佳实践
- 常见问题解答

## 目录结构

```
server/
  app.py              Flask API + CLI（serve / gen-secret / list / cleanup / sync）
  ufw_ops.py          UFW 操作 + 状态持久化
  static/index.html   Web 客户端（单文件 SPA，无需构建）
  config.example.yaml 配置模板
  requirements.txt    依赖清单
client/
  knock.py            Python 客户端（仅标准库）
  knock.sh            Shell 客户端（curl + openssl）
  config.example.yaml 客户端配置模板
nginx/
  ufw-okboy.conf      Nginx 反向代理配置
deploy/
  ufw-okboy.service   Systemd 服务（Gunicorn）
  ufw-okboy-cleanup.* 过期规则清理定时器
  knock.*             客户端自动续期定时器
  install-server.sh   一键安装脚本
```

## 许可证

MIT
