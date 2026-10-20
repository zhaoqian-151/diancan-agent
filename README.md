# 智能点餐 Agent（smart_diancan）

## 首次从 GitHub 下载

仓库包含程序、14 道初始菜单和 AI 示意配图，不包含任何订单、会员、余额、访客数据或真实密钥。现有数据只留在原电脑。

1. 安装 Python 3.12、Node.js 20+、MySQL 8；在项目根目录执行 `python -m venv .venv`，再执行 `.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt` 与 `npm --prefix ui ci`。锁文件记录本次实际验证的依赖版本，原 `requirements.txt` 保留直接依赖声明。
2. 将 `.env.example` 复制为 `.env`，填写自己的 MySQL 连接参数及所需 AI、向量检索、地图服务凭据。已有图片和菜单浏览不需要生成图片的密钥；点餐助手及新图生成需要对应服务配置。
3. 先启动 MySQL，再执行 `.\.venv\Scripts\python.exe scripts\bootstrap_db.py --seed-menu`。建表脚本不会删除现有表；初始菜单只允许导入空菜单，拒绝覆盖现有菜单。不需要初始菜单时省略 `--seed-menu`。
4. 启动后端 `.\.venv\Scripts\python.exe run.py --host 127.0.0.1`，另一个终端执行 `npm --prefix ui run dev`，访问 `http://127.0.0.1:3000/`。

Windows 免安装 MySQL 用户可在准备好已有数据目录及英文路径入口后使用 `scripts/start_local.ps1` 统一启动；安装为系统服务或远程 MySQL 的用户先启动对应数据库，脚本会复用可连接的数据库。`database/schema.sql` 包含十张业务表；`database/menu_seed.sql` 只含菜单，不含销量或模拟交易。首次安装不依赖本仓库父目录中的历史文件。

这是受信任本机使用的工作空间；支付网关、会员身份校验和管理端登录尚未接入，HTTP 支付接口会明确拒绝模拟成功。上传代码不等于已完成公网部署。

## 2026-10-19 产品重构版

### 餐饮视觉与自动配图更新

顾客首页现使用美食大图与首屏点餐助手，14 道现有菜品均已单独生成本地 WebP 配图，标注「AI 示意」。菜品价格、食材、订单与库存仍来自原数据库。原有图片地址先备份到 `artifacts/design/menu-images-before-*.json`，再关联本地图片。

在「餐厅经营 → 菜品管理 → 添加菜品」填写菜名、价格、分类和食材，默认勾选「保存时自动生成缺失图片」。点击保存时先生成、再保存菜品；也可先点「AI 生成菜品图片」预览或重新生成，或手动填写实拍 HTTPS 地址。生成失败会显示错误并保留表单，不会假装成功。图片生成使用已配置百炼账户，实际计费以供应商账户为准。

动态配图使用 Qwen Image 3.0 异步接口，密钥仅在服务器端，可按需配置 `IMAGE_API_KEY`、`IMAGE_API_BASE`、`IMAGE_MODEL`、`IMAGE_TIMEOUT`。本环境默认复用已有百炼 `LLM_API_KEY`；默认模型 `qwen-image-3.0` 已查询账户模型列表并真实调用通过。HTTP 地址默认 `https://dashscope.aliyuncs.com/api/v1`，具体地域要与密钥一致。

接口：`POST /admin/menu/image-jobs` 创建任务，`GET /admin/menu/image-jobs/{job_id}` 查询状态。任务后台最多并行 2 个、最多 8 个待处理；任务状态暂存在进程内，重启后需重新生成。成功图片下载到 `ui/public/images/generated` 并通过 `/images` 提供，不依赖供应商临时链接。

素材和最终提示词：`artifacts/design/image-prompts.json`；设计与验收：`页面设计重构.md`。本段替代下方历史文档中「待上传实拍占位」的当前页面说明；商家仍可换成经核实的实拍。

新增检查：`scripts/test_image_jobs.py`（离线回归）、`scripts/test_food_design.cjs`（界面流程）、`scripts/verify_image_generation.py`（真实调用生图服务，会生成一张图片，不添加菜品或订单）。

当前代码已重构为「知味」单店点餐与经营工作空间。产品评价、详细范围及数据边界见 [产品评审与修改方案](产品评审与修改方案.md)，实际检查结果见 [验收报告](验收报告.md)。下方原始开发记录中的支付演示、共享 guest 用户与 8000 端口说明已被本节替代。

启动后访问：顾客点餐 `http://127.0.0.1:3000/`，经营总览 `http://127.0.0.1:3000/admin`。后端端口以项目 `.env` 的 `SERVER_PORT` 为准（本环境当前为 8000），前端代理自动读取该配置。若该端口被其他项目占用，修改配置后重新启动前后端。

建议使用统一启动入口，避免只启动前后端而漏掉数据库：

```powershell
# 在 smart_diancan 目录运行；复用已有服务，不清空或重新初始化数据
powershell -ExecutionPolicy Bypass -File scripts\start_local.ps1
```

脚本依次检查/启动本地 MySQL、后端、前端，并验证经前端代理的数据库健康状态；日志在 `logs/local-*.log`。重启电脑后需重新运行。配置为远程数据库时，本机脚本不会代为启动远程服务。

也可按以下顺序分开启动：

```powershell
# 在 smart_diancan 目录，数据库先按 .env 的 MYSQL_PORT 启动（本环境为 3307）
powershell -ExecutionPolicy Bypass -File scripts\start_mysql.ps1 -Port 3307
# 另一个终端运行后端
.\.venv\Scripts\python.exe run.py --host 127.0.0.1
# 第三个终端运行前端
npm --prefix ui run dev -- --host 127.0.0.1
```

如需其他后端端口，启动 Vite 前设置 `$env:DIANCAN_API_TARGET='http://127.0.0.1:你的端口'`。生产预览的静态部署需要为 `/api` 配置反向代理；`vite preview` 自身不是完整部署方案。

- 全部业务页读取 MySQL，不提供伪造销量、评分或模拟收入。数据中仍含历史初始化和测试记录，总览明确标注来源。
- 门店名称、营业时间、电话、配送范围来自配置；可选 `MERCHANT_ADDRESS` 用于填写经门店确认的地址。未配置项不编造。
- 菜品原有图片全部是生成接口地址；前端显示待上传实拍占位，可在菜品管理中填写真实图片 HTTPS 地址及编辑菜价、食材和过敏原。
- 微信/支付宝网关及会员身份验证未接入，HTTP 在线支付关闭。提交订单后保留待支付；不生成虚假支付成功。历史支付标记与本地会员余额不代表已核验资金流水。
- 顾客购物车和订单按浏览器 HttpOnly 访客 Cookie 隔离。旧共享 guest 订单仍保留在管理端，不迁移到任何新访客。清除 Cookie 或更换浏览器会建立新访客身份。
- 库存扣减失败回滚订单；补货不会自动上架商家手动停售的菜品，需在菜品管理确认上架。已支付订单取消须等待退款流程接入。
- 管理端仍是受信任本地工作空间，导航切换不提供管理权限认证。正式公网使用前必须补齐身份认证、权限、真实支付及退款、资金审计和部署安全。

检查命令：

```powershell
.\.venv\Scripts\python.exe scripts\test_product_integrity.py
.\.venv\Scripts\python.exe scripts\verify_release.py --external
node scripts\test_ui.cjs
npm --prefix ui run build
```

浏览器脚本优先使用项目中的 Playwright，也可使用 Codex 捆绑运行时；其他机器可将 `playwright` 安装为开发依赖，并通过 `DIANCAN_CHROMIUM` 指定 Chromium 路径。验收截图和机器可读结果保存在 `artifacts/review`。脚本只在测试匿名会话中操作购物车；数据库订单验证强制回滚，不保留测试订单。

---

## 原始开发记录

基于大模型的智能点餐助手：支持菜品推荐与咨询、餐厅信息查询、配送范围检查、多轮对话交互。

## 技术栈

| 层次 | 选型 |
| --- | --- |
| 大模型框架 | LangChain 1.4.5 |
| 对话模型 | `deepseek-v4.1-flash`（OpenAI 兼容网关，阿里云百炼 compatible-mode） |
| 向量化模型 | `text-embedding-v3`（1024 维） |
| 后端框架 | FastAPI 0.143.0 |
| 部署服务器 | Uvicorn 0.54.0 |
| 关系数据库 | MySQL 8.0.28（免安装版） |
| 向量数据库 | Pinecone（索引 `menu-item-index`，1024 维 / cosine） |
| 地图服务 | 高德地图 Web 服务 API |
| 前端 | Vue 3 + Element Plus + Vite 4 |

## 目录结构

```
smart_diancan/
├── .env                    # 全部密钥与可调参数
├── .venv/                  # Python 虚拟环境
├── requirements.txt        # 依赖清单
├── run.py                  # uvicorn 启动入口（已实现）
├── agent/                  # LangChain Agent 与工具定义（已实现）
│   ├── mcp.py              #   三个工具：常规咨询 / 菜品推荐 / 配送检查
│   └── assistant.py        #   用 create_agent 编排工具，对外暴露 chat_with_assistant
├── api/                    # FastAPI 应用与路由（已实现）
│   └── main.py             #   /chat /delivery /menu/list /health
├── service/                # 业务服务层（已实现）
│   └── diancan_service.py  #   smart_chat / delivery_check / get_menu + 会话保持
├── tools/                  # 底层能力封装（已实现）
│   ├── config.py           #   集中读取 .env
│   ├── llm_tool.py         #   大模型调用 + 文本向量化
│   ├── db_tool.py          #   MySQL：菜单 / 购物车 / 订单
│   ├── pinecone_tool.py    #   向量写入与语义检索
│   └── amap_tool.py        #   高德地图与配送范围判定
├── scripts/                # 环境搭建、数据准备与自检脚本
│   ├── init_mysql.ps1      #   一键初始化数据库
│   ├── start_mysql.ps1     #   启动数据库
│   ├── stop_mysql.ps1      #   停止数据库
│   ├── verify_env.py       #   依赖自检
│   ├── verify_mysql.py     #   数据库自检
│   ├── set_merchant.py     #   按地址生成商户经纬度
│   ├── check_delivery.py   #   配送范围连通性抽查
│   ├── seed_pinecone.py    #   把菜单写入向量库
│   ├── cleanup_index.py    #   清理向量库里的历史遗留数据
│   ├── verify_llm_tool.py  #   tools 层分模块自检
│   ├── verify_tools.py     #
│   └── verify_pinecone_tool.py
└── ui/                     # Vue 3 前端
```

工作区根目录（`智能点餐agent/`）下还有几个辅助目录：

```
_downloads/                 # MySQL 免安装 ZIP（可删）
_runtime/                   # MySQL 程序与数据目录（解压后约 700MB）
数据库脚本/menu.sql          # 菜单库建表与初始数据
依赖包/requirements.txt      # 带注释的依赖清单
```

## 环境准备

### 1. Python 依赖

```powershell
cd smart_diancan
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.\.venv\Scripts\python.exe scripts\verify_env.py
```

### 2. MySQL

```powershell
# 一次性初始化（解压、建英文路径入口、初始化、建库、导入 menu.sql）
powershell -ExecutionPolicy Bypass -File scripts\init_mysql.ps1

# 日常启动（在单独窗口里常驻）
powershell -ExecutionPolicy Bypass -File scripts\start_mysql.ps1

# 停止
powershell -ExecutionPolicy Bypass -File scripts\stop_mysql.ps1
```

### 3. 前端

```powershell
cd ui
npm install
npm run dev      # 开发服务器 http://localhost:3000，/api 代理到 127.0.0.1:8000
npm run build    # 生产构建，产物在 ui/dist
```

## 环境相关的坑（重要）

搭建过程中踩到的、必须知道的问题，按重要性排列：

### 1. MySQL 不支持中文路径

项目路径 `D:\BaiduNetdiskDownload\智能点餐agent\...` 含中文，MySQL 8.0.28
会把路径在中文处截断（`basedir` 变成 `D:\BaiduNetdiskDownload\`、`datadir`
变成 `D:\data\`）并启动失败。

**解决**：在 `D:\smart-menu-rt` 建立目录入口指向 `_runtime`，所有 MySQL
参数都走这个纯英文路径。脚本会自动创建；入口丢失时重跑 `init_mysql.ps1`。

`runtime-link` 路径可通过脚本参数 `-RuntimeLink` 修改，两边要保持一致。

### 2. InnoDB 需要可写的临时目录

默认会用系统 `%TEMP%`，本环境下该目录不可写，报
`Unable to create temporary file ... errno: 13`。
**解决**：启动时显式传 `--tmpdir=D:\smart-menu-rt\tmp`（脚本已内置）。

### 3. Windows PowerShell 5.1 读取脚本需要 BOM

含中文的 `.ps1` 若存成无 BOM 的 UTF-8，PS 5.1 会按 GBK 解析，中文变乱码并
报出莫名其妙的语法错误。**本项目 `scripts/` 下的脚本都已带 UTF-8 BOM**；
用编辑器改动后请保持 BOM。

### 4. `$ErrorActionPreference='Stop'` 会误杀原生命令

`mysqld` / `mysql` 把日志写到 stderr，在 `Stop` 模式下会被当成终止性错误
中断脚本。`init_mysql.ps1` 里用 `Invoke-Native` 封装，临时放宽该首选项，
改用 `$LASTEXITCODE` 判断成败。

### 5. Pinecone 索引里有历史遗留向量

索引 `menu-item-index` 里除了本项目写入的 `dish-*`，还存着 10 条更早的实现写下的
向量：ID 是纯数字 `1`~`10`，元数据形如 `{'dish_id': '菜品ID:6'}`、没有 `dish_name`。
它们对应的是另一套 10 道菜的菜单（宫保鸡丁 ¥38、鱼香肉丝、回锅肉、清蒸鲈鱼、米饭…），
和 `menu.sql` 里的 5 道菜不是同一份数据。

`search_menu_items` 已经把这类条目过滤掉了（多取候选、丢弃元数据不完整的），
所以不影响功能。如果想彻底清理：

```powershell
.\.venv\Scripts\python.exe scripts\cleanup_index.py           # 只预览
.\.venv\Scripts\python.exe scripts\cleanup_index.py --apply    # 真正删除
```

### 6. 沙箱环境下的两处限制（仅影响 DSH 会话内）

- **pip 装包**：`tempfile.mkdtemp` 创建的临时目录在本环境不可写（Python 在
  Windows 上把 `mode=0o700` 转成了受限权限）。已在 `.venv\Lib\site-packages\
  sitecustomize.py` 里把 `0o700` 放宽为 `0o777` 修正；删除该文件即恢复默认。
- **前端构建**：esbuild 需要启动子进程并通过管道读取输出，会被沙箱拒绝
  （`spawn EPERM`）。在 DSH 会话内构建前端需要授予完全权限，并建议把
  `TEMP` 指向项目内目录（否则 esbuild 删不掉自己的临时目录）。
  在普通命令行窗口里运行不受影响。

## tools 层能力清单

这一层是后面 Agent 的全部地基，每个模块都能独立调用与自检。

### `db_tool.py` —— MySQL

| 函数 | 作用 |
| --- | --- |
| `check_connection()` | 连通性自检，返回版本与菜品数 |
| `get_menu_items_list()` | 菜品列表，字段直接给前端「菜品列表」用 |
| `get_menu_items(...)` | 按分类/价格区间/辣度上限/素食/关键词筛选 |
| `get_dish_by_id` / `get_dishes_by_ids` | 按 ID 取菜品 |
| `get_categories()` | 全部分类 |
| `get_menu_summary_text()` | 拼成一段文本，直接塞进大模型提示词 |
| `add_to_cart` / `get_cart` / `remove_from_cart` / `clear_cart` / `cart_total` | 购物车读写 |
| `create_order(...)` | 下单，写 `orders` + `order_items` 并清空购物车 |
| `get_orders(user_id)` | 历史订单 |
| `get_or_create_user` / `get_default_user_id` | 用户 |

### `pinecone_tool.py` —— 向量库

| 函数 | 作用 |
| --- | --- |
| `check_connection()` | 索引状态与维度校验 |
| `build_dish_document(dish)` | 把一道菜拼成待向量化的文本 |
| `seed_menu_items(...)` | 从 MySQL 取菜单写入向量库（幂等，可重复执行） |
| `search_menu_items(query, top_k, ...)` | 语义检索，支持分类/价格/辣度/素食过滤 |
| `get_index_stats()` / `delete_all()` | 统计与清空 |

菜品本体数据以 MySQL 为准，向量库只存向量和少量用于过滤的元数据，
检索命中后回 MySQL 取完整信息，避免两边不一致。

### `amap_tool.py` —— 高德地图

| 函数 | 作用 |
| --- | --- |
| `geocode(address)` / `regeocode(lng, lat)` | 地址与经纬度互转 |
| `get_route(destination, mode)` | 路径距离与耗时（1 步行 / 2 骑行 / 3 驾车） |
| `get_merchant_info()` | 本店信息，供「餐厅信息查询」使用 |
| `check_delivery_range(address, travel_mode)` | **配送范围判定**，返回结构直接给前端 |
| `check_connection()` | 连通性自检 |

### `llm_tool.py` —— 大模型与向量化

| 函数 | 作用 |
| --- | --- |
| `call_llm(prompt, system)` | 调用大模型返回文本 |
| `call_llm_raw(...)` | 返回原始消息对象，可看思维链与 token 用量 |
| `embed_texts` / `embed_query` | 文本向量化 |

## Agent 层：工具编排

用 LangChain 1.x 的 `create_agent` 构建工具调用循环。模型是
`deepseek-v4.1-flash`，temperature 0.3（工具选择要稳定）。

### 三个工具（`agent/mcp.py`）

| 工具 | 职责 | 触发场景 |
| --- | --- | --- |
| `restaurant_qa` | 常规咨询 | 店名、地址、电话、营业时间、配送范围、寒暄、忌口建议 |
| `menu_consult` | 菜品查询与推荐 | 让推荐菜、口味偏好、预算、吃素、过敏、问某道菜的价格/食材/做法 |
| `delivery_query` | 配送范围检查 | 顾客给出收货地址并问能不能送到 |

三个工具都返回**可直接展示的中文答复**，同时把结构化结果（推荐菜品 ID、距离等）
写进一次对话的轨迹。轨迹用 `contextvars` 保存，每次对话互不干扰，可安全并发。

### 两个实现细节

**1. Agent 只做路由，不改写内容。** 系统提示里明确要求它把工具返回的答复原样
输出。工具已经写好了带真实数据的答复，让模型二次改写只会引入幻觉。

**2. 数值条件要解析成过滤器。** 纯向量检索理解不了「不超过 20 块」这种约束，
所以 `_parse_preferences` 会先把它解析成 `max_price` / `vegetarian_only` /
`max_spice_level` 交给检索当过滤条件（条件筛空了会自动放宽重试）。

**3. 高亮 ID 靠反查而不是取前几名。** 模型可能只挑了候选里的两道菜，直接取
候选列表前三个会导致前端高亮到用户根本没看到的菜。`_mentioned_menu_ids`
从答复文本里反查真正提到的菜名。

### 对外接口

```python
from agent.assistant import chat_with_assistant

result = chat_with_assistant('我想吃点辣的', history=[...])
# {
#   'response':       '...',          # 展示文本
#   'recommendation': '...' | None,   # 推荐类回复（前端优先看这个）
#   'menu_ids':       [2, 1, 4],      # 要高亮的菜品 ID
#   'type':           'recommend' | 'delivery' | 'general' | 'empty' | 'error',
#   'delivery':       {...} | None,   # 配送结构化结果
#   'tool_calls':     ['menu_consult'],
#   'elapsed_ms':     14342,
# }
```

自检：`.\.venv\Scripts\python.exe scripts\verify_agent.py`

## HTTP 接口

启动：

```powershell
.\.venv\Scripts\python.exe run.py                 # 默认 0.0.0.0:8000
.\.venv\Scripts\python.exe run.py --port 8080     # 换端口
.\.venv\Scripts\python.exe run.py --reload        # 开发时自动重启
```

接口文档在 <http://127.0.0.1:8000/docs>。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/chat` | 智能对话，自动选择三个工具 |
| `POST` | `/delivery` | 配送范围检查 |
| `GET` | `/menu/list` | 菜品列表 |
| `GET` | `/health` | 健康检查，`?deep=true` 额外探测外部依赖 |
| `DELETE` | `/session/{session_id}` | 清空某个会话的历史 |

> **路由不带 `/api` 前缀。** 前端 `vite.config.js` 的代理里带 `rewrite`，
> 会把 `/api` 去掉再转发，所以后端收到的是 `/chat` 而不是 `/api/chat`。

### 多轮对话

`POST /chat` 可以不带 `session_id`，后端会自动新建并在响应里返回。
后续请求带上同一个 `session_id` 即可延续上下文（进程内保存最近 6 轮，
30 分钟过期，重启服务即清空）：

```jsonc
// 请求
{ "query": "我想吃点辣的", "session_id": "a2f5831b..." }
// 响应
{
  "response": "...",
  "recommendation": "...",      // 推荐类回复，前端优先看这个
  "menu_ids": [2, 1, 4],        // 要高亮的菜品 ID
  "type": "recommend",
  "tool_calls": ["menu_consult"],
  "session_id": "a2f5831b...",
  "history_turns": 1,
  "elapsed_ms": 14123
}
```

### 关于同步接口

接口全部用同步 `def` 定义。Agent 内部是阻塞调用，交给 FastAPI 的线程池执行，
既不堵事件循环，也让 `mcp.py` 里的 `contextvars` 轨迹在单线程内正确工作。

自检：`.\.venv\Scripts\python.exe scripts\test_api.py`

## 前后端联调

两个窗口分别启动：

```powershell
# 窗口 1：后端
cd smart_diancan
.\.venv\Scripts\python.exe run.py

# 窗口 2：前端
cd smart_diancan\ui
npm run dev
```

浏览器打开 <http://localhost:3000>。

### 联调时踩到的两个坑

**1. 后端路由不能带 `/api` 前缀。** `vite.config.js` 的代理里带 `rewrite`，
会把 `/api` 去掉再转发，后端收到的是 `/chat`。写成 `/api/chat` 会全线 404。

**2. Vite 只监听 `localhost`（IPv6 `::1`）。** 用 `127.0.0.1:3000` 访问会被
拒绝连接，必须用 `localhost:3000`。另外 Vite 的 SPA 回退只在请求头带
`Accept: text/html` 时才把 `/` 重写成 `index.html`——浏览器天然满足，
但用脚本（urllib/curl）裸测 `GET /` 会得到 404，别误判成故障。

自检：`.\.venv\Scripts\python.exe scripts\test_frontend_e2e.py`
（全部请求走 3000 端口经代理转发，模拟浏览器真实路径）

## 性能

单次对话的耗时构成（实测）：

| 用例 | 总耗时 | 模型调用 | 模型耗时 | 检索等其他 |
| --- | --- | --- | --- | --- |
| 菜品推荐 | 8～20 秒 | 3 次 | 7～15 秒 | 0.6～0.8 秒 |
| 常规咨询 | 4.7 秒 | 3 次 | 4.1 秒 | 0.6 秒 |
| 配送检查 | 4.3 秒 | 2 次 | 3.0 秒 | 1.1 秒 |

**瓶颈是大模型本身。** `deepseek-v4.1-flash` 是推理模型，每次调用都要先输出
思维链；而一次对话要调 2～3 次（选工具 → 工具内生成答复 → Agent 汇总），
所以 10 秒左右是常态。前端已有「AI助手正在思考中…」的加载态，不会让用户
以为卡死。

**已优化掉的一处浪费：Pinecone 索引对象原来没有缓存。** `get_index()` 每次都
重新 `list_indexes()` 再构造 `Index`，两次网络往返；而 Pinecone 7.x 的 `Index`
对象持有 gRPC 通道，重建等于重连。实测单次检索因此要 **3.3 秒**。加上缓存后
降到 **0.45～0.6 秒**，非模型开销从 4～5.4 秒压到 0.6～0.8 秒。

还可以继续压的两点（暂未做）：

- Agent 的「汇总」那次调用是重复劳动——工具返回的已经是成品答复，
  但 `create_agent` 在工具执行后必定再调一次模型来生成最终消息。
- `restaurant_qa` 这种纯咨询也走 3 次调用，其中两次都是在做同一件事。

## 当前进度

- [x] 环境搭建：Python 虚拟环境、依赖、MySQL、数据导入、前端构建
- [x] 外部服务连通性验证：大模型、向量化、Pinecone、高德地图
- [x] `tools/` 四类底层能力封装（`db_tool`、`pinecone_tool`、`amap_tool`、`llm_tool`）
- [x] 菜单写入 Pinecone 向量库
- [x] LangChain Agent 与三个工具的定义和编排
- [x] FastAPI 接口、业务服务层与 uvicorn 启动脚本
- [x] 前端联调：经 vite 代理端到端跑通

## 配置说明

全部配置集中在 `.env`，关键项：

| 变量 | 说明 |
| --- | --- |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI 兼容网关地址、密钥、模型名 |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION` | 向量化模型与维度，必须与 Pinecone 索引一致 |
| `PINECONE_API_KEY` / `PINECONE_INDEX_NAME` | 向量库密钥与索引名 |
| `MYSQL_*` | 数据库连接参数 |
| `AMAP_API_KEY` | 高德地图 Web 服务 key |
| `MERCHANT_LONGITUDE` / `MERCHANT_LATITUDE` | 商户位置（配送起点） |
| `DELIVERY_RADIUS` | 配送范围（米） |
| `DEFAULT_PATH_MODE` | 路径规划模式：1 步行 / 2 骑行 / 3 驾车 |

**注意**：`deepseek-v4.1-flash` 是推理模型，响应体里推理过程在
`reasoning_content` 字段，且推理 token 计入 `completion_tokens`，
`max_tokens` 不能设得过小，否则 `content` 会是空的。
模型名必须带点号，`deepseek-v41-flash` 会报 404。
