# Ace RAG

Ace RAG 是一个面向企业知识库问答的 Agentic RAG 项目。当前支持 TXT/Markdown 文档异步入库与 Knowledge 页面体验；后续将实现混合检索、流式对话与可追溯引用。

目前仓库提供 PostgreSQL、Redis、Milvus、etcd、MinIO、RabbitMQ 和 Attu 等本地开发中间件。

## 本地部署

前提：已安装并启动 Docker Desktop、OrbStack 或 Docker Engine。

```bash
cp .env.docker.example .env.docker
./scripts/docker.sh up
```

部署脚本会拉取镜像、启动服务并等待健康检查通过。

| 服务 | 本地地址 |
| --- | --- |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |
| Milvus | `127.0.0.1:19530` |
| Attu | `http://127.0.0.1:3000` |
| MinIO API | `127.0.0.1:9000` |
| MinIO Console | `http://127.0.0.1:9001` |
| RabbitMQ Console | `http://127.0.0.1:15672` |

查看状态或停止服务：

```bash
./scripts/docker.sh status
./scripts/docker.sh down
```

更多 Docker 操作见 [DOCKER.md](DOCKER.md)。

## 体验文档入库

先按上文启动中间件，并在根目录配置本地模型参数：

```bash
cp .env.example .env
uv sync
./scripts/run-backend.sh
```

该命令会同时启动 FastAPI 与摄取 Worker；按 `Ctrl+C` 会整体停止。再另开一个终端启动前端：

```bash
cd web
corepack pnpm install
corepack pnpm dev
```

打开 `http://localhost:5173`，选择或拖入一个 UTF-8 编码的 `.md` / `.txt` 文件。上传完成后会先返回任务，Worker 在后台完成分片、Embedding 与 Milvus 写入；页面会自动刷新任务状态。
