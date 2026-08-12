from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

CountMap = Mapping[str, int]
NestedCountMap = Mapping[str, CountMap]


class FRMPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FRMPartIPolicy:
    domain_weights: CountMap
    exam_domain_counts: tuple[CountMap, CountMap, CountMap]
    subtopic_counts: NestedCountMap
    question_type_counts: CountMap
    difficulty_counts: tuple[CountMap, CountMap, CountMap]

    def validate(self) -> None:
        domains = set(self.domain_weights)
        if sum(self.domain_weights.values()) != 100:
            raise FRMPolicyError("FRM Part I domain weights must total 100.")
        if any(set(exam) != domains for exam in self.exam_domain_counts):
            raise FRMPolicyError("Every mock exam must allocate every FRM Part I domain.")
        if any(sum(exam.values()) != 100 for exam in self.exam_domain_counts):
            raise FRMPolicyError("Every FRM Part I mock exam must contain 100 questions.")
        if any(dict(exam) != dict(self.domain_weights) for exam in self.exam_domain_counts):
            raise FRMPolicyError(
                "Every FRM Part I mock exam must preserve the 20/20/30/30 domain weights."
            )
        aggregate_counts = {
            domain: sum(exam[domain] for exam in self.exam_domain_counts) for domain in domains
        }
        expected_counts = {domain: weight * 3 for domain, weight in self.domain_weights.items()}
        if aggregate_counts != expected_counts:
            raise FRMPolicyError("Three-exam domain totals must preserve the FRM Part I weights.")
        if set(self.subtopic_counts) != domains:
            raise FRMPolicyError("Every FRM Part I domain requires a subtopic policy.")
        if any(
            sum(self.subtopic_counts[domain].values()) != weight
            for domain, weight in self.domain_weights.items()
        ):
            raise FRMPolicyError("Subtopic allocations must equal their domain weights.")
        if sum(self.question_type_counts.values()) != 100:
            raise FRMPolicyError("Question-type allocations must total 100.")
        if any(sum(profile.values()) != 100 for profile in self.difficulty_counts):
            raise FRMPolicyError("Every difficulty profile must total 100.")


def _counts(values: dict[str, int]) -> CountMap:
    return MappingProxyType(values)


def _nested_counts(values: dict[str, dict[str, int]]) -> NestedCountMap:
    return MappingProxyType({domain: _counts(counts) for domain, counts in values.items()})


FRM_PART_I_POLICY = FRMPartIPolicy(
    domain_weights=_counts(
        {
            "Foundations of Risk Management": 20,
            "Quantitative Analysis": 20,
            "Financial Markets and Products": 30,
            "Valuation and Risk Models": 30,
        }
    ),
    exam_domain_counts=(
        _counts(
            {
                "Foundations of Risk Management": 20,
                "Quantitative Analysis": 20,
                "Financial Markets and Products": 30,
                "Valuation and Risk Models": 30,
            }
        ),
        _counts(
            {
                "Foundations of Risk Management": 20,
                "Quantitative Analysis": 20,
                "Financial Markets and Products": 30,
                "Valuation and Risk Models": 30,
            }
        ),
        _counts(
            {
                "Foundations of Risk Management": 20,
                "Quantitative Analysis": 20,
                "Financial Markets and Products": 30,
                "Valuation and Risk Models": 30,
            }
        ),
    ),
    subtopic_counts=_nested_counts(
        {
            "Foundations of Risk Management": {
                "Risk types, risk appetite, and enterprise risk management": 4,
                "Corporate governance and risk-management frameworks": 3,
                "Portfolio theory, diversification, and efficient portfolios": 4,
                "CAPM, factor models, and risk-adjusted performance": 4,
                "Financial failures, crises, and risk-management lessons": 3,
                "Ethics and professional conduct": 2,
            },
            "Quantitative Analysis": {
                "Probability, random variables, and distributions": 4,
                "Sampling, estimation, and hypothesis testing": 3,
                "Correlation and linear regression": 4,
                "Multiple regression and model interpretation": 3,
                "Time-series analysis and forecasting": 3,
                "Simulation and Monte Carlo methods": 2,
                "Data quality and machine-learning concepts": 1,
            },
            "Financial Markets and Products": {
                "Financial institutions, exchanges, OTC markets, and clearing": 4,
                "Forwards and futures": 6,
                "Options and option strategies": 6,
                "Swaps": 5,
                "Fixed-income and credit-market instruments": 4,
                "Mortgages, mortgage-backed securities, and securitization": 3,
                "Foreign exchange and commodity markets": 2,
            },
            "Valuation and Risk Models": {
                "Discounting, arbitrage, and interest-rate fundamentals": 3,
                "Bond pricing, yields, and return measures": 3,
                "Duration, convexity, DV01, and term-structure risk": 5,
                "Binomial-tree and Black-Scholes-Merton valuation": 5,
                "Option Greeks and hedging": 3,
                "Value at Risk, Expected Shortfall, and risk measures": 5,
                "Volatility, correlation, and portfolio-risk estimation": 2,
                "Credit ratings, default risk, and country risk": 2,
                "Stress testing, backtesting, and model limitations": 2,
            },
        }
    ),
    question_type_counts=_counts(
        {
            "Applied conceptual": 38,
            "Numerical calculation": 38,
            "Scenario or mini-case": 16,
            "Model interpretation and limitations": 6,
            "Ethics and professional conduct": 2,
        }
    ),
    difficulty_counts=(
        _counts({"Foundational": 15, "Standard exam-level": 60, "Difficult": 25}),
        _counts({"Foundational": 14, "Standard exam-level": 60, "Difficult": 26}),
        _counts({"Foundational": 14, "Standard exam-level": 58, "Difficult": 28}),
    ),
)
FRM_PART_I_POLICY.validate()
