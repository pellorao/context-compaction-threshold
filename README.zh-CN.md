[English](README.md) | 简体中文

# DeepSeek 最佳压缩阈值

这是一个基于真实 DeepSeek Codex session 的经验计算工具，用于权衡 token
费用与上下文压缩耗时。它会重放真实请求，用实测压缩数据拟合费用与耗时模型，
再通过块重采样扩充工作负载，最后生成独立 HTML 图表。

[查看在线页面](https://deepseek-compaction-threshold.pages.dev/)

不存在适用于所有人的唯一阈值。合适的阈值取决于工作需要保留多少上下文，
以及使用者对额外费用和压缩等待时间的接受程度。

## 数据范围

- 只分析使用 `deepseek-flash` 的 Codex session。
- 按 response ID 去重。
- 自动排除 smoke、probe、test 类 session。
- 可用重复的 `--exclude-thread` 参数排除压缩校准 session。
- 可用 `--active-thread` 排除正在分析的会话，并纳入它最后一次压缩后的连续片段。
- 当前校准文件包含 9 次真实压缩：6 次把真实 session 上下文语义裁剪后压缩，
  3 次是会话内原生压缩。

## 计算方法

单次请求费用：

```text
Q(x, c, y) = p_m * ((1-c) + alpha*c) * x + p_o * y
alpha = p_c / p_m
rho = p_o / p_m
```

单次压缩耗时：

```text
t_c = a*(C-K) + G/v
```

其中 `C` 是压缩输入，`K` 是可复用的缓存前缀，`G` 是摘要输出，`a` 是
未缓存 token 的预处理时间，`v` 是摘要的等效生成速度。页面把 `v` 显示为
“服务端输出速度”滑块；调节它不会改变费用。

阈值曲线分三步生成：

1. 对每个真实 session 精确重放，得到原始的整数台阶曲线。
2. 从真实请求变化中按每 8 个请求一块做 circular block bootstrap，用固定
   随机种子生成 100 组工作负载。
3. 在每组重采样工作负载上逐阈值重放，再对结果取平均。

最终曲线没有再做平滑。曲线呈现为连续期望值，是因为平均发生在重采样请求
序列的重放结果上，而不是对已经算出的折线做滤波。

## 快速开始

项目不需要第三方 Python 依赖。

```bash
python3 src/generate.py
```

复现指定分析会话的结果：

```bash
python3 src/generate.py \
  --active-thread <active-thread-id> \
  --exclude-thread <calibration-thread-1> \
  --exclude-thread <calibration-thread-2>
```

受限沙箱可能禁止 Python multiprocessing 创建进程通信 socket。此时可在沙箱外
运行，或使用较慢的单进程模式：

```bash
python3 src/generate.py --workers 1
```

输出文件：

```text
artifacts/result.json
artifacts/curves.csv
artifacts/threshold-chart.html
```

## 目录结构

```text
data/compaction_trials.json   脱敏后的真实压缩数据
src/analysis.py               session 读取、拟合、重放和重采样
src/render.py                 独立 HTML 渲染器
src/generate.py               命令行入口
artifacts/                    页面、曲线和完整结果
tests/                        使用标准库的单元测试
```

运行测试：

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 隐私

程序只读取 `~/.codex/sessions` 中的原始 JSONL，不会将其复制到仓库。生成的
JSON 只包含聚合数量、拟合系数、曲线和脱敏后的校准样本，不包含 session ID、
本地路径、工作目录、提示词、工具输出或消息正文。

如果把其他机器上的分析结果发布到公开仓库，仍应在提交前检查生成文件。

## 注意事项

- 结果依赖当前工作负载分布和 DeepSeek 价格。
- 块重采样只能扩充真实样本中已有的变化模式，不能凭空创造新的工作方式。
- 压缩样本仍然较少。页面阴影表示实测缓存前缀和摘要长度变化，不是正式置信区间。
- session、价格或服务端吞吐发生明显变化后，应重新运行分析。
