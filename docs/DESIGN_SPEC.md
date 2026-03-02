# What-If 计算图方案设计说明书

> 版本：v2.0 | 日期：2026-03-02

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [总体架构](#2-总体架构)
3. [目录结构](#3-目录结构)
4. [节点与关系连接示意图](#4-节点与关系连接示意图)
5. [领域模型层（Models）](#5-领域模型层models)
   - 5.1 ComputationLevel
   - 5.2 ComputationEngine
   - 5.3 ComputationRelationType
   - 5.4 InputSpec / OutputSpec
   - 5.5 ComputationNode
   - 5.6 ComputationRelationship
   - 5.7 ComputationGraph
6. [领域服务层（Services）](#6-领域服务层services)
   - 6.1 DataProvider（抽象接口）
   - 6.2 Neo4jDataProvider
   - 6.3 ComputationGraphExecutor
   - 6.4 Neo4jGraphManager
   - 6.5 ScenarioRunResult / NodeError
   - 6.6 WhatIfSimulator
7. [辅助工具（Examples/Utils）](#7-辅助工具examplesutils)
8. [类与类关系详图](#8-类与类关系详图)
9. [数据流与调用链](#9-数据流与调用链)
10. [关键设计决策](#10-关键设计决策)
11. [典型 Demo 场景：认证/物料/工序计算图](#11-典型-demo-场景认证物料工序计算图)

---

## 1. 背景与目标

本系统实现了一套「**What-If 计算图仿真框架**」，核心能力包括：

- 以**有向无环图（DAG）**描述业务推导逻辑（如认证周期、物料到货时间、工序完成时间等）。
- 支持从 **Neo4j 图数据库**按 `uuid` 加载业务节点属性，作为计算图的输入数据。
- 在内存中执行计算图（基于 **NetworkX 拓扑排序 + Python eval**），结果写回内存数据节点，并可同步回 Neo4j 用于可视化。
- 支持 **What-If 场景仿真**：在隔离的内存状态上应用属性覆盖值后重跑计算，对比 baseline 与 scenario 的差异，不持久化、不污染执行器状态。

---

## 2. 总体架构

```
┌────────────────────────────────────────────────────────────────────┐
│                       应用层 / Demo 脚本                           │
│  certifies_demo.py  simple_computation_chain.py  supply_chain_...  │
└────────────┬──────────────────────────┬───────────────────────────┘
             │ 构建图                    │ 加载数据 / 同步 / 写回
             ▼                          ▼
┌────────────────────┐      ┌────────────────────────┐
│    领域模型层       │      │      领域服务层          │
│  (Models - 不可变) │◄─────│  Neo4jGraphManager     │
│                    │      │  ComputationGraphExec. │
│  ComputationGraph  │      │  WhatIfSimulator       │
│  ComputationNode   │      └──────────┬─────────────┘
│  ComputationRel.   │                 │
│  InputSpec         │      ┌──────────▼─────────────┐
│  OutputSpec        │      │   DataProvider 层       │
│  枚举类             │      │  Neo4jDataProvider     │
└────────────────────┘      │  (或 MockNeo4jManager) │
                            └──────────┬─────────────┘
                                       │ Bolt 协议
                            ┌──────────▼─────────────┐
                            │     Neo4j 数据库        │
                            │  业务节点 / DataNode /  │
                            │  ComputationNode        │
                            └────────────────────────┘
```

**两层分工**：

| 层 | 职责 | 特性 |
|----|------|------|
| 领域模型层 | 描述计算图结构（图、节点、关系、输入输出规格） | **不可变**（`frozen=True`），无 IO、无执行逻辑 |
| 领域服务层 | 数据加载、图执行、Neo4j 同步、What-If 仿真 | 有状态，依赖 Neo4j 驱动或 mock |

---

## 3. 目录结构

```
whatif2_cursor/
├── src/
│   ├── domain/
│   │   ├── models/
│   │   │   ├── __init__.py                  # 统一导出所有模型类
│   │   │   ├── computation_level.py         # 枚举：计算层级
│   │   │   ├── computation_engine.py        # 枚举：计算引擎
│   │   │   ├── computation_relation_type.py # 枚举：关系类型
│   │   │   ├── io_spec.py                   # InputSpec / OutputSpec
│   │   │   ├── computation_node.py          # ComputationNode
│   │   │   ├── computation_relationship.py  # ComputationRelationship
│   │   │   └── computation_graph.py         # ComputationGraph
│   │   └── services/
│   │       ├── __init__.py                  # 统一导出所有服务类
│   │       ├── computation_executor.py      # DataProvider / Neo4jDataProvider
│   │       ├── computation_graph_executor.py# ComputationGraphExecutor
│   │       ├── neo4j_graph_manager.py       # Neo4jGraphManager
│   │       └── what_if_simulator.py         # WhatIfSimulator / ScenarioRunResult
├── examples/
│   ├── demo_utils.py                        # 公共工具：print_header / MockNeo4jManager
│   ├── simple_computation_chain.py          # 简单链式计算 Demo
│   ├── certifies_demo.py                    # 认证/物料/工序计算 Demo
│   ├── supply_chain_delay_demo.py           # 供应链延误 Demo
│   ├── seed_certifies_neo4j.py              # 认证场景 Neo4j 数据初始化
│   └── supply_chain_seed_neo4j_data.py      # 供应链 Neo4j 数据初始化
└── test/
    ├── conftest.py                          # pytest fixture：共用图/数据/节点
    ├── test_models.py                       # 模型层单元测试
    ├── test_computation_graph_executor.py   # 执行器单元测试
    ├── test_what_if_simulator.py            # What-If 模拟器单元测试
    └── test_neo4j_data_provider.py          # DataProvider 测试
```

---

## 4. 节点与关系连接示意图

下图以「订单计税」为例，展示**数据节点（DataNode）**、**计算节点（ComputationNode）**及两类连接关系（`DEPENDS_ON` / `OUTPUT_TO`）的完整结构：

![计算图节点与关系连接示意图](assets/computation_graph_node_diagram.png)

**图中要素说明：**

| 要素 | 图形 | 说明 |
|------|------|------|
| **DataNode（数据节点）** | 蓝色圆角矩形 | 业务属性的载体（如 `order_001`、`invoice_001`），属性值来自 Neo4j 或内存 `node_data_map`；输出属性由计算节点写入 |
| **ComputationNode（计算节点）** | 橙色圆角矩形 | 包含 `code` 表达式（Python），执行时从上游变量字典取值并 `eval` 求值 |
| **DEPENDS_ON（蓝色虚线箭头）** | DataNode → ComputationNode | 表示「读」：将数据节点的指定属性（`property_name`）注入为计算节点 `eval` 的变量 |
| **OUTPUT_TO（绿色实线箭头）** | ComputationNode → DataNode | 表示「写」：将计算结果写入目标数据节点的指定属性（`property_name`） |

**执行顺序保证**：`ComputationGraphExecutor` 对依赖子图做拓扑排序，除显式 `DEPENDS_ON` 边外，还会自动识别「写者→读者」隐式依赖（A 写 `subtotal` → B 读 `subtotal`），确保 `calc_subtotal` 始终先于 `calc_tax` 执行。

---

## 5. 领域模型层（Models）

所有模型类使用 `@dataclass(frozen=True, slots=True)` 声明，**不可变**且支持哈希，不依赖任何服务或 IO。

---

### 5.1 ComputationLevel（计算层级）

**文件**：`computation_level.py`

```python
class ComputationLevel(Enum):
    PROPERTY = "property"  # 属性级：计算单个属性值（当前主要使用）
    NODE = "node"          # 节点级：计算整个节点（预留）
    GRAPH = "graph"        # 图级：全图计算（预留）
```

**作用**：标注一个 `ComputationNode` 的计算粒度，当前所有实际场景均使用 `PROPERTY` 级别，`NODE`/`GRAPH` 为扩展预留。

**被引用**：`ComputationNode.level`。

---

### 5.2 ComputationEngine（计算引擎）

**文件**：`computation_engine.py`

```python
class ComputationEngine(Enum):
    NEO4J = "neo4j"        # 预留：由 Neo4j 本身执行（如 Cypher）
    PYTHON = "python"      # 当前实现：由 Python eval() 执行
    EXTERNAL = "external"  # 预留：外部服务调用
```

**作用**：标注 `ComputationNode.code` 由哪个引擎执行。`ComputationGraphExecutor` 当前仅支持 `PYTHON` 引擎（使用 `eval(code, {"datetime": ..., "timedelta": ...}, variables)`）。

**被引用**：`ComputationNode.engine`；`ComputationGraphExecutor._execute_node` 中读取。

---

### 5.3 ComputationRelationType（计算关系类型）

**文件**：`computation_relation_type.py`

```python
class ComputationRelationType(Enum):
    DEPENDS_ON = "depends_on"  # 数据/计算节点 → 计算节点（读数据）
    OUTPUT_TO = "output_to"    # 计算节点 → 数据/计算节点（写结果）
```

**作用**：区分图中边的语义——`DEPENDS_ON` 表示「某节点的属性是计算的输入」，`OUTPUT_TO` 表示「计算的结果写往某节点的某属性」。

**被引用**：
- `ComputationRelationship.relation_type`
- `ComputationGraphExecutor._build_networkx_graph`：决定边方向与语义
- `ComputationGraphExecutor._get_dependency_graph`：仅保留 DEPENDS_ON 边做拓扑排序，并通过「写者→读者」关系添加隐式依赖
- `Neo4jGraphManager.create_relationships`：决定 source/target 是按 uuid 还是 elementId 匹配

---

### 5.4 InputSpec / OutputSpec（输入/输出规格）

**文件**：`io_spec.py`

#### InputSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_type` | `str` | 来源类型，如 `"property"` |
| `entity_type` | `str` | 实体类型，如 `"Order"`、`"MPart"` |
| `property_name` | `str \| None` | 具体属性名，如 `"price"` |
| `graph_name` | `str \| None` | 图名（预留，当前未使用） |
| `node_id` | `str \| None` | 指定节点引用（预留） |

#### OutputSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_type` | `str` | 目标类型，如 `"property"` |
| `entity_type` | `str` | 实体类型，如 `"Invoice"` |
| `property_name` | `str \| None` | 具体属性名，如 `"subtotal"` |
| `graph_name` | `str \| None` | 图名（预留） |

**作用**：
- `InputSpec` 描述「计算从哪读」，与 `ComputationRelationship.datasource` 绑定，执行器根据 `property_name` 从对应数据节点取值，注入到 `eval` 变量字典（变量名 = `property_name`）。
- `OutputSpec` 描述「计算往哪写」，与 `ComputationRelationship.data_output` 绑定；`ComputationGraph.get_output_properties_by_data_node` 遍历 OUTPUT_TO 关系的 `data_output.property_name` 得到每个数据节点要写回 Neo4j 的属性列表。

**被引用**：`ComputationNode.inputs`/`outputs`、`ComputationRelationship.datasource`/`data_output`。

---

### 5.5 ComputationNode（计算节点）

**文件**：`computation_node.py`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 唯一标识，如 `"calc_certification_completion_time"` |
| `name` | `str` | 描述性名称，如 `"certification_completion_time"` |
| `level` | `ComputationLevel` | 计算粒度 |
| `inputs` | `tuple[InputSpec, ...]` | 输入规格列表（声明式，非执行时路由） |
| `outputs` | `tuple[OutputSpec, ...]` | 输出规格列表（声明式） |
| `code` | `str` | 可被 `eval` 执行的 Python 表达式，变量名对应 `InputSpec.property_name` |
| `engine` | `ComputationEngine` | 执行引擎 |
| `properties` | `Mapping[str, Any]` | 附加元数据（可选） |
| `priority` | `int` | 同入度节点执行顺序（数值越小越先执行，默认 0） |

**关键方法**：
- `with_properties(**new_properties)` → 返回**新** `ComputationNode`（不可变语义，合并 properties 后返回副本）。
- `get_property(key, default=None)` → 安全读取 properties 中的值。

**`code` 字段说明**：`code` 是一个 Python 表达式字符串，执行时由 `ComputationGraphExecutor._execute_node` 调用 `eval(code, {"datetime": datetime, "timedelta": timedelta}, variables)` 求值，其中 `variables` 字典的 key 为 `datasource.property_name`，value 为从上游数据节点取到的当前值。

**示例（认证完成时间计算）**：
```python
ComputationNode(
    id="calc_certification_completion_time",
    code="(datetime.fromisoformat(reqCertificationStartTime.replace('Z','+00:00')) "
         "+ timedelta(days=supplierCertificationCycleLt)).isoformat() "
         "if (status or '').strip() != '已认证' "
         "else datetime.fromisoformat(reqCertificationStartTime.replace('Z','+00:00')).isoformat()",
    ...
)
```

**被引用**：`ComputationGraph.computation_nodes`（dict，key 为 `id`）；`ComputationGraphExecutor._build_networkx_graph` 将其转为 NetworkX 节点；`Neo4jGraphManager.create_computation_nodes` 将其写入 Neo4j `ComputationNode` 标签节点。

---

### 5.6 ComputationRelationship（计算关系）

**文件**：`computation_relationship.py`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 唯一标识，如 `"rel_cert_start_to_calc"` |
| `source_id` | `str` | 源节点 ID（数据节点 ID 或计算节点 ID） |
| `target_id` | `str` | 目标节点 ID（数据节点 ID 或计算节点 ID） |
| `name` | `str` | 关系描述名 |
| `relation_type` | `ComputationRelationType` | DEPENDS_ON 或 OUTPUT_TO |
| `level` | `str` | 层级说明（如 `"property"`） |
| `datasource` | `OutputSpec \| None` | DEPENDS_ON 时指定读取的属性（复用 OutputSpec 结构） |
| `data_output` | `OutputSpec \| None` | OUTPUT_TO 时指定写回的属性 |
| `properties` | `Mapping[str, Any]` | 附加元数据（可选） |

**关键约定**：
- `DEPENDS_ON` 关系：`source_id` 为数据节点（或中间计算节点）ID，`target_id` 为计算节点 ID，`datasource` 指明从 source 读取哪个属性并以 `property_name` 作为变量名注入执行上下文。
- `OUTPUT_TO` 关系：`source_id` 为计算节点 ID，`target_id` 为数据节点（或计算节点）ID，`data_output` 指明将计算结果写入 target 的哪个属性。

**关键方法**：
- `with_properties(**new_properties)` → 返回新 `ComputationRelationship`（不可变语义）。
- `get_property(key, default=None)` → 安全读取。

**被引用**：`ComputationGraph.computation_relationships`（dict，key 为 `id`）；执行器依此路由变量与写回；`Neo4jGraphManager.create_relationships` 依此在 Neo4j 创建关系并设置 `datasource`/`data_output` 等属性。

---

### 5.7 ComputationGraph（计算图）

**文件**：`computation_graph.py`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 图唯一标识，如 `"certifies"` |
| `computation_nodes` | `Mapping[str, ComputationNode]` | 所有计算节点字典（key = node.id） |
| `computation_relationships` | `Mapping[str, ComputationRelationship]` | 所有关系字典（key = rel.id） |
| `outgoing` | `Mapping[str, Tuple[str, ...]]` | node_id → 出边 rel_id 列表 |
| `incoming` | `Mapping[str, Tuple[str, ...]]` | node_id → 入边 rel_id 列表 |
| `base_graph_id` | `str \| None` | 关联业务数据图 ID（预留） |

**关键方法**：

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_computation_node(node_id)` | `ComputationNode \| None` | 按 ID 查计算节点 |
| `get_computation_relationship(rel_id)` | `ComputationRelationship \| None` | 按 ID 查关系 |
| `get_outgoing_relationships(node_id)` | `Tuple[ComputationRelationship, ...]` | 某节点出边列表 |
| `get_incoming_relationships(node_id)` | `Tuple[ComputationRelationship, ...]` | 某节点入边列表 |
| `get_dependencies(node_id)` | `Tuple[ComputationNode, ...]` | 该计算节点依赖的其他**计算节点**（通过 DEPENDS_ON） |
| `get_dependents(node_id)` | `Tuple[ComputationNode, ...]` | 依赖该节点的**计算节点**（通过 OUTPUT_TO） |
| `get_data_node_ids()` | `Set[str]` | 从关系中收集所有**数据节点** ID（DEPENDS_ON 的 source、OUTPUT_TO 的 target，排除计算节点 ID） |
| `get_output_properties_by_data_node()` | `Dict[str, List[str]]` | 从 OUTPUT_TO 推导每个数据节点要写回 Neo4j 的属性名列表 |
| `add_computation_node(node)` | `ComputationGraph` | 返回**新图**（不可变，链式构建） |
| `add_computation_relationship(rel)` | `ComputationGraph` | 返回**新图**，并更新 outgoing/incoming 索引 |

**不可变设计**：图构建使用链式 `add_*` 方法，每次返回新实例，原图不被修改，便于多版本图共存（如 baseline 图 vs. 修改后的图）。

**数据节点的隐式性**：数据节点（`DataNode`）不在 `ComputationGraph` 中显式存储，仅通过关系的 `source_id`/`target_id` 引用。其实际属性存在于 `node_data_map`（内存 dict）和 Neo4j 的 `DataNode` 标签节点中。

---

## 6. 领域服务层（Services）

---

### 6.1 DataProvider（抽象数据提供者接口）

**文件**：`computation_executor.py`

```python
class DataProvider(ABC):
    async def get_node_data(node_id: str) -> Optional[Dict[str, Any]]: ...
    async def set_node_properties(node_id: str, properties, ...) -> bool: ...
    async def create_node(node_type: str, properties, ...) -> Optional[str]: ...
    async def close() -> None: ...
```

**作用**：抽象的数据访问接口，定义从存储层「读节点数据、写节点属性、创建节点、关闭连接」等操作，**便于测试时换成 Mock，便于未来切换存储后端**。

**被引用**：`Neo4jDataProvider` 实现该接口；`Neo4jGraphManager` 通过 `self.data_provider` 持有并调用。

---

### 6.2 Neo4jDataProvider（Neo4j 数据提供者）

**文件**：`computation_executor.py`

**继承关系**：`Neo4jDataProvider` → 实现 `DataProvider`

**初始化参数**：

| 参数 | 说明 |
|------|------|
| `uri` | Neo4j Bolt URI，如 `"bolt://localhost:7687"` |
| `user` | 用户名 |
| `password` | 密码 |
| `mock_data` | 若提供此 dict 则以 mock 模式运行（不连接真实 Neo4j） |

**核心方法**：

| 方法 | 说明 |
|------|------|
| `get_node_data(node_id)` | 按 elementId 读节点（mock 模式：按 key 查 mock_data） |
| `get_data_node_by_uuid(uuid)` | 按 uuid 从业务节点（非 DataNode）查属性；优先查节点，找不到则查关系（`()-[r]->()` 场景，如 `Certifies` 关系有 uuid） |
| `set_node_properties(node_id, props, *, match_by_uuid)` | 写属性；`match_by_uuid=True` 时用 `MATCH (n:DataNode {uuid: $uuid})`，否则按 elementId |
| `create_node(node_type, properties)` | 创建节点，返回 elementId；属性值自动做类型安全 Cypher 转义 |
| `merge_data_node(uuid, properties)` | MERGE `DataNode` 节点（按 uuid），设置属性；用于将业务节点属性物化为 DataNode |
| `create_relationship(source_id, target_id, rel_type, props, *, source_match_by_uuid, target_match_by_uuid)` | 按 elementId 或 uuid 匹配源/目标，创建关系 |
| `close()` | 关闭 Neo4j driver |

**Mock 模式**：当 `mock_data` 非空时，所有方法操作内存字典，不发起任何网络请求，便于单元测试和无 Neo4j 环境运行。

**关于 `get_data_node_by_uuid` 的特殊处理**：某些业务对象（如 `Certifies`、`Requires`）在 Neo4j 中是**关系（relationship）**而非节点，因此该方法先查节点，查不到再查关系，统一用 uuid 识别。

**被引用**：`Neo4jGraphManager.connect()` 实例化并持有；`Neo4jGraphManager` 所有数据 IO 操作均通过 `self.data_provider` 转发。

---

### 6.3 ComputationGraphExecutor（计算图执行器）

**文件**：`computation_graph_executor.py`

**初始化**：
```python
executor = ComputationGraphExecutor(graph: ComputationGraph, node_data_map: Dict[str, Dict])
```

初始化时调用 `_build_networkx_graph()` 将计算图和数据节点转为 NetworkX `DiGraph`，存入 `self.G`。

#### 内部 NetworkX 图结构

每个节点（计算节点 + 数据节点）均作为 `self.G` 的节点：

| 节点属性 | 计算节点 | 数据节点 |
|---------|---------|---------|
| `is_computation` | `True` | `False` |
| `name` | 节点 name | — |
| `code` | 表达式字符串 | — |
| `engine` | `"python"` | — |
| `priority` | priority 值 | `0` |
| 业务属性 | — | 来自 node_data_map（如 `price`, `quantity`） |

每条关系作为 `self.G` 的有向边，携带 `relation_type`（`"DEPENDS_ON"` / `"OUTPUT_TO"`）和 `property_name`。

#### 核心方法

**`_get_dependency_graph()`**：
提取用于拓扑排序的依赖子图，包含两类边：
1. `DEPENDS_ON` 边（数据节点 → 计算节点）：表示计算节点依赖数据节点，需先有数据才能计算。
2. **写者→读者隐式依赖**：若计算节点 A 通过 OUTPUT_TO 向数据节点 D 写属性 `prop`，而计算节点 B 通过 DEPENDS_ON 从数据节点 D 读同一属性 `prop`，则自动添加 A → B 的依赖边，确保 A 先于 B 执行。

**`_get_execution_order()`**：
在依赖子图上调用 NetworkX 字典序拓扑排序（`lexicographical_topological_sort`），key 为 `(priority, node_id)`，同层节点按 priority 升序再按 id 字典序稳定排序。存在环时返回 `None`。

**`_execute_node(node_id, verbose)`**：
1. 遍历所有 `DEPENDS_ON` 关系，找出 `target_id == node_id` 的关系，从 `self.G.nodes[source_id]` 取 `datasource.property_name` 对应的值，构建 `variables` 字典（变量名 = property_name，缺失时为 `None`）。
2. 执行 `eval(code, {"datetime": datetime, "timedelta": timedelta}, variables)`。
3. 遍历 `OUTPUT_TO` 后继边，将结果写入 `self.G.nodes[target_id][property_name]`。

**`execute(verbose)`**：
按 `_get_execution_order()` 遍历，对每个计算节点调用 `_execute_node`。成功返回 `True`，有环返回 `False`。

**快照/恢复机制**（供 What-If 使用）：

| 方法 | 说明 |
|------|------|
| `snapshot_data_nodes()` | 深拷贝所有数据节点当前状态，返回 `Dict[str, Dict]` |
| `restore_data_nodes(snapshot)` | 将数据节点状态还原到 snapshot 时刻（调用 `.clear()` + `.update()`） |
| `update_node_property(node_id, property_name, value)` | 修改单个数据节点属性（用于注入 What-If 覆盖值） |

**查询方法**：

| 方法 | 说明 |
|------|------|
| `get_node_data(node_id)` | 返回单节点当前所有属性的副本 |
| `get_all_data_nodes()` | 返回所有**数据节点**的属性字典（过滤掉计算节点） |
| `print_node_data(title)` | 以 INFO 日志输出当前所有数据节点属性 |

**被引用**：`WhatIfSimulator` 持有并调用（执行、快照、恢复、更新属性）；应用层（Demo）直接创建并调用 `execute()`。

---

### 6.4 Neo4jGraphManager（Neo4j 图管理器）

**文件**：`neo4j_graph_manager.py`

**初始化**：
```python
manager = Neo4jGraphManager(uri: str, user: str, password: str)
await manager.connect()   # 实例化 Neo4jDataProvider
await manager.disconnect() # 关闭连接
```

**职责分类**：

#### A. 业务节点创建（供 seed 脚本使用）

**`create_business_nodes(specs: Dict[str, Dict])`**：
- 输入：`uuid → {"label": "Order", "field": value, ...}` 规格字典
- 操作：调用 `data_provider.create_node(label, props)`（自动注入 uuid）
- 输出：`uuid → neo4j elementId` 映射

#### B. 从 Neo4j 加载数据节点（得到 node_data_map）

**`load_data_nodes_from_neo4j(uuids)`**：
- 按 uuid 列表逐一调用 `data_provider.get_data_node_by_uuid(uuid)` 读取属性
- 对每个找到的业务节点，调用 `data_provider.merge_data_node(uuid, props)` 将属性物化为 `DataNode` 节点
- 返回 `{uuid: props_dict}` 作为 `node_data_map`

**`load_data_nodes_from_neo4j_by_mapping(data_node_id_to_neo4j_uuid)`**：
- 输入：`{计算图数据节点ID → Neo4j uuid}` 映射（如 `{"MPart_DataNode_001": "MPart_uuid_001"}`）
- 按映射关系读 Neo4j，结果以**计算图数据节点 ID** 为 key 返回（而非 uuid），使得 `node_data_map` 的 key 与计算图中关系引用的 `source_id`/`target_id` 一致
- 这是对 `load_data_nodes_from_neo4j` 的扩展，支持「计算图节点 ID 与 Neo4j uuid 不同」的场景

**`load_graph_data_from_neo4j(graph, *, extra_data_node_ids, data_node_id_to_neo4j_uuid)`**：
- 统一入口：从 `graph.get_data_node_ids()` 收集所有数据节点 ID，合并 `extra_data_node_ids`
- 若提供 `data_node_id_to_neo4j_uuid`，则走 by_mapping 路径；否则直接用 data_node_id 作为 uuid 查询
- 若有缺失的数据节点（Neo4j 中找不到），抛出 `ValueError`
- 返回 `node_data_map` 供 `ComputationGraphExecutor` 使用

#### C. 同步计算图到 Neo4j（可视化）

**`sync_graph_to_neo4j(graph, node_data_map=None)`**：
完整同步三步：
1. 若 `node_data_map` 为 `None`：调用 `load_graph_data_from_neo4j(graph)` 加载；否则调用 `ensure_data_nodes_from_map` 将内存数据写入 Neo4j `DataNode`。
2. 调用 `create_computation_nodes(graph)`：将计算节点写入 Neo4j `ComputationNode` 标签节点（携带 id、name、code、engine、graph_id 等属性），维护 `self.comp_node_id_map`（逻辑 ID → neo4j elementId）。
3. 调用 `create_relationships(graph)`：将所有计算关系写入 Neo4j（DEPENDS_ON / OUTPUT_TO），DataNode 端按 uuid 匹配，ComputationNode 端按 elementId 匹配。

**`clear_graph_from_neo4j(graph)`**：
删除该图对应的所有 `DataNode`（按 uuid）和 `ComputationNode`（按 `graph_id`）及其关系，便于幂等重建。

**`ensure_data_nodes_from_map(node_data_map, graph_id)`**：
将内存中的 `node_data_map` 同步为 Neo4j `DataNode`（MERGE by uuid，可选设置 `graph_id`）。

#### D. 写回计算结果

**`write_output_properties(node_uuid, node_data, output_properties)`**：
将执行器计算后数据节点中的指定属性写回 Neo4j（按 DataNode uuid 匹配，调用 `set_node_properties(uuid, props, match_by_uuid=True)`）。

#### E. 可视化辅助

**`get_visualization_cypher(graph)`**：
生成可直接粘贴到 Neo4j Browser 的 Cypher 查询，展示完整计算图（DataNode + ComputationNode + 关系）。

**`print_visualization_instructions(graph)`**：
在日志中输出参数内联的 Cypher 查询，便于手动复制执行。

**`print_graph_structure()`**：
查询 Neo4j 并在日志中输出 DataNode、ComputationNode、关系列表（调试用）。

---

### 6.5 ScenarioRunResult / NodeError（What-If 结果结构）

**文件**：`what_if_simulator.py`

#### NodeError

```python
@dataclass
class NodeError:
    node_id: str               # 出错的计算节点 ID
    message: str               # 错误描述
    exception: Optional[Exception] = None
```

**作用**：结构化记录单个计算节点执行失败信息，存入 `ScenarioRunResult.errors`。

#### ScenarioRunResult

```python
@dataclass
class ScenarioRunResult:
    baseline: Dict[str, Dict[str, Any]]   # 变更前所有数据节点属性快照
    scenario: Dict[str, Dict[str, Any]]   # 变更后执行结果
    diff: List[Dict[str, Any]]            # 变化属性列表（见下）
    overrides: Dict[str, Dict[str, Any]]  # 本次应用的覆盖值（node_id → {prop: value}）
    outputs_per_node: Dict[str, Dict[str, Any]]  # 关键输出属性（来自 OUTPUT_TO 关系）
    affected_node_ids: List[str]          # 有属性变化的数据节点 ID 列表
    errors: List[NodeError]               # 执行失败的节点错误列表
    success: bool                         # 是否全部成功
```

**`diff` 条目结构**：
```python
{
    "node_id": "MPart_DataNode_001",
    "property_name": "material_arrival_time",
    "baseline_value": "2025-03-01T00:00:00+00:00",
    "scenario_value": "2025-03-11T00:00:00+00:00",
}
```

**辅助函数 `format_scenario_result(result, label, *, max_diff_items, log_fn)`**：
格式化输出 `ScenarioRunResult`，依次打印：overrides（输入覆盖）、affected_node_ids（受影响节点）、outputs_per_node（关键输出）、diff 列表（属性变化，截断至 `max_diff_items`）、success/errors 状态。

---

### 6.6 WhatIfSimulator（What-If 模拟器）

**文件**：`what_if_simulator.py`

**初始化**：
```python
simulator = WhatIfSimulator(
    executor: ComputationGraphExecutor,
    neo4j_manager: Neo4jGraphManager,  # 当前 run_scenario 内不写回 Neo4j，预留扩展
)
```

**核心方法 `run_scenario(property_changes, title, *, verbose)`**：

完整执行流程：

```
1. snapshot = executor.snapshot_data_nodes()          # 深拷贝当前状态
2. baseline = executor.get_all_data_nodes()           # 记录基线
3. for (node_id, prop, val) in property_changes:
       executor.update_node_property(node_id, prop, val)  # 注入覆盖值
4. executor.execute(verbose=verbose)                  # 重跑计算图
5. scenario = executor.get_all_data_nodes()           # 读取场景结果
6. diff = _compute_diff(baseline, scenario)           # 对比差异
7. overrides = _property_changes_to_overrides(...)    # 结构化覆盖值
8. affected_node_ids = sorted({d["node_id"] for d in diff})
9. outputs_per_node = _build_outputs_per_node(executor.graph, scenario)
10. result = ScenarioRunResult(...)
11. executor.restore_data_nodes(snapshot)             # 恢复原始状态（finally 块）
12. return result
```

**关键特性**：
- **隔离性**：通过 snapshot/restore 机制，`run_scenario` 执行完成后执行器恢复到调用前状态，不干扰 baseline 状态。
- **多场景串行**：可对同一 executor 多次调用 `run_scenario`（不同 property_changes），每次独立隔离。
- **`outputs_per_node` 构建**：调用 `executor.graph.get_output_properties_by_data_node()` 得到「数据节点 → 输出属性名列表」，再从 scenario 状态取值，只暴露「被计算图定义为输出」的属性。

**内部辅助函数**：

| 函数 | 说明 |
|------|------|
| `_compute_diff(baseline, scenario)` | 全量对比两个状态字典，返回所有变化属性列表 |
| `_property_changes_to_overrides(changes)` | 将 `[(node_id, prop, val), ...]` 转为 `{node_id: {prop: val}}` |
| `_build_outputs_per_node(graph, scenario)` | 从图的 OUTPUT_TO 关系推导关键输出，从 scenario 取值 |

---

## 7. 辅助工具（Examples/Utils）

### MockNeo4jManager

**文件**：`examples/demo_utils.py`

```python
class MockNeo4jManager:
    """占位用 Neo4j 管理器：不连接 Neo4j，不执行任何持久化。"""
```

**作用**：在 `WhatIfSimulator(executor, neo4j_manager=MockNeo4jManager())` 中作为占位对象，使得 What-If 仿真可以在无 Neo4j 连接的纯内存环境下运行。

### clear_nodes_by_uuids

```python
async def clear_nodes_by_uuids(manager: Neo4jGraphManager, uuids: List[str])
```

**作用**：按 uuid 列表批量 `DETACH DELETE` Neo4j 节点（任意标签），供 seed 脚本 `--clear` 模式使用，保证幂等重建。

### print_header

```python
def print_header(title: str, width: int = 60)
```

**作用**：在日志中输出等宽分隔线 + 标题，统一 Demo 脚本控制台输出格式。

---

## 8. 类与类关系详图

```
【枚举层（无依赖）】
  ComputationLevel
  ComputationEngine
  ComputationRelationType

【规格层（仅引用枚举）】
  InputSpec    ─── source_type, entity_type, property_name 等
  OutputSpec   ─── target_type, entity_type, property_name 等

【模型层（引用枚举 + 规格）】
  ComputationNode
    .level      : ComputationLevel
    .engine     : ComputationEngine
    .inputs     : tuple[InputSpec, ...]
    .outputs    : tuple[OutputSpec, ...]

  ComputationRelationship
    .relation_type : ComputationRelationType
    .datasource    : OutputSpec | None   ← DEPENDS_ON 时的读规格
    .data_output   : OutputSpec | None   ← OUTPUT_TO 时的写规格

  ComputationGraph
    .computation_nodes         : {id → ComputationNode}
    .computation_relationships : {id → ComputationRelationship}
    .outgoing / .incoming      : 边索引（{node_id → (rel_id, ...)})

【数据访问层（无图模型依赖）】
  DataProvider (ABC)
    └── Neo4jDataProvider (实现)
          .mock_data      : Dict （mock 模式）
          ._driver        : neo4j.AsyncGraphDatabase

【服务层（依赖图模型 + 数据访问层）】
  ComputationGraphExecutor
    .graph          : ComputationGraph      ← 图结构
    .node_data_map  : Dict[str, Dict]       ← 初始数据节点数据
    .G              : nx.DiGraph            ← 内部 NetworkX 图

  Neo4jGraphManager
    .data_provider  : Neo4jDataProvider    ← 数据 IO
    .comp_node_id_map : Dict[str, str]     ← 逻辑ID → Neo4j elementId

  WhatIfSimulator
    .executor       : ComputationGraphExecutor  ← 执行与快照
    .neo4j_manager  : Neo4jGraphManager         ← 预留写回

【结果结构（被 WhatIfSimulator 构造）】
  ScenarioRunResult
    .baseline / .scenario / .diff
    .overrides / .outputs_per_node
    .affected_node_ids / .errors / .success
  NodeError
    .node_id / .message / .exception

【辅助工具】
  MockNeo4jManager  ─ 实现 Neo4jGraphManager 的占位接口
  format_scenario_result ─ 格式化输出 ScenarioRunResult
```

**关键依赖方向**（箭头表示「依赖/使用」）：

```
ComputationGraph ──► ComputationNode
ComputationGraph ──► ComputationRelationship
ComputationNode ──► ComputationLevel, ComputationEngine, InputSpec, OutputSpec
ComputationRelationship ──► ComputationRelationType, OutputSpec

ComputationGraphExecutor ──► ComputationGraph, ComputationRelationType
Neo4jGraphManager ──► Neo4jDataProvider, ComputationGraph, ComputationRelationType
WhatIfSimulator ──► ComputationGraphExecutor, Neo4jGraphManager
WhatIfSimulator ──► ScenarioRunResult, NodeError
```

---

## 9. 数据流与调用链

### 9.1 完整执行流程

```
① 构建计算图（纯代码，无 IO）
   InputSpec / OutputSpec / ComputationNode / ComputationRelationship
   → ComputationGraph.add_computation_node / add_computation_relationship
   → ComputationGraph（不可变 DAG）

② 连接并加载数据
   Neo4jGraphManager.connect()
     → Neo4jDataProvider(uri, user, password)
   Neo4jGraphManager.load_graph_data_from_neo4j(graph, data_node_id_to_neo4j_uuid=...)
     → graph.get_data_node_ids()           # 从关系中收集数据节点 ID
     → data_provider.get_data_node_by_uuid(uuid)  # 按 uuid 读业务节点属性
     → data_provider.merge_data_node(uuid, props) # 物化为 DataNode（可选）
     → node_data_map: Dict[str, Dict]      # key=数据节点ID，value=属性字典

③ 执行计算
   ComputationGraphExecutor(graph, node_data_map)
     → _build_networkx_graph()    # 数据节点 + 计算节点 + 边
   executor.execute(verbose=True)
     → _get_execution_order()     # 依赖图拓扑排序（含写者→读者隐式依赖）
     → _execute_node(node_id)     # eval(code, {datetime,timedelta}, variables)
     → 结果写入 self.G.nodes[target_id][prop]

④ 同步到 Neo4j（可视化）
   Neo4jGraphManager.sync_graph_to_neo4j(graph, node_data_map=executor.get_all_data_nodes())
     → ensure_data_nodes_from_map → data_provider.merge_data_node(...)
     → create_computation_nodes  → data_provider.create_node("ComputationNode", ...)
     → create_relationships      → data_provider.create_relationship(...)
   (可选) neo4j_manager.write_output_properties(uuid, node_data, output_props)

⑤ What-If 仿真
   WhatIfSimulator(executor, neo4j_manager)
   simulator.run_scenario([(node_id, prop, new_val), ...], title="...")
     → executor.snapshot_data_nodes()
     → executor.update_node_property(node_id, prop, val)
     → executor.execute()
     → executor.get_all_data_nodes() → scenario
     → _compute_diff(baseline, scenario) → diff
     → executor.restore_data_nodes(snapshot)
     → ScenarioRunResult(baseline, scenario, diff, overrides, outputs_per_node, ...)

⑥ 清理（幂等运行）
   neo4j_manager.clear_graph_from_neo4j(graph)
     → DETACH DELETE DataNode (by uuid)
     → DETACH DELETE ComputationNode (by graph_id)
   neo4j_manager.disconnect()
```

### 9.2 节点属性在各阶段的位置

| 阶段 | 数据位置 | 读写方式 |
|------|---------|---------|
| 加载后 | `node_data_map[node_id][prop]` | Python dict |
| 执行中 | `executor.G.nodes[node_id][prop]` | NetworkX 节点属性 |
| 快照 | `snapshot[node_id][prop]` | 深拷贝 dict |
| Neo4j 可视化 | `(:DataNode {uuid: node_id}).prop` | Cypher MERGE/SET |
| 写回结果 | `(:DataNode {uuid: node_id}).output_prop` | Cypher MATCH SET |

---

## 10. 关键设计决策

### 10.1 模型不可变（`frozen=True`）

所有 `ComputationNode`、`ComputationRelationship`、`ComputationGraph` 均为不可变 dataclass。好处：
- 可安全共享（多个执行器可引用同一图实例）
- 链式构建图时历史版本不被破坏
- 哈希安全，可作为字典 key

### 10.2 数据节点隐式性

`ComputationGraph` 不显式存储数据节点结构，只通过关系引用其 ID。好处：
- 图结构描述与数据分离，图定义可复用于不同数据集
- 数据节点属性完全由 `node_data_map`（运行时）或 Neo4j（持久化时）管理

### 10.3 拓扑排序中的写者→读者隐式依赖

仅有 DEPENDS_ON 边不足以保证正确顺序——当计算节点 A 写的中间结果被计算节点 B 读取时，NetworkX 图中若 A、B 都连接同一数据节点，而节点间没有直接边，拓扑排序无法感知此依赖。因此 `_get_dependency_graph` 中显式遍历关系列表，添加「OUTPUT_TO + DEPENDS_ON 同数据节点同属性」的隐式 A → B 边。

### 10.4 What-If 的隔离机制

`run_scenario` 使用 `snapshot_data_nodes`（深拷贝）→ 修改 → 执行 → 收集结果 → `restore_data_nodes`（还原），在 `try/finally` 中保证即使执行出错也能恢复，不污染执行器原始状态。

### 10.5 `get_data_node_by_uuid` 兼容节点与关系

Neo4j 中某些业务对象建模为**关系**（如 `(MPart)-[:Certifies {uuid: ...}]->(Supplier)`），查询时先查节点找不到再查关系，统一以 uuid 识别，使得计算图的数据节点 ID 映射对应用层透明。

---

## 11. 典型 Demo 场景：认证/物料/工序计算图

**文件**：`examples/certifies_demo.py`

### 业务背景

计算链：
```
认证完成时间 → 物料可用时间 → 子工序2完成时间 ┐
                                              ├→ 工序完成时间
计划开始时间 → 子工序1完成时间 ───────────────┘
```

### 计算节点（共 5 个）

| 节点 ID | 业务含义 | 主要输入 | 计算逻辑 |
|---------|---------|---------|---------|
| `calc_certification_completion_time` | 认证完成时间 | `reqCertificationStartTime`, `supplierCertificationCycleLt`, `status` | 若 status != '已认证'：开始时间 + 认证周期；否则 = 开始时间 |
| `calc_material_arrival_time` | 物料可用时间 | 认证完成时间、`purchaseCycleLt`、`hasPurchaseOrders`、订单量/库存/需求量/最早到货时间 | 无订单或量不足：认证完成 + 采购周期；否则：最早满足需求的到货时间 |
| `calc_op001_completion_time` | 子工序1完成时间（先序） | `startTime`（VehicleBatch）、`workCalendarDay`（AOProcedures_001） | startTime + 工期 |
| `calc_op002_completion_time` | 子工序2完成时间（后序） | 物料到货时间、子工序1完成时间、`workCalendarDay`（AOProcedures_002） | max(物料到货, 工序1完成) + 工期 |
| `calc_process_completion_time` | 工序完成时间 | 子工序1完成时间、子工序2完成时间 | max(工序1完成, 工序2完成) |

### 数据节点（共 6 个参与计算的）

| 数据节点 ID | 对应 Neo4j 实体/关系 | 关键属性 |
|------------|-------------------|---------|
| `Certifies_DataNode_001` | 关系 `Certifies`（uuid=Certifies_uuid_001） | `reqCertificationStartTime`, `status`, `certification_completion_time`（输出） |
| `MPart_DataNode_001` | 节点 `MPart`（uuid=MPart_uuid_001） | `supplierCertificationCycleLt`, `purchaseCycleLt`, `hasPurchaseOrders`, `totalOrderQuantity`, `warehouseInventory`, `requiredQuantity`, `earliestDeliveryTime`, `material_arrival_time`（输出） |
| `AOProcedures_DataNode_001` | 节点 `AOProcedures`（uuid=AOProcedures_uuid_001） | `workCalendarDay`, `op001_completion_time`（输出） |
| `AOProcedures_DataNode_002` | 节点 `AOProcedures`（uuid=AOProcedures_uuid_002） | `workCalendarDay`, `op002_completion_time`（输出） |
| `VehicleBatch_DataNode_001` | 节点 `VehicleBatch`（uuid=VehicleBatch_uuid_001） | `startTime`, `process_completion_time`（输出） |

### What-If 场景示例

| 场景 | 输入覆盖 | 关键输出变化 |
|------|---------|------------|
| 认证周期延长 | `MPart_DataNode_001.supplierCertificationCycleLt: 30 → 40` | `certification_completion_time +10天`，`material_arrival_time +10天`，`op002_completion_time +10天`，`process_completion_time +10天` |
| 采购周期缩短 | `MPart_DataNode_001.purchaseCycleLt: 30 → 20` | `material_arrival_time -10天`，`op002_completion_time -10天`，`process_completion_time -10天` |

---

*以上即为当前实现的完整方案设计说明书，涵盖各类的字段、方法、职责以及类间依赖与调用关系。*
