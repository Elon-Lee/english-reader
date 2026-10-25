# 拾页 SAAS 前后端启动部署指南

更新时间：2025-01-21（Asia/Shanghai）

---

## 架构概览

拾页有两种运行模式：

### 1. 单用户模式（旧版）
- **用途**：本地开发、单机部署
- **后端端口**：8765（默认）
- **SAAS 启用**：false
- **数据库**：SQLite
- **启动命令**：`./start-reader.sh` 或 `python3 tools/reader_server.py`

### 2. SAAS 多租户模式（新版）⭐
- **用途**：生产环境、多用户 SaaS 服务
- **后端端口**：8790（默认，可配置）
- **SAAS 启用**：true
- **数据库**：PostgreSQL
- **缓存**：Redis
- **启动命令**：`./start-reader.sh --saas-local 8790`

**⚠️ 重要：首页产品化改造针对 SAAS 模式，必须启动 SAAS 版本后端才能验收所有功能！**

---

## 1. SAAS 后端启动（正确方式）

### 前置要求

1. **环境变量配置**（必须）

创建 `.env` 文件（位于项目根目录）：

```bash
# SAAS 数据库配置
SHIYUE_SAAS_DB_URL=postgresql://user:password@localhost:5432/shiyue_saas

# Redis 缓存（可选但推荐）
SHIYUE_REDIS_URL=redis://localhost:6379/0

# 会话密钥（生产环境必须设置）
SHIYUE_SECRET_KEY=your-random-secret-key-here

# SAAS 模式启用标志
SHIYUE_SAAS_ENABLED=1

# 管理员账号（首次启动时创建）
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
BOOTSTRAP_ADMIN_PASSWORD=your-secure-password
```

2. **数据库准备**

```bash
# 创建 PostgreSQL 数据库
createdb shiyue_saas

# 运行数据库迁移（如有）
# python3 tools/migrate_db.py
```

### 启动命令

```bash
cd /Users/x/Documents/english

# 方式 1：使用启动脚本（推荐）
./start-reader.sh --saas-local 8790

# 方式 2：后台运行
nohup ./start-reader.sh --saas-local 8790 > saas_backend.log 2>&1 &

# 方式 3：直接调用（仅调试用）
python3 tools/run_local_saas.py
```

**参数说明**：
- `--saas-local`：启动本地 SAAS 模式
- `8790`：后端监听端口（可选，默认 8790）

### 验证 SAAS 后端

```bash
# 1. 检查进程
ps aux | grep run_local_saas | grep -v grep

# 2. 检查端口
lsof -nP -iTCP:8790 -sTCP:LISTEN

# 3. 健康检查（最重要）
curl http://localhost:8790/api/health | python3 -m json.tool

# 预期响应：
# {
#   "status": "ok",
#   "runtimeMode": "full",
#   "saasEnabled": true,  ← 必须是 true
#   "redisEnabled": true,
#   "redisReady": true,
#   "books": 123,
#   "time": "2025-01-21T16:30:00Z"
# }

# 4. 测试公开统计接口
curl http://localhost:8790/api/public/stats
# 预期响应：
# {"totalSentences":12345,"totalHours":678,"retentionRate":85}
```

### 常见启动错误

**错误 1：`saasEnabled: false`**

```bash
# 原因：未使用 --saas-local 启动
# 解决：必须使用启动脚本的 SAAS 模式
./start-reader.sh --saas-local 8790
```

**错误 2：数据库连接失败**

```bash
# 检查 .env 文件
cat .env | grep SHIYUE_SAAS_DB_URL

# 测试数据库连接
psql "$SHIYUE_SAAS_DB_URL" -c "SELECT 1"
```

**错误 3：端口被占用**

```bash
# 查找占用进程
lsof -i :8790

# 杀死进程
kill -9 <PID>

# 或使用其他端口
./start-reader.sh --saas-local 8791
```

---

## 2. 前端开发服务器启动

### 前置要求

- Node.js 18+
- npm 或 pnpm

### 配置 API 代理

**重要**：前端需要代理到 SAAS 后端的 8790 端口！

编辑 `frontend/vite.config.js`：

```javascript
export default {
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://localhost:8790',  // ← 改为 SAAS 后端端口
        changeOrigin: true
      }
    }
  }
}
```

### 启动命令

```bash
cd /Users/x/Documents/english

# 方式 1：开发模式（热重载）
npm run dev:modern

# 方式 2：后台运行
nohup npm run dev:modern > frontend.log 2>&1 &
```

### 默认配置

- **监听端口**：5173
- **监听地址**：127.0.0.1（仅本地访问）
- **热重载**：已启用
- **API 代理**：`/api/*` → `http://localhost:8790/api/*`（SAAS 后端）

### 检查前端状态

```bash
# 查看进程
ps aux | grep vite | grep -v grep

# 查看监听端口
lsof -nP -iTCP:5173 -sTCP:LISTEN

# 浏览器访问
open http://localhost:5173/

# 测试 API 代理
curl http://localhost:5173/api/health
```

---

## 3. 完整启动流程（SAAS 模式）

### 开发环境一键启动

```bash
cd /Users/x/Documents/english

# Step 1: 确保 .env 文件存在且配置正确
cat .env | grep SHIYUE_SAAS_DB_URL

# Step 2: 启动 SAAS 后端（8790 端口）
nohup ./start-reader.sh --saas-local 8790 > saas_backend.log 2>&1 &
echo "SAAS 后端已启动，PID: $!"

# Step 3: 等待后端就绪
sleep 3
curl -s http://localhost:8790/api/health | python3 -m json.tool

# Step 4: 确认 saasEnabled 为 true
curl -s http://localhost:8790/api/health | grep '"saasEnabled": true' && echo "✓ SAAS 模式已启用" || echo "✗ SAAS 模式未启用"

# Step 5: 启动前端（5173 端口）
npm run dev:modern

# 前端启动后会输出：
# VITE v5.x.x  ready in xxx ms
# ➜  Local:   http://localhost:5173/
# ➜  Network: use --host to expose
```

### 验证完整服务

```bash
# 1. 检查 SAAS 后端健康
curl http://localhost:8790/api/health | python3 -m json.tool

# 2. 检查公开统计接口（首页需要）
curl http://localhost:8790/api/public/stats

# 3. 检查前端可访问
curl -I http://localhost:5173/

# 4. 检查前端 API 代理
curl http://localhost:5173/api/health

# 5. 浏览器验收
open http://localhost:5173/
```

---

## 4. 停止服务

```bash
# 停止 SAAS 后端
pkill -f run_local_saas

# 停止前端
pkill -f vite

# 或者使用专用脚本
./start-reader.sh --stop-saas-local
```

---

## 5. 常见问题排查

### 问题 1：前端无法连接后端

**症状**：浏览器控制台显示 `Failed to fetch /api/...`

**排查步骤**：
```bash
# 1. 确认 SAAS 后端运行在 8790
lsof -nP -iTCP:8790 -sTCP:LISTEN

# 2. 确认 Vite 代理配置指向 8790
cat frontend/vite.config.js | grep -A 3 "target:"

# 3. 测试后端直连
curl http://localhost:8790/api/health

# 4. 测试前端代理
curl http://localhost:5173/api/health

# 5. 查看后端日志
tail -50 saas_backend.log
```

### 问题 2：SAAS 模式未启用

**症状**：`/api/health` 返回 `"saasEnabled": false`

**原因**：使用了错误的启动命令

**解决方案**：
```bash
# ✗ 错误：直接运行 reader_server.py
python3 tools/reader_server.py  # saasEnabled = false

# ✗ 错误：使用默认启动脚本
./start-reader.sh  # saasEnabled = false

# ✓ 正确：使用 SAAS 启动参数
./start-reader.sh --saas-local 8790  # saasEnabled = true
```

### 问题 3：公开统计接口 404

**症状**：`/api/public/stats` 返回 404

**原因**：
1. SAAS 模式未启用（最常见）
2. 后端代码中路由未正确配置
3. 认证拦截器未排除该路由

**解决方案**：
```bash
# 1. 确认 SAAS 启用
curl http://localhost:8790/api/health | grep saasEnabled

# 2. 确认路由已添加（应该在 reader_server.py 第 259-261 行）
grep -n "api/public/stats" tools/reader_server.py

# 3. 确认认证拦截器已排除（应该在第 309 行）
grep -n 'route not in.*api/public/stats' tools/reader_server.py

# 4. 测试接口
curl http://localhost:8790/api/public/stats
```

### 问题 4：数据库连接失败

**症状**：后端启动失败，日志显示数据库错误

**解决方案**：
```bash
# 1. 检查 .env 配置
cat .env | grep SHIYUE_SAAS_DB_URL

# 2. 测试数据库连接
psql "postgresql://user:pass@host:5432/dbname" -c "SELECT 1"

# 3. 检查 PostgreSQL 服务
brew services list | grep postgresql
# 或
systemctl status postgresql

# 4. 创建数据库（如果不存在）
createdb shiyue_saas
```

### 问题 5：Redis 连接失败

**症状**：后端启动但 `redisReady: false`

**解决方案**：
```bash
# 1. 检查 Redis 服务
brew services list | grep redis
# 或
systemctl status redis

# 2. 启动 Redis
brew services start redis
# 或
sudo systemctl start redis

# 3. 测试连接
redis-cli ping  # 应返回 PONG

# 4. 如果不需要 Redis，可以在 .env 中删除 SHIYUE_REDIS_URL
```

---

## 6. 端口总结表

| 服务 | 端口 | 监听地址 | 启动命令 | 用途 |
|------|------|----------|----------|------|
| **SAAS 后端** | **8790** | 0.0.0.0 | `./start-reader.sh --saas-local 8790` | **生产/验收环境** |
| 前端开发服务器 | 5173 | 127.0.0.1 | `npm run dev:modern` | Vite 热重载 |
| 旧版单用户后端 | 8765 | 0.0.0.0 | `./start-reader.sh` | 本地开发 |
| PostgreSQL | 5432 | localhost | `brew services start postgresql` | 数据库 |
| Redis | 6379 | localhost | `brew services start redis` | 缓存 |
| Nginx（生产） | 80/443 | 0.0.0.0 | `sudo systemctl start nginx` | 反向代理 |

**⚠️ 重要提醒：首页验收必须使用 SAAS 后端（8790），否则信任数据区和统计接口无法正常工作！**

---

## 7. 快速验收检查清单

### 启动前检查

- [ ] `.env` 文件存在且包含 `SHIYUE_SAAS_DB_URL`
- [ ] PostgreSQL 服务运行中
- [ ] Redis 服务运行中（可选）
- [ ] 8790 端口未被占用
- [ ] 5173 端口未被占用

### 启动命令

```bash
# 1. 启动 SAAS 后端
./start-reader.sh --saas-local 8790 &

# 2. 验证 SAAS 模式
curl http://localhost:8790/api/health | grep '"saasEnabled": true'

# 3. 启动前端
npm run dev:modern

# 4. 打开浏览器
open http://localhost:5173/
```

### 验收检查

- [ ] Hero 区显示新标题和沉浸式背景
- [ ] 互动演示区可点击单词
- [ ] 痛点区显示表情符号
- [ ] 信任数据区显示统计（如有数据）
- [ ] 套餐区可切换简化/详细对比
- [ ] 主按钮使用陶土橙配色
- [ ] 移动端响应式正常

---

## 8. 相关文档

- **首页改造交接**：`HANDOFF.md`
- **启动脚本源码**：`../../start-reader.sh`
- **SAAS 后端入口**：`../../tools/run_local_saas.py`
- **前端配置**：`../../frontend/vite.config.js`
- **环境变量模板**：`../../.env.example`（如有）

