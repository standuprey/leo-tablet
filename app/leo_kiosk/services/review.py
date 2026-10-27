"""Review-write service: parent decisions applied to the catalog.

Reads stay in CatalogService; this owns the write path for the review
editor: rename/rating/age-range drafts, first-trial tested markers and
parent deletions (tombstones without the auto marker, so reimports cannot
resurrect them). Events are appended per decision; the caller of the
service owns nothing transactional — each method is one transaction.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from leo_kiosk.domain.reviews import AgeRange, ReviewDraft, StarRating
from leo_kiosk.storage.catalog import CatalogRepository
from leo_kiosk.storage.database import transaction


class ReviewService:
    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    def mark_tested(self, game_id: UUID) -> None:
        """Record a trial launch: tested_at is set once, events every trial."""
        now = datetime.now(UTC)
        with transaction(self._repository.connection):
            if self._repository.mark_tested(game_id, now):
                self._event(game_id, "tested", {"auto": "first-trial"}, now)
            else:
                self._event(game_id, "tested", {"again": "trial"}, now)

    def apply_review(
        self,
        game_id: UUID,
        name: str,
        stars: StarRating | None,
        age: AgeRange | None,
    ) -> None:
        draft = ReviewDraft(name=name, stars=stars, age=age)
        now = datetime.now(UTC)
        with transaction(self._repository.connection):
            self._repository.apply_review(
                game_id,
                draft.name,
                (draft.stars.production, draft.stars.education, draft.stars.fun)
                if draft.stars
                else None,
                draft.age.min_years if draft.age else None,
                draft.age.max_years if draft.age else None,
                now,
            )
            self._event(
                game_id,
                "reviewed",
                {
                    "name": draft.name,
                    "stars": (
                        {
                            "production": draft.stars.production,
                            "education": draft.stars.education,
                            "fun": draft.stars.fun,
                        }
                        if draft.stars
                        else None
                    ),
                    "age_min": draft.age.min_years if draft.age else None,
                    "age_max": draft.age.max_years if draft.age else None,
                },
                now,
            )

    def delete_game(self, game_id: UUID) -> None:
        """Parent delete: a tombstone no reimport can resurrect."""
        now = datetime.now(UTC)
        with transaction(self._repository.connection):
            if not self._repository.record_deletion(game_id, now):
                raise ValueError("Game is already deleted")
            self._event(game_id, "deleted", {"parent": True}, now)

    def _event(
        self, game_id: UUID, kind: str, change: dict[str, object], when: datetime
    ) -> None:
        import json

        self._repository.connection.execute(
            "INSERT INTO review_events (id, game_id, event_kind, timestamp, change_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                str(game_id),
                kind,
                when.isoformat(),
                json.dumps(change, sort_keys=True),
            ),
        )
