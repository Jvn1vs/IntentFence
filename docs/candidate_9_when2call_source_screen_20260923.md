# When2Call 动作对照来源筛查（2026-09-23）

## 结论

优先提出 NVIDIA When2Call **preference 训练文件的隔离只读审计**，但不将其直接接入 candidate 9。它的 `chosen_response` / `rejected_response` 可提供同一用户请求与工具定义下的动作对照，尤其是缺必填参数却调用工具、参数值错误和工具不匹配。论文明确这些错误响应是合成反事实，不是观察到的真实代理执行；因此即使审计通过也只能称为 source-grounded proposed actions，不能称真实执行轨迹或直接继承本项目 `aligned/unrelated/ambiguous/malicious` 标签。

## 官方证据与边界

- [NAACL 2025 论文](https://aclanthology.org/2025.naacl-long.174.pdf) §2.2、§3.3.2：训练问题以 APIGen Simple/Multiple Function 为基础，Mixtral 8x22B 生成修改后的请求和错误选项；preference 的 rejected 可由去掉必填参数、改错参数值或漏掉部分工具调用产生。评测集则来自 BFCL v2 Live；两者不是可随意混用的同一划分。论文也警告单纯增加负例可能令工具调用过于保守。
- [NVIDIA 数据卡](https://huggingface.co/datasets/nvidia/When2Call) 把 `train_pref` 列为 9,000 条、`train_sft` 列为 15,000 条，标为合成、自动标注，声明 CC-BY-4.0 和训练/评测用途。只考虑前者的审计；不下载测试文件，也不使用其测试标签设计本项目样本。
- [NVIDIA 仓库格式示例](https://github.com/NVIDIA/When2Call/blob/main/README.md) 展示同一请求、工具定义、chosen 澄清与 rejected 工具调用的配对。`request_for_info` 只是该来源的决策类别，不等同 Task Shield 的 `ambiguous`；`cannot_answer` 也不自动等同 `unrelated`。
- [NVIDIA 仓库数据生成说明](https://github.com/NVIDIA/When2Call/blob/main/README.md) 指明训练输入来自 Salesforce xLAM/APIGen。其[原始数据卡](https://huggingface.co/datasets/Salesforce/xlam-function-calling-60k) 有访问确认条件；二次数据的 CC-BY-4.0 声明不能替代对上游条款的核查。审计前不声明训练再利用权已闭合。

## 固定审计范围

Hugging Face 元数据 API 于 2026-09-23 返回 revision `0582f7749df63a96fdc3070932e83e72396ace53`。只读候选 `train/when2call_train_pref.jsonl` 为 17,369,692 bytes，LFS SHA-256 `d90637f108fabf1b097493c5818c3692e1d73140259d2f8e490536255e765bc4`；`README.md` 为 5,038 bytes；总下载上限 17,374,730 bytes。详细机器范围在 `configs/candidate_9_when2call_audit_proposal_20260923.yaml`。本阶段只读取官方页面和元数据，没有下载数据文件。

## 审计时的判定

1. 逐行区分原始 APIGen 请求/正确调用、When2Call 生成的用户请求、chosen 与 rejected；记录变换谱系和来源族，不能把同一基础请求的不同版本拆到不同角色。
2. 只筛选 **显式工具调用** 的 paired rows。按项目四类独立审查是否有真正无关动作、授权或参数依据不明动作；澄清/拒答响应本身不是动作，风险类也不能从该来源任务标签推断。
3. 对源内及现有保护集做指纹/家族隔离审计，不用最终测试结果选例或调规则。任何无法核实上游归属、实际工具定义、必填参数或动作语义的样本保持隔离。
4. 最终记录可用量和证据质量；不执行工具，不赋正式标签，不生成训练 split，不启动训练。

当前状态 `owner_approved=false`：项目所有者此前对常规阶段的持续批准不覆盖 `configs/execution_policy.yaml` 中的新来源条款责任。当前“批准”仅据现有上下文解释为继续推进已授权的筛查工作，不能事后写作对这个刚形成的精确下载范围的确认。
