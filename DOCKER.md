# Ace RAG 本地中间件一键部署

本项目第一版只部署技术方案中需要的中间件：

- PostgreSQL：LangGraph `AsyncPostgresSaver` Checkpoint，以及文档摄取任务与 Outbox
- Redis：RAG Retrieval Cache
- Milvus：Chunk、Dense Vector、BM25 Sparse Vector、Hybrid Retrieval
- Attu：Milvus 数据查看界面（仅本地开发）
- etcd：Milvus 元数据依赖
- MinIO：Milvus 依赖与上传原文件存储
- RabbitMQ：文档异步摄取任务队列

不部署 Celery、Elasticsearch，也不使用 Redis 保存会话 Memory。

## 一键启动

确保本机已经启动 Docker Desktop / OrbStack / Docker Engine，然后在项目根目录执行：

```bash
./scripts/docker.sh
```

第一次执行会自动：

1. 从 `.env.docker.example` 生成 `.env.docker`
2. 拉取镜像
3. 启动 7 个容器
4. 等待核心中间件健康检查通过
5. 输出 FastAPI 可直接使用的连接地址

也可以显式执行：

```bash
./scripts/docker.sh up
```

## 常用命令

```bash
./scripts/docker.sh status
./scripts/docker.sh logs
./scripts/docker.sh logs milvus
./scripts/docker.sh restart
./scripts/docker.sh down
```

彻底清空本地数据库和向量数据：

```bash
./scripts/docker.sh clean
```

`clean` 会要求输入 `YES` 二次确认。

## 默认端口

| 服务 | 本机地址 | 用途 |
|---|---|---|
| PostgreSQL | `127.0.0.1:5432` | LangGraph Checkpoint |
| Redis | `127.0.0.1:6379` | Retrieval Cache |
| Milvus | `127.0.0.1:19530` | Vector / BM25 Retrieval |
| Attu | `http://127.0.0.1:3000` | 查看 Milvus Collection 与数据 |
| MinIO API | `127.0.0.1:9000` | 上传原文件存储 |
| MinIO Console | `http://127.0.0.1:9001` | 仅本地调试 |
| RabbitMQ | `127.0.0.1:5672` | 文档摄取任务队列 |
| RabbitMQ Console | `http://127.0.0.1:15672` | 仅本地调试 |

etcd 不暴露宿主机端口；Milvus 的 9091 管理端口也不暴露到宿主机。

## FastAPI 本地连接

默认配置下：

```env
POSTGRES_URI=postgresql://ace_rag:ace_rag_dev@127.0.0.1:5432/ace_rag
REDIS_URL=redis://127.0.0.1:6379/0
MILVUS_URI=http://127.0.0.1:19530
MINIO_ENDPOINT=127.0.0.1:9000
RABBITMQ_URL=amqp://ace_rag:ace_rag_dev@127.0.0.1:5672/
```

后续如果 FastAPI 本身也放进同一个 Compose 网络，则把宿主机地址改成服务名：

```env
POSTGRES_URI=postgresql://ace_rag:ace_rag_dev@postgres:5432/ace_rag
REDIS_URL=redis://redis:6379/0
MILVUS_URI=http://milvus:19530
MINIO_ENDPOINT=minio:9000
RABBITMQ_URL=amqp://ace_rag:ace_rag_dev@rabbitmq:5672/
```

## 数据持久化

持久化：

- PostgreSQL
- Milvus
- etcd
- MinIO
- RabbitMQ

Redis 仍只做 Retrieval Cache，不保存会话 Memory。为保留缓存，Redis 启用 AOF 并挂载 Docker named volume；`clean` 会一并删除该缓存数据。

## LangGraph Checkpointer

Docker 只负责创建 PostgreSQL 数据库。应用启动时会运行本项目的摄取 Job/Outbox Migration；`AsyncPostgresSaver` 所需 Checkpoint 表仍应由会话工作流阶段调用官方 `setup()` 初始化，不在 Docker 里手写一套 LangGraph Checkpoint 表，以免和 LangGraph 版本耦合。
