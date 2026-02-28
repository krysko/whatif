"""
计算节点模型：表示图中一个「计算单元」，包含输入/输出规格与可执行代码。

- inputs/outputs 为 InputSpec/OutputSpec 元组，与关系的 datasource/data_output 对应。
- code 为可被 eval 的表达式或语句，执行时从 DEPENDS_ON 来源读取变量并写入 OUTPUT_TO 目标。
- priority 用于同层多节点时的执行顺序（数值越小越先执行）。
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

from .computation_engine import ComputationEngine
from .computation_level import ComputationLevel
from .io_spec import InputSpec, OutputSpec


@dataclass(frozen=True, slots=True)
class ComputationNode:
    """计算图中的单点计算单元：id、名称、层级、输入/输出规格、可执行 code、引擎与优先级。"""
    id: str
    name: str  # e.g., 'calculate_total_price'
    level: ComputationLevel
    inputs: tuple[InputSpec, ...]
    outputs: tuple[OutputSpec, ...]
    code: str  # Computation logic implementation
    engine: ComputationEngine
    properties: Mapping[str, Any] = field(default_factory=dict)
    priority: int = 0  # 同入度时执行顺序：数值越小越先执行

    def with_properties(self, **new_properties: Any) -> 'ComputationNode':
        """Return a new ComputationNode with updated properties"""
        merged_properties = {**self.properties, **new_properties}
        return ComputationNode(
            id=self.id,
            name=self.name,
            level=self.level,
            inputs=self.inputs,
            outputs=self.outputs,
            code=self.code,
            engine=self.engine,
            properties=merged_properties,
            priority=self.priority,
        )

    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a property value"""
        return self.properties.get(key, default)
