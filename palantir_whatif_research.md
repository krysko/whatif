# Palantir Foundry Vertex Scenarios（What-If）功能调研报告

## 一、概述与定位

**Scenarios（场景）** 是 Palantir Foundry 中 **Vertex** 提供的核心能力，用于在“建模后的业务宇宙”上做 **What-If 模拟**：通过改变条件或决策路径，模拟不同运营情境下的结果，从而支持“如果……会怎样？”类问题。

- **文档依据**：[Scenarios Overview](https://www.palantir.com/docs/foundry/vertex/scenarios-overview/)
- **产品归属**：Ontology 体系下的 Vertex 工具集，面向“数字孪生”上的监控、模拟与优化。

---

## 二、核心概念

### 2.1 Scenarios 是什么

- 基于**系统图（system graph）** 配置，对“动作 + 一个或多个建模输入”进行评估，并**计算输出**，以反映数字孪生中的真实业务关系。
- Vertex 支持**多组交互的建模与串联**：可将一个模型的输出自动作为下一个模型的输入，从而分析**端到端影响**，而不仅是单点变化。

### 2.2 与 Ontology、模型的关系

- 业务逻辑与行为通过 **Ontology 中的模型** 以及 **[Models in the Ontology](https://www.palantir.com/docs/foundry/ontology/models/)** 文档所描述的流程进行定义和部署。
- 模型可视为：接收预定义输入、返回计算结果的“任务”；模型版本规定输入/输出参数，并与系统图中的对象类型绑定，使“建模概念”与数字孪生对齐，实现动态系统交互。

---

## 三、业务逻辑与模型在 Foundry 中的实现

### 3.1 Functions on models

- 运营条件的定义、本体关系与预期行为，通过 **[Functions on models](https://www.palantir.com/docs/foundry/functions/functions-on-models/)** 实现：在 Foundry 内编写、评估并部署基于模型的业务逻辑。
- 将这类 Function **发布为 Action** 后，可在 Vertex 中配置，用于交互式运行 Scenarios，评估潜在运营条件的影响。
- Functions 支持在看板、应用等运营场景中快速执行，也可在 Vertex 中驱动动态模拟与案例研究。

### 3.2 从模型到 Vertex 的路径

- 文档建议：为在 Vertex Scenarios 中持续使用“模型”，应优先采用 **Function 封装模型** → **发布为 Function-backed Action** → 在 Vertex 中通过 **添加 Action** 进行 What-If，而不是依赖即将废弃的“在 Vertex 内直接选模型”的旧流程。

---

## 四、时间序列支持

- 要理解并交互“系统随时间的变化”，需将度量值组织为**时间序列**，并作为模型的输入；模型则产生**计算后的时间序列输出**，用于与基线或其它情景对比。
- 支持：监控当前状态、查看历史趋势、在模拟覆盖下预测未来变化。
- 时间序列的配置与使用见 [Time series 文档](https://www.palantir.com/docs/foundry/time-series/time-series-overview/)。

---

## 五、Vertex 与 Scenarios 的定位（摘自 Vertex Overview）

- **Vertex** 用于在“组织的数字孪生”上**可视化与量化因果关系**，可访问/探索已发布的系统图或构建新图。
- 基于**当前、预测或假设条件**支撑数据驱动决策，提供监控、模拟与优化运营决策的工具，以最大化组织结果。
- 典型价值：学习与优化、模拟未来、聚焦重要风险与机会、跨职能透明查看整体网络。

---

## 六、Scenarios 使用流程（Getting Started）

### 6.1 添加 Action

- 通过 **Add scenario** 创建新场景，在场景内 **Add Action**，选择已发布的 Action（如基于模型的 Function Action）。
- 更新 Action 参数并 **Submit** 保存，即可运行该场景并查看 Action 对系统的影响；可继续添加更多 Action 或（在仍支持的情况下）添加模型以深化模拟。

### 6.2 选择模型 [Sunset]

- 文档标明：在 Vertex 内直接“选择/配置/运行模型”的流程处于 **Sunset**，将在未来弃用。推荐路径为：**为模型配置 Function → 发布为 Function-backed Action → 在 Scenarios 中通过添加 Action 使用**。

### 6.3 输入/输出参数

- 通过 **+ Add input or output** 将需要展示的**时间序列、对象属性或指标**加入场景表；可选“添加全部已配置参数”。
- **输入**可在场景表中**手动覆盖**后再运行，用于 What-If；输出用于对比与影响分析。

### 6.4 运行场景与构建 What-If 案例

- 配置好参数后，**Run** 会根据当前（或所选时间）的输入计算模型输出；完成后显示运行状态与耗时。
- 构建 What-If：对要测试的参数进行**覆盖**（override），再运行场景；新输出可与**基线场景**对比。可多次运行、多组覆盖以寻找较优方案。
- 场景与案例可在面板顶部**重命名**，便于区分类似系统下的不同情境。

### 6.5 链式模型 [Sunset]

- **Chained models**：在单一案例中添加多个模型，将前序模型的输出（若已映射为参数）作为后续模型的输入，用于评估**端到端影响**。文档标明该能力也处于 Sunset，推荐通过 **Function-backed Action 链** 实现类似逻辑。

---

## 七、Scenario 选项（Scenario options）

- **时间窗口**：选择有可用数据的时间范围，作为运行场景的时间窗口。
- **高级选项**：如按分钟数配置**时间序列平滑**。
- **范围（Scope）**：对基于对象的系统图，可将场景范围限定为“图中可见对象”，以限制参与计算的输入/输出参数。
- **Run baseline scenario**：在包含 Action 或 override 的场景运行时，可选择**同时运行一次无 Action、无 override 的基线场景**，便于与 What-If 结果对比，评估改动影响。

---

## 八、Ontology 与模型的收益（与 What-If 相关）

- **规模化连接**：模型与 Ontology 结合后，组织在“数据 + 逻辑”上形成单一事实来源，Ontology 成为企业级数字孪生，支持在全组织范围内模拟变更。
- **规模经济**：模型可被多用例复用（如一个预测模型服务多个场景），减少重复建设。
- **可解释性**：结果以本体对象属性（如预测、估计、分类）呈现，业务用户无需理解 ML 细节即可使用 What-If 结果。

---

## 九、总结与建议

| 维度         | 内容摘要 |
|--------------|----------|
| **功能定位** | Vertex Scenarios 在 Foundry 数字孪生上提供 What-If 模拟，支持 Action 与参数覆盖，并可对比基线。 |
| **实现路径** | 业务逻辑通过 **Functions on models** 编写；发布为 **Function-backed Action** 后在 Vertex 中配置与运行。 |
| **时间维度** | 依赖时间序列作为输入/输出，支持当前状态、历史与预测的模拟与对比。 |
| **端到端分析** | 通过 Action 链或（在未完全下线前）链式模型，将多步骤、多系统的影响串联分析。 |
| **演进方向** | 直接“在 Vertex 里选模型/链式模型”的能力处于 Sunset；建议统一走 **模型 → Function → Action → Vertex Scenarios**。 |

---

## 参考链接

- [Scenarios Overview](https://www.palantir.com/docs/foundry/vertex/scenarios-overview/)
- [Scenarios Getting Started](https://www.palantir.com/docs/foundry/vertex/scenarios-getting-started/)
- [Scenarios Options](https://www.palantir.com/docs/foundry/vertex/scenarios-options/)
- [Vertex Overview](https://www.palantir.com/docs/foundry/vertex/overview/)
- [Models in the Ontology](https://www.palantir.com/docs/foundry/ontology/models/)
- [Chained models (Sunset)](https://www.palantir.com/docs/foundry/vertex/chained-models/)
