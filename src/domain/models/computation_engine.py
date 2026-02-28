"""计算引擎枚举：当前执行器仅使用 PYTHON（eval）。"""

from enum import Enum


class ComputationEngine(Enum):
    NEO4J = "neo4j"
    PYTHON = "python"
    EXTERNAL = "external"
