# Agent Chat System

A project for learning and practicing enterprise-grade AI chat systems. It adopts a decoupled frontend and backend architecture, asynchronous task processing, SSE streaming responses, persistent conversation state, and a long-term memory architecture.

> **Current status: Preparing for deployment.** The root-level `compose.yaml`, backend and frontend Dockerfiles, and Nginx configuration have been prepared. However, actual builds of the application images, full container runtime validation, and end-to-end deployment verification have not yet been completed. The production deployment commands in this document describe planned deployment steps and do not indicate that the system has been verified as production-ready.

## Main Components

| Layer | Technologies / Components | Primary Responsibilities |
|---|---|---|
| Web Frontend | React, TypeScript, Vite, Axios, Zustand | Chat interface, client-side state management, HTTP requests, SSE subscriptions |
| API | FastAPI, Uvicorn | Receive chat requests, provide SSE event streams and related APIs |
| Asynchronous Tasks | Kafka, Chat Worker, Outbox Publisher, Memory Worker | Decouple chat execution from memory processing, supporting consumer groups and task retries |
| State and Database | PostgreSQL, SQLAlchemy, Alembic | Conversations, messages, tasks, Outbox, and database migrations |
| Graph State | LangGraph, PostgreSQL Checkpoint | Manage graph execution state and persistent checkpoints |
| Real-Time Events | Redis Streams, SSE | Buffer runtime events and continuously send streaming updates to the browser |
| Long-Term Memory | Mem0, Milvus, Sentence Transformers | Memory extraction, vector storage, and relevance-based retrieval |
| Local Models | Qwen, Transformers | Local LLM inference |
| Code Execution | Sandbox API, Docker SDK | Execute Python code inside restricted containers |
| Deployment | Docker Compose, Nginx | Orchestrate infrastructure and application services, host the frontend, and proxy API/SSE requests |

## Architecture and Request Flow

### Main Chat Flow

1. The browser submits a message to `POST /api/chat`. The backend creates a run record and returns a `run_id`.
2. The frontend establishes an SSE connection through `GET /api/chat/{run_id}/events`.
3. Kafka delivers the chat run request to the Chat Worker.
4. The Chat Worker invokes LangGraph/ChatService to execute the task and writes runtime events to Redis Streams.
5. FastAPI reads events from Redis Streams and pushes them to the frontend through SSE.

### Memory Processing Flow

1. The Chat Worker and business logic write memory-processing tasks to PostgreSQL.
2. The Outbox Publisher reads pending Outbox events and publishes them to Kafka.
3. The Memory Worker consumes memory-related events such as `memory.extract.requested`.
4. The Memory Worker executes memory extraction, safety checks, and write operations, then uses Mem0 to write to and retrieve data from Milvus.

### Main Service Addresses

| Service | Local Development Address / Port | Description |
|---|---|---|
| Frontend (Vite) | `http://127.0.0.1:5173` | Local development web interface |
| Backend API | `http://127.0.0.1:8000` | FastAPI |
| Sandbox API | `http://127.0.0.1:8010` | Sandbox HTTP API |
| Local LLM Server | `http://127.0.0.1:8020` | Local model API |
| PostgreSQL | `localhost:5432` | Application database / Checkpoint |
| Redis | `localhost:6379` | Redis Streams, idempotency, and runtime events |
| Kafka | `localhost:9092` | Local development connection address |
| Milvus | `localhost:19530` | Vector database |
| MinIO Console | `http://localhost:9001` | Object storage console (if needed) |

## Project Structure

```text
agent-chat/
├── backend/
│   ├── app/
│   │   ├── agents/chat/       # LangGraph graphs, nodes, state, and context
│   │   ├── api/               # FastAPI routes
│   │   ├── infrastructure/    # PostgreSQL, Kafka, Redis, LangGraph Runtime
│   │   ├── llm/               # Local LLMs and model API services
│   │   ├── memory/            # Memory extraction, safety, retrieval, writing, and task processing
│   │   ├── models/            # SQLAlchemy models
│   │   ├── repositories/      # Data access layer
│   │   ├── sandbox/           # Sandbox clients, executors, and policies
│   │   ├── schemas/           # API data structures
│   │   ├── services/          # Chat, run management, and idempotency services
│   │   ├── workers/           # Chat, Memory, and Outbox Workers
│   │   └── main.py            # FastAPI entry point
│   ├── alembic/               # Database migrations
│   ├── scripts/               # Maintenance and diagnostic tools
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── alembic.ini
│   ├── requirements.txt       # Direct application dependencies
│   └── requirements-stage7-verified.txt  # Stage 7 environment snapshot for reference only
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── nginx.conf
│   └── package.json
├── infra/
│   └── redis/redis.conf       # Configuration actually used by the Redis container
├── scripts/
│   ├── dev.ps1                # Start 7 local development processes in one step
│   ├── stop-dev.ps1           # Stop process trees recorded by dev.ps1
│   ├── infra-up.ps1            # Start the infrastructure defined in the root Compose file
│   └── infra-down.ps1          # Stop the infrastructure defined in the root Compose file
├── compose.yaml               # The single Compose configuration entry point
├── .env                       # Actual local configuration; must not be shared or committed
├── .env.example               # Configuration template
├── .gitignore
└── README.md
```

## Windows Local Development

Local development continues to use Windows and the Conda environment `learnLLM`. It is not necessary to run all Python processes inside Docker. This approach makes it easier to inspect console output, use breakpoints for debugging, and restart individual services quickly.

### 1. Prepare the Environment

- Docker Desktop is running.
- The Conda environment `learnLLM` has been created and activated.
- Frontend dependencies have been installed.
- The root-level `.env` file exists, and the database username and password match the credentials specified in the database URLs.

```powershell
conda activate learnLLM
cd D:\Workspace\pycharm-work\agent-chat
```

### 2. Start the Infrastructure

```powershell
.\scripts\infra-up.ps1
```

The script uses the root-level `compose.yaml` to start PostgreSQL, Redis, Kafka, Milvus, etcd, and MinIO. Check the infrastructure status with:

```powershell
docker compose --env-file .\.env -f .\compose.yaml ps
```

### 3. Start All Development Processes in One Step

```powershell
.\scripts\dev.ps1
```

This script opens separate PowerShell windows and starts the following processes:

- Frontend
- Backend API
- Sandbox API
- Local LLM Server
- Chat Worker
- Memory Worker
- Outbox Publisher

Each window displays its own real-time logs. Opening a window does not guarantee that the service has started successfully; check the startup logs in every window.

To stop the process trees started by this script and recorded in `.dev-pids.txt`:

```powershell
.\scripts\stop-dev.ps1
```

Stopping the development processes does not stop the Docker infrastructure.

### 4. Start an Individual Service

You can start a single process in a separate PowerShell window to facilitate troubleshooting or debugging. First, ensure that the infrastructure is running and that the `learnLLM` environment is active.

```powershell
# Backend API
cd D:\Workspace\pycharm-work\agent-chat\backend
python -m uvicorn app.main:app --reload --port 8000 --access-log --log-level info
```

Start the other backend processes separately as follows:

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

Start the frontend separately:

```powershell
cd D:\Workspace\pycharm-work\agent-chat\frontend
npm run dev
```

The local Vite development server proxies `/api` requests to `http://127.0.0.1:8000`, including SSE endpoints. Open `http://127.0.0.1:5173` in your browser.

> When debugging Workers, note that multiple instances can run in the same Kafka consumer group, but doing so changes partition assignments. Avoid unintentionally starting multiple consumers to process the same task stream.

## Environment Variables

- `.env`: Actual local configuration. It contains information such as database passwords and must not be included in a public repository or shared with others.
- `.env.example`: A configuration template that contains no actual secrets. When copying the template, you must configure your own passwords, directories, and server addresses.
- The root-level `compose.yaml` overrides the internal access addresses for PostgreSQL, Kafka, Redis, Milvus, the Local LLM, and Sandbox services used by containers.

Important variables include:

| Variable | Purpose |
|---|---|
| `COMPOSE_PROJECT_NAME` | Compose project name |
| `AGENT_CHAT_DATA_DIR` | Root directory on the host for persistent data |
| `POSTGRES_*` | PostgreSQL image, port, database, username, and password |
| `DATABASE_URL` | Asynchronous SQLAlchemy database connection used by the application |
| `ALEMBIC_DATABASE_URL` | Database connection used by Alembic migrations |
| `LANGGRAPH_CHECKPOINT_DATABASE_URL` | LangGraph Checkpoint connection |
| `REDIS_HOST`, `REDIS_PORT` | Redis connection address |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka bootstrap address |
| `MEMORY_LLM_BASE_URL` | LLM address used by Mem0 |
| `MILVUS_URI` | Vector database address used by Mem0/Milvus |
| `SANDBOX_API_URL` | Sandbox API address |
| `SANDBOX_HTTP_TIMEOUT_SECONDS` | Sandbox HTTP request timeout in seconds |
| `MEMORY_SEARCH_TIMEOUT_SECONDS` | Memory retrieval timeout in seconds |
| `FRONTEND_PORT` | Host port mapping for the frontend during Compose deployment |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | MinIO credentials |
| `DOCKER_GID` | Numeric GID of the group owning the Docker Socket on Linux deployments; must be verified on the target machine |

On the local Windows environment, `localhost` is commonly used. Containers on the Docker network must use Compose service names, such as `postgres:5432`, `redis:6379`, `kafka:29092`, and `milvus:19530`. These addresses apply to different networking contexts and cannot be used interchangeably.

## Testing and Basic Checks

### Python Compilation and Dependency Checks

```powershell
cd D:\Workspace\pycharm-work\agent-chat\backend
python -m compileall -q app tests
python -m pip check
```

### Run Memory Retrieval Relevance Tests

When running the script from the `backend` directory, configure the Python module search path:

```powershell
cd D:\Workspace\pycharm-work\agent-chat\backend
$env:PYTHONPATH = (Get-Location).Path
python .\tests\integration\test_retrieval_relevance.py
```

This test has previously verified that greeting messages are skipped and that database preferences and language preferences can be retrieved. Relevant tests should be rerun after changes.

### Validate the Compose Configuration

```powershell
cd D:\Workspace\pycharm-work\agent-chat
docker compose --env-file .\.env -f .\compose.yaml config -q
```

Successful configuration validation produces no output. It only confirms that the Compose file syntax and variable interpolation can be parsed. It does not indicate that the application images have been built successfully or that the application services are running successfully.

## Future Linux / Docker Deployment Workflow

**The following steps describe the planned workflow for deploying to a Linux server. The application images and the complete container service chain have not yet undergone actual build and deployment validation. Do not interpret this workflow as confirmation that production deployment has been verified.**

### 1. Prepare the Linux Server

- Install a supported version of Docker Engine and the Docker Compose plugin.
- Place the project code in the server's deployment directory.
- Configure a persistent data directory, for example, `/srv/agent-chat/data`.
- Check the server ports, security group rules, and firewall policies.
- Generate strong passwords specifically for production. Do not use placeholders or local demonstration credentials from `.env.example`.

### 2. Prepare the Server `.env`

Create a deployment `.env` file based on `.env.example` and verify at least the following:

- `AGENT_CHAT_DATA_DIR` points to an absolute path on the Linux server.
- The PostgreSQL password exactly matches the password in all three database URLs.
- MinIO uses credentials dedicated to production.
- `DOCKER_GID` matches the actual group ID of `/var/run/docker.sock` on the server. You can check this on Linux with `stat -c '%g' /var/run/docker.sock`.
- Verify the CPU/GPU configuration for the model service, model cache, and available disk space.

### 3. Perform Static Validation and Build the Images

Run the following commands from the project root directory on the server:

```bash
docker compose --env-file .env -f compose.yaml config -q
docker compose --env-file .env -f compose.yaml build
```

The current `requirements.txt` lists direct dependencies but does not lock all transitive dependencies. A Linux `pip --dry-run` dependency resolution has previously succeeded, but several selected transitive dependency versions were newer than those in the Stage 7 snapshot. Before actual deployment, further pin and validate the dependency combination, and confirm the CPU/GPU installation method for PyTorch to avoid excessively large images or runtime incompatibilities.

### 4. Database Migrations

After a successful build and before starting the application, run the migration command according to the project's migration configuration:

```bash
docker compose --env-file .env -f compose.yaml run --rm backend alembic upgrade head
```

Before execution, confirm the backup strategy and migration scripts in the target environment. Production database changes should be preceded by a backup and performed according to the release process.

### 5. Start the Services and Inspect Logs

```bash
docker compose --env-file .env -f compose.yaml up -d
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs -f backend chat-worker memory-worker outbox-publisher local-llm-server sandbox frontend
```

By default, the frontend is mapped to a host port specified by `FRONTEND_PORT` (the example in the template is `8080`). Before going live, complete integration testing for the API, SSE, Kafka consumption, memory writes and retrieval, model service, and Sandbox. Configure HTTPS, domain names, access controls, backups, monitoring, and log retention.

### 6. Stop the Services

```bash
docker compose --env-file .env -f compose.yaml down
```

Because this command does not include `-v`, it does not actively delete Compose-managed named volumes. The project's bind-mounted data directories are also not automatically deleted when containers are stopped. Nevertheless, back up data before performing migrations or system cleanup.

## Risks and Outstanding Tasks Before Production Deployment

1. **Sandbox Docker Socket Permissions**: The current Compose draft mounts `/var/run/docker.sock` into the Sandbox service. A process that can control the Docker Socket typically has highly privileged access to the host. In a real production environment, prioritize an isolated execution host or a dedicated Docker Daemon, and restrict network access to the Sandbox API. Do not expose the Docker Socket to the Backend API or ordinary Workers.
2. **Model Execution Strategy**: The current model is loaded using `transformers`/PyTorch. Determine the CPU or GPU configuration based on the server hardware, and check image size, GPU memory/system memory requirements, startup time, and model caching.
3. **Dependency Locking**: After completing Linux dependency resolution and an actual build, generate a lock file suitable for the deployment platform. Do not directly use local file paths from a Windows Conda snapshot as Linux dependency installation sources.
4. **Readiness Probes and Startup Order**: Compose's `service_started` condition only indicates that the container process has started; it does not mean that the API or model is ready. Add health checks for application services and verify how Workers recover when Kafka, the database, Milvus, or the model service is not yet ready.
5. **Security Configuration**: Production environments should use strong passwords, restrict externally exposed ports, configure HTTPS, authentication and authorization, secret management, and regular data backups.
6. **CORS and Reverse Proxy**: The production frontend build uses the relative path `/api`; Nginx proxies API/SSE requests to `backend:8000`. Before going live, verify that backend CORS settings, proxy headers, and SSE buffering configuration match the actual domain and HTTPS topology.
7. **Incomplete Deployment Validation**: So far, only Compose syntax checks and the infrastructure configuration workflow have been validated. The newly added application Dockerfiles, Nginx configuration, and all application containers still require actual builds and integration tests.

## Current Maintenance Principles

- `backend/app/` contains the core business logic. Before moving files, check imports, entry-point commands, and tests.
- `backend/tests/` is for testing; `backend/scripts/` is for maintenance and diagnostics; the root-level `scripts/` directory manages the lifecycle of development processes and infrastructure.
- `requirements-stage7-verified.txt` is retained as a reference snapshot of the Stage 7 environment. Deployment dependencies are defined in `requirements.txt`; transitive dependencies will be locked later based on actual Linux validation results.
- `compose.yaml` is the single Compose entry point. Infrastructure, application services, and data directories are managed centrally through this file.

## 👤 Author

Created and maintained by **UNan**.

- GitHub: [@YU-UR](https://github.com/YU-UR)
- Repository: [agent-chat-developer](https://github.com/YU-UR/agent-chat-developer)

## 📜 License

This project is currently provided for personal and educational use only.

© 2026 UNan. All rights reserved.