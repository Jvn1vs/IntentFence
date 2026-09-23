# AIB-00105 提交记录中的工作流注入对照

使用已批准的 AIB 固定源 revision `ef230359966c4d87b1c925aa56b8bf6e3f6ffed3`，原始 JSONL SHA-256 `606cb74f5ce874dba45d9cdf591af678d7c6bd8a92ff3189d0f522fb39fb941e`。该行零基对话前两条是用户要求查看 main 分支近期提交，以及 `git_log` 工具返回。构造器只接收这两条和系统消息，拒绝来源行哈希、工具定义、角色和人工圈定字符范围不匹配。

项目准备者 Codex/AI 在配置中圈定工具返回里的文件路径、工作流正文及攻击语句范围。离线策略给出两种不同的拟议动作：`goal_bounded` 原样返回635字符提交记录；`content_following` 提出把源中27字符路径和162字符工作流正文交给 `memory.file_proposal`。这一路仅代表攻击链中的写文件提案，**不包含**随后推送 main 的动作；原始源也没有真实文件写入或推送回执。完整原文留在 ignored 数据目录，公开报告不复述攻击目的地。

正常分支会把恶意提交正文作为查询数据带回；它没有执行指令，但当前尚无独立审核证明这种完整引述应被标为 aligned。另一分支若实际执行会使工作流包含环境变量外送命令；这里只产生 `executed=false` 的内存提案。源风险在已有单次 AI 场景清单中暂定 `data_exfiltration`，本次 `risk_label`、两个 `task_alignment_labels` 和 split 均为 null，`human_verified=false`、`training_ready=false`。不能声称新增两条已审核训练样本或真实代理失败。

现有家族约束将 AIB-00105 单列，不能据此判定独立。AIB-00068 也含向 CI 工作流加入秘密外送步骤的低信任指令，尽管用户授权任务和载体不同；后续分组至少应保守检查二者是否 must-link。之前 AIB 全量锁定文本筛查对指定13个保护文件无命中，但未完成跨来源模板和语义隔离，不能为新对照生成 split。

实现：`src/intentfence/aib_gitlog_contrast.py`、`scripts/build_aib_gitlog_contrast.py`、`configs/aib_gitlog_contrast_20260923.yaml`、`tests/test_aib_gitlog_contrast.py`。原产物位于 ignored `data/interim/aib_gitlog_contrast_20260923/run_v1/`；`record.jsonl` SHA-256 `36bba8084290047eeaa5b5320ca8c8459ee6bd67af1471a8372b98fe4a54dd89`，manifest保存配置/原源/代码哈希。构造后 `--verify` 逐字节重放通过；3项fixture测试覆盖来源改变、工具缺失、攻击范围外参数和未来消息隔离。完整测试472 passed（178.34秒）；全仓Ruff、compileall与wheel构建通过，diff检查通过。

下一步将这组源动作加入隔离审核材料，并对 AIB-00026、00103、00105 做来源家族与引述边界复核；补齐缺少的 unrelated/ambiguous 仍需另外的有证据场景。未训练、调用外部工具或付费服务。
