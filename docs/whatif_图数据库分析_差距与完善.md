# 基于图数据库的 What-If 分析：差距与完善点

本文档基于当前代码与 [.cursor/plans/what-if_分析改进建议_6b405185.plan.md](../.cursor/plans/what-if_分析改进建议_6b405185.plan.md) 的结论，梳理**已有能力**、**仍缺功能**与**可完善点**，便于按优先级落地。

---

## 一、当前已具备的能力

| 能力 | 位置 | 说明 |
|------|------|------|
| **计算图模型** | `computation_graph.py`、`computation_node.py`、`computation_relationship.py` | 不可变图、DEPENDS_ON/OUTPUT_TO、InputSpec/OutputSpec、`get_data_node_ids()`、`get_output_properties_by_data_node()` |
| **拓扑执行** | `computation_graph_executor.py` | NetworkX 建图、依赖图、拓扑序执行、writer-before-reader 边 |
| **基线快照与恢复** | `computation_graph_executor.py` | `snapshot_data_nodes()` / `restore_data_nodes()`，What-If 后恢复原值 |
| **单属性 What-If** | `what_if_simulator.py` | `simulate_property_change(node_id, property_name, new_value)`，内部先 snapshot 再 restore |
| **Neo4j 读写** | `neo4j_graph_manager.py` | 按 uuid 加载业务节点、MERGE DataNode、创建 ComputationNode/关系、`write_output_properties` |
| **多节点写回** | `what_if_simulator.py` + demo | `output_targets: Dict[node_id, List[prop]]` 支持多节点多属性写回 |
| **端到端 Demo** | `supply_chain_delay_demo.py`、`simple_computation_chain.py` | 从 Neo4j 加载 → 执行 → 写回 → What-If（交付延迟等） |

当前主路径是：**Neo4j 提供数据 → 内存 `node_data_map` + ComputationGraphExecutor 执行 → 可选写回 Neo4j**；What-If 仅绑在 ComputationGraphExecutor 这条路径上。

---

## 二、仍缺的功能（按优先级）

### 1. 高优先级

#### 1.1 多变量 / 批量 Overrides 与结构化结果

- **现状**：只有单属性修改 `simulate_property_change(node_id, property_name, new_value)`，无法一次表达「改价格 + 改数量」等组合场景。
- **建议**：
  - 增加 `simulate_overrides(node_overrides: Dict[str, Dict[str, Any]], write_back: bool = False) -> ScenarioResult`。
  - `node_overrides` 形如：`{"order_001": {"price": 150, "quantity": 10}, "shipment_001": {"actual_delivery_days": 110}}`。
  - 引入 **ScenarioResult** 结构：至少包含 `overrides`、`outputs_per_node`（各数据节点关键输出）、可选 `affected_node_ids`、`errors`，便于做「基线 vs 场景 A vs 场景 B」对比和前端/报表展示。

#### 1.2 写回策略显式化与安全

- **现状**：传了 `output_node_id` 或 `output_targets` 就会写回 Neo4j，容易把 what-if 结果误当真实数据持久化。
- **建议**：
  - 所有 simulate 接口统一 **默认不写回**：`write_back: bool = False`（或保留 `output_node_id` 但文档明确「仅在确认落库时传」）。
  - 若需持久化 what-if，可写回「场景节点」或单独属性（如 `scenario_xyz_final_price`），而不是覆盖主数据节点同一属性；由配置或调用方决定。

#### 1.3 命名场景与「基线 + 多场景」可对比

- **现状**：`simulate_property_change` 内部已做 snapshot/restore，但无「命名场景」和统一入口，不便于程序化对比多场景。
- **建议**：
  - 提供 `run_scenario(name: str, overrides: Dict, write_back: bool = False) -> ScenarioResult`：在基线上应用 overrides，执行后返回结构化结果且不写回（除非显式开启）；每次调用前从基线恢复，保证可重复、可对比。

### 2. 中优先级

#### 2.1 敏感性分析（单变量扫描）

- **现状**：无「单变量在区间内步进、观察输出变化」的能力。
- **建议**：
  - `sensitivity_scan(node_id, property_name, value_range: Sequence, ...) -> List[ScenarioResult]`，在基线上固定其他输入，仅对该属性在 `value_range` 上取点执行，返回结果列表；可再封装为 `(input_value, output_value)` 供绘图/报表。

#### 2.2 影响分析

- **现状**：`ComputationGraph.get_dependents(node_id)` 基于 **OUTPUT_TO** 的 target，即「该节点输出到哪些节点」；对「数据节点 + 属性」的**上游影响链**（谁读该属性、会波及哪些计算节点与输出）没有现成 API。
- **建议**：
  - 利用 DEPENDS_ON 反查：从「数据节点 + 属性」找到读取该属性的计算节点，再沿 OUTPUT_TO 找下游数据节点与属性。
  - 提供 `get_impact_for_input(data_node_id: str, property_name: str) -> List[ComputationNode]` 或 `Set[output_property_names]`，便于解释与 UI 高亮。

#### 2.3 执行安全（表达式执行）

- **现状**：`computation_graph_executor._execute_node` 使用 `eval(code, {}, variables)`，存在注入与安全风险。
- **建议**：用受限执行替代裸 `eval`（如 AST 白名单仅允许数学/比较表达式，或使用 `simpleeval`/`asteval` 等并限制名字空间）。

#### 2.4 错误处理与部分执行策略

- **现状**：单节点 `eval` 失败时仅 `print` 后 `return None`，后继节点仍执行，可能静默传播错误。
- **建议**：
  - 在结构化结果中增加 `errors: List[NodeError]`、`success: bool`。
  - 支持策略：**fail_fast**（任一步失败即中止）或 **best_effort**（继续执行但标记依赖该节点的下游为不可用）。

### 3. 低优先级

#### 3.1 可观测性与 API 化

- **现状**：Simulator 内大量 `print`，不利于嵌入服务/前端或自动化测试。
- **建议**：`simulate_*` / `run_scenario` 统一返回 **ScenarioResult**；将「打印」改为可选（如 `verbose: bool = False` 或通过 logger），默认不打印。

#### 3.2 与「Neo4j 全流程」路径的语义统一

- **现状**：当前代码中执行逻辑只在 ComputationGraphExecutor（内存 + NetworkX）；`computation_executor.py` 仅含 DataProvider/Neo4jDataProvider，无独立「在 Neo4j 上直接执行」的 ComputationExecutor。What-If 已明确是「从 Neo4j 拉取 → 内存执行 → 可选写回」。
- **建议**：在文档中明确推荐 what-if 路径为上述流程，并说明「写回默认关闭、显式确认再落库」，避免误把假设结果当真实数据。

---

## 三、可完善的具体点（按模块）

### 3.1 WhatIfSimulator（`what_if_simulator.py`）

- 增加 `simulate_overrides(...)` 与 `run_scenario(...)`，返回 **ScenarioResult**。
- 所有写回行为收口到 `write_back` 与可选 `output_node_id`/`output_targets`，且默认不写回。
- 用 `verbose` 或 logger 替代必选的 print，便于 API 化。

### 3.2 ComputationGraphExecutor（`computation_graph_executor.py`）

- 保留并继续使用 `snapshot_data_nodes` / `restore_data_nodes`（已满足「基线恢复」）。
- 将 `eval(code, {}, variables)` 替换为安全表达式执行（见上）。
- 单节点执行失败时写入本次执行的错误列表，并支持 fail_fast / best_effort 策略。

### 3.3 ComputationGraph（`computation_graph.py`）

- 增加「按数据节点+属性」的影响分析：如 `get_impact_for_input(data_node_id, property_name)`，基于 DEPENDS_ON 与 OUTPUT_TO 推导受影响的计算节点与输出属性。

### 3.4 Neo4jGraphManager（`neo4j_graph_manager.py`）

- 写回接口保持现有能力即可；是否写回、写回哪些节点/属性由 Simulator 的 `write_back` 与 `output_targets` 控制。
- 若有「场景节点」写回需求，可后续增加「写回至指定标签/属性」的选项。

### 3.5 新增模块（可选）

- **ScenarioResult**：可在 `what_if_simulator.py` 或 `domain/models` 中定义 dataclass，包含 `overrides`、`outputs_per_node`、`affected_node_ids`、`errors`、`success`。
- **敏感性分析**：`sensitivity_scan` 可放在 `what_if_simulator.py` 或独立 `sensitivity.py`，内部复用 `run_scenario`/`simulate_overrides`。

---

## 四、实施顺序建议（与计划一致）

1. **先做**：基线/快照（已有）+ **多变量 overrides + ScenarioResult** + **写回默认关闭并显式化** → 即可支持多场景并列对比且不误写库。
2. **再做**：敏感性扫描、影响分析 → 提升分析能力与可解释性。
3. **随后**：安全执行、错误策略 → 提升健壮性。
4. **最后**：可观测性（返回结构、verbose/log）、文档明确双路径与推荐用法。

---

## 五、小结

要实现**完整可用的基于图数据库的 what-if 分析**，当前主要差距在：

- **能力层面**：多变量/批量 overrides、命名场景与结构化结果（ScenarioResult）、敏感性分析、影响分析。
- **安全与健壮性**：写回显式可控（默认不写回）、安全表达式执行、错误收集与 fail_fast/best_effort。
- **可集成性**：以结构化结果替代 print、可选 verbose/log，便于 API 与前端使用。

图数据库侧（Neo4j）当前已承担「数据源 + 可选结果落库」的角色；计算与 what-if 逻辑在内存图（ComputationGraphExecutor）中完成，这条分工是合理的。优先补齐「多变量场景 + 结构化结果 + 写回策略」后，再逐步加敏感性、影响分析与安全/错误处理，即可在现有架构下显著提升基于图数据库的 what-if 分析完整度与可用性。
