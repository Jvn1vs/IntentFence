# AIB 动作证据登记册 v3

在2026-09-11固定的23条 `register_v2.json` 后，只追加 AIB-00105 的同前缀两条隔离动作，生成25条 `register_v3.json`。旧v2文件未覆盖；逐条比较确认新文件前23条与v2完全相同，25个 `action_observation_id` 唯一。新增两条保留原 `record.jsonl` 的来源路径/哈希、观测位置、动作及字段span，并以新构造器与共享内存契约的字节哈希生成派生策略ID。这些是证据登记ID，不是新模型自主动作。

生成器检查v2的固定SHA-256 `b8c38e4d5942ddf52451be8300c4367e8eecd466961471dad475ed1d3dc435d2` 及其全部历史输入哈希，再检查AIB-00105记录 `36bba8084290047eeaa5b5320ca8c8459ee6bd67af1471a8372b98fe4a54dd89`、manifest `afed6420b314bd3774511fba29f517bf1b5712cc7442ef726ccb51bf5a064faf` 和其中列出的所有固定输入。构造器根据原始AIB源行、固定配置与精确span重建两条动作后，要求与保存记录完全相等。`--verify` 再将整份v3登记册逐字节重放。

输出位于 ignored `data/interim/aib_action_evidence_20260923/register_v3.json`，SHA-256 `d2a4fbf34d9d06df13a94a236a8e211a6081cd8f6d93473533ed7a60f3a7d5fd`。新增 `src/intentfence/action_register_extension.py`、`scripts/extend_aib_action_register.py`、`configs/aib_action_register_v3_20260923.yaml` 和 `tests/test_action_register_extension.py`。3项fixture覆盖旧记录不变、重复ID或已应用标签拒绝、缺失/不同前缀、已执行动作和伪称模型生成的来源拒绝；完整测试481 passed（112.12秒），全仓Ruff、compileall、wheel、v3逐字节重放及diff检查通过。

v3仍为 `training_ready=false`、`route_b_admission_verified=false`，所有25条正式Risk/Alignment/split为空，`human_verified=false`。旧23条AI审核意见不自动套用到新两条；00105尚需独立语义审核和家族/锁定集合核验。当前只是把新动作纳入同一可追溯审核入口，不构成合格训练集或训练授权。
