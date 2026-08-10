# Job Agent OS 前端分期实施计划

## 技术栈总览

| 层面 | 选择 |
|------|------|
| 框架 | Next.js 14 (App Router) + TypeScript |
| UI | shadcn/ui + Tailwind CSS |
| 状态 | Zustand |
| 请求 | TanStack Query |
| 动画 | Framer Motion |
| 表单 | React Hook Form + Zod |

---

## 第一期 P0：核心对话体验（MVP）

目标：跑通「用户输入意图 → Agent 执行 → 实时进度 → 审批交互 → 完成」的核心闭环。

### Step 1：项目初始化

- 使用 `create-next-app` 初始化 Next.js 14 项目（TypeScript, App Router, Tailwind）
- 安装依赖：`@tanstack/react-query`, `zustand`, `framer-motion`, `lucide-react`, `zod`, `react-hook-form`
- 初始化 shadcn/ui（`npx shadcn-ui@latest init`），添加基础组件：Button, Input, Card, Badge, Dialog, Toast, Skeleton, Avatar, ScrollArea
- 配置 `next.config.ts` 中的 API 代理（rewrites 到 `http://localhost:8000`）
- 配置 Tailwind 主题色（深蓝主色调）
- 建立目录结构骨架：`app/`, `components/`, `lib/`, `stores/`, `types/`

### Step 2：类型定义 + API 客户端

- `src/types/api.ts`：统一响应类型 `ApiResponse<T> = { code, message, data, meta }`
- `src/types/session.ts`：SessionCreate, SessionResponse, SessionProgress, SessionMessage
- `src/types/approval.ts`：ApprovalResponse, ApprovalRespondRequest
- `src/lib/api/client.ts`：fetch 封装，统一拦截 code !== 0 抛错、401 自动 refresh、Toast 错误提示
- `src/lib/api/auth.ts`：register / login / refresh / logout
- `src/lib/api/sessions.ts`：createSession / getSession / sendMessage / getTimeline
- `src/lib/api/approvals.ts`：listApprovals / respondToApproval

### Step 3：认证模块

- `src/stores/auth-store.ts`：Zustand store 管理 token + user 状态，persist 到 localStorage
- `src/lib/hooks/useAuth.ts`：封装登录/登出/刷新逻辑
- `src/app/(auth)/login/page.tsx`：登录/注册表单页（React Hook Form + Zod 校验）
  - 登录表单：email + password
  - 注册表单：username + email + password + phone(可选)
  - 登录成功后跳转 `/chat`
- `src/middleware.ts`：Next.js 中间件，未认证时重定向到 `/login`

### Step 4：主布局框架

- `src/app/(main)/layout.tsx`：认证后布局（顶部导航 + 内容区）
- `src/components/layout/Sidebar.tsx`：左侧导航栏（对话/看板/岗位/简历/面试/设置图标入口）
- `src/components/layout/Header.tsx`：顶栏（Logo + 用户头像下拉菜单）
- `src/app/(main)/chat/layout.tsx`：对话页三栏布局（会话列表 | 对话流 | 上下文面板）

### Step 5：对话核心组件

- `src/stores/chat-store.ts`：管理当前会话消息列表、输入状态、会话 ID
- `src/stores/session-store.ts`：管理 session 轮询状态、progress、pending approval
- `src/components/chat/ChatStream.tsx`：消息流容器（ScrollArea + 自动滚底 + 消息列表渲染）
- `src/components/chat/MessageBubble.tsx`：用户消息（右对齐）/ 系统消息（左对齐）气泡
- `src/components/chat/ChatInput.tsx`：底部输入框 + 发送按钮 + 快捷模板（"河南 国企 Java"等）
- `src/app/(main)/chat/page.tsx`：对话主页面，组合以上组件

### Step 6：Session 轮询 + 进度卡片

- `src/lib/hooks/useSession.ts`：
  - 创建 session 后启动 2s 轮询 `GET /v1/sessions/{id}`
  - status 为 running 时持续轮询
  - status 为 waiting_approval 时暂停，触发审批流
  - status 为 completed/failed 时停止
- `src/components/chat/ProgressCard.tsx`：
  - 横向步骤条：意图解析 → 岗位搜索 → JD解析 → 匹配评分 → 简历优化 → 面试准备 → 投递创建
  - 状态：已完成(绿) / 进行中(蓝脉冲) / 待执行(灰)
  - 从 session.progress 读取 completed_steps / current_step / pending_steps

### Step 7：审批交互卡片

- `src/components/chat/ClarificationCard.tsx`：
  - 显示 Agent 追问文本
  - 提供输入框让用户补充信息
  - 提交后调用 `POST /v1/sessions/{id}/messages`（message_type: "clarification"）
- `src/components/chat/ApprovalCard.tsx`：
  - 显示审批标题 + 描述 + payload 预览
  - 操作按钮：批准 / 打回 / 跳过
  - 可选反馈文本框
  - 提交后调用 `POST /v1/approvals/{id}/respond`
  - 响应后恢复 session 轮询

### Step 8：右侧上下文面板

- `src/components/chat/ContextPanel.tsx`：
  - 执行进度区（竖向步骤列表，与 ProgressCard 数据同步）
  - 待审批提醒区（显示 pending_approval 信息，点击滚动到对应卡片）
  - Token 用量区（从 session.token_usage 读取，进度条展示）
- `src/app/(main)/chat/page.tsx` 中集成三栏布局

### P0 验收标准

- [ ] 能登录/注册，token 持久化
- [ ] 在对话框输入"河南 国企 Java"，成功创建 session
- [ ] 实时看到 Agent 执行进度（ProgressCard 步骤推进）
- [ ] 遇到审批节点时弹出 ApprovalCard，可操作
- [ ] 操作完成后流程继续，直到 completed
- [ ] 右侧面板同步显示进度和 Token 用量

---

## 第二期 P1：完整业务流程

目标：补全所有富卡片类型，实现会话管理、岗位浏览、简历管理等完整业务页面。

### Step 9：推荐结果卡片

- `src/components/chat/RecommendationCard.tsx`：
  - 岗位推荐列表（公司名 + 岗位 + 匹配分 + 推荐理由）
  - 每项可展开查看结构化 JD 详情
  - 底部操作：接受全部 / 逐个选择 / 拒绝重新匹配
  - 接受后调用 `POST /v1/sessions/{id}/recommendations/feedback`
- 对接 `GET /v1/sessions/{id}/recommendations` 获取推荐数据

### Step 10：简历对比卡片 + 面试题卡片

- `src/components/chat/ResumeDiffCard.tsx`：
  - Before/After 双栏对比布局
  - 修改处高亮标注（绿色新增 / 红色删除）
  - 修改理由列表
  - 操作：确认使用 / 打回重做
- `src/components/chat/InterviewCard.tsx`：
  - 题目列表（技术题/行为题分组）
  - 难度标签（easy/medium/hard 彩色 Badge）
  - 可折叠展开：题目 → 参考答案 → 评分标准
- `src/components/chat/ResultSummaryCard.tsx`：
  - 流程完成摘要：搜索 N 个岗位、匹配 M 个、优化简历、生成 K 道面试题
  - 快捷跳转链接：查看看板 / 查看面试题 / 查看岗位
- `src/components/chat/ErrorCard.tsx`：
  - 错误类型 + 消息展示
  - 重试按钮（重新发送消息或恢复 session）

### Step 11：会话列表 + 历史记录

- `src/components/chat/SessionList.tsx`：
  - 左侧会话列表（时间倒序）
  - 每项显示：意图摘要 + 状态标签 + 时间
  - 新建会话按钮
  - 点击切换会话（加载历史消息）
- `src/app/(main)/chat/[sessionId]/page.tsx`：
  - 加载历史 session 的 timeline 数据
  - 渲染历史消息流（只读模式，卡片不可再操作）
- 对接 `GET /v1/sessions` 列表 + `GET /v1/sessions/{id}/timeline`

### Step 12：岗位列表页

- `src/app/(main)/jobs/page.tsx`：岗位列表主页面
- `src/components/jobs/JobFilters.tsx`：筛选栏（地区/公司类型/薪资/技能多选）
- `src/components/jobs/JobCard.tsx`：岗位卡片（公司+岗位+薪资+地点+技能标签）
- `src/components/jobs/JobDetailDrawer.tsx`：右侧抽屉详情（结构化JD、技能要求、来源链接）
- 对接 `GET /v1/jobs`（分页+过滤）、`GET /v1/jobs/{id}`
- 手动录入 Dialog：`POST /v1/jobs/manual`

### Step 13：简历管理页

- `src/app/(main)/resume/page.tsx`：简历列表 + 上传入口
- `src/components/resume/ResumeUploader.tsx`：拖拽上传区域（支持 PDF/Markdown）
- `src/components/resume/ResumeCard.tsx`：简历卡片（标题+版本+方向+活跃状态）
- `src/components/resume/ResumeDetail.tsx`：简历详情（结构化数据展示）
- 对接 `POST /v1/resumes`（上传）、`GET /v1/resumes`（列表）、`PATCH /v1/resumes/{id}`（更新/设活跃）

### P1 验收标准

- [ ] 推荐结果以富卡片展示，可接受/拒绝
- [ ] 简历优化对比可视化，可审批
- [ ] 面试题按难度分组展示
- [ ] 可切换历史会话，查看完整执行记录
- [ ] 岗位列表可筛选、分页、查看详情
- [ ] 简历可上传、管理多版本

---

## 第三期 P2：增强体验与优化

目标：完善辅助功能页面，提升交互体验和视觉品质。

### Step 14：投递看板（拖拽）

- `src/app/(main)/kanban/page.tsx`：看板主页面
- `src/components/kanban/KanbanBoard.tsx`：看板容器（6 列：待投递/已投递/笔试/一面/二面/Offer）
- `src/components/kanban/KanbanColumn.tsx`：单列组件（标题+计数+卡片列表）
- `src/components/kanban/KanbanCard.tsx`：投递卡片（公司+岗位+匹配分+优先级色条）
- 使用 `@dnd-kit/core` 实现拖拽排序
- 拖拽结束调用 `PATCH /v1/applications/{id}/status`（后端状态机校验，非法流转 Toast 报错）
- 顶部统计栏：对接 `GET /v1/applications/statistics`（总数/各阶段数/转化率）

### Step 15：面试准备页

- `src/app/(main)/interview/page.tsx`：面试准备主页面
- `src/components/interview/QuestionGenerator.tsx`：
  - 选择岗位（下拉搜索）+ 题目类型（技术/行为/混合）+ 难度 + 数量
  - 触发生成 `POST /v1/interview/questions`
  - 轮询 `GET /v1/interview/questions/{task_id}` 直到完成
- `src/components/interview/QuestionList.tsx`：
  - 按类型分组（技术题/行为题 Tab 切换）
  - 每题可折叠：题目 → 参考答案 → 评分标准 → 追问
  - 难度 Badge + 收藏按钮 + 标记已练习
- 本地存储练习进度（localStorage 或后端 memory API）

### Step 16：设置页 + Token 用量可视化

- `src/app/(main)/settings/page.tsx`：设置主页面
- 个人信息区：用户名/邮箱/手机展示与修改
- Token 用量区：
  - 对接 `GET /v1/monitoring/token-usage`
  - 日用量折线图（recharts 或简单 SVG）
  - 按 Agent 分布饼图
  - 预算剩余进度条
- 偏好设置区：默认搜索地区/方向/企业类型
- 对接 `GET /v1/users/me`、`PATCH /v1/users/me`

### Step 17：暗色模式 + 响应式适配

- 暗色模式：
  - shadcn/ui ThemeProvider + next-themes
  - 设置页/顶栏添加主题切换按钮
  - 验证所有组件在 dark 模式下的显示
- 响应式适配：
  - 对话页：移动端隐藏左侧会话列表（汉堡菜单唤出）、右侧面板折叠为底部 Sheet
  - 看板页：移动端横向滚动
  - 岗位/简历页：卡片网格自适应列数
  - 断点：sm(640) / md(768) / lg(1024) / xl(1280)

### Step 18：消息通知 + 全局优化

- 审批提醒：
  - 顶栏 Bell 图标 + 未读 Badge
  - 轮询 `GET /v1/approvals?status=pending` 获取待审批数
  - 点击跳转到对应对话的审批卡片
- 全局 Loading 状态：页面切换 Skeleton、按钮 loading 态
- 错误边界：`error.tsx` + `not-found.tsx` 页面
- SEO/性能：metadata 配置、图片优化、代码分割
- 空状态设计：各页面无数据时的引导插图

### P2 验收标准

- [ ] 看板可拖拽，非法流转有明确报错
- [ ] 面试题可生成、分组、折叠、标记练习
- [ ] Token 用量有可视化图表
- [ ] 暗色模式全站可用，无色彩异常
- [ ] 移动端核心流程可走通
- [ ] 有待审批通知提醒

---

## 项目目录结构

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── (auth)/login/       # 登录/注册
│   │   ├── (main)/             # 需要认证的布局组
│   │   │   ├── chat/           # 对话主界面
│   │   │   ├── kanban/         # 投递看板
│   │   │   ├── jobs/           # 岗位列表
│   │   │   ├── resume/         # 简历管理
│   │   │   ├── interview/      # 面试准备
│   │   │   └── settings/       # 设置
│   │   ├── layout.tsx          # 根布局
│   │   └── page.tsx            # 首页重定向
│   ├── components/
│   │   ├── ui/                 # shadcn/ui 基础组件
│   │   ├── chat/               # 对话相关组件
│   │   │   ├── ChatStream.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── ProgressCard.tsx
│   │   │   ├── ClarificationCard.tsx
│   │   │   ├── RecommendationCard.tsx
│   │   │   ├── ApprovalCard.tsx
│   │   │   ├── ResumeDiffCard.tsx
│   │   │   ├── InterviewCard.tsx
│   │   │   ├── ResultSummaryCard.tsx
│   │   │   ├── ErrorCard.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   ├── SessionList.tsx
│   │   │   └── ContextPanel.tsx
│   │   ├── kanban/             # 看板组件
│   │   ├── jobs/               # 岗位组件
│   │   ├── resume/             # 简历组件
│   │   ├── interview/          # 面试组件
│   │   └── layout/             # 布局组件 (Sidebar, Header)
│   ├── lib/
│   │   ├── api/                # API 客户端 (按模块)
│   │   │   ├── client.ts
│   │   │   ├── auth.ts
│   │   │   ├── sessions.ts
│   │   │   ├── approvals.ts
│   │   │   ├── applications.ts
│   │   │   ├── jobs.ts
│   │   │   ├── resumes.ts
│   │   │   └── interview.ts
│   │   ├── hooks/              # 自定义 Hooks
│   │   │   ├── useSession.ts
│   │   │   ├── useApprovals.ts
│   │   │   └── useAuth.ts
│   │   └── utils.ts
│   ├── stores/                 # Zustand stores
│   │   ├── auth-store.ts
│   │   ├── chat-store.ts
│   │   └── session-store.ts
│   └── types/                  # TypeScript 类型
│       ├── api.ts
│       ├── session.ts
│       ├── approval.ts
│       ├── application.ts
│       ├── job.ts
│       └── resume.ts
├── public/
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## 视觉风格

- **主色调**: 深蓝 + 白底（专业、求职场景）
- **卡片风格**: 圆角 12px、轻阴影、左侧彩色边条标识类型
- **进度条**: 横向步骤条，已完成绿色、进行中蓝色脉冲、待执行灰色
- **暗色模式**: 支持（shadcn/ui 原生支持）
- **响应式**: 优先桌面端，右侧面板在移动端折叠为底部 Sheet
