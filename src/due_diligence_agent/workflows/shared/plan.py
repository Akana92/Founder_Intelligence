from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    task_id: str
    node_name: str
    depends_on: list[str] = Field(default_factory=list)
    required_output_schema: str


class AnalysisPlan(BaseModel):
    objectives: list[str]
    steps: list[PlanStep]
    token_budget: int
    max_reflexion_rounds: int = Field(default=2, ge=0, le=2)
