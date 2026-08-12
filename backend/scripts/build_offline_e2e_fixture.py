from pathlib import Path
import sys

from exam_prep.packages.models import OfflineExamQuestion, OfflineFlashcard, OfflineMockExam
from exam_prep.packages.rendering import FlashcardFileInput, MockExamFileInput, OfflineRenderer


def build_fixture(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    renderer = OfflineRenderer()
    cards = (
        OfflineFlashcard(
            card_id="card-capm",
            book_id="book-1",
            learning_objective="Explain the capital asset pricing model",
            concept_id="capm",
            prompt="What risk does beta measure in CAPM?",
            answer="Beta measures an asset's systematic risk relative to the market portfolio.",
            source_page=42,
            source_reference="FRM Book 1, page 42",
            source_excerpt="Beta measures the sensitivity of an asset return to the market return.",
        ),
        OfflineFlashcard(
            card_id="card-var",
            book_id="book-1",
            learning_objective="Interpret value at risk",
            concept_id="var",
            prompt="What does a one-day 99% VaR of $1 million mean?",
            answer="Under the model, losses exceed $1 million on about one day out of 100.",
            source_page=84,
            source_reference="FRM Book 1, page 84",
            source_excerpt="A 99 percent VaR is exceeded with one percent probability over the horizon.",
        ),
    )
    questions = (
        OfflineExamQuestion(
            question_id="question-capm",
            question_number=1,
            domain="Foundations of Risk Management",
            subtopic="Capital asset pricing model",
            learning_objective="Explain the capital asset pricing model",
            question_type="Applied concept",
            difficulty="Standard exam-level",
            prompt="A stock has a beta of 1.4. Which statement is most accurate?",
            choices=(
                "Its total volatility is 40% above the market's volatility.",
                "Its expected return is always 40% above the risk-free rate.",
                "Its systematic exposure is 40% greater than the market's.",
                "Its idiosyncratic risk is 40% greater than the market's.",
            ),
            correct_choice_index=2,
            explanation="Beta measures systematic exposure, not total volatility or idiosyncratic risk. A beta of 1.4 indicates 40% greater sensitivity to market excess returns.",
            source_reference="FRM Book 1, page 42",
            source_excerpt="Beta measures the sensitivity of an asset return to the market return.",
            quality_score=0.95,
            quality_confidence=0.93,
            quality_label="high_quality",
            quality_accepted=True,
            quality_model_version="offline-e2e-1",
            quality_model_source="pytorch_checkpoint",
        ),
        OfflineExamQuestion(
            question_id="question-var",
            question_number=2,
            domain="Quantitative Analysis",
            subtopic="Value at risk",
            learning_objective="Interpret value at risk",
            question_type="Model interpretation and limitations",
            difficulty="Standard exam-level",
            prompt="Which conclusion follows from a one-day 99% VaR of $1 million?",
            choices=(
                "The maximum possible daily loss is $1 million.",
                "The model assigns a 1% chance to a loss greater than $1 million.",
                "The expected daily loss is $10,000.",
                "Losses will equal $1 million once every 100 trading days.",
            ),
            correct_choice_index=1,
            explanation="VaR is a quantile, not a maximum or an expected loss. The stated VaR implies a 1% modeled probability of exceeding $1 million over one day.",
            source_reference="FRM Book 1, page 84",
            source_excerpt="A 99 percent VaR is exceeded with one percent probability over the horizon.",
            quality_score=0.96,
            quality_confidence=0.94,
            quality_label="high_quality",
            quality_accepted=True,
            quality_model_version="offline-e2e-1",
            quality_model_source="pytorch_checkpoint",
        ),
    )
    (output_dir / "flashcards.html").write_text(
        renderer.render_flashcards(
            FlashcardFileInput(
                package_id="offline-e2e",
                file_id="flashcards",
                version=1,
                title="FRM Part I Flashcards",
                cards=cards,
            )
        ),
        encoding="utf-8",
    )
    (output_dir / "mock-exam.html").write_text(
        renderer.render_mock_exam(
            MockExamFileInput(
                package_id="offline-e2e",
                file_id="mock-exam",
                version=1,
                exam=OfflineMockExam(
                    exam_id="mock-exam-1",
                    title="FRM Part I Mock Exam",
                    timer_minutes=5,
                    questions=questions,
                ),
            )
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_offline_e2e_fixture.py OUTPUT_DIR")
    build_fixture(Path(sys.argv[1]).resolve())
