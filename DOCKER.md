# Ace RAG 本地中间件一键部署

本项目第一版只部署技术方案中需要的中间件：

- PostgreSQL：LangGraph `AsyncPostgresSaver` Checkpoint 持久化
- Redis：RAG Retrieval Cache
- Milvus：Chunk、Dense Vector、BM25 Sparse Vector、Hybrid Retrieval
- etcd：Milvus 元数据依赖
- MinIO：Milvus 对象存储依赖

不部署 RabbitMQ、Celery、Elasticsearch，也不使用 Redis 保存会话 Memory。

## 一键启动

确保本机已经启动 Docker Desktop / OrbStack / Docker Engine，然后在项目根目录执行：

```bash
./scripts/docker.sh
```

第一次执行会自动：

1. 从 `.env.docker.example` 生成 `.env.docker`
2. 拉取镜像
3. 启动 5 个容器
4. 等待全部健康检查通过
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
| MinIO Console | `127.0.0.1:9001` | 仅本地调试 |

etcd 不暴露宿主机端口；Milvus 的 9091 管理端口也不暴露到宿主机。

## FastAPI 本地连接

默认配置下：

```env
POSTGRES_URI=postgresql://ace_rag:ace_rag_dev@127.0.0.1:5432/ace_rag
REDIS_URL=redis://127.0.0.1:6379/0
MILVUS_URI=http://127.0.0.1:19530
```

后续如果 FastAPI 本身也放进同一个 Compose 网络，则把宿主机地址改成服务名：

```env
POSTGRES_URI=postgresql://ace_rag:ace_rag_dev@postgres:5432/ace_rag
REDIS_URL=redis://redis:6379/0
MILVUS_URI=http://milvus:19530
```

## 数据持久化

持久化：

- PostgreSQL
- Milvus
- etcd
- MinIO

Redis 仍只做 Retrieval Cache，不保存会话 Memory。为保留缓存，Redis 启用 AOF 并挂载 Docker named volume；`clean` 会一并删除该缓存数据。

## LangGraph Checkpointer

Docker 只负责创建 PostgreSQL 数据库。`AsyncPostgresSaver` 所需 Checkpoint 表仍应由应用启动阶段调用官方 `setup()` / migration 初始化，不在 Docker 里手写一套业务表，以免和 LangGraph 版本耦合。
