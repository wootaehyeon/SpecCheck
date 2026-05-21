from pydantic import BaseModel
from typing import List, Optional


class StorageItem(BaseModel):
    type: str  # e.g., 'NVMe', 'SATA', 'M.2'
    capacity_gb: Optional[int]


class BuildRequest(BaseModel):
    cpu: Optional[str]
    gpu: Optional[str]
    motherboard: Optional[str]
    ram: Optional[str]
    psu_watt: Optional[int]
    storage: Optional[List[StorageItem]] = []
    use_case: Optional[str]  # e.g., 'gaming', 'office', 'workstation'


class CompatibilityIssue(BaseModel):
    type: str
    component: str
    message: str


class CompatibilityResult(BaseModel):
    issues: List[CompatibilityIssue]
    estimated_required_watt: int
    recommended_psu_watt: int


class RiskBreakdown(BaseModel):
    price_performance_factor: float
    compatibility_penalty: float
    storage_penalty: float
    use_case_mismatch_penalty: float


class EvaluationResult(BaseModel):
    cpu_matched: Optional[str]
    cpu_score: int
    gpu_matched: Optional[str]
    gpu_score: int
    overall_score: int
    tier: str
    compatibility: CompatibilityResult
    risk_score: int
    risk_breakdown: RiskBreakdown
