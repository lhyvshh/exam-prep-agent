from dataclasses import dataclass


@dataclass(slots=True)
class DifficultyModel:
    model_name: str = "difficulty-predictor-placeholder"
