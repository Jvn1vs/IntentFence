# C3b ONNX、INT8、FastAPI 与 CPU 基准运行手册

状态：C3b 的导出契约、ONNX/INT8 元数据校验、API 版本/故障策略和延迟基准框架已完成，
只用 fixture 与规则后端验证。当前没有真实 checkpoint、ONNX 文件或 INT8 安全结果；因此
不能把本阶段的 smoke 数字写成模型性能或安全结论。

## 1. 导出前只读预检

`export_onnx.py --preflight-only` 只读取冻结模型目录中的 `metadata.json` 和必要文件，
检查完整 40 字符 revision、Risk/Alignment 标签、模型目录结构、opset 和输出目录状态。
它不导入 PyTorch/Transformers、不读取权重、不创建输出文件：

```powershell
Set-Location E:\IntentFence
python deployment/export_onnx.py `
  --model-dir checkpoints\base-action-multitask-seed42\best `
  --output-dir artifacts\c3b\onnx-seed42 `
  --opset 17 `
  --quantize `
  --preflight-only
```

输出目录必须不存在，即使是空目录也会拒绝覆盖。源模型必须是项目所有者冻结并验证过的
checkpoint；本命令不会替项目所有者完成训练、校准或最终测试授权。

## 2. 项目所有者执行导出

真实 checkpoint 可用且该阶段获得明确执行确认后，项目所有者去掉 `--preflight-only`，并
在 `intentfence` 环境安装固定 extras：

```powershell
conda activate intentfence
python -m pip install -e ".[ml,onnx]" --index-url https://pypi.org/simple
python deployment/export_onnx.py `
  --model-dir checkpoints\base-action-multitask-seed42\best `
  --output-dir artifacts\c3b\onnx-seed42 `
  --opset 17 `
  --quantize
```

导出目录包含 `model.onnx`、可选的 `model.int8.onnx`、复制出的 `tokenizer/` 和
`export_metadata.json`。元数据绑定源模型树哈希、源 model revision、两个模型文件哈希、
tokenizer 树哈希、opset、输入输出名、动态轴、标签和 max length。写入后脚本会再次校验；
任何文件被篡改，`OnnxBackend` 都会拒绝加载。导出产物属于本地 artifact，不应提交到 Git。

## 3. FP32/INT8 运行时检查

可以对已产生的导出目录执行只读校验：

```powershell
python -c "from intentfence.deployment import validate_export_artifacts; validate_export_artifacts('artifacts/c3b/onnx-seed42'); print('export artifacts passed')"
```

API 的 ONNX 后端默认优先选择 `model.int8.onnx`，没有该文件时回退到 `model.onnx`。直接
创建 `OnnxBackend` 时，`model_path` 必须是元数据登记的 FP32 或 INT8 变体，tokenizer 也
必须是同一导出目录的副本。FP32 与 INT8 必须在同一冻结输入和同一固定阈值下分别重跑安全
指标；不能只比较延迟，也不能从测试集重新选择阈值。

## 4. CPU 延迟、吞吐和内存

基准脚本记录冷启动初始化时间、第一次请求、预热后的请求 P50/P95/均值/标准差、顺序或
并发吞吐、模型 artifact 大小/哈希、进程峰值 RSS 和 Python 分配峰值。支持 `short`、
`medium`、`long` 输入以及进程内共享后端的并发请求；报告路径已存在时拒绝覆盖：

```powershell
python benchmarks/latency.py `
  --backend onnx `
  --model-dir artifacts\c3b\onnx-seed42 `
  --calibration artifacts\c2c\seed42\calibration.json `
  --onnx-variant int8 `
  --case short `
  --warmup 20 `
  --iterations 200 `
  --concurrency 1 `
  --output reports\c3b\onnx-int8-short.json
```

`peak_process_rss_bytes` 是主机进程级峰值；`peak_python_allocated_bytes` 不包含 PyTorch 或
ONNX Runtime 的全部 native tensor 内存。报告必须连同 CPU、Python、依赖、commit、模型和
校准哈希保存，才能用于可重复的工程比较。当前规则后端 smoke 仅证明工具链可用，不代表
ONNX 模型的真实 P50/P95。

## 5. FastAPI 健康与故障策略

```powershell
$env:INTENTFENCE_BACKEND = "onnx"
$env:INTENTFENCE_MODEL_DIR = "artifacts/c3b/onnx-seed42"
$env:INTENTFENCE_CALIBRATION_PATH = "artifacts/c2c/seed42/calibration.json"
intentfence-api
```

`GET /health` 的 `version` 是应用版本；`model_version` 是后端实际绑定的模型 revision（规则
后端为 `rules-v1`），`model_revision` 单独返回完整 revision，另有 calibration 和 policy
版本。`POST /v1/evaluate` 返回相同的模型版本绑定和服务端推理耗时。

检测器异常时 API 返回 `503`，并在响应 detail 中给出已经应用的策略：公开只读使用受限
fail-open（`allow` + `restricted_fail_open`），外部通信和敏感工具 fail-closed（`block` +
`fail_closed_tool`）；高风险动作仍需真实鉴权、最小权限和人工确认。测试只使用 mock/规则
后端，不执行发送、上传、删除、支付或其他真实工具操作。

## 6. Docker 规则后端 smoke

Dockerfile 默认使用透明规则后端，不包含模型、真实数据或结果缓存；`.dockerignore` 会在
构建上下文阶段排除这些目录和常见权重文件。容器以非 root 用户运行，并通过 `/health`
提供 Docker health status。Docker daemon 可用时，可执行一次本地 smoke：

```powershell
.\scripts\run_c3b_docker_smoke.ps1
```

脚本会构建镜像、等待 `/health` 可用、断言规则后端和外部通信阻断策略，并只清理自己创建
的容器；可用 `-HostPort` 和 `-TimeoutSeconds` 调整端口与等待时间。该 smoke 只验证容器、
健康检查、API 响应和规则策略，不产生模型安全或延迟结论；容器不会执行任何真实发送、
上传、删除、支付或权限变更动作。

## 7. 本阶段验证边界

```powershell
conda activate intentfence
python -m ruff check .
python -m pytest -q
python -m compileall -q src baselines benchmarks scripts deployment
python -m build --wheel
```

上述命令验证代码、fixture 和可导入性；Docker smoke 另外需要本机 Docker daemon。项目所有者
提供冻结 checkpoint 并执行真实导出、
FP32/INT8 安全重跑、CPU 测量和可选 Docker smoke 之前，C3b 研究证据仍保持未完成。
