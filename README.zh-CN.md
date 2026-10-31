[English](README.md) | 简体中文

# 上下文压缩阈值

这是一个经验计算工具，用来权衡 token 费用与上下文压缩耗时。它会重放真实的
智能体会话，用实测压缩数据拟合费用与耗时模型，再用块重采样扩充工作负载，最后
生成静态站点：一个用来选择模型的首页，加上每个模型各一张图表页（Codex 上的
DeepSeek Flash，Claude Code 上的 Claude Opus 5.5 和 Claude Sonnet 5.5）。页面
提供英文和简体中文。

[查看在线页面](https://context-compaction-threshold.pages.dev/)

不存在适用于所有人的唯一阈值。合适的阈值取决于你需要保留多少上下文，以及你
能接受多少额外费用和压缩等待。对 Claude Code，页面还会告诉你该设置多大的
`autoCompactWindow`。

固定规则（阈值步长、坐标轴上限、价格及其来源、会话和请求怎么算、压缩怎么找、
重采样参数）以及各模型的数据统计，都写在 [docs/methodology.zh-CN.md](docs/methodology.zh-CN.md)。

## 快速开始

不需要第三方 Python 依赖。

```bash
python3 src/generate.py --profile claude-opus-5-5 --workers 30   # 分析，然后重建站点
python3 src/generate.py --render-only                           # 用 data/*/*/result.json 重建页面
python3 -m unittest discover -s tests -p 'test_*.py'            # 测试
```

`--profile` 默认是 `deepseek-flash`（读取 `~/.codex/sessions` 里的 Codex 会话）。
`--harness codex|claude-code` 可以覆盖 profile 里指定的 harness。受限沙箱如果
禁止 multiprocessing 的 socket，加上 `--workers 1`。其余参数见 `--help`。

## 配置

- `config/models.json`：模型 profile（模型事实：价格、上下文窗口、阈值范围、
  模型名过滤）和 harness（日志怎么采集、触发点怎么设置）。新增模型时，复制一个
  profile，改价格、窗口和名称即可；阈值步长固定为 2000。
- `config/pages.json`：全部页面文字，分共用层、harness 层和 profile 层，每层都有
  英文和中文。`src/render.py` 里的同一个模板渲染所有页面。

## 输出与部署

git 里只存数据。一个（harness，profile）组合的全部数据放在
`data/<harness>/<profile>/` 下，路径由这两个名字推出：

```text
data/<harness>/<profile>/compactions.json   脱敏后的压缩样本（校准输入）
data/<harness>/<profile>/result.json        分析结果（页面的唯一输入）
```

`artifacts/` 只放生成的页面，被 git 忽略，不提交：`artifacts/index.html`（首页）和
`artifacts/<profile>.html`（每个模型一张图表页）。每个 profile 只有一个默认
harness，所以 `<profile>.html` 不会有歧义。

每次推送到 `main`，Cloudflare Pages 都会用 `python3 src/generate.py --render-only`
构建站点，并发布 `artifacts/`。构建只需要 Python 3 和已提交的 `result.json`，不需要
会话、网络或第三方包。Python 3.8 及以上即可。

`compactions.json` 每行是一次实测压缩：`name`、`source`、`input_tokens`、
`cached_tokens`、`output_tokens`、`seconds`，只有数字。Codex 的文件保留 9 个手工计时的样本，每次分析还会加上从日志读到的压缩（`log-auto`）。
Claude Code 每次分析都会从对话记录重新写出样本（`transcript-auto` 或
`transcript-manual`），拟合再读回这些样本。Claude Sonnet 5.5 自己的压缩太少，拟合时
借用 Opus 的样本；借来的行不会复制进它的文件。用 `--compactions FILE` 可以改用别的
样本文件拟合。

私有的原始会话不进仓库，例如放在被 git 忽略的 `.tmp/sessions/<harness>/<profile>/`
下，用 `--session-root` 传入。默认根目录仍然是各 harness 自己的
（`~/.codex/sessions`、`~/.claude/projects`）。

## 目录结构

```text
config/       models.json、pages.json
data/         按 harness 和 profile 提交的数据：compactions.json、result.json
docs/         方法与统计数据
src/          分析、harness、profile 加载、渲染、入口
tests/        使用标准库的单元测试
artifacts/    只放生成的页面（被 git 忽略，部署时生成）
```

## 隐私

程序只读取原始会话日志（`~/.codex/sessions`、`~/.claude/projects`），不会复制。
提交和生成的文件只有聚合数量、拟合系数、曲线和脱敏后的压缩样本，不含会话 ID、路径、
提示词或消息正文。发布其他机器上的结果前，请先检查生成文件。
