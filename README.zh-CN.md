[English](README.md) | 简体中文

# 上下文压缩阈值

这是一个经验计算工具，通过展示 token 费用与上下文压缩耗时之间的权衡，帮助你决定智能体应当在多大的上下文处触发压缩。

[查看在线页面](https://context-compaction-threshold.pages.dev/)

图表上没有适用于所有人的唯一最优阈值：合适的阈值取决于你需要保留多少工作上下文，以及你能接受多少压缩费用与等待时间。在线站点包含一个用于选择模型的首页，以及每个模型各自的一张图表页（Codex 上的 DeepSeek Flash、GPT-6.1 Sol、GPT-6.1 Terra 和 GPT-6 Luna，以及 Claude Code 上的 Claude Opus 5.5 和 Claude Sonnet 5.5）。对于 Claude Code，页面还会直接给出对应的 `autoCompactWindow` 设置值。所有页面均提供英文和简体中文。

为了生成这些曲线，工具会重放真实的智能体会话，用实测压缩数据拟合费用与耗时模型，再通过块重采样扩充工作负载，最后将结果发布为静态站点。项目的所有固定规则（阈值步长、坐标轴上限、价格及其来源、会话与请求的计入标准、压缩记录的提取方式、重采样参数）以及各模型的数据统计，均记录在 [docs/methodology.zh-CN.md](docs/methodology.zh-CN.md)。

## 快速开始

在本地运行分析或重建站点只需要 Python 3，不需要任何第三方 Python 依赖。

```bash
python3 src/generate.py --profile claude-opus-5-5 --workers 30   # 分析，然后重建站点
python3 src/generate.py --render-only                           # 用 data/*/*/result.json 重建页面
python3 -m unittest discover -s tests -p 'test_*.py'            # 测试
```

运行分析时，`--profile` 默认为 `deepseek-flash`（读取 `~/.codex/sessions` 里的 Codex 会话），`--harness codex|claude-code` 可以覆盖 profile 默认指定的 harness。如果受限沙箱禁止 multiprocessing 的 socket，请加上 `--workers 1`。其余参数见 `--help`。

默认情况下，各 harness 会直接读取各自的日志目录（`~/.codex/sessions`、`~/.claude/projects`）。如果要使用存放在仓库之外的私有原始会话——例如被 git 忽略的 `.tmp/sessions/<harness>/<profile>/`——请通过 `--session-root` 传入路径。

三个 GPT 模型的 Codex profile 只筛选最近 14 天内开始的会话，普通请求和压缩校准使用同一批筛选出的会话。由于 14 天窗口会随运行时间推移，基于冻结的会话快照复现实验时，可用 `--snapshot-at 2026-10-31T21:11:07Z` 锚定时间窗口；不传则以运行时刻为基准。它们的费用曲线遵循本项目约定的订阅口径，使用固定的接口 token 权重，不加长上下文附加费。

## 配置

跑通生成流程后，可以通过两个配置文件和一个渲染模板来新增模型，或调整页面文案与版式：

- `config/models.json` 定义模型 profile（模型事实：价格、上下文窗口、阈值范围、模型名过滤）和 harness（日志如何采集、触发点如何设置）。新增模型时，复制一个现有 profile 并修改价格、窗口和名称即可；阈值步长固定为 2000。
- `config/pages.json` 存放全部页面文案，分为共用层、harness 层和 profile 层，每层均包含英文和中文。`src/render.py` 中的同一个模板负责渲染所有页面。

调整文案请改 `config/pages.json`，调整布局请改 `src/render.py`，改完重新生成即可，不要直接修改生成的 HTML。首页卡片保持紧凑布局，右上角显示 harness 标记，最低费用触发点用灰色普通字重显示；卡片描述和 Claude 窗口设置行均予省略，以确保在 1920px 视口宽度下，中英文首页的内容高度都小于 900px。

## 输出与部署

生成器会将提交入库的数据与生成的 HTML 页面分开存放，使站点无需原始会话日志即可完成构建与部署。

git 仓库里只保存数据。每个 `(harness, profile)` 组合的全部数据都存放在 `data/<harness>/<profile>/` 下，路径直接由这两个名称导出：

```text
data/<harness>/<profile>/compactions.json   脱敏后的压缩样本（校准输入）
data/<harness>/<profile>/result.json        分析结果（页面的唯一输入）
```

`compactions.json` 每行记录一次实测压缩，包含 `name`、`source`、`input_tokens`、`cached_tokens`、`output_tokens` 和 `seconds`，全部为纯数字。分析运行时如何更新该文件取决于所使用的 harness：Codex 每次运行都会刷新从日志中读取的压缩记录（`log-auto`），同时 DeepSeek 会保留原有的 9 个手工计时样本；Claude Code 每次运行都会从对话记录重新写出样本（`transcript-auto` 或 `transcript-manual`），拟合时再读回这些样本。Claude Sonnet 5.5 自身的压缩样本过少，拟合时会借用 Opus 的样本，但借用的行不会写入它自己的文件。如需改用其他样本文件进行拟合，可传入 `--compactions FILE`。

渲染器随后只读取 `result.json`，将静态页面输出到 `artifacts/` 目录：`artifacts/index.html`（首页）和 `artifacts/<profile>.html`（每个模型一张图表页；由于每个 profile 只有一个默认 harness，`<profile>.html` 不会产生歧义）。`artifacts/` 只存放生成的页面，被 git 忽略，从不提交。

生成的页面不入库，所以部署时由数据重新构建：每次推送到 `main` 分支时，Cloudflare Pages 都会执行 `python3 src/generate.py --render-only` 构建站点并发布 `artifacts/`。由于渲染只需读取已提交的 `result.json`，构建环境只需要 Python 3（Python 3.8 及以上即可），不需要会话日志、网络连接或第三方包。本地也不需要安装 Wrangler；如需修改 Pages 配置，请直接调用 Cloudflare API。

## 目录结构

上述配置、入库数据、文档、源码、测试与构建产物分别对应仓库顶层的六个目录：

```text
config/       models.json、pages.json
data/         按 harness 和 profile 提交的数据：compactions.json、result.json
docs/         方法与统计数据
src/          分析、harness、profile 加载、渲染、入口
tests/        使用标准库的单元测试
artifacts/    只放生成的页面（被 git 忽略，部署时生成）
```

## 隐私

由于原始会话日志包含完整对话内容，项目对私有日志与公开产物做了严格隔离。原始会话日志（`~/.codex/sessions`、`~/.claude/projects`）以及存放在被 git 忽略的 `.tmp/` 下的冻结本地快照（见快速开始）都属于私有数据。提交入库和生成的页面文件只包含聚合计数、拟合系数、曲线以及脱敏后的压缩样本，不含任何会话 ID、路径、提示词或消息正文。发布其他机器上跑出的结果前，请先检查生成的文件。
