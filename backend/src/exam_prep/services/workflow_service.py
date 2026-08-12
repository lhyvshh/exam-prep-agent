from exam_prep.agent_core.models import AgentRunRequest
from exam_prep.agent_core.orchestrator import AgentOrchestrator, AgentOrchestratorRuntime
from exam_prep.core.config import get_settings
from exam_prep.core.exceptions import WorkflowStateError
from exam_prep.repositories.course_store import CourseStore
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.workflow_store import WorkflowStore
from exam_prep.schemas.graph import ExamPrepGraphState, GroundingContext
from exam_prep.schemas.quiz import QuizBundle
from exam_prep.schemas.workflow import CurrentWorkflowResponse


class WorkflowService:
    def __init__(
        self,
        *,
        workflow_store: WorkflowStore,
        course_store: CourseStore,
        material_store: MaterialStore,
        material_catalog: MaterialCatalog,
        quiz_store: QuizStore,
    ) -> None:
        self.workflow_store = workflow_store
        self.course_store = course_store
        self.material_store = material_store
        self.material_catalog = material_catalog
        self.quiz_store = quiz_store
        self.settings = get_settings()

    def set_current_course(self, course_id: str, module_id: str | None = None) -> None:
        normalized_course_id = course_id.strip()
        if not normalized_course_id:
            raise WorkflowStateError("Course ID is required.")
        self.workflow_store.set_current_selection(normalized_course_id, module_id)

    def get_current_workflow(self) -> CurrentWorkflowResponse:
        course_id = self.workflow_store.get_current_course_id()
        module_id = self.workflow_store.get_current_module_id()
        return self._build_response(course_id, module_id)

    def get_workflow_for_course(
        self,
        course_id: str | None,
        module_id: str | None = None,
    ) -> CurrentWorkflowResponse:
        if course_id is None:
            self.workflow_store.clear_current_selection()
            return self._build_response(None, None)
        normalized_course_id = course_id.strip()
        if not normalized_course_id:
            raise WorkflowStateError("Course ID is required.")
        self.workflow_store.set_current_selection(normalized_course_id, module_id)
        return self._build_response(normalized_course_id, module_id)

    def _build_response(
        self,
        course_id: str | None,
        module_id: str | None,
    ) -> CurrentWorkflowResponse:
        available_course_ids = self._available_course_ids()
        if course_id is not None and self.course_store.get_course(course_id) is None:
            self.workflow_store.clear_current_selection()
            course_id = None
            module_id = None
        elif module_id is not None and self.course_store.get_module(module_id) is None:
            self.workflow_store.set_current_selection(course_id, None)
            module_id = None
        if course_id is None:
            graph_state = ExamPrepGraphState()
            return CurrentWorkflowResponse(
                workflow_id="current",
                course_id=None,
                module_id=None,
                graph_state=graph_state,
                material_count=0,
                has_active_course=False,
                available_course_ids=available_course_ids,
            )

        initial_state = ExamPrepGraphState(
            course_id=course_id,
            module_id=module_id,
            requested_module_ids=[module_id] if module_id else [],
        )
        graph_state = self._run_graph(initial_state)
        return CurrentWorkflowResponse(
            workflow_id="current",
            course_id=course_id,
            module_id=module_id,
            graph_state=graph_state,
            material_count=len(graph_state.material_ids),
            has_active_course=True,
            available_course_ids=available_course_ids,
        )

    def _available_course_ids(self) -> list[str]:
        return [course.course_id for course in self.course_store.list_courses()]

    def _run_graph(self, initial_state: ExamPrepGraphState) -> ExamPrepGraphState:
        orchestrator = AgentOrchestrator(
            AgentOrchestratorRuntime(
                resolve_material_ids=self._resolve_material_ids,
                retrieve_grounding_context=self._retrieve_grounding_context,
                resolve_scope_source_ids=self._resolve_scope_source_ids,
                resolve_active_quiz=self._resolve_active_quiz,
                resolve_mastery=self._resolve_mastery,
                enable_torch_inference=self.settings.enable_torch_inference,
            )
        )
        return orchestrator.run(
            AgentRunRequest(
                intent="workflow_snapshot",
                course_id=initial_state.course_id,
                module_id=initial_state.module_id,
                module_ids=initial_state.requested_module_ids or (
                    [initial_state.module_id] if initial_state.module_id else []
                ),
            )
        )

    def _resolve_material_ids(self, state: ExamPrepGraphState) -> list[str]:
        if state.course_id is None:
            return []
        return [
            record.material_id
            for record in self.material_store.list_records_by_course(state.course_id, state.module_id)
        ]

    def _retrieve_grounding_context(self, state: ExamPrepGraphState) -> list[GroundingContext]:
        if state.course_id is None:
            return []

        contexts: list[GroundingContext] = []
        for document in self.material_store.list_parsed_documents_by_course(
            state.course_id,
            state.module_id,
        ):
            for chunk in document.chunks:
                if state.material_ids and chunk.material_id not in state.material_ids:
                    continue
                excerpt = " ".join(chunk.text.split())
                if not excerpt:
                    continue
                contexts.append(
                    GroundingContext(
                        material_id=chunk.material_id,
                        excerpt=excerpt[:280],
                        score=chunk.priority_score,
                    )
                )

        return sorted(contexts, key=lambda item: item.score, reverse=True)[:5]

    def _resolve_scope_source_ids(self, state: ExamPrepGraphState) -> list[str]:
        if state.course_id is None:
            return []
        effective_module_ids = state.requested_module_ids or (
            [state.module_id] if state.module_id else []
        )
        documents = []
        seen_material_ids: set[str] = set()
        if not effective_module_ids:
            documents = self.material_store.list_parsed_documents_by_course(state.course_id, None)
        else:
            for module_id in effective_module_ids:
                for document in self.material_store.list_parsed_documents_by_course(
                    state.course_id,
                    module_id,
                ):
                    if document.record.material_id in seen_material_ids:
                        continue
                    seen_material_ids.add(document.record.material_id)
                    documents.append(document)
        return sorted(
            {
                section.source_id
                for document in documents
                for section in document.sections
            }
        )

    def _resolve_active_quiz(self, state: ExamPrepGraphState) -> QuizBundle | None:
        if state.course_id is None:
            return None

        sessions = [
            session
            for session in self.quiz_store.list_quiz_sessions_by_course(
                state.course_id,
                state.module_id,
            )
            if not session.quiz.query.startswith("remediation:")
        ]
        if not sessions:
            return None
        return sorted(
            sessions,
            key=lambda session: session.quiz.created_at or session.quiz.quiz_id,
            reverse=True,
        )[0].quiz

    def _resolve_mastery(self, state: ExamPrepGraphState) -> tuple[dict[str, float], list[str]]:
        if state.course_id is None:
            return {}, []
        snapshot = self.quiz_store.get_mastery_snapshot(state.course_id, state.module_id)
        return snapshot.mastery_by_concept, snapshot.wrong_concepts
