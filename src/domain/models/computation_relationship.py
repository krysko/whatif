"""
计算关系模型：图中边的类型与绑定。

- DEPENDS_ON：数据/计算节点 -> 计算节点，通过 datasource 指定读取的属性。
- OUTPUT_TO：计算节点 -> 数据/计算节点，通过 data_output 指定写回的属性。
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

from .computation_relation_type import ComputationRelationType
from .io_spec import OutputSpec


@dataclass(frozen=True, slots=True)
class ComputationRelationship:
    """图中一条边：源/目标节点 ID、关系类型、以及可选的 datasource（读）/ data_output（写）绑定。"""
    id: str
    source_id: str  # Source computation node ID
    target_id: str  # Target computation node ID
    name: str  # Relationship name
    relation_type: ComputationRelationType
    level: str  # Relationship level description
    datasource: OutputSpec | None = None  # Data source for DEPENDS_ON
    data_output: OutputSpec | None = None  # Data output for OUTPUT_TO
    properties: Mapping[str, Any] = field(default_factory=dict)

    def with_properties(self, **new_properties: Any) -> 'ComputationRelationship':
        """Return a new ComputationRelationship with updated properties"""
        merged_properties = {**self.properties, **new_properties}
        return ComputationRelationship(
            id=self.id,
            source_id=self.source_id,
            target_id=self.target_id,
            name=self.name,
            relation_type=self.relation_type,
            level=self.level,
            datasource=self.datasource,
            data_output=self.data_output,
            properties=merged_properties
        )

    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a property value"""
        return self.properties.get(key, default)
