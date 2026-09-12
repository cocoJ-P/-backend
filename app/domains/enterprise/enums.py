"""Enterprise domain enumerations.

Stored as strings in the database so SQLite and PostgreSQL stay compatible.
"""

from enum import StrEnum


class EnterpriseType(StrEnum):
    TECHNOLOGY_STARTUP = "technology_startup"
    SME = "sme"
    LARGE_ENTERPRISE = "large_enterprise"
    OTHER = "other"


class ProductStage(StrEnum):
    IDEA = "idea"
    PROTOTYPE = "prototype"
    DEMO = "demo"
    PRODUCT_VALIDATION = "product_validation"
    COMMERCIAL_VALIDATION = "commercial_validation"
    SCALING = "scaling"
    MATURE = "mature"


class BusinessStage(StrEnum):
    PRE_REVENUE = "pre_revenue"
    EARLY_REVENUE = "early_revenue"
    REPEATABLE_REVENUE = "repeatable_revenue"
    GROWTH = "growth"
    SCALE = "scale"


class RevenueStage(StrEnum):
    NO_REVENUE = "no_revenue"
    EARLY_REVENUE = "early_revenue"
    STABLE_REVENUE = "stable_revenue"
    GROWTH_REVENUE = "growth_revenue"
    UNKNOWN = "unknown"


class FundingStage(StrEnum):
    BOOTSTRAPPED = "bootstrapped"
    PRE_SEED = "pre_seed"
    SEED = "seed"
    PRE_A = "pre_a"
    SERIES_A = "series_a"
    LATER = "later"
    UNKNOWN = "unknown"
