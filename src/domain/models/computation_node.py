from dataclasses import dataclass, field
from typing import Any, Mapping

from .computation_engine import ComputationEngine
from .computation_level import ComputationLevel
from .io_spec import InputSpec, OutputSpec


@dataclass(frozen=True, slots=True)
class ComputationNode:
    """Represents a computation node in the computation graph"""
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
