# 教师备课系统 - 后端

## 环境要求

* [Docker](https://www.docker.com/)
* [uv](https://docs.astral.sh/uv/) — Python 包和环境管理工具

## Docker Compose

按照 [../development.md](../development.md) 中的指南，使用 Docker Compose 启动本地开发环境。

## 开发工作流

本项目默认使用 [uv](https://docs.astral.sh/uv/) 管理依赖，请先安装它。

在 `./backend/` 目录下安装所有依赖：

```console
$ uv sync
```

然后激活虚拟环境：

```console
# Windows
$ .venv\Scripts\activate
```

确保你的编辑器使用的是正确的 Python 虚拟环境，解释器路径为 `backend/.venv/bin/python`（Windows 下为 `backend\.venv\Scripts\python.exe`）。

在 `./backend/app/models.py` 中修改或添加 SQLModel 数据模型和 SQL 表，在 `./backend/app/api/` 中添加 API 端点，在 `./backend/app/crud.py` 中编写 CRUD 工具函数。

## VS Code

项目已配置好通过 VS Code 调试器运行后端，你可以使用断点、暂停、探索变量等功能。

同样也已配置好通过 VS Code 的 Python 测试面板运行测试。

## Docker Compose 覆盖配置

在开发过程中，你可以在 `compose.override.yml` 文件中修改 Docker Compose 设置，这些修改只影响本地开发环境。

例如，后端代码目录会在 Docker 容器中同步挂载，你修改的代码会实时同步到容器内，无需重新构建 Docker 镜像即可立即测试更改。这只适用于开发环境，生产环境应使用最新版本的后端代码构建 Docker 镜像。

还有一个命令覆盖，运行 `fastapi run --reload` 而不是默认的 `fastapi run`。它启动单个服务器进程（而非生产环境的多进程），并在代码变更时自动重载。注意：如果 Python 文件有语法错误并保存，进程会崩溃退出，容器也会停止。修复错误后重新启动：

```console
$ docker compose watch
```

## 后端测试

运行后端测试：

```console
$ bash ./scripts/test.sh
```

测试使用 Pytest 运行，可以在 `./backend/tests/` 中修改和添加测试。

如果你使用了 GitHub Actions，测试会自动运行。

### 在运行中的容器中测试

如果 Docker 容器已经在运行，只想执行测试：

```bash
docker compose exec backend bash scripts/tests-start.sh
```

该脚本会在确认其他服务就绪后调用 `pytest`。如需传递额外参数给 `pytest`：

```bash
docker compose exec backend bash scripts/tests-start.sh -x
```

### 测试覆盖率

测试运行后会在 `htmlcov/index.html` 生成覆盖率报告，可以在浏览器中打开查看。

## 数据库迁移

在本地开发时，应用目录作为卷挂载到容器内，你可以在容器内使用 `alembic` 命令运行迁移，生成的迁移文件会保存在你的应用目录中（而非仅存在于容器内），方便提交到 Git 仓库。

每次修改模型后，务必创建 "revision" 并 "upgrade" 数据库，否则应用会报错。

* 进入后端容器的交互式会话：

```console
$ docker compose exec backend bash
```

* Alembic 已配置好导入 `./backend/app/models.py` 中的 SQLModel 模型。

* 修改模型后（例如添加字段），在容器内创建迁移版本：

```console
$ alembic revision --autogenerate -m "为 User 模型添加 last_name 字段"
```

* 将 alembic 目录中生成的文件提交到 Git 仓库。

* 创建版本后，运行迁移以实际更新数据库：

```console
$ alembic upgrade head
```

如果不想使用迁移，可以取消 `./backend/app/core/db.py` 中以下代码的注释：

```python
SQLModel.metadata.create_all(engine)
```

并注释 `scripts/prestart.sh` 中的：

```console
$ alembic upgrade head
```

如果想从头开始自定义模型，可以删除 `./backend/app/alembic/versions/` 下的所有版本文件（`.py` 文件），然后按上述步骤创建首次迁移。

## 邮件模板

邮件模板位于 `./backend/app/email-templates/`。包含两个目录：`build` 和 `src`。`src` 目录存放用于构建最终邮件模板的源文件，`build` 目录存放应用实际使用的模板。

使用前请确保在 VS Code 中安装了 [MJML 扩展](https://github.com/mjmlio/vscode-mjml)。

安装 MJML 扩展后，可以在 `src` 目录创建新的邮件模板。创建 `.mjml` 文件并在编辑器中打开，使用 `Ctrl+Shift+P` 打开命令面板，搜索 `MJML: Export to HTML`。这将把 `.mjml` 文件转换为 `.html` 文件，保存到 build 目录即可。
