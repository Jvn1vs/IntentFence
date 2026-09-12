# 14个内容单元的Risk双模型试点

2026-09-12。沿用所有者指定sol/terra，创建两个无历史继承的新任务，各自仅收到Risk CSV与评分说明，没有动作、Alignment意见、源ID或家族提示。23条动作按其动作前最近tool_result去重为14项；这是当前内容Risk审核，不是整段源场景全部载体的全面审核。多轮139使用当前动作前最近工具返回，140使用最新查询返回，不能把旧场景攻击标签直接套入。

## 结果

| Risk意见 | sol/A | terra/B |
|---|---:|---:|
| benign | 4 | 4 |
| instruction_hijacking | 3 | 3 |
| data_exfiltration | 4 | 3 |
| privilege_escalation | 1 | 2 |
| tool_manipulation | 2 | 2 |

双方14条completed、无弃权，完整性校验通过。一致13/14=92.8571%，kappa=0.9084967。唯一分歧为AIB-00032：A把公开私有备份读取归为外传，B归为权限提升。没有临时追加第三模型或以root意见覆盖分歧。

新增 `configs/aib_review_holds_20260912.yaml` 记录7个案例共8条动作的准备暂缓理由：桶策略Risk分歧、航班/旧数值Alignment分歧、截断公钥、部分摘要和仅澄清不能成完整配对。暂缓是数据准备状态，不是裁定标签错误；未列入暂缓也不等于准入，因为全局独立元数据、类别/家族/划分条件仍缺失。

## 执行限制与哈希

精确revision和temperature仍不可验证。A一度将通用“Codex based on GPT-6”身份描述误填为revision，已由原审核者新增metadata_correction.json改正为未知；原CSV与原metadata不覆盖。没有伪造温度0、审核耗时或完整协议通过。未使用训练/API执行数据中的动作。

- A原表 `f87136fbe41d178e312724cbd4ff88d8ea6e62d630183f9f9fd9ce3c03ee0c4a`，回收 `105d2f3b35345b6a1c6aea6fe8e5ec7250dd348d34ea937fa8c4ba6e4fd2749e`，原metadata `c93717f8023616f9758f48ce8c012fcdfcb838a6f7a553b053dd6655dec5af61`。
- B原表 `c7016c0045f28afb74bd00f27f7d520d892e706960c902179536ba24fdd1bcf8`，回收 `9ff9bfa05043bc7f0d11df1ecc1fe6a65f3d8fb3db82693cb60512cb0608c352`，metadata `a72d27e10344c37cdedae3aa9d3327e9e5e5976cc8a3d7aae473852c2f90c86a`。
- ignored `data/interim/aib_risk_review_20260912/coordinator_only/comparison.json` SHA-256 `00ea24c5c4fdfc220a37600d581a29e19f3b6f975847344d14c36bfc8b86645d`。

新增Risk打包/回收比较脚本及6项fixture测试，6 passed（0.24秒）、相关Ruff通过，原表CSV往返哈希校验通过。Conda命令为 `python -m scripts.package_aib_risk_review` 和 `python -m scripts.compare_aib_risk_reviews`，均拒绝覆盖已有产物。

下一步应处理缺失类别与语义边界，而不是继续对同一批数据重复投票。已有试点仍不足以形成每个内部角色覆盖五Risk四Alignment的训练数据；原训练结果保留，新增标签未应用、训练未启动。
