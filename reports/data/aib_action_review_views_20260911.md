# 桶策略与澄清动作的表示核对

2026-09-11。完整回读AIB-00032、00159源记录，检查动作前字段与旧提案；源后续assistant示范没有用于生成新动作。新增的是两项审核展示视图，不增加21条观测数量，不修改旧标签意见。

## 桶策略

[AWS官方put-bucket-policy文档](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-bucket-policy.html)将bucket和JSON policy列为必需参数。旧提案的五个字段可以无损表达为Bucket加单Statement的Policy字符串，无需补造Version、凭据或其他权限字段。新视图保留原Effect/Principal/Action/Resource及目标桶；它是离线请求结构展示，不是可执行适配器。

只能证明该表示与文档参数结构相符，不能证明原始嵌套shell引号可直接执行、服务会接受请求、账户具权限或最终有效访问发生变化。旧action_realism=ambiguous意见不自动改写，新视图供后续审核使用。

## 澄清

00159的动作前上下文给出联系人，但没有Q3报告摘要正文。旧missing:body代码展示为“Please provide the email body you want to send.”，同时保留原代码。文字来源明确为确定性工程渲染器，不是来源对话、模型观测或人工标签。没有补造正文、发送邮件或添加隐藏bcc。遇到其他问题码时拒绝套用这条单一缺正文文案，避免漏报收件人/授权问题。

## 产物与限制

- `src/intentfence/action_review_views.py`：严格输入的离线展示函数。
- `scripts/build_aib_action_review_views.py`：绑定两份固定动作文件哈希，生成原动作到视图的关联。
- `tests/test_action_review_views.py`：5项fixture检查策略不增字段、资源错配/权限泛化失败、澄清不吞掉额外问题。
- ignored `data/interim/aib_action_review_views_20260911/views.json` SHA-256 `3e916597ed5cb42f276d2c4ca1f20211bd875ab6551cabe98b4829cca92602ae`。

完整工程检查：432 passed（153.03秒），全仓Ruff、compileall及wheel构建通过。检查在Conda intentfence中启动，OPENBLAS_NUM_THREADS和OMP_NUM_THREADS均为1。

Conda复现：`python scripts/build_aib_action_review_views.py`，已有产物拒绝覆盖。逐项读取落盘视图确认与旧提案字段一致。当前21条原观测及其AI意见保持不变，新增训练样本0、标签应用0。下一步继续上下文完整的指令劫持来源对照；展示改进不会解决unrelated/ambiguous覆盖和独立审核缺口。
