from exam_prep.analytics.models import MasterySnapshot


class AnalyticsService:
    def get_course_mastery(self, course_id: str) -> MasterySnapshot:
        return MasterySnapshot(course_id=course_id, percent_mastery=0.0)

    def update_mastery(
        self,
        snapshot: MasterySnapshot,
        *,
        concept: str,
        is_correct: bool,
    ) -> MasterySnapshot:
        normalized_concept = concept.strip()
        previous_attempts = snapshot.attempt_count_by_concept.get(normalized_concept, 0)
        previous_mastery = snapshot.mastery_by_concept.get(normalized_concept, 0.0)
        updated_attempts = previous_attempts + 1
        updated_mastery = (
            (previous_mastery * previous_attempts) + (1.0 if is_correct else 0.0)
        ) / updated_attempts

        snapshot.attempt_count_by_concept[normalized_concept] = updated_attempts
        snapshot.mastery_by_concept[normalized_concept] = round(updated_mastery, 4)

        if is_correct:
            snapshot.wrong_concepts = [
                wrong_concept
                for wrong_concept in snapshot.wrong_concepts
                if wrong_concept != normalized_concept
            ]
        elif normalized_concept not in snapshot.wrong_concepts:
            snapshot.wrong_concepts.append(normalized_concept)

        if snapshot.mastery_by_concept:
            snapshot.percent_mastery = round(
                sum(snapshot.mastery_by_concept.values()) / len(snapshot.mastery_by_concept) * 100.0,
                2,
            )

        return snapshot
