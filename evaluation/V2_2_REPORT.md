# 符号导航改进与真实案例复核

## 为什么前一轮从 0.70 变成 0.65

逐例对比发现，10 个案例中只有 Click #2836 的最终引用文件召回从 1.0 变为 0.5：报告读到并引用 `src/click/core.py`，但漏了 `src/click/termui.py`。该案例有两个标注文件，因此 0.5 的单例差距经 10 例平均就是 0.05。其他 9 例的最终文件召回没有下降。两轮各只运行一次；这不能证明项目的一般性能持续下降，也不能证明它已稳定。

更持续的问题是模型没有追到关键值的定义。原 `find_symbol` 只能查函数和类：Requests PR7308 的 `HEADER_VALIDATORS` 是赋值和导入，PR7433 的 `_body_position` 在属性赋值处形成，PR7425 的 `HooksInputType` 是类型别名。模型即使询问这些名字，也可能得到空结果。

## 这次做了什么

- 从索引时捕获的 Python 快照建立 AST 符号位置索引，记录赋值/声明、导入、函数和类；忽略注释与字符串，不执行目标仓库代码。
- `find_symbol` 接受裸名、`self.属性名` 和大小写变体。定义赋值排在导入位置之前，返回 `kind`、文件与行号。候选赋值不证明运行时采用了哪个值，仍需 `read_file` 和控制流核对。
- Agent、MCP 和网页轨迹都展示新增候选类型；网页明确提示需要继续核对实际运行路径。

在固定的 Requests 修复前快照上，查询 `HEADER_VALIDATORS` 返回 `_internal_utils.py:20` 的赋值和 `utils.py:28` 的导入；查询 `_body_position` 找到 `models.py` 的赋值位置；查询 `HooksInputType` 找到 `_types.py:37`。这验证导航能力存在，并不验证模型诊断正确。

## 十案例开发集结果

沿用 [第二版评测](V2_REPORT.md) 的 10 个 Click/Requests 开发案例、相同固定 Git SHA、BM25、最多 6 次工具调用、英语输出及本地 Qwen3-4B Q4 模型。标签不进入模型提示。

| 指标 | 上轮读取边界版 | 本轮符号导航版 |
| --- | ---: | ---: |
| 初始检索文件 Recall@3 | 0.75 | 0.75 |
| 实际读取文件 Recall@3 | 0.65 | 0.90 |
| 最终引用文件 Recall@3 | 0.65 | 0.90 |
| 协议完成 / 来源检查通过 | 10/10 / 10/10 | 10/10 / 10/10 |
| 耗时中位数 | 14.04 秒 | 14.17 秒 |
| 平均工具调用 | 3.5 | 4.0 |

[本轮原始摘要](results/v2_2_symbol_release_4b.json)、[配对统计](results/v2_2_symbol_comparison_4b.json)、[实际读码覆盖](results/v2_2_read_coverage_4b.json)。中间一次实现还未输出候选类型，单次开发集文件召回为 0.80；最终版本另跑一次得到 0.90。两个版本并不完全相同，不能把两次结果当独立重复试验。

## 文件命中与因果解释仍有差距

这轮 0.90 **是修复文件的文件级召回，不是根因准确率**。例如：

- Requests PR7433 终于引用 `models.py`，但把 `_body_position` 猜成“不是整数”，没有发现 `Iterable` 检测漏掉动态 `__iter__` 导致位置未记录。
- Requests PR7308 终于引用 `_internal_utils.py`，但报告错误地关注 `parse_list_header`，没有解释正则 `$` 为何允许末尾换行。
- Click #2836 引用了两个目标文件，却声称 `show_default` 没有设置为字符串；问题恰恰是已设置的字符串在布尔分支中未被传递。
- Requests PR7425 仍漏掉 `_types.py`，只命中 `sessions.py`，且没有指出确切需要修改的两处类型。

这些是开发助手对固定源码和修复 PR 的定性核对，**不是独立盲评，也没有执行上游回归测试**。网页仍标出模型的不确定性和“结论尚未验证”。

## 复现与边界

```bash
python scripts/evaluate_investigations.py evaluation/investigation_cases.jsonl \
  /tmp/repopilot-benchmark/checkouts.json \
  --model-url http://127.0.0.1:18081/v1 \
  --output /tmp/repopilot-symbols.json
python scripts/compare_read_coverage.py evaluation/investigation_cases.jsonl \
  evaluation/results/v2_1_read_boundary.json /tmp/repopilot-symbols.json
```

本数据集只有 10 个参与开发的案例，每版单次运行；GPU 与模型输出不保证逐次完全一致。新 AST 能提高部分值定义的可达性，但无法解析动态派发、别名的实际对象或跨函数的完整数据流。下一步若要主张诊断能力提升，需要独立案例和根因判定，并与更强模型或结构化数据流追踪作对照。

## 同源码的 8B 对照

随后在**完全相同的源码摘要、固定案例、仓库 SHA、BM25 和 6 次工具调用上限**下，将本地模型从 Qwen3-4B Q4 换成 Qwen3-8B Q4_K_M。两者都通过同一 llama.cpp 版本、16K 上下文和关闭思考的设置调用。模型文件来源与校验见[模型清单](results/v2_2_model_manifest.json)；[8B 运行摘要](results/v2_2_symbol_release_8b.json)和[模型配对结果](results/v2_2_model_comparison.json)不包含目标仓库源码全文。8B 的三个重点案例还单独试跑了一次，完整轨迹仅保存在本机未上传的学习目录。

| 指标 | 4B | 8B |
| --- | ---: | ---: |
| 初始检索文件 Recall@3 | 0.75 | 0.75 |
| 最终引用文件 Recall@3 | 0.90 | 0.75 |
| 协议完成 / 来源检查通过 | 10/10 / 10/10 | 10/10 / 10/10 |
| 平均工具调用 | 4.0 | 1.9 |
| 耗时中位数 | 14.17 秒 | 17.64 秒 |

8B 没有解决此前指出的重点错误。Click #2836 只读了 `core.py`，没有检查 `termui.py`，并推测已被代码分支排除的字符串会传给 `prompt`。Requests PR7308 没读到 `_internal_utils.py` 的验证正则，反而说没有找到显式换行检查。PR7433 只读 `models.py` 一次，却猜测代理对象的 `tell` 行为异常，没有识别 `Iterable` 判定漏掉动态 `__iter__`。这些是对已知修复与代码的人工定性核对，不是独立根因准确率分数。8B 在本次设置下较早停止读码，较大参数量没有自动换来更好的诊断，故可视化工作台继续默认使用 4B。

上述对照只运行单次，10 例均为开发集；0.90 与 0.75 也可能受生成波动影响，不能推广到其他模型、量化版本或项目。后续改进应先让调查流程在关键表达式之后核对其值来源和下游分支，并建立独立案例上的根因判定。当前页面的“引用范围已核对”只表示引用来自实际读取的源码，不表示因果推理通过验证。
