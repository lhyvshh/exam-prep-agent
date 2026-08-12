from exam_prep.packages.models import OfflineExamQuestion, OfflineFlashcard, OfflineMockExam
from exam_prep.packages.rendering import FlashcardFileInput, MockExamFileInput, OfflineRenderer


def test_flashcard_renderer_embeds_data_safely_and_has_no_network_dependencies() -> None:
    deck = FlashcardFileInput(
        package_id="package-1",
        file_id="flashcards-book-1",
        version=1,
        title="FRM Book 1 Flashcards",
        cards=(
            OfflineFlashcard(
                card_id="card-1",
                book_id="book-1",
                learning_objective="Explain CAPM",
                learning_objective_title="Capital asset pricing model",
                concept_id="concept-1",
                prompt="</script><script>bad()</script>",
                answer="CAPM prices systematic risk.",
                source_page=12,
                source_reference="FRM Book 1, page 12",
            ),
        ),
    )

    html = OfflineRenderer().render_flashcards(deck)

    assert "https://" not in html
    assert "http://" not in html
    assert "</script><script>bad()" not in html
    assert "\\u003c/script\\u003e" in html
    assert "localStorage" in html
    assert 'rel="icon" type="image/png" href="data:image/png;base64,' in html
    assert 'data-action="next"' in html
    assert 'id="type-filter"' in html
    assert 'id="difficulty-filter"' in html
    assert 'id="import-progress-button"' in html
    assert 'id="objective-options"' in html
    assert 'id="card-list"' in html
    assert 'data-action="select-all-objectives"' in html
    assert 'data-action="clear-objectives"' in html
    assert "state.selectedObjectives" in html
    assert "`${selected.size} of ${items.length} selected`" in html
    assert "selected.size||items.length" not in html
    assert "learning_objective_title" in html
    assert 'aria-current="true"' in html
    assert 'document.activeElement.closest("input,select,textarea,button,label")' in html
    assert "grid-template-columns:44px minmax(0,1fr) 44px" in html
    assert "state.cardType" in html
    assert "state.difficulty" in html
    assert "list.scrollTop" in html
    assert "scrollIntoView" not in html
    assert "exam-prep:${payload.package_id}:${payload.file_id}:v${payload.version}" in html


def test_mock_exam_renderer_hides_answers_until_submission() -> None:
    exam = MockExamFileInput(
        package_id="package-1",
        file_id="mock-exam-1",
        version=1,
        exam=OfflineMockExam(
            exam_id="exam-1",
            title="FRM Part I Mock Exam 1",
            timer_minutes=90,
            questions=(
                OfflineExamQuestion(
                    question_id="question-1",
                    question_number=1,
                    domain="Quantitative Analysis",
                    subtopic="Correlation and linear regression",
                    learning_objective="Interpret regression output",
                    question_type="Model interpretation and limitations",
                    difficulty="Standard exam-level",
                    prompt="Which conclusion is most appropriate?",
                    choices=("Choice A", "Choice B", "Choice C", "Choice D"),
                    correct_choice_index=2,
                    explanation="Choice C follows from the reported coefficient and p-value.",
                    source_reference="FRM Book 1, page 120",
                    quality_score=0.92,
                    quality_confidence=0.88,
                    quality_label="high_quality",
                    quality_accepted=True,
                    quality_model_version="torch-1",
                    quality_model_source="pytorch",
                ),
            ),
        ),
    )

    html = OfflineRenderer().render_mock_exam(exam)

    assert "data-correct-answer" not in html
    assert "correctAnswerId" in html
    assert "state.submitted" in html
    assert "Submit exam" in html
    assert 'class="practice-toggle"' in html
    assert "Save completed exam" in html
    assert 'id="save-completed"' in html
    assert 'id="attempt-data"' in html
    assert "content_sha256" in html
    assert "crypto.randomUUID" in html
    assert "text/html" in html
    assert "clone.querySelector(\"#attempt-data\")" in html
    assert "importedAttempt" in html
    assert "localStorage" in html
    assert "flex-wrap:nowrap;overflow-x:auto" in html
    assert '<div class="progress"><strong id="timer"></strong>' in html
    assert "remainingSeconds:exam.timer_minutes*60" in html
    assert "state.remainingSeconds" in html
    assert "localStorage.removeItem(storageKey);state={...initial}" in html
    assert "Total score" in html
    assert "buildBreakdown(\"Domain\",item=>item.domain)" in html
    assert "buildBreakdown(\"Subtopic\",item=>item.subtopic)" in html
    assert "buildBreakdown(\"Question type\",item=>item.question_type)" in html
    assert "buildBreakdown(\"Difficulty\",item=>item.difficulty)" in html
    assert "--artifact-ink" in html
    assert "@media(max-width:720px)" in html
    assert "#submit{grid-column:1/-1}" in html
    assert "renderQuestion()" in html
    assert 'button.setAttribute("aria-current","true")' in html
    assert 'button.setAttribute("aria-label",`Question ${item.question_number}' in html
