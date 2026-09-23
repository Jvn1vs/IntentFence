# AIB-00105 补充独立审核材料

从固定v3登记册只选 `AIB-00105:0/1`，生成两套待填写 Alignment 表（各2条动作）及两套 Risk 表（各1条动作前最近工具返回）。Alignment材料仅含最新用户目标、动作前system与对话、来源工具定义和拟议动作；Risk材料仅含低信任内容。后续assistant示范、源ground_truth、源案例ID、构造策略名、家族约束、旧双模型意见均不进入审核表。原攻击文本仍作为待审核材料保留，不以删去难点换取表面清洁。

固定输入：v3登记册 SHA-256 `d2a4fbf34d9d06df13a94a236a8e211a6081cd8f6d93473533ed7a60f3a7d5fd`、AIB原源 `606cb74f5ce874dba45d9cdf591af678d7c6bd8a92ff3189d0f522fb39fb941e`、新动作记录 `36bba8084290047eeaa5b5320ca8c8459ee6bd67af1471a8372b98fe4a54dd89`。每条新登记记录的来源观测须与保存记录相同。逐行CSV解析重建材料哈希，审核状态、标签、身份及时间列均为空，审核文件中无 `AIB-00105` 源ID。

输出在 ignored `data/interim/aib_00105_review_20260923/`：

| 文件 | SHA-256 |
|---|---|
| `alignment/reviewer_A/alignment.csv` | `3e1696c4e8d6bd577edac58ffed4dd3eada1485472c6d7fb9c7c8a16dc41ed11` |
| `alignment/reviewer_B/alignment.csv` | `145ce9a69ced13face28b2da9f6ae9d2e5f4f722de9edbf89ea047990f498237` |
| `risk/reviewer_A/risk.csv` | `9067fc6a61953956ec47cf038c51e305ce54ccd7d08d784abd9b2c8eae097c08` |
| `risk/reviewer_B/risk.csv` | `9067fc6a61953956ec47cf038c51e305ce54ccd7d08d784abd9b2c8eae097c08` |

Risk只有一行，两位审核者看到的输入文件相同是预期；独立性取决于后续分离执行与身份/版本/温度元数据，而非文件排序。`coordinator_only/mapping.json` SHA-256 `73ad1bfdca2c270eabf82ad6b2280345089f8d20b26f25609ffbded7f476a5e2`，manifest SHA-256 `7f15f7172deebc7f73bad7a06be80d76d80022b1bdf10d0ae984b7150bcc1`；manifest也记录两份复用的白名单/CSV函数源码哈希。协调材料不可给审核者。

新增 `scripts/package_aib_00105_review.py`、`configs/aib_00105_review_package_20260923.yaml` 和 `tests/test_aib_00105_review_package.py`。2项fixture覆盖未来消息/源标签排除、空答复列、缺少或错配动作拒绝；初版manifest遗漏复用函数哈希，经核对四表和映射不变后仅刷新manifest，随后 `--verify` 逐文件重放通过。最终完整测试483 passed（76.48秒），全仓Ruff、compileall、wheel及diff检查通过。本阶段只打包，`review_complete=false`、`independence_verified=false`、`human_verified=false`、`training_ready=false`。不能把旧23条的AI意见自动赋给新两条，也不能声称正式400条审核协议已完成。
