# 第二版后续实验：补读与源码截断边界

## 结论

针对第二版文件召回下降的问题，尝试在模型完成报告前自动读取其解释中提到、但尚未读取的函数实现。**这条启发式没有作为默认功能发布**：各实现变体在同一开发集上的最终文件 Recall@3 为 0.95、0.80、0.65；其中前两轮分别只有 8/10、9/10 份报告通过引用来源检查。结果不足以证明可靠提升，也没有证明根因判断更准确。

最终保留的是 `read_file` 的确定性边界修正：8000 字符上限只返回完整的编号源码行，`end_line` 指向实际完整返回的最后一行；`more_lines` 和 `next_start_line` 只表示**本次请求范围**尚未返回完。这样可避免工具元数据把未返回的行误报为已读，也避免把“文件还有后续内容”误导成“继续逐段读取”。

## 数据与指标

沿用 [第二版评测](V2_REPORT.md) 的 10 个 Click/Requests 开发案例、固定修复前 Git SHA、本地 Qwen3-4B、BM25 和最多 6 次工具调用。修复标签仍只在事后评分时使用。此集合参与开发；每个变体只运行一次，代码与提示也发生变化，因此下表既不能作为独立准确率估计，也不能把差异全部归因于某一个改动。

| 实现 / 公共记录 | 实际读取文件 Recall@3 | 最终引用文件 Recall@3 | 来源检查通过的报告 | 耗时中位数 |
| --- | ---: | ---: | ---: | ---: |
| [原第二版](results/v2_final.json) | 0.70 | 0.70 | 10/10 | 12.97 秒 |
| [自动补读初稿](results/v2_1_gap_initial.json) | 0.95 | 0.95 | 8/10 | 13.54 秒 |
| [补读后引用失败则保留原报告](results/v2_1_gap_with_fallback.json) | 0.85 | 0.80 | 9/10 | 13.85 秒 |
| [同时调整截断提示](results/v2_1_gap_with_boundary.json) | 0.65 | 0.65 | 10/10 | 14.39 秒 |
| [最终保留：仅修正读取边界](results/v2_1_read_boundary.json) | 0.65 | 0.65 | 10/10 | 14.04 秒 |

“实际读取文件”只计无错误、至少有一行完整返回的 `read_file` 路径，文件去重后取前 3 个；搜索结果和 `find_callers` 返回的片段不算读取。最终引用仍按报告的前 3 个文件评分。两个指标都以修复 PR 的源文件作标签，**不衡量因果解释是否正确**。计算过程和逐案例文件见 [读码覆盖对比](results/v2_1_read_coverage.json)，可由 `scripts/compare_read_coverage.py` 重算；[最终配对统计](results/v2_1_comparison.json)保留所有失败项。

## 失败机制

自动补读依赖模型在初稿中提到准确的函数名。某轮 Requests PR7433 初稿提到了 `prepare_body`，因而补读了 `models.py`；另一轮只谈 `rewind_body` 和重定向，没有提 `prepare_body`，仍漏读 `models.py`。即使补读到相关文件，模型也可能继续错误解释代理对象和 `_body_position` 的条件。Requests PR7308 某轮补读了 `to_native_string`，但真正应核对的是请求头正则，文件召回改善也不能证明定位正确。

两轮补读报告出现了“列出文件但没有给出该文件的有效行号引用”，来源检查如实标为不足。后续加入保留原报告的回退，但召回收益没有稳定复现。增加源码读取内容还会改变模型后续生成；这些运行不能用来估计自动补读的一般收益。

最终边界修正也会改变模型看到的截断提示。单次最终运行的引用文件召回是 0.65，低于原第二版的 0.70；因此**不宣称本轮提高了召回率或诊断准确率**。它解决的是工具返回内容与行号元数据不一致的可复现错误。

## 复现

准备固定仓库快照并启动本地模型后：

```bash
python scripts/evaluate_investigations.py evaluation/investigation_cases.jsonl \
  /tmp/repopilot-benchmark/checkouts.json \
  --model-url http://127.0.0.1:18081/v1 \
  --output /tmp/repopilot-read-boundary.json
python scripts/compare_read_coverage.py evaluation/investigation_cases.jsonl \
  evaluation/results/v2_final.json /tmp/repopilot-read-boundary.json
```

公开记录省略上游源码正文；包含源码的完整轨迹只留在用户本机项目外的学习目录。最终结果的 `source_digest` 与发布前 Python 源码一致。检查方式包括 73 项 Python 测试、Ruff 和 mypy；源码截断、续读边界、无效行引用有专门测试。

## 简历和面试表述

可以讲：基于固定修复前版本构建了检索、实际读码、最终引用三个阶段的评测；发现提示式补读不稳定，保留实验数据并撤销默认功能；修复 `read_file` 行号与返回内容不一致的问题。

不要讲：本轮提升了定位准确率、自动补读稳定提高召回、26 条来源引用通过就代表 26 条因果解释正确。
