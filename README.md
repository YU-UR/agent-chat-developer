# Agent Chat System

一个用于学习和实践企业级 AI 聊天系统的项目，采用前后端分离、异步任务处理、SSE 流式响应、持久化会话状态以及长期记忆架构。

> **当前状态：Stage 8 部署准备中。** 根目录 `compose.yaml`、后端/前端 Dockerfile 和 Nginx 配置已准备，但尚未完成应用镜像的真实构建、全量容器运行和端到端部署验收。本文件中的生产部署命令是未来部署步骤，不代表当前已验证可直接投入生产。

## 主要组件

| 层 | 技术/组件 | 主要职责 |
|---|---|---|
| Web 前端 | React、TypeScript、Vite、Axios、Zustand | 聊天界面、客户端状态、HTTP 请求、SSE 订阅 |
| API | FastAPI、Uvicorn | 接收聊天请求、提供 SSE 事件流及相关 API |
| 异步任务 | Kafka、Chat Worker、Outbox Publisher、Memory Worker | 解耦聊天执行和记忆处理，支持消费组与任务重试 |
| 状态与数据库 | PostgreSQL、SQLAlchemy、Alembic | 会话、消息、任务、Outbox 及数据库迁移 |
| 图状态 | LangGraph、PostgreSQL Checkpoint | 管理图执行状态和持久化检查点 |
| 实时事件 | Redis Streams、SSE | 缓存运行事件并向浏览器持续发送流式更新 |
| 长期记忆 | Mem0、Milvus、Sentence Transformers | 记忆提取、向量存储与相关性检索 |
| 本地模型 | Qwen、Transformers | 本地 LLM 推理 |
| 代码执行 | Sandbox API、Docker SDK | 在受限容器中执行 Python 代码 |
| 部署 | Docker Compose、Nginx | 组织基础设施和应用服务，托管前端并转发 API/SSE |

## 架构与请求流程

### 聊天主流程

1. 浏览器向 `POST /api/chat` 提交消息，后端创建运行记录并返回 `run_id`。
2. 前端通过 `GET /api/chat/{run_id}/events` 建立 SSE 连接。
3. Kafka 将聊天运行请求传递给 Chat Worker。
4. Chat Worker 调用 LangGraph/ChatService 执行任务，将运行事件写入 Redis Stream。
5. FastAPI 从 Redis Stream 读取事件，并通过 SSE 推送给前端。

### 记忆处理流程

1. Chat Worker 和业务逻辑将记忆写入任务记录到 PostgreSQL。
2. Outbox Publisher 读取待发布的 Outbox 事件并发布到 Kafka。
3. Memory Worker 消费 `memory.extract.requested` 等记忆相关事件。
4. Memory Worker 调用记忆提取、安全检查和写入逻辑，再通过 Mem0 写入/检索 Milvus。

### 主要服务地址

| 服务 | 本地开发地址/端口 | 说明 |
|---|---|---|
| Frontend (Vite) | `http://127.0.0.1:5173` | 本地开发网页 |
| Backend API | `http://127.0.0.1:8000` | FastAPI |
| Sandbox API | `http://127.0.0.1:8010` | Sandbox HTTP 接口 |
| Local LLM Server | `http://127.0.0.1:8020` | 本地模型 API |
| PostgreSQL | `localhost:5432` | 应用数据库/Checkpoint |
| Redis | `localhost:6379` | Redis Streams、幂等与运行事件 |
| Kafka | `localhost:9092` | 本地开发连接地址 |
| Milvus | `localhost:19530` | 向量数据库 |
| MinIO Console | `http://localhost:9001` | 对象存储控制台（如有需要） |

## 项目目录

```text
agent-chat/
├── backend/
│   ├── app/
│   │   ├── agents/chat/       # LangGraph 图、节点、状态与上下文
│   │   ├── api/               # FastAPI 路由
│   │   ├── infrastructure/    # PostgreSQL、Kafka、Redis、LangGraph Runtime
│   │   ├── llm/               # 本地 LLM 与模型 API 服务
│   │   ├── memory/            # 记忆提取、安全、检索、写入与任务处理
│   │   ├── models/            # SQLAlchemy 模型
│   │   ├── repositories/      # 数据访问层
│   │   ├── sandbox/           # Sandbox 客户端、执行器与策略
│   │   ├── schemas/           # API 数据结构
│   │   ├── services/          # 聊天、运行管理、幂等服务
│   │   ├── workers/           # Chat、Memory、Outbox Worker
│   │   └── main.py            # FastAPI 入口
│   ├── alembic/               # 数据库迁移
│   ├── scripts/               # 维护/诊断工具
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── alembic.ini
│   ├── requirements.txt       # 应用直接依赖清单
│   └── requirements-stage7-verified.txt  # Stage 7 环境快照，仅作参考
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── nginx.conf
│   └── package.json
├── infra/
│   └── redis/redis.conf       # Redis 容器实际使用的配置
├── scripts/
│   ├── dev.ps1                # 一键启动 7 个本地开发进程
│   ├── stop-dev.ps1           # 停止由 dev.ps1 记录的进程树
│   ├── infra-up.ps1            # 启动根目录 Compose 中的基础设施
│   └── infra-down.ps1          # 停止根目录 Compose 中的基础设施
├── compose.yaml               # 唯一的 Compose 配置入口
├── .env                       # 本机真实配置，不应分享或提交
├── .env.example               # 配置模板
├── .gitignore
└── README.md
```

## Windows 本地开发

本地开发继续使用 Windows + Conda 环境 `learnLLM`。不需要把所有 Python 进程放进 Docker；这样更容易查看控制台输出、使用断点调试和快速重启单个服务。

### 1. 准备环境

- Docker Desktop 已启动。
- 已创建并激活 Conda 环境 `learnLLM`。
- 前端依赖已经安装。
- 根目录 `.env` 存在，且数据库用户名/密码与数据库 URL 中的凭据一致。

```powershell
conda activate learnLLM
cd D:\Workspace\pycharm-work\agent-chat
```

### 2. 启动基础设施

```powershell
.\scripts\infra-up.ps1
```

脚本使用根目录 `compose.yaml` 启动 PostgreSQL、Redis、Kafka、Milvus、etcd 和 MinIO。查看基础设施状态：

```powershell
docker compose --env-file .\.env -f .\compose.yaml ps
```

### 3. 一键启动开发进程

```powershell
.\scripts\dev.ps1
```

此脚本会打开独立 PowerShell 窗口，分别运行：

- Frontend
- Backend API
- Sandbox API
- Local LLM Server
- Chat Worker
- Memory Worker
- Outbox Publisher

每个窗口显示各自的实时日志。打开窗口不等于服务必然成功；请检查每个窗口的启动日志。

停止由该脚本启动并写入 `.dev-pids.txt` 的进程树：

```powershell
.\scripts\stop-dev.ps1
```

停止开发进程不会停止 Docker 基础设施。

### 4. 单独启动某个服务

可以在独立的 PowerShell 窗口中启动一个进程，方便排错或调试。先确保基础设施已启动，并处于 `learnLLM` 环境。

```powershell
# Backend API
cd D:\Workspace\pycharm-work\agent-chat\backend
python -m uvicorn app.main:app --reload --port 8000 --access-log --log-level info
```

其他后端进程分别使用：

```powershell
# Sandbox API
python -m uvicorn app.sandbox.main:app --host 127.0.0.1 --port 8010

# Local LLM Server
python -m uvicorn app.llm.local_llm_server:app --host 127.0.0.1 --port 8020

# Chat Worker
python -m app.workers.chat_worker

# Memory Worker
python -m app.workers.memory_worker

# Outbox Publisher
python -m app.workers.outbox_publisher
```

前端单独启动：

```powershell
cd D:\Workspace\pycharm-work\agent-chat\frontend
npm run dev
```

本地 Vite 将 `/api` 请求代理到 `http://127.0.0.1:8000`，包括 SSE 路径。浏览器访问 `http://127.0.0.1:5173`。

> 调试 Worker 时注意：同一个 Kafka consumer group 可以运行多个实例，但这会改变分区分配。不要在无意间重复启动多个消费者来处理同一任务流。

## 环境变量

- `.env`：本机真实配置。包含数据库密码等信息，不应放入公开仓库或分享给他人。
- `.env.example`：不含真实秘密的配置模板。复制模板时必须自行设置密码、目录和服务器地址。
- 根目录 `compose.yaml` 对容器服务覆盖数据库、Kafka、Redis、Milvus、Local LLM 与 Sandbox 的内部访问地址。

重要变量包括：

| 变量 | 用途 |
|---|---|
| `COMPOSE_PROJECT_NAME` | Compose 项目名 |
| `AGENT_CHAT_DATA_DIR` | 数据持久化的宿主机根目录 |
| `POSTGRES_*` | PostgreSQL 镜像、端口、数据库、用户和密码 |
| `DATABASE_URL` | 应用 SQLAlchemy 异步数据库连接 |
| `ALEMBIC_DATABASE_URL` | Alembic 迁移连接 |
| `LANGGRAPH_CHECKPOINT_DATABASE_URL` | LangGraph Checkpoint 连接 |
| `REDIS_HOST`、`REDIS_PORT` | Redis 连接地址 |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka bootstrap 地址 |
| `MEMORY_LLM_BASE_URL` | Mem0 调用的 LLM 地址 |
| `MILVUS_URI` | Mem0/Milvus 向量库地址 |
| `SANDBOX_API_URL` | Sandbox API 地址 |
| `SANDBOX_HTTP_TIMEOUT_SECONDS` | Sandbox HTTP 请求超时（秒） |
| `MEMORY_SEARCH_TIMEOUT_SECONDS` | 记忆检索超时（秒） |
| `FRONTEND_PORT` | Compose 部署时前端映射到宿主机的端口 |
| `MINIO_ROOT_USER`、`MINIO_ROOT_PASSWORD` | MinIO 凭据 |
| `DOCKER_GID` | Linux 部署时 Docker Socket 所属组的数字 GID（必须在目标机器核实） |

本地 Windows 环境的常见地址是 `localhost`。Docker 网络中的容器必须使用 Compose 服务名，例如 `postgres:5432`、`redis:6379`、`kafka:29092`、`milvus:19530`。这两种地址场景不同，不能直接互换。

## 测试与基础检查

### Python 编译检查与依赖检查

```powershell
cd D:\Workspace\pycharm-work\agent-chat\backend
python -m compileall -q app tests
python -m pip check
```

### 运行记忆检索相关性测试

从 `backend` 目录运行脚本测试时，设置模块搜索路径：

```powershell
cd D:\Workspace\pycharm-work\agent-chat\backend
$env:PYTHONPATH = (Get-Location).Path
python .\tests\integration\test_retrieval_relevance.py
```

该测试曾验证问候跳过、数据库偏好检索和语言偏好检索。变更后仍应重新运行相关测试。

### 检查 Compose 配置

```powershell
cd D:\Workspace\pycharm-work\agent-chat
docker compose --env-file .\.env -f .\compose.yaml config -q
```

配置校验成功不会输出内容。它只证明 Compose 文件语法和变量展开可解析，不代表应用镜像已成功构建或应用服务已成功运行。

## 未来 Linux / Docker 部署流程

**以下是实际准备部署到 Linux 服务器时的操作顺序。当前应用镜像和完整容器链路尚未完成真实构建验收，因此不要把此流程理解为生产部署已经验证。**

### 1. 准备 Linux 服务器

- 安装受支持的 Docker Engine 和 Docker Compose 插件。
- 将项目代码放到服务器部署目录。
- 为数据配置持久化目录，例如 `/srv/agent-chat/data`。
- 检查服务器端口、安全组和防火墙策略。
- 生成生产专用的强密码，不要使用 `.env.example` 中的占位符或本地演示凭据。

### 2. 准备服务器 `.env`

根据 `.env.example` 创建部署用 `.env`，至少确认：

- `AGENT_CHAT_DATA_DIR` 指向 Linux 服务器的绝对路径。
- PostgreSQL 密码和三个数据库 URL 中的密码完全一致。
- MinIO 使用生产专用凭据。
- `DOCKER_GID` 与该服务器 `/var/run/docker.sock` 的实际组 ID 匹配（可在 Linux 上用 `stat -c '%g' /var/run/docker.sock` 查看）。
- 检查模型服务的 CPU/GPU 方案、模型缓存与磁盘空间。

### 3. 静态校验和构建

在服务器项目根目录执行：

```bash
docker compose --env-file .env -f compose.yaml config -q
docker compose --env-file .env -f compose.yaml build
```

当前 `requirements.txt` 是直接依赖清单，并不锁定全部间接依赖；Linux `pip --dry-run` 曾经成功解析，但选择的若干间接依赖版本比 Stage 7 快照更新。真实部署前应进一步固定并验证依赖组合，并确认 PyTorch 的 CPU/GPU 安装方式，以免镜像过大或运行时不匹配。

### 4. 数据库迁移

构建成功后，在启动应用前按项目迁移配置运行：

```bash
docker compose --env-file .env -f compose.yaml run --rm backend alembic upgrade head
```

执行前应先在目标环境确认备份策略和迁移脚本；生产数据库变更应先备份，并按发布流程执行。

### 5. 启动服务和检查日志

```bash
docker compose --env-file .env -f compose.yaml up -d
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs -f backend chat-worker memory-worker outbox-publisher local-llm-server sandbox frontend
```

前端默认通过 `FRONTEND_PORT` 映射到宿主机（模板示例为 `8080`）。上线前应完成完整的 API、SSE、Kafka 消费、记忆写入/检索、模型服务和 Sandbox 集成测试，并配置 HTTPS、域名、访问控制、备份、监控和日志保留。

### 6. 停止服务

```bash
docker compose --env-file .env -f compose.yaml down
```

该命令不带 `-v`，不会主动删除 Compose 管理的命名卷；项目使用的绑定挂载数据目录也不会因停止容器而自动删除。仍然应在执行数据迁移或系统清理之前先做备份。

## 生产部署前的风险与待办

1. **Sandbox Docker Socket 权限**：当前 Compose 草案将 `/var/run/docker.sock` 挂载到 Sandbox 服务。能够控制 Docker Socket 的进程通常具有很高的宿主机权限。真实生产环境优先使用隔离的执行主机或专用 Docker Daemon，并限制 Sandbox API 的网络可达范围。不要把 Docker Socket 暴露给 Backend API 或普通 Worker。
2. **模型运行方式**：当前模型由 `transformers`/PyTorch 加载。需要根据服务器硬件确定 CPU 或 GPU 方案，检查镜像大小、显存/内存、启动耗时和模型缓存。
3. **依赖锁定**：完成 Linux 依赖解析和真实构建后，生成适合部署平台的锁定清单；不要直接把 Windows Conda 快照中的本地文件路径当成 Linux 依赖安装来源。
4. **就绪探针和启动顺序**：Compose 的 `service_started` 只表示容器进程已启动，不等于 API 或模型已就绪。应补齐应用服务 healthcheck，并验证 Worker 在 Kafka、数据库、Milvus 和模型服务尚未准备好时的恢复行为。
5. **安全配置**：生产环境应使用强密码、限制对外暴露的端口、配置 HTTPS、身份验证/授权、密钥管理和定期数据备份。
6. **CORS 与反向代理**：前端生产构建使用相对路径 `/api`；Nginx 将 API/SSE 转发到 `backend:8000`。上线时确认后端 CORS、代理头和 SSE 不缓冲配置符合实际域名与 HTTPS 拓扑。
7. **未完成的部署验收**：当前仅做过 Compose 语法检查和基础设施配置流程验证。新增的应用 Dockerfile、Nginx 配置以及所有应用容器尚需真实构建与集成测试。

## 当前维护原则

- `backend/app/` 是核心业务代码，移动文件前先检查 import、入口命令和测试。
- `backend/tests/` 用于测试；`backend/scripts/` 用于维护与诊断；根目录 `scripts/` 用于开发和基础设施生命周期管理。
- `requirements-stage7-verified.txt` 保留作 Stage 7 环境快照参考；部署依赖使用 `requirements.txt`，后续再结合实际 Linux 验证结果锁定间接依赖。
- `compose.yaml` 是唯一 Compose 入口。基础设施、应用服务和数据目录统一从该文件管理。


## 👤 Author

Created and maintained by **UNan**.

- GitHub: [@YU-UR](https://github.com/YU-UR)
- Repository: [agent-chat-developer](https://github.com/YU-UR/agent-chat-developer)

## 📜 License

This project is currently provided for personal and educational use only.

© 2026 UNan. All rights reserved.