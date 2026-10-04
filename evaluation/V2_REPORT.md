# 第二版评测与边界 — v0.9

## 结论

第二版已实现可核对的行号引用、候选调用方查找、明确的不确定性与复核状态，以及可复现的两版对比。**本轮没有证明诊断准确率提高。** 引用的来源正确，不代表引用能支持模型的因果解释；真实案例中仍有错误和退步。

## 数据与实验设置

- 10 个开发案例：5 个 Click 历史问题，5 个 Requests 问题或修复 PR；覆盖运行时行为和 1 个类型标注问题。
- [案例清单](investigation_cases.jsonl)逐项记录仓库、修复前完整 SHA、问题/修复链接、文件标签和核对要点。Requests 每例使用相应 PR 的修复前基线，不混用已经修复的代码。
- 查询是开发过程中对公开问题/PR 的改写；部分查询整理时已看过修复。此集合参与了调试，**不是留出集**，也不能代表所有仓库。
- 标签来自修复 PR 的源文件，排除测试、文档和更新日志。修复文件不一定涵盖所有合法证据文件；因此文件召回也不是根因准确率。
- 本地 Qwen3-4B Q4_K_M、llama.cpp Vulkan、16K 上下文、BM25、6 次工具预算。模型权重和运行时见[固定版本记录](results/local_models_manifest.json)。未使用付费 API。
- 工具调查阶段输出上限 1,536 tokens；第二版多一次无工具的结构化证据整理，上限 2,200 tokens，关闭 thinking。评测用英语避免中文转述额外影响比较。网页可以请求中文。
- 顺序运行、模型已加载、每案单次测量。GPU 运行不保证完全确定；耗时不是冷启动、并发或稳定统计基准。

## 配对运行结果

| 指标 | 第一版基线 | 第二版 |
| --- | ---: | ---: |
| 报告协议完成 | 10/10 | 10/10 |
| 初始上下文文件 Recall@3 | 0.75 | 0.75 |
| 最终引用列表文件 Recall@3 | 0.85 | 0.70 |
| 通过逐行来源核对的报告 | 不支持该检查 | 10/10 |
| 通过来源核对的引用 | 不支持该检查 | 22/22 |
| 耗时中位数（秒） | 7.11 | 12.97 |
| 平均工具调用次数 | 2.4 | 3.3 |

初始 Recall 是实际传给 Agent 的前 5 个检索片段去重后的前 3 个文件，**与旧版检索报告对全量候选计算的 Recall@3 不同**。最终引用 Recall 只看模型返回文件列表的前 3 项；失败报告按空列表计分，不从分母移除。第二版要求引用来自真正读取的行，收紧了最终文件列表，但也漏掉了部分修复文件；不能把 0.70 描述为准确率提高。

原始摘要：[基线](results/v2_baseline.json)、[第二版](results/v2_final.json)、[程序生成的统计](results/v2_comparison.json)。公开记录省略上游源码正文，完整轨迹留在本地学习目录。

## 逐案源码核对

以下由本次开发助手结合固定源码及链接的修复 PR 做定性核对，**不是独立盲评，没有运行上游回归测试**。`supported_mechanism` 表示解释指出了与源码一致的机制；`partial` 表示缺少关键环节；`weak` 表示主要复述现象；`unsupported` 表示存在错误归因。这些标签用于定位下一步工作，不用于声称一般准确率。

| 案例 / 上游修复 | 第一版 → 第二版 | 核对记录 |
| --- | --- | --- |
| [pallets/click#3019](https://github.com/pallets/click/pull/3021) | weak → unsupported | 第一版主要复述空后缀现象。第二版错误归因于参数默认值；显式传入空串不会被默认值覆盖，仍遗漏输入路径无条件追加空格。 |
| [pallets/click#2952](https://github.com/pallets/click/pull/2956) | unsupported → partial | 第一版误归因于 show_default。第二版找到了 flag_value 与 default 的分支，但仍未追踪环境变量值的解析与转换，不能建立完整因果链。 |
| [pallets/click#2836](https://github.com/pallets/click/pull/3328) | supported_mechanism → unsupported | 第一版识别了 prompt_for_value 只转发布尔 show_default 的分支。第二版退步为猜测默认值或 show_default 未设置，没有说明自定义字符串被丢弃。 |
| [pallets/click#3015](https://github.com/pallets/click/pull/3471) | unsupported → unsupported | 两版都聚焦大小写；未识别 enum 的字符串表示与 Choice 接受的规范化值不一致。 |
| [pallets/click#3043](https://github.com/pallets/click/pull/3126) | supported_mechanism → supported_mechanism | 两版均指向 format_completion 将多行 help 直接拼入输出。与固定源码一致，但没有执行回归测试。 |
| [psf/requests#PR7502](https://github.com/psf/requests/pull/7502) | weak → weak | 两版均停留在 prepare_body 一带，没有找到 _encode_files 的运行时协议检查与 __getattr__ 文件包装器之间的问题。 |
| [psf/requests#PR7433](https://github.com/psf/requests/pull/7433) | unsupported → unsupported | 两版均把代理对象推测为不支持 seek。实际关键是 prepare_body 的 Iterable 检测遗漏动态 __iter__，未记录 _body_position。第二版最终引用还遗漏 models.py。 |
| [psf/requests#PR7309](https://github.com/psf/requests/pull/7309) | unsupported → partial | 第一版的编码回退解释错误。第二版正确指出对布尔值调用 strip，但没有建立解析器对缺少等号的参数写入 True 的完整路径。 |
| [psf/requests#PR7308](https://github.com/psf/requests/pull/7308) | weak → unsupported | 两版均未读到实际正则定义。第二版错误关注 to_native_string / proxy_bypass；真正需要核对的是正则 $ 对尾随换行的行为。 |
| [psf/requests#PR7425](https://github.com/psf/requests/pull/7425) | unsupported → partial | 第一版混淆 HookType 与输入形状。第二版提到两个入口的类型标注不一致，但未明确指出应使用 HooksInputType | None 的两个位置，且遗漏 sessions.py 引用。 |

完整核对记录：[v2_source_review.json](results/v2_source_review.json)。保留模型初稿和最终报告，可以观察结构化整理纠正或引入了哪些判断；它不是保证正确的复核器。

## 为什么需要证据检查

- 校验引用文件存在于快照、范围合法且不超过 200 行。
- 每一行必须匹配成功的 `read_file` 实际返回内容；截断行和仅搜索到的文件不能通过。
- 每个最终引用文件需要具体行号；仅有测试/文档证据不能证明 Python 实现。
- 引用不足或模型列出不确定性时，LangGraph 标记需要复核。
- **检查不理解因果语义**。本轮 22 条引用均通过，表中仍有多项错误，这正是必须区分两者的原因。

`find_callers` 通过 Python AST 找调用表达式、候选调用方和行号，忽略注释和字符串中的同名文本。它只按最终标识符匹配，不解析别名、类型、继承或动态调用，因此界面显示“候选调用方”，不能视为完整调用图。

## 保留的失败实验

1. 仅加强提示并添加调用方工具：[v2_candidate.json](results/v2_candidate.json)。缺引用、格式错误仍存在。
2. 将未验证初稿传入证据整理：[v2_draft_conditioned.json](results/v2_draft_conditioned.json)。发现初稿锚定、未见文件引用及预算耗尽问题。
3. 最终方案用已读取源码独立整理，用文件枚举约束输出，并在工具预算用完时直接进行有上限的整理。
4. 在 3 个开发案例上尝试整理阶段开启 thinking、上限 4,096 tokens：[v2_reasoning_probe.json](results/v2_reasoning_probe.json)。耗时更高，仍出现错误/不完整报告，未选作默认配置。这不是额外测试集，也未用于替换完整对比中的失败项。

各轮源代码摘要、文件哈希、案例数与推理设置见[实验清单](results/v2_experiments.json)。复现命令见[评测说明](README.md#v2-paired-investigation-evaluation)。源码摘要记录运行开始时的 Python 文件状态；开发期间的 `source_commit` 是父提交，需结合摘要和对应改动识别版本。

## 当前可以如何描述项目

可以描述：实现了只读代码调查、4 种工具、逐行证据检查、候选调用方追踪、可视化报告，以及 2 个真实仓库的固定版本对比和失败分析。

不应描述：自动准确定位并修复 Bug、诊断正确率 100%、定位准确率得到提升、已经验证生产可用。

后续优先解决的是相关实现代码覆盖、强弱模型对照和独立案例评测，而非继续靠这 10 个开发案例调整提示。

## 发布前复现验收

中文转述改为只翻译文字数组后，用最终源码再次运行全部 10 个案例，单独保存为 [发布验收](results/v2_release_verification.json) 和 [统计](results/v2_release_comparison.json)，未替换上述主对比。最终源码摘要与该记录一致。本次协议完成 10/10、来源检查通过 10/10、引用文件 Recall@3 为 0.70，耗时中位数 13.11 秒。该重复运行仍是同一个开发集，不能当作独立验证集。
