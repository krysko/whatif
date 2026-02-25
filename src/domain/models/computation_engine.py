from enum import Enum


class ComputationEngine(Enum):
    NEO4J = "neo4j"
    PYTHON = "python"
    EXTERNAL = "external"
