# 前端（Vue 3 + Element Plus）

教师备课系统前端，替代原 React 实现。

## 技术栈

- Vue 3（Composition API + `<script setup>`）
- TypeScript
- Vite 7
- Element Plus（中文 locale，主题色粉色 `#ec4899`）
- Pinia（认证状态）
- Vue Router（路由守卫）
- axios（类型化 API 封装）
- vis-network（知识图谱可视化）

## 目录结构

```
src/
├── api/            # axios 客户端 + 类型化 API + SSE 流式聊天
├── stores/auth.ts  # Pinia 认证 store
├── router/         # 路由 + 登录守卫 + 超管守卫
├── layouts/        # 侧边栏布局
├── views/          # 业务页面
│   ├── DashboardView.vue       # AI 助手（SSE 流式聊天）
│   ├── DocumentsView.vue       # 文档管理（上传/抽取/搜索）
│   ├── KnowledgeGraphView.vue  # 知识图谱（vis-network + 表格）
│   ├── LessonPlansView.vue     # 教案（AI 生成/导出 Word）
│   ├── CurriculumView.vue      # 教材课标（学科/教材/章节树）
│   ├── PptView.vue             # PPT 生成/编辑
│   ├── RemindersView.vue       # 备忘提醒（课程表/任务）
│   ├── SettingsView.vue        # 个人设置
│   ├── AdminView.vue           # 管理后台（超管）
│   └── Login/Signup/Recover/ResetPassword   # 认证页
└── types.ts        # 与后端 API 对应的类型定义
```

## 开发

```bash
npm install
npm run dev      # http://localhost:5173（/api 代理到 localhost:8000）
npm run build    # 类型检查 + 产物构建
```

## API 对接说明

- axios baseURL 为 `/api/v1`；开发环境由 Vite 代理，生产环境由 Nginx 反向代理到 backend 服务
- AI 助手使用原生 `fetch` 读取 `text/event-stream`，逐 token 渲染
- 登录后 token 存于 localStorage（`access_token`），请求拦截器自动附带，401 自动跳转登录
