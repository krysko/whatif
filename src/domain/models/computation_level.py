"""计算层级：属性级、节点级、图级（预留）。"""

from enum import Enum


class ComputationLevel(Enum):
    PROPERTY = "property"
    NODE = "node"
    GRAPH = "graph"
