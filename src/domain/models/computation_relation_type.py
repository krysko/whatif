"""计算图中边的类型：依赖（读）与输出（写）。"""

from enum import Enum


class ComputationRelationType(Enum):
    DEPENDS_ON = "depends_on"  # 源 -> 计算节点，表示该计算从源读取数据
    OUTPUT_TO = "output_to"    # 计算节点 -> 目标，表示该计算将结果写入目标
