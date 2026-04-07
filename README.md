# UFW OkBoy

**动态防火墙白名单管理工具** — 授权用户认证后自动将其 IP 注册到 UFW，IP 变化时无缝切换，保持防火墙规则整洁可追溯。

[English](README.en.md) | 中文

---

## 背景问题

服务器上的敏感端口（管理后台、数据库、API）通过 UFW 防火墙白名单限制访问 IP。但客户端 IP 会变化——切换网络、出差换地方、重启路由器，每次都要联系管理员手动更新防火墙，效率极低。

## 解决方案

UFW OkBoy 将这个流程自动化。客户端通过 HTTPS 端点认证，服务器自动识别当前 IP 并更新 UFW 规则。IP 变化时，旧规则在下一次心跳时自动替换。每条规则标注用户名，`ufw status` 一目了然。

```
客户端（浏览器 / Python / Shell）
    |
    | HTTPS + HMAC-SHA256 认证
    v
Nginx（反向代理，TLS，传递 X-Real-IP）
    |
    v
Flask API（验证身份，获取客户端真实 IP）
    |
    v
UFW（移除旧规则 → 添加新规则 → 注释：ufw-okboy:<用户名>）
```

## 核心特性

- **网页客户端** — 打开页面登录一次，每 30 秒自动续期。凭证保存在浏览器中，重开页面自动恢复连接。手机同样适用。
- **一人一个 IP 槽** — 添加新 IP 前自动移除旧规则，防火墙始终保持整洁
- **规则可追溯** — 每条 UFW 规则带注释 `ufw-okboy:<用户名>`，`ufw status` 直接看出归属
- **防凭证共享** — 共享凭证 = 互相踢（同一账号只有一个 IP 有效）；异常 IP 切换频率自动告警
- **自动清理** — 超过 7 天未活跃的用户规则由每日定时任务自动清除
- **认证简洁安全** — HMAC-SHA256 + 时间戳，密钥不在网络传输，全程 HTTPS 加密
- **三种客户端** — Web UI（仅需浏览器）、Python 脚本、Shell 脚本（仅需 curl + openssl）

## 快速开始

**服务端（管理员）：**

```bash
git clone https://github.com/lvusyy/UFW-OkBoy.git /opt/ufw-okboy
cd /opt/ufw-okboy
python3 -m venv venv && venv/bin/pip install -r server/requirements.txt
cd server
../venv/bin/python app.py gen-secret alice        # 生成用户密钥
cp config.example.yaml config.yaml                # 编辑：填入端口和密钥
sudo ../venv/bin/python app.py serve --debug       # 启动（开发模式）
```

**客户端（用户）：**

用浏览器打开 `https://your-server.com/` → 输入用户名和密钥 → 点击 Connect。

## 完整文档

详见 **[GUIDE.md](GUIDE.md)**，包含：

- 服务端部署（UFW 前置配置、Nginx、Systemd）
- 密钥生成与安全分发流程（含发给用户的模板消息）
- 客户端使用说明（Web / Python / Shell）
- 日常管理（用户增删、规则清理、故障排查）
- 安全机制与最佳实践
- 常见问题解答

## 目录结构

```
server/
  app.py              Flask API + CLI 管理（serve/gen-secret/list/cleanup/sync）
  ufw_ops.py          UFW 操作 + 状态管理
  static/index.html   Web 客户端（单文件 SPA，无需构建）
  config.example.yaml 服务端配置模板
  requirements.txt    Python 依赖
client/
  knock.py            Python 客户端（仅标准库，零外部依赖）
  knock.sh            Shell 客户端（仅需 curl + openssl）
  config.example.yaml 客户端配置模板
nginx/
  ufw-okboy.conf      Nginx 反向代理配置
deploy/
  ufw-okboy.service   Systemd 服务（Gunicorn）
  ufw-okboy-cleanup.* 每日过期规则清理定时器
  knock.*             客户端自动续期定时器
  install-server.sh   服务端一键安装脚本
```

## 许可证

MIT
