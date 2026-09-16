# 教师备课系统 - 部署指南

你可以使用 Docker Compose 将项目部署到远程服务器。

本项目需要使用 Traefik 代理来处理外部通信和 HTTPS 证书。

你可以使用 CI/CD（持续集成和持续部署）系统进行自动部署，项目已配置好 GitHub Actions 工作流。

## 准备工作

* 准备一台可用的远程服务器。
* 配置域名的 DNS 记录，指向刚创建的服务器的 IP。
* 为域名配置泛解析子域名，方便为不同服务使用不同子域名，例如 `*.your-domain.com`。这样可以访问不同的组件，如 `dashboard.your-domain.com`、`api.your-domain.com`、`traefik.your-domain.com`、`adminer.your-domain.com`，以及测试环境如 `dashboard.staging.your-domain.com`、`adminer.staging.your-domain.com` 等。
* 在远程服务器上安装并配置 [Docker](https://docs.docker.com/engine/install/)（Docker Engine，而非 Docker Desktop）。

## 公共 Traefik

需要一个 Traefik 代理来处理外部请求和 HTTPS 证书。以下步骤只需执行一次。

### Traefik Docker Compose

* 在远程服务器上创建目录存放 Traefik Docker Compose 文件：

```bash
mkdir -p /root/code/traefik-public/
```

将 Traefik Docker Compose 文件复制到服务器，可以在本地终端使用 `rsync` 命令：

```bash
rsync -a compose.traefik.yml root@your-server.com:/root/code/traefik-public/
```

### Traefik 公共网络

Traefik 需要一个名为 `traefik-public` 的 Docker 公共网络来与你的应用通信。

这样，由单个公共 Traefik 代理处理与外部世界的通信（HTTP 和 HTTPS），然后在内部可以运行一个或多个使用不同域名的应用，即使它们在同一台服务器上。

在远程服务器上运行以下命令创建 Docker 公共网络：

```bash
docker network create traefik-public
```

### Traefik 环境变量

Traefik Docker Compose 文件需要设置一些环境变量。

* 创建 HTTP 基本认证的用户名：

```bash
export USERNAME=admin
```

* 创建 HTTP 基本认证的密码：

```bash
export PASSWORD=changethis
```

* 使用 openssl 生成密码的哈希值：

```bash
export HASHED_PASSWORD=$(openssl passwd -apr1 $PASSWORD)
```

验证哈希密码是否正确：

```bash
echo $HASHED_PASSWORD
```

* 设置服务器域名：

```bash
export DOMAIN=your-domain.com
```

* 设置 Let's Encrypt 邮箱：

```bash
export EMAIL=admin@your-domain.com
```

**注意**：需要设置真实的邮箱地址，`@example.com` 邮箱不可用。

### 启动 Traefik

进入远程服务器上存放 Traefik Docker Compose 文件的目录：

```bash
cd /root/code/traefik-public/
```

设置好环境变量并准备好 `compose.traefik.yml` 后，启动 Traefik：

```bash
docker compose -f compose.traefik.yml up -d
```

## 部署应用

Traefik 就绪后，即可使用 Docker Compose 部署应用。

### 复制代码

```bash
rsync -av --filter=":- .gitignore" ./ root@your-server.com:/root/code/app/
```

注意：`--filter=":- .gitignore"` 告诉 `rsync` 使用与 git 相同的忽略规则，忽略 Python 虚拟环境等文件。

### 环境变量

部署前需要设置以下环境变量。

#### 生成安全密钥

`.env` 文件中有些变量默认值为 `changethis`，必须替换为安全密钥。运行以下命令生成：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

复制输出内容作为密码/密钥。重复运行生成多个不同的安全密钥。

#### 必填环境变量

设置 `ENVIRONMENT`，部署到服务器时使用 `staging` 或 `production`：

```bash
export ENVIRONMENT=production
```

设置 `DOMAIN`：

```bash
export DOMAIN=your-domain.com
```

设置 `POSTGRES_PASSWORD`：

```bash
export POSTGRES_PASSWORD="your-secure-password"
```

设置 `SECRET_KEY`（用于签名令牌）：

```bash
export SECRET_KEY="your-secret-key"
```

设置 `FIRST_SUPERUSER_PASSWORD`：

```bash
export FIRST_SUPERUSER_PASSWORD="your-superuser-password"
```

设置 `BACKEND_CORS_ORIGINS`：

```bash
export BACKEND_CORS_ORIGINS="https://dashboard.${DOMAIN},https://api.${DOMAIN}"
```

其他可配环境变量：

* `PROJECT_NAME`：项目名称，显示在 API 文档和邮件中。
* `STACK_NAME`：Docker Compose 标签和项目名称，不同环境应使用不同名称，如 `your-domain-com` 和 `staging-your-domain-com`。
* `BACKEND_CORS_ORIGINS`：允许的 CORS 来源列表，逗号分隔。
* `FIRST_SUPERUSER`：初始超级用户邮箱。
* `SMTP_HOST`：SMTP 邮件服务器地址。
* `SMTP_USER`：SMTP 邮件服务器用户名。
* `SMTP_PASSWORD`：SMTP 邮件服务器密码。
* `EMAILS_FROM_EMAIL`：发件邮箱地址。
* `POSTGRES_SERVER`：PostgreSQL 服务器主机名，默认 `db` 即可。
* `POSTGRES_PORT`：PostgreSQL 端口，默认即可。
* `POSTGRES_USER`：Postgres 用户名。
* `POSTGRES_DB`：应用数据库名称，默认 `app`。
* `SENTRY_DSN`：Sentry DSN（如果使用）。

### 使用 Docker Compose 部署

环境变量就绪后，执行部署：

```bash
cd /root/code/app/
docker compose -f compose.yml build
docker compose -f compose.yml up -d
```

生产环境不使用 `compose.override.yml`，因此明确指定 `compose.yml`。

## 持续部署（CD）

可以使用 GitHub Actions 自动部署项目，支持多环境部署。

### 安装 GitHub Actions Runner

* 在远程服务器上创建 GitHub Actions 用户：

```bash
sudo adduser github
```

* 为 `github` 用户添加 Docker 权限：

```bash
sudo usermod -aG docker github
```

* 切换到 `github` 用户：

```bash
sudo su - github
```

* 进入 home 目录：

```bash
cd
```

* [按照官方指南安装 GitHub Action 自托管 Runner](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners#adding-a-self-hosted-runner-to-a-repository)。

* 当询问标签时，添加环境标签，如 `production`。

安装完成后，官方指南会让你运行一个命令启动 runner。但该进程会在终端关闭或连接断开后停止。为了确保持续运行，需要安装为系统服务：

```bash
exit  # 回到 root 用户
sudo su  # 切换到 root
cd /home/github/actions-runner
./svc.sh install github  # 安装服务
./svc.sh start           # 启动服务
./svc.sh status          # 检查状态
```

### 配置 GitHub Environments

部署工作流使用 [GitHub Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) 管理 `staging` 和 `production` 环境。进入仓库的 **Settings** > **Environments** 创建环境。

### 设置 Secrets

为每个 GitHub Environment 配置所需的环境 secrets：

* `DOMAIN_PRODUCTION`
* `DOMAIN_STAGING`
* `STACK_NAME_PRODUCTION`
* `STACK_NAME_STAGING`
* `EMAILS_FROM_EMAIL`
* `FIRST_SUPERUSER`
* `FIRST_SUPERUSER_PASSWORD`
* `POSTGRES_PASSWORD`
* `SECRET_KEY`
* `LATEST_CHANGES`
* `SMOKESHOW_AUTH_KEY`

## 访问地址

替换 `your-domain.com` 为你的实际域名。

### 生产环境

* 前端：`https://dashboard.your-domain.com`
* 后端 API 文档：`https://api.your-domain.com/docs`
* 后端 API 基础地址：`https://api.your-domain.com`
* 数据库管理：`https://adminer.your-domain.com`

### 测试环境

* 前端：`https://dashboard.staging.your-domain.com`
* 后端 API 文档：`https://api.staging.your-domain.com/docs`
* 后端 API 基础地址：`https://api.staging.your-domain.com`
* 数据库管理：`https://adminer.staging.your-domain.com`
