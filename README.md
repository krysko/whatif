# WhatIf2 — 基于计算图的 What-If 分析系统

## 一、项目定位

基于 **计算图（Computation Graph）** 的 What-If 分析：在由节点和边组成的图上，修改输入（如价格、数量、交付天数），按依赖顺序重算，得到新的派生结果，并可选择将结果写回 Neo4j。

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 领域模型 (src/domain/models/)                                              │
│   ComputationGraph / ComputationNode / ComputationRelationship          │
│   InputSpec / OutputSpec / ComputationRelationType / ComputationEngine   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 服务层 (src/domain/services/)                                             │
│   ComputationGraphExecutor (内存图 + 拓扑执行)                             │
│   Neo4jGraphManager (Neo4j 读写)  │  WhatIfSimulator (What-If 模拟)       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
              Neo4j (图数据库)              内存 node_data_map
```

- **领域模型**：不可变计算图（节点、边、输入/输出规格）。
- **服务层**：ComputationGraphExecutor 负责内存图构建与拓扑执行，Neo4jGraphManager 负责 Neo4j 读写，WhatIfSimulator 提供 What-If 模拟入口；数据从 Neo4j 加载后在内存中执行，可选写回 Neo4j。
- **数据**：Neo4j 存业务数据与图结构；内存 `node_data_map` 承载节点数据供执行使用。

---

## 三、模块功能

### 3.1 领域模型 (`src/domain/models/`)

| 模块 | 文件 | 功能 |
|------|------|------|
| **ComputationGraph** | `computation_graph.py` | 不可变计算图；`get_data_node_ids()`、`get_output_properties_by_data_node()`、`get_dependencies()`、`get_dependents()`；`add_computation_node` / `add_computation_relationship` 构建图。 |
| **ComputationNode** | `computation_node.py` | 计算节点：`inputs`（InputSpec）、`outputs`（OutputSpec）、`code`（如 `price * quantity`）、`engine`（PYTHON/NEO4J/EXTERNAL）、`priority`。 |
| **ComputationRelationship** | `computation_relationship.py` | 边：`DEPENDS_ON`（数据/上游 → 计算节点）、`OUTPUT_TO`（计算节点 → 数据节点属性）；含 `datasource` / `data_output`。 |
| **InputSpec / OutputSpec** | `io_spec.py` | 输入/输出规格：如 `InputSpec("property", "Order", "price")`、`OutputSpec("property", "Invoice", "subtotal")`。 |
| **ComputationRelationType** | `computation_relation_type.py` | 关系类型：DEPENDS_ON、OUTPUT_TO。 |
| **ComputationEngine / ComputationLevel** | `computation_engine.py`、`computation_level.py` | 计算引擎与层级枚举。 |

### 3.2 服务层 (`src/domain/services/`)

| 模块 | 文件 | 功能 |
|------|------|------|
| **ComputationGraphExecutor** | `computation_graph_executor.py` | 用 NetworkX 建图；依赖图含 DEPENDS_ON + writer-before-reader 边；拓扑序执行；`snapshot_data_nodes()` / `restore_data_nodes()` 做基线快照与恢复；单节点 `eval(code)` 执行，经 OUTPUT_TO 写回后继节点。 |
| **WhatIfSimulator** | `what_if_simulator.py` | What-If 入口：`simulate_property_change(node_id, property_name, new_value, ...)`；内部先 snapshot → 改属性 → 执行 → 可选写回 Neo4j → 最后 restore，保证基线可重复。支持 `output_node_id` 或 `output_targets` 多节点写回。`run_scenario(property_changes, title)`：在隔离环境中执行一次模拟（可多属性修改），不改变 executor 内存，返回 `ScenarioRunResult(baseline, scenario, diff)`，其中 diff 为模拟与基线的属性级差异列表。 |
| **Neo4jGraphManager** | `neo4j_graph_manager.py` | 连接 Neo4j；`create_business_nodes(specs)` 创建业务节点；**`sync_graph_to_neo4j(graph, node_data_map=None)`** 一步完成：同步数据节点、创建计算节点、创建计算关系（便于 Neo4j 可视化）；不传 `node_data_map` 时从 Neo4j 按 uuid 加载，传入时从内存同步；`get_visualization_cypher(graph)`、`print_visualization_instructions(graph)` 生成 Cypher；`write_output_properties(...)` 写回。 |

---

## 四、Demo 流程

### 4.1 主路径：Neo4j → 内存执行 → 可选写回（推荐用于 What-If）

**代表 Demo**：`simple_computation_chain.py`、`supply_chain_delay_demo.py`。

1. **连接 Neo4j**：`Neo4jGraphManager.connect()`。
2. **同步图到 Neo4j（一步）**：`node_data_map = await neo4j_manager.sync_graph_to_neo4j(graph)` — 同步数据节点、计算节点、计算关系到 Neo4j；不传 `node_data_map` 时从 Neo4j 按 uuid 加载数据，传入时从内存同步。运行 `print_visualization_instructions(graph)` 可打印 Cypher，在 Neo4j Browser (http://localhost:7474) 中可视化。
3. **执行计算**：`ComputationGraphExecutor(graph, node_data_map)`，再 `executor.execute()`；按拓扑序执行，结果写入内存中数据节点的属性。
4. **写回 Neo4j（可选）**：对需要写回的节点调用 `write_output_properties(node_uuid, executor.get_node_data(node_uuid), output_properties)`；可从 `graph.get_output_properties_by_data_node()` 得到各节点写回属性列表。
5. **What-If**：`WhatIfSimulator(executor, neo4j_manager).simulate_property_change(node_id, property_name, new_value, output_node_id=... 或 output_targets=...)`；内部会 snapshot → 改值 → 执行 → 可选写回 → restore。若需程序化对比模拟与基线，可用 `run_scenario(property_changes, title)`，返回 `ScenarioRunResult(baseline, scenario, diff)`，不写 Neo4j、不改变 executor 内存。

### 4.2 Simple Computation Chain (`simple_computation_chain.py`)

- **图结构**：Order（price, quantity）→ calc_subtotal → Invoice（subtotal）；Invoice（subtotal, tax_rate）→ calc_tax → Invoice（tax）。
- **流程**：上述 1～6；What-If 示例：改 Order 的 price 或 quantity，观察 Invoice 的 subtotal、tax 变化。
- **预置数据**：可先运行 `simple_computation_seed_neo4j_data.py`（可选 `--clear`）在 Neo4j 中创建 Order、Invoice 业务节点。

### 4.3 Supply Chain Delay (`supply_chain_delay_demo.py`)

- **图结构**：Shipment（planned_delivery_days, actual_delivery_days）→ calc_delay_days → Shipment（delay_days）；Shipment（delay_days）+ ProductionPlan（planned_start_days）→ calc_actual_start_days → ProductionPlan（actual_start_days）；ProductionPlan → calc_production_ready_days → Product（production_ready_days）。
- **流程**：同上 1～6；Step 4 会打印 Neo4j 可视化 Cypher；Step 7 用 `run_scenario` 做 What-If（交付延迟），返回 baseline/scenario/diff。

### 4.4 Supply Chain Rich (`supply_chain_rich_demo.py`)

- **图结构**：在 4.3 基础上扩展 — 有效交付日、延迟天数、实际开工、完工日、延迟影响天数、延迟惩罚；Shipment 侧增加 delay_severity（依赖 delay_days）、delay_notification_flag（依赖 delay_severity）、risk_score；Product 侧增加 risk_level、total_cost。同层多节点时用 `priority` 决定执行顺序。
- **数据**：纯内存 `node_data_map`，不依赖 Neo4j 预置数据；可选将图同步到 Neo4j 并打印可视化 Cypher。
- **流程**：构建图与初始数据 → 基线执行 → 多组 `run_scenario`（交付延迟、缓冲调整、承诺日、多属性）→ 可选连接 Neo4j、`ensure_data_nodes_from_map` + 创建计算节点与关系 + 打印可视化说明。

### 4.5 Multi-Relation (`multi_relation_demo.py`)

- **图结构**：同一 Product 节点通过多条 DEPENDS_ON/OUTPUT_TO 连接多个计算节点：calc_total → total_output；calc_discount → price_after_discount；calc_tax → final_price。
- **流程**：从 Neo4j 读 Product → 用 `ComputationGraphExecutor` 在内存执行；What-If 时修改数据节点属性（如 price、quantity）后重跑，观察 total_output、price_after_discount、final_price 等传导。

### 4.6 种子数据脚本

- **simple_computation_seed_neo4j_data.py**：在 Neo4j 中预创建 Order、Invoice（按 uuid）；支持 `--clear` 先按 uuid 删除再建。
- **supply_chain_seed_neo4j_data.py**：为供应链 Demo 预创建 Shipment、ProductionPlan、Product 等业务节点（若存在类似脚本）。

---

## 五、原理简述

### 5.1 计算图语义

- **数据节点**：业务实体（Order、Invoice、Shipment、Product 等），由 uuid 标识，属性可被计算节点读/写。
- **计算节点**：输入来自 InputSpec（对应 DEPENDS_ON 的 source 与 property），输出由 OutputSpec 指定（对应 OUTPUT_TO 的 target 与 property）；`code` 为 Python 表达式，当前在 executor 中通过 `eval(code, {}, variables)` 执行（变量来自前驱节点属性）。
- **依赖与顺序**：
  - DEPENDS_ON：数据 → 计算节点（谁读谁，谁先算）。
  - OUTPUT_TO：计算节点 → 数据节点（写回属性）。
  - Writer-before-reader：若计算节点 A 写入某 (数据节点, 属性)，计算节点 B 读取同一 (数据节点, 属性)，则依赖图中加入 A → B，保证执行顺序。

### 5.2 拓扑执行

1. 将 ComputationGraph + node_data_map 转成 NetworkX 有向图（数据节点 + 计算节点 + DEPENDS_ON/OUTPUT_TO 边）。
2. 构建依赖图（DEPENDS_ON + 上述 writer-before-reader 边），拓扑排序（同入度按 priority、node_id 排序）。
3. 按序执行计算节点：从所有前驱聚合属性 → `eval(code)` → 沿 OUTPUT_TO 把结果写入后继数据节点的指定属性。

### 5.3 What-If 与基线恢复

- What-If 不污染基线：执行前 `snapshot_data_nodes()` 深拷贝所有数据节点状态；模拟结束后 `restore_data_nodes(snapshot)` 恢复，因此可重复做多场景对比。
- 单次 What-If：改某一数据节点的某一属性 → 重算 → 可选写回 Neo4j；写回由调用方通过 `output_node_id` 或 `output_targets` 显式指定。

### 5.4 Neo4j 的角色

- **数据源**：业务节点（任意 label）按 uuid 存储；加载时按图的 `get_data_node_ids()` 取属性，在内存中形成 `node_data_map`。
- **可选持久化**：可把 ComputationNode、Relationship 写入 Neo4j；计算得到的输出属性可通过 `write_output_properties` 写回对应节点（按 uuid 匹配）。
- 当前 What-If 主路径是：**Neo4j 提供数据 → 内存 node_data_map + ComputationGraphExecutor 执行 → 可选写回 Neo4j**。

---

## 六、运行与依赖

- **Python**：建议 3.10+。
- **Neo4j**：如 `bolt://localhost:7687`，默认账号 `neo4j/123456789`（与 Demo 内常量一致）。
- **依赖**：`neo4j`（async）、`networkx`。
- **启动 Neo4j**（示例）：
  ```bash
  docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/123456789 neo4j
  ```
- **运行示例**（项目根目录，需将 `src` 加入 Python 路径，如 `PYTHONPATH=src`）：
  ```bash
  PYTHONPATH=src python examples/simple_computation_seed_neo4j_data.py   # 可选 --clear
  PYTHONPATH=src python examples/simple_computation_chain.py
  PYTHONPATH=src python examples/supply_chain_delay_demo.py              # 需 Neo4j 已起且有种子数据
  PYTHONPATH=src python examples/supply_chain_rich_demo.py               # 可无 Neo4j，纯内存运行
  PYTHONPATH=src python examples/multi_relation_demo.py
  ```

---

## 七、关键文件索引

| 类型 | 路径 |
|------|------|
| 图模型 | `src/domain/models/computation_graph.py`、`computation_node.py`、`computation_relationship.py`、`io_spec.py` |
| 执行 | `src/domain/services/computation_graph_executor.py` |
| Neo4j 与 What-If | `src/domain/services/neo4j_graph_manager.py`、`what_if_simulator.py` |
| 示例 | `examples/simple_computation_chain.py`、`examples/supply_chain_delay_demo.py`、`examples/supply_chain_rich_demo.py`、`examples/multi_relation_demo.py` |
| 设计/差距说明 | `docs/whatif_图数据库分析_差距与完善.md`、`.cursor/plans/项目运作说明_c434e5bb.plan.md` |

---

## 八、扩展与限制（参考文档）

- **已有**：单属性 What-If（simulate_property_change）、多场景隔离与 diff（run_scenario → ScenarioRunResult）、基线快照/恢复、多节点写回（output_targets）、从图推导写回属性、计算图+数据节点在 Neo4j Browser 中可视化（print_visualization_instructions）、同层节点用 priority 排序。
- **规划中**：多变量/批量 overrides、敏感性分析、按「数据节点+属性」的影响分析、写回默认关闭与安全执行等，见 `docs/whatif_图数据库分析_差距与完善.md`。
