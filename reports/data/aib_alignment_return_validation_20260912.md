# Alignment审核回收格式校验

2026-09-12。新增 `scripts/validate_aib_alignment_return.py` 与8项fixture测试；联合前阶段打包测试10 passed（0.58秒）、相关Ruff通过。没有真实审核回收结果，未生成或应用任何正式审核标签。

校验固定A/B原表SHA-256、CSV表头/行序/行数/唯一ID与不可变材料单元格；拒绝不完整或畸形行。已完成项限定四类Alignment，弃权必须标签为空且有理由；动作形式限三值，reviewed_at要求时区，reviewer_id必须匹配调用者声明。

输出明确区分form_integrity_verified=true和reviewer_identity_authenticated/independence_verified=false。格式通过不代表身份真实、盲态成立、观点一致或标签正确，也不触发合并/训练。具体命令已加入 `docs/aib_alignment_review_instructions_20260912.md`。

当前独立审核执行条件仍未落实：两个文件夹不是两个审核执行单元，已有root看过旧意见，不能代作独立审核。冻结协议 `docs/route_b_ai_review_protocol.md` 要求身份元数据与运行证据；任何派发前须核实真实模型组合、材料范围与现有授权。不能用同模型不同名字或人工填造revision补条件。

下一步落实可用的独立审核执行身份，同时继续准备独立Risk材料；Alignment包本身不覆盖Risk审核。五风险四Alignment的原目标、类别缺口和最终准入条件保持不变。
