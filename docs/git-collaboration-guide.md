# Git 协作与提交规范

本文档用于说明通用的 Git 协作流程和提交信息规范，适用于大多数个人项目、课程项目和团队协作项目。不同项目可能会有自己的分支策略、发布规则和提交要求；如果项目已有明确规范，应优先遵守项目现有规范。

## 一、协作目标

Git 协作的核心目标是：

- 每个人都在自己的分支上独立开发，避免互相覆盖代码。
- 重要分支保持稳定，未经检查的代码不直接进入主分支。
- 每次改动都能被追踪、审查和回滚。
- 团队成员通过 Pull Request 或 Merge Request 进行代码审查。

说明：GitHub 通常称为 Pull Request，GitLab 通常称为 Merge Request。本文统一简称为 PR。

## 二、常见分支约定

大多数项目可以采用以下分支约定：

| 分支 | 作用 |
| --- | --- |
| `main` / `master` | 主分支，保存稳定、可发布的代码 |
| `develop` | 开发集成分支，用于合并日常开发完成的代码 |
| `feature/*` | 功能分支，用于开发新功能 |
| `bugfix/*` | 修复分支，用于修复测试或联调中发现的问题 |
| `hotfix/*` | 紧急修复分支，用于修复线上或发布版本中的严重问题 |

现在很多新项目默认使用 `main` 作为主分支，部分旧项目仍使用 `master`。两者作用类似，实际使用时以仓库中的默认分支名称为准。

如果项目规模较小，也可以只使用 `main` 和 `feature/*`。是否保留 `develop`，由团队根据项目复杂度决定。

## 三、分支命名规范

分支名应简短、清楚，能够看出正在处理什么任务。

推荐格式：

```text
feature/<name-or-task>
bugfix/<name-or-issue>
hotfix/<name-or-issue>
```

示例：

```text
feature/login-page
feature/user-profile
bugfix/register-validation
hotfix/payment-timeout
```

建议使用小写英文、数字和连字符 `-`，避免使用空格、中文和特殊符号。

## 四、提交信息规范

推荐使用 Conventional Commits 风格：

```text
<type>(<scope>): <description>
```

其中 `scope` 是可选项。新手可以先使用最简单的格式：

```text
<type>: <description>
```

示例：

```text
feat: add login page
fix: correct register validation
docs: update installation guide
```

### 1. `type`

`type` 表示本次提交的主要变更类型。建议统一使用小写英文，从以下类型中选择：

| 类型 | 使用场景 | 示例 |
| --- | --- | --- |
| `feat` | 新增功能 | `feat: add login page` |
| `fix` | 修复缺陷 | `fix: handle empty username` |
| `docs` | 修改文档 | `docs: update README` |
| `style` | 代码格式调整，不影响功能 | `style: format user service` |
| `refactor` | 重构代码，不新增功能也不修复缺陷 | `refactor: simplify auth flow` |
| `perf` | 性能优化 | `perf: reduce image loading time` |
| `test` | 新增或修改测试 | `test: add login tests` |
| `build` | 构建系统或依赖变更 | `build: upgrade vite` |
| `ci` | CI/CD 配置变更 | `ci: add build workflow` |
| `chore` | 其他杂项维护 | `chore: update gitignore` |
| `revert` | 回滚提交 | `revert: revert login page change` |

### 2. `scope`

`scope` 用于说明变更影响的范围，可写可不写。常见范围包括模块、页面、接口、目录或功能名。

示例：

```text
feat(auth): add login page
fix(api): handle expired token
docs(readme): update setup steps
```

如果不确定 `scope` 应该怎么写，可以先省略，保持提交信息清楚即可。

### 3. `description`

`description` 用一句话说明本次提交做了什么。建议遵循以下规则：

- 使用简短、明确的描述。
- 只描述本次提交的主要内容。
- 不要写过于笼统的内容，例如 `update`、`fix bug`、`修改代码`。
- 可以使用英文或中文，但同一个项目内尽量保持统一。

较好的示例：

```text
feat: add user profile page
fix: prevent duplicate form submission
docs: add local development steps
```

不推荐的示例：

```text
update
fix bug
修改了一些东西
```

## 五、Gitmoji 对照表

Gitmoji 可以作为提交信息的辅助标识，让提交记录更直观。它不是必需项，也不应替代 `type`。为了兼容更多项目和自动化工具，建议始终保留 Conventional Commits 的 `type`。

推荐写法：

```text
✨ feat: add login page
🐛 fix: correct register validation
```

常用 Gitmoji 对照表：

| Gitmoji | 代码 | 推荐 `type` | 使用场景 |
| --- | --- | --- | --- |
| ✨ | `:sparkles:` | `feat` | 新增功能 |
| 🐛 | `:bug:` | `fix` | 修复缺陷 |
| 📝 | `:memo:` | `docs` | 修改文档 |
| 🎨 | `:art:` | `style` | 调整代码格式或结构，不影响功能 |
| ♻️ | `:recycle:` | `refactor` | 重构代码 |
| ⚡️ | `:zap:` | `perf` | 性能优化 |
| ✅ | `:white_check_mark:` | `test` | 新增或修改测试 |
| 📦 | `:package:` | `build` | 构建、打包或依赖变更 |
| 👷 | `:construction_worker:` | `ci` | CI/CD 配置变更 |
| 🔧 | `:wrench:` | `chore` | 工具、配置或杂项维护 |
| ⏪ | `:rewind:` | `revert` | 回滚提交 |
| 🚑 | `:ambulance:` | `fix` | 紧急修复严重问题 |
| 🔒 | `:lock:` | `fix` | 修复安全问题 |
| 🚀 | `:rocket:` | `chore` | 发布、部署或上线相关操作 |

如果团队希望使用 `gitmoji-cli`，可以先安装 Node.js 和 npm，然后执行：

```bash
npm i -g gitmoji-cli
gitmoji -v
```

在仓库目录下执行以下命令，可以通过交互界面选择 emoji 并创建提交：

```bash
gitmoji -c
```

## 六、标准开发流程

下面以“从 `develop` 创建功能分支，并通过 PR 合并回 `develop`”为例。若项目不使用 `develop`，可将相关命令中的 `develop` 替换为 `main` 或项目指定的目标分支。

### 1. 克隆仓库

第一次参与项目时，需要先把远程仓库下载到本地：

```bash
git clone <repo-url>
cd <repo-name>
```

### 2. 同步远程信息

```bash
git fetch origin
```

这个命令会获取远程仓库的最新分支和提交信息，但不会直接修改当前工作区文件。

### 3. 切换到目标基础分支并拉取最新代码

如果项目使用 `develop`：

```bash
git checkout develop
git pull origin develop
```

如果项目没有 `develop`，通常使用 `main`：

```bash
git checkout main
git pull origin main
```

### 4. 创建个人开发分支

开发新功能：

```bash
git checkout -b feature/<name-or-task>
```

修复普通问题：

```bash
git checkout -b bugfix/<name-or-issue>
```

### 5. 在个人分支上开发

查看当前分支和文件状态：

```bash
git branch
git status
```

当前所在分支前面会显示 `*`。提交前应确认自己不在 `main`、`master` 或 `develop` 等重要分支上直接开发。

查看具体改动：

```bash
git diff
```

### 6. 提交改动

添加全部改动：

```bash
git add .
```

只添加某个文件：

```bash
git add <file-path>
```

提交代码：

```bash
git commit -m "feat: add login page"
```

提交信息应说明“这次提交做了什么”，而不是说明“我正在做什么”。

### 7. 定期同步目标分支

多人协作时，目标分支可能会持续更新。为了减少冲突，开发过程中应定期同步。

如果目标分支是 `develop`：

```bash
git fetch origin
git checkout develop
git pull origin develop
git checkout feature/<name-or-task>
git merge develop
```

如果目标分支是 `main`：

```bash
git fetch origin
git checkout main
git pull origin main
git checkout feature/<name-or-task>
git merge main
```

如果出现冲突，需要打开冲突文件，保留正确内容，删除冲突标记，然后执行：

```bash
git add .
git commit
```

如果不确定如何解决冲突，应及时和相关成员沟通，不要随意删除他人的代码。

### 8. 推送个人分支到远程仓库

第一次推送该分支：

```bash
git push -u origin feature/<name-or-task>
```

后续再次推送同一分支：

```bash
git push
```

### 9. 发起 PR

在 GitHub、GitLab、Gitee 或其他代码托管平台中发起 PR。

通常应填写：

- 源分支：自己的 `feature/*`、`bugfix/*` 或 `hotfix/*` 分支。
- 目标分支：项目指定的合并目标，通常是 `develop` 或 `main`。
- 变更内容：本次改了什么。
- 影响范围：可能影响哪些功能、页面、接口或配置。
- 测试情况：做过哪些检查，例如本地运行、单元测试、构建等。

### 10. Code Review 与合并

提交 PR 后，由其他成员进行代码审查。审查通过后，再合并到目标分支。

不建议绕过 PR 直接向 `main`、`master` 或 `develop` 推送代码。重要分支应设置分支保护规则，限制直接推送。

### 11. 删除已合并分支

PR 合并后，可以删除已经完成任务的远程分支，保持仓库整洁：

```bash
git push origin --delete feature/<name-or-task>
```

本地分支也可以删除：

```bash
git branch -d feature/<name-or-task>
```

## 七、合并到主分支与发布

如果项目使用 `develop`，通常流程是：

1. 日常功能和修复先合并到 `develop`。
2. 当 `develop` 达到阶段性稳定状态后，由负责人发起从 `develop` 到 `main` / `master` 的 PR。
3. 测试通过后，再合并到 `main` / `master`。
4. 如有发布流程，可在主分支上打版本标签。

示例：

```bash
git tag v1.0.0
git push origin v1.0.0
```

是否打标签由项目发布规则决定，新手日常开发一般不需要操作。

## 八、团队协作规范

- 不直接向 `main`、`master` 或 `develop` 推送代码，除非项目明确允许。
- 日常开发从最新的目标分支创建个人分支。
- 一项任务对应一个分支，避免多个无关任务混在同一个分支中。
- 提交前先检查 `git status`，确认只提交需要提交的文件。
- 提交信息应清楚说明本次改动内容。
- 提 PR 前先同步目标分支，尽量提前解决冲突。
- PR 描述应写明变更内容、影响范围和测试情况。
- 合并前至少由一名其他成员进行 review，具体人数按项目要求执行。
- 不要提交密码、密钥、Token、数据库文件、大型临时文件等敏感或无关内容。
- 一次提交只做一类事情，避免把多个无关改动放进同一个提交。

## 九、什么时候需要 fork

同一个团队成员如果已经拥有主仓库写权限，通常不需要 fork，直接在同一个仓库中创建个人分支即可。

以下情况更适合使用 fork：

- 外部协作者没有主仓库写权限。
- 开源项目要求贡献者通过 fork 提交 PR。
- 需要将个人实验性开发与主仓库彻底隔离。
- 不希望个人分支直接出现在主仓库中。

无论是否使用 fork，推荐做法都是：先在个人分支中开发，再通过 PR 合并到目标分支。

## 十、新手常见问题

### 1. 我应该从哪个分支开始开发？

以项目要求为准。常见情况是从 `develop` 创建分支；如果项目没有 `develop`，通常从 `main` 创建分支。

### 2. 我可以直接在 `main` 上改代码吗？

不建议。`main` / `master` 通常代表稳定版本，直接修改容易影响其他成员和发布流程。

### 3. 为什么要先提 PR？

PR 可以让团队在合并前检查代码、讨论问题、运行自动化检查，并保留完整的变更记录。

### 4. 什么时候需要同步目标分支？

开发时间较长、多人同时修改同一模块、准备提交 PR 之前，都建议同步一次目标分支。

### 5. 我应该使用中文还是英文写提交信息？

两者都可以，但同一个项目内应尽量统一。多数工具和开源项目更常使用英文；课程项目或内部项目也可以使用中文。

### 6. Gitmoji 是必须的吗？

不是。Gitmoji 只是让提交记录更直观的辅助标识。更重要的是提交信息中的 `type` 和 `description` 要清楚、统一。
