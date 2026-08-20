# Ace RAG

Ace RAG 是一个面向企业知识库问答的 Agentic RAG 项目。后续将实现文档入库、混合检索、流式对话与可追溯引用。

目前仓库已提供本地开发所需的基础中间件：PostgreSQL、Redis、Milvus、etcd 和 MinIO。

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
| MinIO Console | `http://127.0.0.1:9001` |

查看状态或停止服务：

```bash
./scripts/docker.sh status
./scripts/docker.sh down
```

更多 Docker 操作见 [DOCKER.md](DOCKER.md)。应用功能与使用方式将在实现后补充。
