# Pipelines 层接口说明

## BasePipeline & PipelineManager
- **位置**：`src/pipelines/base_pipeline.py`
- `BasePipeline.process_item(item)`: 抽象方法，处理并返回 item。
- `PipelineManager`: 顺序执行一组 pipeline，`run(item)` 将依次传递结果。

## TransformPipeline
- **位置**：`src/pipelines/transform.py`
- **作用**：为字典类型的 item 附加 `processed_at` UTC 时间戳。
- **扩展**：可在此阶段实现字段清洗、去重、结构校验等逻辑。

## DataSaverPipeline
- **位置**：`src/pipelines/data_saver.py`
- **作用**：将 item 追加写入 JSON Lines 文件（默认文件名 `items_YYYYMMDD.jsonl`）。
- **参数**：构造时需传入输出目录和可选文件名。
- **特点**：对 `set` 自动排序以便序列化，保持顺序 determinisitic。
