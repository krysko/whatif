from enum import Enum


class ComputationRelationType(Enum):
    DEPENDS_ON = "depends_on"
    OUTPUT_TO = "output_to"
