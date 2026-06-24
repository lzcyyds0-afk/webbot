# WebBot — 网页自动化测试机器人

基于 Playwright 的网页自动化测试平台，支持任务编排、实时日志推送与结果查看。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2.0 · Alembic · Playwright · python-socketio |
| 前端 | React 18 · TypeScript · Vite · Ant Design · Zustand · Socket.IO Client |
| 数据库 | SQLite (dev) / PostgreSQL (prod) |
| 缓存 | Redis |

## 本地启动

### 前置条件

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (Python 包管理)
- pnpm (`npm i -g pnpm`)
- Playwright 浏览器 (`playwright install`)

### 一键初始化

```bash
bash scripts/init-dev.sh
```

### 手动启动

```bash
# 后端
cd backend
uv sync
uv run playwright install
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend
pnpm install
pnpm dev
```

### Docker Compose

```bash
docker compose up --build
```

- 后端: http://localhost:8000
- 前端: http://localhost:5173
- API 文档: http://localhost:8000/docs

## Windows 部署

### 前置条件

- Python 3.11+（安装时勾选 "Add to PATH"）
- Node.js 18+（安装时勾选 "Add to PATH"）
- [uv](https://docs.astral.sh/uv/):
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- pnpm:
  ```powershell
  npm install -g pnpm
  ```
- Google Chrome（推荐）或 Microsoft Edge — Playwright 会自动回退到内置 Chromium

### 一键启动（推荐）

双击运行 `scripts/start-dev.bat`，会自动打开两个窗口分别启动后端和前端。

### 手动启动

```powershell
# 后端
cd backend
$env:PYTHONPATH = "$PWD"
uv sync
uv run playwright install chromium
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

# 前端（另一个 PowerShell 窗口）
cd frontend
pnpm install
pnpm dev
```

### Windows 常见问题

| 问题 | 解决 |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | 确保设置了 `PYTHONPATH` 环境变量指向 backend 目录 |
| Playwright 启动失败 / Chrome 找不到 | 安装 Google Chrome，或让 Playwright 自动下载 Chromium |
| 端口被占用 | 检查是否有其他程序占用了 8000 或 5173 端口 |
| 前端报错 502 | 后端服务未启动，先启动后端再刷新前端 |
| Alembic 迁移失败 | 数据库 schema 由 Alembic 管理（不再启动时自动建表）。全新环境直接 `uv run alembic upgrade head`。旧的「自动建表」库没有迁移版本记录，若 schema 已完整可执行 `uv run alembic stamp head`，否则删除 `backend/data/webbot.db` 后重新 `alembic upgrade head` |

## Cookie 配置（登录态支持）

测试需要登录的页面时，可以在用例编辑器中配置 Cookie，执行测试时 Playwright 会自动将其注入浏览器上下文。

### 方式一：脚本自动提取（推荐）

适用于 Cookie **不含 `HttpOnly` 标记**的网站。

1. 在浏览器中**登录目标网站**（确保登录成功）
2. 按 **F12** 打开开发者工具，切换到 **Console** 标签
3. 在 WebBot 用例编辑器的「Cookie 配置」面板中，点击 **「复制提取脚本」**
4. **切换到目标网站的浏览器标签页**，在 Console 中粘贴脚本并回车
5. Cookie JSON 会自动复制到剪贴板
6. 回到 WebBot，粘贴到 Cookie JSON 编辑器中，保存即可

> ⚠️ `document.cookie` **无法读取 `HttpOnly` Cookie**。如果登录态依赖 HttpOnly Cookie，请用方式二。

### 方式二：手动从 DevTools 复制（支持 HttpOnly）

适用于 Cookie **包含 `HttpOnly` 标记**的网站（大多数现代 Web 应用的 session 认证）。

1. 在浏览器中**登录目标网站**
2. 按 **F12** 打开开发者工具 → 切换到 **Application（应用）** 标签
3. 左侧展开 **Cookies** → 点击目标域名
4. 找到维持登录态的关键 Cookie（如 `sessionid`、`token`、`auth` 等）
5. 手动填入 JSON 格式：

```json
[
  {
    "name": "sessionid",
    "value": "abc123",
    "domain": ".example.com",
    "path": "/",
    "httpOnly": true,
    "secure": true,
    "sameSite": "Lax"
  }
]
```

### 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | Cookie 名称 |
| `value` | ✅ | Cookie 值 |
| `domain` | ✅ | 所属域名（不要带 `https://`），如 `coze.cn` |
| `path` | 可选 | 默认 `/` |
| `httpOnly` | 可选 | HttpOnly 标记的填 `true` |
| `secure` | 可选 | HTTPS 网站填 `true` |
| `sameSite` | 可选 | `Strict` / `Lax` / `None` |

### 验证 Cookie 是否生效

保存 Cookie 后运行测试，查看第一步 `goto` 之后的截图：

- 已登录 → ✅ Cookie 生效
- 仍在登录页 → ❌ 检查 `domain`、`sameSite` 是否正确，或补充缺失的 HttpOnly Cookie

## 项目结构

```
webbot/
├── backend/          # FastAPI 后端
│   ├── app/          # 应用源码
│   ├── migrations/   # Alembic 迁移
│   └── tests/        # pytest 测试
├── frontend/         # React 前端
│   └── src/
├── scripts/          # 辅助脚本
│   ├── start-dev.bat      # Windows 一键启动
│   ├── start-backend.bat  # Windows 启动后端
│   └── start-frontend.bat # Windows 启动前端
└── docker-compose.yml
```
