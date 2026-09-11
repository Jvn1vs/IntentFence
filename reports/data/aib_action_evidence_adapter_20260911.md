# 六批AIB观测的统一证据适配

2026-09-11。新增独立寄存文件，原六批试点不覆盖。23条观测均得到唯一action_observation_id及绑定实现哈希的action_policy_id；它们是适配器派生标识，不是新增运行或模型自主动作证据。

## 绑定范围

每条记录保留原文件路径/字节SHA-256、零基记录和观测位置、case_id、原观测规范化哈希、完整原观测、原始观测ID和策略名。派生观测ID绑定这些来源定位及内容；派生策略ID绑定原策略名和对应实现哈希。原文件哈希经固定审核receipt或新航班固定hash验证，所登记实现文件与当前字节核对通过。

第一批从原观测取得offline_actions实现哈希；通信批取得通信实现及共享契约哈希；风险/推广批取得risk实现及共享契约哈希；旧值和航班批保留记录中的代码哈希图。此范围没有宣称冻结完整解释器/依赖环境或重新执行全部源选择器，配置与准备细节仍通过原观测和源文件指针追溯。

field_provenance保持各原表示（span/JSON指针等），完整解析到前缀以及统一action_pair_group仍需后续适配；有ID不等于通过Route B。所有正式标签/split保持null，human_verified/training_ready=false。明确sandbox_policy_output、model_generated=false。

## 文件与验证

新增 `src/intentfence/action_evidence_adapter.py`、`scripts/adapt_aib_action_evidence.py`、`tests/test_action_evidence_adapter.py`。拒绝执行过的观测、缺策略、缺字段来源、已应用标签/split或冒充人审。6项fixture通过（0.53秒）、相关Ruff通过；覆盖ID随动作/实现变动、输入隔离与证据禁止提升。

初次测试错误修改了冻结的fixture模型，已改为构造新模型；同时为输入观测增加深复制，防止返回记录随调用者后续变更而与其哈希不一致。初次register.json作为历史输出保留，当前产物register_v2.json。

ignored `data/interim/aib_action_evidence_20260911/register_v2.json` SHA-256 `b8c38e4d5942ddf52451be8300c4367e8eecd466961471dad475ed1d3dc435d2`。Conda复现命令 `python -m scripts.adapt_aib_action_evidence`，拒绝覆盖输出。23条唯一ID检查通过，无新增训练样本。

下一步核验字段来源能否解引用回原前缀，并形成同上下文配对与家族约束的统一记录；继续保持独立审核、缺失类别及正式准入状态可见，不能把本层包装当成数据补齐完成。
