# AIB CI工作流机制的补充隔离约束

原 `data/interim/aib_family_constraints_20260911/constraints.json` 固定哈希 `635bdebe9cc1e1f15e41c455123eb999d17673cbce3b0156b75fef5e38b65d2f`，182个案例、107个保守连通组。本轮只增加一条 must-link：AIB-00068 与 AIB-00105 均在低信任内容中指示把秘密或环境信息外送步骤写进 CI 工作流。两例用户任务与载体不同，此关联只约束未来划分，不声称文本重复或正式Risk标签相同。

补充配置将两条固定源行 SHA-256 绑定至现有 AIB revision `ef230359966c4d87b1c925aa56b8bf6e3f6ffed3`，并验证完整原文件 SHA-256。历史107组结果不覆盖；新输出在 ignored `data/interim/aib_family_supplement_20260923/constraints_v2.json`，SHA-256 `d310ede866d757e48b60a149384f22538c7ad0029da567bf16092624cb33fa32`。重放检验通过，182例保持齐全，得到106个**约束组**。目标组为 AIB-00068、00075、00105；00075由旧版同名家族约束与00068相连，不是本次独立证明的相同机制，后续仍须复核旧组是否过宽。

新输出保留 `family_isolation_complete=false`、`split=null`、`training_ready=false`、`human_verified=false`。106是连通约束组数量，不能宣传为106个已验证独立家族。没有读取最终测试预测、生成训练划分或应用标签。

新增 `configs/aib_family_supplement_20260923.yaml`、`scripts/build_aib_family_supplement.py`、`tests/test_aib_family_supplement.py`。6项fixture覆盖传递合并、无效/未知ID、历史未隔离状态拒绝；`--verify` 对新文件逐字节重放成功。完整测试478 passed（113.88秒），全仓Ruff、compileall、wheel及diff检查通过。下一步继续审核 AIB-00105 动作语义与源中正常分支引述，并核验更多近义机制，不能依赖单一手工连边断言隔离完成。
