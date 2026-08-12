import math
import re
from collections import Counter
from dataclasses import dataclass

from exam_prep.schemas.materials import ParsedMaterialDocument, SourceChunk
from exam_prep.schemas.retrieval import IndexedChunk, LocalVectorIndex, RetrievalHit
from exam_prep.schemas.materials import ContentLabel


@dataclass(slots=True)
class IndexingService:
    backend_name: str = "local-sparse-vector"

    def build_course_index(
        self,
        course_id: str,
        documents: list[ParsedMaterialDocument],
    ) -> LocalVectorIndex:
        chunks = [chunk for document in documents for chunk in document.chunks]
        document_frequency = self._compute_document_frequency(chunks)
        entries = [
            IndexedChunk(
                chunk=chunk,
                vector=self._build_weighted_vector(
                    self._tokenize(chunk.text),
                    document_frequency,
                    max(len(chunks), 1),
                ),
            )
            for chunk in chunks
        ]
        return LocalVectorIndex(
            course_id=course_id,
            chunk_count=len(chunks),
            document_frequency=document_frequency,
            entries=entries,
        )

    def query_index(
        self,
        index: LocalVectorIndex,
        query: str,
        top_k: int,
        selected_source_ids: list[str] | None = None,
    ) -> list[RetrievalHit]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        query_vector = self._build_weighted_vector(
            query_tokens,
            index.document_frequency,
            max(index.chunk_count, 1),
        )
        if not query_vector:
            return []

        selected_source_id_set = {
            source_id.strip()
            for source_id in (selected_source_ids or [])
            if source_id.strip()
        }
        candidate_entries = index.entries
        if selected_source_id_set:
            candidate_entries = [
                entry for entry in index.entries if entry.chunk.source_id in selected_source_id_set
            ]
        else:
            preferred_entries = [
                entry
                for entry in index.entries
                if entry.chunk.is_default and entry.chunk.content_label == ContentLabel.TESTABLE_CONTENT
            ]
            if not preferred_entries:
                preferred_entries = [
                    entry for entry in index.entries if entry.chunk.is_default
                ]
            if preferred_entries:
                candidate_entries = preferred_entries

        hits: list[RetrievalHit] = []
        for entry in candidate_entries:
            score = self._cosine_similarity(query_vector, entry.vector)
            if score <= 0.0:
                continue
            weighted_score = score * max(entry.chunk.priority_score, 0.05)
            hits.append(RetrievalHit(score=round(weighted_score, 6), chunk=entry.chunk))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    def _compute_document_frequency(self, chunks: list[SourceChunk]) -> dict[str, int]:
        frequency: Counter[str] = Counter()
        for chunk in chunks:
            frequency.update(set(self._tokenize(chunk.text)))
        return dict(frequency)

    def _build_weighted_vector(
        self,
        tokens: list[str],
        document_frequency: dict[str, int],
        total_documents: int,
    ) -> dict[str, float]:
        if not tokens:
            return {}

        token_counts = Counter(tokens)
        total_tokens = len(tokens)
        weighted: dict[str, float] = {}
        for token, count in token_counts.items():
            tf = count / total_tokens
            df = document_frequency.get(token, 0)
            idf = math.log((total_documents + 1) / (df + 1)) + 1.0
            weighted[token] = tf * idf
        return weighted

    def _cosine_similarity(
        self,
        left: dict[str, float],
        right: dict[str, float],
    ) -> float:
        shared = set(left).intersection(right)
        numerator = sum(left[token] * right[token] for token in shared)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return numerator / (left_norm * right_norm)

    def _tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        normalized: list[str] = []
        for token in tokens:
            normalized.append(token)
            if token.endswith("s") and len(token) > 4:
                normalized.append(token[:-1])
        return normalized
