# 教师备课系统 - 开发指南

## Docker Compose

* 使用 Docker Compose 启动本地环境：

```bash
docker compose watch
```

* 在浏览器中访问以下地址：

前端（Docker 构建，按路径处理路由）：<http://localhost:5173>

后端（基于 OpenAPI 的 JSON Web API）：<http://localhost:8000>

Swagger UI 自动交互式文档：<http://localhost:8000/docs>

Adminer 数据库管理：<http://localhost:8080>

Traefik UI（查看代理路由情况）：<http://localhost:8090>

**注意**：首次启动可能需要等待一分钟，后端需要等待数据库就绪并完成配置。可以通过查看日志来监控状态。

查看所有日志：

```bash
docker compose logs
```

查看特定服务的日志：

```bash
docker compose logs backend
```

## Mailcatcher

Mailcatcher 是一个简单的 SMTP 服务器，在本地开发时捕获所有后端发送的邮件。不会发送真实邮件，而是在 Web 界面中显示。

用途：
* 开发时测试邮件功能
* 验证邮件内容和格式
* 调试邮件相关功能而不发送真实邮件

使用 Docker Compose 本地运行时，后端自动配置为使用 Mailcatcher（SMTP 端口 1025）。所有捕获的邮件可在 <http://localhost:1080> 查看。

## 本地开发

Docker Compose 配置使每个服务在 `localhost` 的不同端口上可用。

后端和前端使用与本地开发服务器相同的端口，所以后端在 `http://localhost:8000`，前端在 `http://localhost:5173`。

这样，你可以停止某个 Docker Compose 服务，转而启动其本地开发服务器，一切照常工作，因为端口号一致。

例如，停止 Docker 中的前端服务：

```bash
docker compose stop frontend
```

然后启动本地前端开发服务器：

```bash
bun run dev
```

或者停止 Docker 中的后端服务：

```bash
docker compose stop backend
```

然后运行本地后端开发服务器：

```bash
cd backend
fastapi dev app/main.py
```

## Docker Compose 文件和环境变量

主配置文件 `compose.yml` 包含了整个技术栈的配置，由 `docker compose` 自动加载。

还有一个 `compose.override.yml` 包含开发环境的覆盖配置，例如将源代码挂载为卷。它也会被 `docker compose` 自动应用。

这些文件使用 `.env` 文件中的配置，将其注入为容器的环境变量。

修改环境变量后，请确保重启服务：

```bash
docker compose watch
```

## .env 文件

`.env` 文件包含所有配置、生成的密钥和密码等。

根据你的工作流决定是否将其加入 `.gitignore`。如果项目是公开的，建议排除。这种情况下，需要确保 CI 工具在构建或部署时能获取到这些环境变量。

## 代码检查

项目使用 [prek](https://prek.j178.dev/)（[Pre-commit](https://pre-commit.com/) 的现代替代品）进行代码检查和格式化。

安装后，每次 git commit 之前会自动运行，确保代码在提交前保持一致和格式化。

根目录下有 `.pre-commit-config.yaml` 配置文件。

### 安装 prek 自动运行

`prek` 已包含在项目依赖中。安装后需要在本地仓库中初始化，使其在每次提交前自动运行。

在 `backend` 目录下使用 `uv`：

```bash
❯ uv run prek install -f
prek installed at `../.git/hooks/pre-commit`
```

`-f` 标志强制安装，如果之前已安装过 pre-commit hook 则覆盖。

现在每次提交时 prek 会自动运行，检查并格式化即将提交的代码。

### 手动运行 prek

也可以手动对所有文件运行 `prek`：

```bash
❯ uv run prek run --all-files
check for added large files..............................................Passed
check toml...............................................................Passed
check yaml...............................................................Passed
fix end of files.........................................................Passed
trim trailing whitespace.................................................Passed
ruff.....................................................................Passed
ruff-format..............................................................Passed
biome check..............................................................Passed
```

## 本地访问地址

### 开发地址

* 前端：<http://localhost:5173>
* 后端：<http://localhost:8000>
* Swagger UI 交互式文档：<http://localhost:8000/docs>
* ReDoc 替代文档：<http://localhost:8000/redoc>
* Adminer：<http://localhost:8080>
* Traefik UI：<http://localhost:8090>
* MailCatcher：<http://localhost:1080>
