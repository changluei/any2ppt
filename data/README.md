# Any2PPT 知识库交接说明

GitHub 仓库只同步程序代码，不同步知识库本体。当前语文、数学、英语官方库和个人库保存在 Docker 数据卷中，体积达到数 GB，不能直接提交到 GitHub。

正确的交接方式是：

1. 代码通过 GitHub 同步。
2. 在原电脑导出一个 `any2ppt-knowledge-*.tar.gz` 知识库迁移包。
3. 通过移动硬盘、局域网或网盘把迁移包和 `.sha256` 校验文件交给同学。
4. 同学克隆代码后，将迁移包导入自己的 Docker 数据卷。

迁移包包含：

- 三个官方知识库的完整 Chroma 向量索引；
- 个人知识库的向量索引；
- 四个知识库的状态与片段统计；
- 个人知识库中上传的原始文件和数据库元数据。

迁移包不包含 Slidev 模板缓存、PPT 导出文件和原始的 14 GB 数据集。模板会在使用时重新缓存；官方知识库拿到向量索引后不需要重新处理原始数据。

## 一、在原电脑打包

先确认项目正在正常运行：

```bash
cd /Users/changluei/cd/nku/暑期实训/any2ppt
docker compose --env-file .env -f deploy/docker-compose.yml ps
```

为了得到一致的 Chroma 快照，打包时暂时停止后端和渲染器，但保留 MySQL：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml stop backend renderer
docker compose --env-file .env -f deploy/docker-compose.yml run --rm --no-deps backend \
  python scripts/export_knowledge_bundle.py
docker compose --env-file .env -f deploy/docker-compose.yml up -d
```

脚本会在 `data/transfer/` 生成两个文件：

```text
any2ppt-knowledge-20260727-220000.tar.gz
any2ppt-knowledge-20260727-220000.tar.gz.sha256
```

查看大小并校验：

```bash
ls -lh data/transfer/
cd data/transfer
shasum -a 256 -c any2ppt-knowledge-*.tar.gz.sha256
cd ../..
```

请将压缩包和同名 `.sha256` 文件一起交给同学。`data/transfer/` 中的迁移包已被 Git 忽略，不会误推到 GitHub。

如果需要指定输出文件名：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml stop backend renderer
docker compose --env-file .env -f deploy/docker-compose.yml run --rm --no-deps backend \
  python scripts/export_knowledge_bundle.py /app/transfer/classmate-knowledge.tar.gz
docker compose --env-file .env -f deploy/docker-compose.yml up -d
```

不要执行 `docker compose down -v`，它会删除本机 MySQL 和 Chroma 数据卷。

## 二、同学拿到后导入

同学先克隆 GitHub 代码并准备环境：

```bash
git clone git@github.com:changluei/any2ppt.git
cd any2ppt
cp .env.example .env
```

根据自己的电脑修改 `.env` 中的 MySQL 密码和端口。然后把收到的两个文件放到：

```text
any2ppt/data/transfer/
```

先校验传输是否完整：

```bash
cd data/transfer
shasum -a 256 -c any2ppt-knowledge-*.tar.gz.sha256
cd ../..
```

构建后端、启动 MySQL 并创建数据库表：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml build backend
docker compose --env-file .env -f deploy/docker-compose.yml up -d mysql
docker compose --env-file .env -f deploy/docker-compose.yml run --rm --no-deps backend \
  alembic upgrade head
```

确保没有后端或渲染器正在访问数据卷，然后导入。把下面的文件名替换成实际文件名：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml stop backend renderer
docker compose --env-file .env -f deploy/docker-compose.yml run --rm --no-deps backend \
  python scripts/import_knowledge_bundle.py \
  /app/transfer/any2ppt-knowledge-20260727-220000.tar.gz \
  --replace
```

`--replace` 表示用迁移包替换接收方现有的四个知识库。如果接收方已经上传过自己的个人资料，应先导出备份，否则这些资料会被覆盖。

导入完成后启动系统：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
docker compose --env-file .env -f deploy/docker-compose.yml ps
```

打开 <http://localhost:5173>，进入“知识库”页面。正常情况下应看到：

- 官方语文知识库：122,887 个片段；
- 官方数学知识库：162,153 个片段；
- 官方英语知识库：12,125 个片段；
- 个人知识库：显示打包时已有的资料和片段数。

也可以通过接口检查：

```bash
curl http://localhost:8000/api/knowledge-bases
```

## 三、常见问题

### GitHub 为什么看不到知识库压缩包？

这是正常的。GitHub 单文件大小有限制，数 GB 的迁移包也不适合放进 Git 历史。仓库只保存导入导出脚本和本说明。

### 同学还需要复制 `data/datasets/` 的 14 GB 原始资料吗？

不需要。迁移包已经包含构建完成的向量索引。只有想从原始语料重新构建官方库时，才需要复制原始数据集并执行官方库导入脚本。

### 导入时提示 SHA-256 校验失败怎么办？

压缩包传输不完整或文件被修改。不要继续导入，重新复制 `.tar.gz` 和 `.sha256` 文件。

### 导入后页面显示知识库不可用怎么办？

依次检查：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml ps
docker compose --env-file .env -f deploy/docker-compose.yml logs --tail 100 backend
curl http://localhost:8000/health
curl http://localhost:8000/api/knowledge-bases
```

确认导入时使用的代码版本与 GitHub `main` 分支一致，并且没有删除 Docker 数据卷。
