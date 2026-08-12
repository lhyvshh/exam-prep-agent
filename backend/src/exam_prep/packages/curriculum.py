from dataclasses import dataclass, field

from pydantic import Field

from exam_prep.schemas.materials import (
    MaterialRecord,
    MaterialStudyDocument,
    MaterialStudySection,
    StudyConceptCard,
    StudyFlashcard,
)

from .models import OfflineFlashcard, OfflineFormula, PackageModel


class CurriculumConceptSnapshot(PackageModel):
    concept_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    learning_outcome: str = Field(min_length=1)
    source_pages: tuple[int, ...]
    source_anchors: tuple[str, ...]
    flashcards: tuple[OfflineFlashcard, ...]


class CurriculumBookSnapshot(PackageModel):
    material_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content_hash: str | None = None
    concepts: tuple[CurriculumConceptSnapshot, ...]
    formulas: tuple[OfflineFormula, ...]


class CurriculumSnapshot(PackageModel):
    course_id: str = Field(min_length=1)
    books: tuple[CurriculumBookSnapshot, ...]
    rejected_flashcard_count: int = Field(default=0, ge=0)
    rejected_formula_count: int = Field(default=0, ge=0)


@dataclass(slots=True)
class _ConceptAccumulator:
    concept_id: str
    title: str
    learning_outcome: str
    source_pages: set[int] = field(default_factory=set)
    source_anchors: set[str] = field(default_factory=set)
    flashcards: dict[str, OfflineFlashcard] = field(default_factory=dict)


class CurriculumSnapshotBuilder:
    def build(
        self,
        *,
        course_id: str,
        materials: list[MaterialRecord],
        study_documents: list[MaterialStudyDocument],
    ) -> CurriculumSnapshot:
        documents = {document.material_id: document for document in study_documents}
        books: list[CurriculumBookSnapshot] = []
        rejected_flashcards = 0
        rejected_formulas = 0

        for material in materials:
            document = documents.get(material.material_id)
            if document is None:
                books.append(self._empty_book(material))
                continue
            concepts, concept_keys = self._collect_concepts(document.sections)
            rejected_flashcards += self._collect_flashcards(
                material,
                document.sections,
                concepts,
                concept_keys,
            )
            formulas, rejected = self._collect_formulas(material, document.sections)
            rejected_formulas += rejected
            books.append(
                CurriculumBookSnapshot(
                    material_id=material.material_id,
                    title=material.display_name or material.file_name,
                    content_hash=material.content_hash,
                    concepts=tuple(self._freeze_concept(concept) for concept in concepts.values()),
                    formulas=tuple(formulas.values()),
                )
            )

        return CurriculumSnapshot(
            course_id=course_id,
            books=tuple(books),
            rejected_flashcard_count=rejected_flashcards,
            rejected_formula_count=rejected_formulas,
        )

    def _collect_concepts(
        self,
        sections: list[MaterialStudySection],
    ) -> tuple[dict[tuple[str, str], _ConceptAccumulator], dict[str, tuple[str, str]]]:
        concepts: dict[tuple[str, str], _ConceptAccumulator] = {}
        concept_keys: dict[str, tuple[str, str]] = {}
        for section in sections:
            outcome_titles = {
                concept.concept_id: outcome.outcome_title
                for outcome in section.learning_outcomes
                for concept in outcome.concepts
            }
            candidates = [
                *(concept for outcome in section.learning_outcomes for concept in outcome.concepts),
                *section.concepts,
            ]
            for concept in candidates:
                learning_outcome = concept.learning_outcome or outcome_titles.get(concept.concept_id)
                if not learning_outcome or not concept.title.strip():
                    continue
                key = (section.section_id, self._normalize(learning_outcome))
                accumulator = concepts.setdefault(
                    key,
                    _ConceptAccumulator(
                        concept_id=concept.concept_id,
                        title=concept.title.strip(),
                        learning_outcome=learning_outcome.strip(),
                    ),
                )
                self._add_concept_sources(accumulator, concept, section)
                concept_keys[concept.concept_id] = key
        return concepts, concept_keys

    def _collect_flashcards(
        self,
        material: MaterialRecord,
        sections: list[MaterialStudySection],
        concepts: dict[tuple[str, str], _ConceptAccumulator],
        concept_keys: dict[str, tuple[str, str]],
    ) -> int:
        rejected = 0
        for section in sections:
            for card in section.flashcards:
                key = concept_keys.get(card.concept_id or "")
                if key is None or card.source_page is None:
                    rejected += 1
                    continue
                concept = concepts[key]
                concept.flashcards[card.flashcard_id] = self._offline_flashcard(
                    material,
                    concept,
                    card,
                )
                concept.source_pages.add(card.source_page)
        return rejected

    def _collect_formulas(
        self,
        material: MaterialRecord,
        sections: list[MaterialStudySection],
    ) -> tuple[dict[str, OfflineFormula], int]:
        formulas: dict[str, OfflineFormula] = {}
        rejected = 0
        for section in sections:
            for formula in section.formulas:
                application = formula.usage_note or formula.example_if_available or formula.source_excerpt
                if formula.source_page is None or not application.strip():
                    rejected += 1
                    continue
                formulas[formula.formula_id] = OfflineFormula(
                    formula_id=formula.formula_id,
                    name=formula.formula_name or formula.formula_text,
                    expression=formula.formula_latex or formula.formula_text,
                    variables=formula.variables_json,
                    application=application,
                    source_page=formula.source_page,
                    source_reference=self._source_reference(material, formula.source_page),
                )
        return formulas, rejected

    @staticmethod
    def _add_concept_sources(
        accumulator: _ConceptAccumulator,
        concept: StudyConceptCard,
        section: MaterialStudySection,
    ) -> None:
        accumulator.source_pages.update(concept.source_pages)
        accumulator.source_anchors.update(source_id for source_id in section.source_ids if source_id)
        if section.source_anchor:
            accumulator.source_anchors.add(section.source_anchor)

    @staticmethod
    def _offline_flashcard(
        material: MaterialRecord,
        concept: _ConceptAccumulator,
        card: StudyFlashcard,
    ) -> OfflineFlashcard:
        source_page = card.source_page
        if source_page is None:
            raise AssertionError("Grounded flashcards require a source page.")
        return OfflineFlashcard(
            card_id=card.flashcard_id,
            book_id=material.material_id,
            learning_objective=concept.learning_outcome,
            learning_objective_title=concept.title,
            concept_id=concept.concept_id,
            prompt=card.front,
            answer=card.back_concise or card.back,
            card_type=card.card_type,
            difficulty=card.difficulty.value,
            source_page=source_page,
            source_reference=CurriculumSnapshotBuilder._source_reference(material, source_page),
            source_excerpt=card.source_excerpt or card.source_text_snippet or None,
        )

    @staticmethod
    def _freeze_concept(concept: _ConceptAccumulator) -> CurriculumConceptSnapshot:
        return CurriculumConceptSnapshot(
            concept_id=concept.concept_id,
            title=concept.title,
            learning_outcome=concept.learning_outcome,
            source_pages=tuple(sorted(concept.source_pages)),
            source_anchors=tuple(sorted(concept.source_anchors)),
            flashcards=tuple(concept.flashcards.values())[:10],
        )

    @staticmethod
    def _empty_book(material: MaterialRecord) -> CurriculumBookSnapshot:
        return CurriculumBookSnapshot(
            material_id=material.material_id,
            title=material.display_name or material.file_name,
            content_hash=material.content_hash,
            concepts=(),
            formulas=(),
        )

    @staticmethod
    def _source_reference(material: MaterialRecord, source_page: int) -> str:
        return f"{material.display_name or material.file_name}, page {source_page}"

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())
