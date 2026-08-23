# 建立前端基础技术栈

## Goal

以用户现有的 `landing-customs-law-portal/frontend/admin` 为参考，为龙田街道舆情系统建立一致、可直接承载后续业务页面的前端基础技术栈，同时保持当前本地健康检查页面的可见行为。

## Background

- 当前 `frontend/` 已使用 React 19、TypeScript 6、Vite 8、Tailwind CSS 4、pnpm 11.14.0 和 shadcn/ui，但仍是单页面初始化状态。
- 当前项目使用 ESLint 以及 `new-york` / Radix 风格的 shadcn 配置；已复制 Button、Badge、Card 三个 UI 组件。
- 参考项目的管理端是静态 Vite SPA，采用 React Router Data Mode、TanStack Query、React Hook Form + Zod、Lucide、Vitest + Testing Library、Oxlint、Prettier，以及 `base-nova` / Base UI 风格的 shadcn 配置。
- 用户已批准以参考项目的管理端为基准，并在本任务中迁移现有 shadcn 基础到 Base UI 风格。

## Requirements

### R1. Runtime foundation

- 添加 React Router，建立应用 router 和根路由错误边界；当前健康检查页面作为 `/` 的 index route 保留。
- 添加 TanStack Query，并通过单一应用 Provider 挂载 QueryClient。
- 添加 React Hook Form、`@hookform/resolvers` 和 Zod，作为后续表单的统一基础；本任务不虚构业务表单。
- 添加 Lucide React，作为后续功能图标库；品牌与平台标识仍使用经过确认的项目资源。
- 不添加 Zustand、Motion、TanStack Table、React Query Devtools 或其他尚无消费者的状态/动画/表格依赖。

### R2. shadcn foundation migration

- 将 `components.json` 从当前 `new-york` / Radix 配置迁移到参考项目的 `base-nova` / Base UI 配置。
- 使用当前 shadcn CLI 重新生成或迁移 Button、Badge、Card，并逐个审查差异；不得覆盖当前页面的龙田街道品牌配色、排版和“四社区连接标记”。
- 仅在所有引用清除后移除 `@radix-ui/react-slot`；不得留下未声明的传递依赖。
- 保持已有组件对当前页面的公开用法兼容，或在同一变更内更新调用方并通过测试。

### R3. Quality tooling

- 使用 Oxlint 替换 ESLint，删除 ESLint 配置和只服务于 ESLint 的依赖。
- 添加 Prettier 和 `prettier-plugin-tailwindcss`，提供 `format`、`format:check` 命令，并让插件读取当前 `src/index.css`。
- 添加 Vitest、jsdom、Testing Library、jest-dom 和 user-event，建立测试配置与全局清理入口。
- 保留明确的 `typecheck` 与生产 `build` 命令；`build` 不应重复隐藏或替代独立质量门。

### R4. Application composition and behavior

- `main.tsx` 只负责根节点校验、StrictMode 和应用挂载。
- Router 和全局 Provider 分别位于 `src/app/`，页面组合位于 `src/routes/`。
- 当前健康检查页面仍覆盖 loading、connected、unavailable、retry，后端返回契约不变。
- 新增行为测试证明初始路由通过 Router/Provider 渲染，并覆盖至少一个健康状态或重试行为；测试不得依赖真实后端。

### R5. Dependency and repository hygiene

- 所有前端依赖只写入 `frontend/package.json` 和唯一的 `frontend/pnpm-lock.yaml`。
- 依赖安装和所有验证均使用 mise 管理的 Node 24 与 pnpm 11.14.0。
- 不修改 `backend/`、`third_party/MediaCrawler`、`db_data/` 或 `logs/`。
- 不在本任务引入 pnpm workspace、OpenAPI 生成器、生成式 API client 或新的顶层目录。

## Acceptance Criteria

- [ ] `pnpm install --frozen-lockfile` 在 Node 24 下成功，锁文件无漂移。
- [ ] `package.json` 包含批准的运行时与测试/格式化工具，不再包含 ESLint-only 依赖。
- [ ] `components.json` 记录 `base-nova` / Base UI，现有 Button、Badge、Card 不再依赖 Radix Slot。
- [ ] `/` 通过 React Router 和应用 Provider 渲染，健康检查四种交互行为保持不变。
- [ ] Vitest + Testing Library 测试通过，且不访问真实 FastAPI 服务。
- [ ] `pnpm format:check`、`pnpm lint`、`pnpm typecheck`、`pnpm test:run`、`pnpm build` 全部通过且无项目自身警告。
- [ ] 本机浏览器桌面与窄屏验证 connected、unavailable、retry，无控制台错误或横向溢出。
- [ ] MediaCrawler gitlink/工作树以及用户运行数据目录保持不变。

## Out of Scope

- OpenAPI JSON 导出、`openapi-typescript`、`openapi-fetch`、`openapi-react-query` 和生成客户端。
- 真实业务路由、登录页、平台账号表单、采集配置、舆情列表或数据库功能。
- pnpm monorepo/workspace、共享 UI package、SSR 或 React Router Framework Mode。
- 引入未在 Requirements 中列出的 shadcn 组件。
