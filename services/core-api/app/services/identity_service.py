"""IdentityService — application service for actor identity and authorized elders.

Orchestrates repository queries to provide:
- Actor profile information (GET /me)
- Authorized elders listing with mode-based dispatch (GET /me/authorized-elders)

This service validates mode/role compatibility, actor status, and applies
cursor-based pagination to elder listings.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.exceptions import AuthorizationDeniedError
from app.middleware.auth import ActorContext
from app.models.enums import ActorType
from app.policies import RoleModeIncompatibleError
from app.repositories.actor_repo import ActorRepository
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.repositories.care_relationship_repo import CareRelationshipRepository
from app.repositories.care_unit_membership_repo import CareUnitMembershipRepository
from app.repositories.tenant_membership_repo import TenantMembershipRepository
from app.repositories.types import AuthorizedElderRow

# --- Mode/Role Compatibility Matrix ---

# "family" covers legal representatives too: ActorType has no
# LEGAL_REPRESENTATIVE member, because legal representation is a
# CareRelationship, not a kind of actor (document 06 section 4.1). Such an
# actor authenticates as FAMILY_MEMBER; the relationship type is what
# distinguishes them, and _list_family_elders queries for both.
_ALLOWED_MODE_ROLES: dict[str, set[str]] = {
    "daycare": {ActorType.DAYCARE_CARE_WORKER},
    "home-care": {ActorType.HOME_CARE_WORKER},
    "family": {ActorType.FAMILY_MEMBER},
}


# --- Result Dataclass ---


@dataclass(frozen=True)
class AuthorizedEldersResult:
    """Paginated result for authorized elders listing.

    Attributes:
        items: List of authorized elder rows for the current page.
        next_cursor: Opaque cursor for the next page, or None if no more.
        has_more: Whether there are additional items beyond this page.
    """

    items: list[AuthorizedElderRow]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class ActorProfile:
    """Actor profile returned by GET /me.

    Attributes:
        actor_id: The actor's UUID.
        actor_type: The actor's role/type.
        display_name: Formal display name loaded from the actor table.
        tenant_id: The actor's tenant UUID.
        role: Same as actor_type (from ActorContext).
        care_unit_ids: List of care unit UUIDs the actor belongs to.
    """

    actor_id: UUID
    actor_type: str
    display_name: str
    tenant_id: UUID
    role: str
    care_unit_ids: list[UUID]


# --- Cursor Utilities ---


def encode_cursor(display_name: str, elder_id: UUID) -> str:
    """Encode a pagination cursor as base64-encoded JSON.

    Args:
        display_name: The elder's display name (sort key).
        elder_id: The elder's UUID (tiebreaker).

    Returns:
        URL-safe base64-encoded cursor string.
    """
    payload = json.dumps([display_name, str(elder_id)])
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, UUID]:
    """Decode a pagination cursor from base64-encoded JSON.

    Args:
        cursor: URL-safe base64-encoded cursor string.

    Returns:
        Tuple of (display_name, elder_id).

    Raises:
        ValueError: If the cursor is malformed.
    """
    data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return data[0], UUID(data[1])


# --- Service Class ---


class IdentityService:
    """Application service for actor identity and authorized elders queries.

    Orchestrates mode/role validation, repository dispatch, and pagination.
    All authorization-relevant time checks are performed by the repositories;
    this service handles the mode/role compatibility matrix and pagination
    logic.
    """

    def __init__(
        self,
        actor_repo: ActorRepository,
        tenant_membership_repo: TenantMembershipRepository,
        care_unit_membership_repo: CareUnitMembershipRepository,
        care_relationship_repo: CareRelationshipRepository,
        care_assignment_repo: CareAssignmentRepository,
    ) -> None:
        """Initialize with repository dependencies.

        Args:
            actor_repo: For loading formal actor identity state.
            tenant_membership_repo: For checking actor's tenant membership.
            care_unit_membership_repo: For getting actor's care unit IDs.
            care_relationship_repo: For querying care relationships.
            care_assignment_repo: For querying care assignments.
        """
        self._actor_repo = actor_repo
        self._tenant_membership_repo = tenant_membership_repo
        self._care_unit_membership_repo = care_unit_membership_repo
        self._care_relationship_repo = care_relationship_repo
        self._care_assignment_repo = care_assignment_repo

    async def get_actor_profile(
        self,
        actor_context: ActorContext,
        current_time: datetime,
    ) -> ActorProfile:
        """Return actor profile information including care unit IDs.

        Args:
            actor_context: The authenticated actor's context.
            current_time: Trusted server time for membership evaluation.

        Returns:
            ActorProfile with actor info and care_unit_ids.
        """
        membership = await self._tenant_membership_repo.get_active_membership(
            actor_id=actor_context.actor_id,
            tenant_id=actor_context.tenant_id,
            role_code=actor_context.actor_role,
            current_time=current_time,
        )
        if membership is None:
            raise AuthorizationDeniedError("Resource not found")

        actor = await self._actor_repo.get_active_by_id(actor_context.actor_id)
        if actor is None or actor.actor_type != actor_context.actor_role:
            raise AuthorizationDeniedError("Resource not found")

        care_unit_ids = await self._care_unit_membership_repo.get_care_unit_ids(
            actor_id=actor_context.actor_id,
            tenant_id=actor_context.tenant_id,
            role_code=actor_context.actor_role,
            current_time=current_time,
        )

        return ActorProfile(
            actor_id=actor.id,
            actor_type=actor.actor_type,
            display_name=actor.display_name,
            tenant_id=actor_context.tenant_id,
            role=membership.role_code,
            care_unit_ids=care_unit_ids,
        )

    async def get_authorized_elders(
        self,
        actor_context: ActorContext,
        mode: str,
        current_time: datetime,
        cursor: str | None = None,
        limit: int = 20,
    ) -> AuthorizedEldersResult:
        """Get paginated list of elders the actor is authorized to access.

        Validates mode/role compatibility, dispatches to the appropriate
        repository query, and applies cursor-based pagination.

        Args:
            actor_context: The authenticated actor's context.
            mode: One of "daycare", "home-care", "family".
            current_time: Current UTC time for time-window checks.
            cursor: Optional opaque pagination cursor.
            limit: Maximum number of items to return (default 20).

        Returns:
            AuthorizedEldersResult with items, next_cursor, and has_more.

        Raises:
            RoleModeIncompatibleError: If actor's role is incompatible with mode.
            ActorInactiveError: If actor's status is not ACTIVE.
        """
        # Validate mode/role compatibility
        self._validate_mode_role_compatibility(actor_context.actor_role, mode)

        # Dispatch query by mode
        all_items = await self._dispatch_by_mode(actor_context, mode, current_time)

        # Apply cursor-based pagination
        return self._apply_pagination(all_items, cursor, limit)

    def _validate_mode_role_compatibility(self, actor_role: str, mode: str) -> None:
        """Validate that the actor's role is compatible with the requested mode.

        Args:
            actor_role: The actor's role from ActorContext.
            mode: The requested mode.

        Raises:
            RoleModeIncompatibleError: If incompatible or ADMIN.
        """
        # ADMIN always denied
        if actor_role == ActorType.ADMIN:
            raise RoleModeIncompatibleError("ADMIN role cannot access authorized-elders endpoint.")

        allowed_roles = _ALLOWED_MODE_ROLES.get(mode)
        if allowed_roles is None:
            # Invalid mode — should be caught by schema validation before here
            raise RoleModeIncompatibleError(
                f"Invalid mode: {mode}. Valid values: daycare, home-care, family"
            )

        if actor_role not in allowed_roles:
            raise RoleModeIncompatibleError(
                f"Actor role {actor_role} is incompatible with mode {mode}."
            )

    async def _dispatch_by_mode(
        self,
        actor_context: ActorContext,
        mode: str,
        current_time: datetime,
    ) -> list[AuthorizedElderRow]:
        """Dispatch to the appropriate repository query based on mode.

        Args:
            actor_context: The authenticated actor's context.
            mode: One of "daycare", "home-care", "family".
            current_time: Current UTC time for time-window checks.

        Returns:
            List of AuthorizedElderRow from the appropriate source.
        """
        if mode == "daycare":
            return await self._query_daycare(actor_context, current_time)
        elif mode == "home-care":
            return await self._query_home_care(actor_context, current_time)
        elif mode == "family":
            return await self._query_family(actor_context, current_time)
        else:
            # Should not reach here due to validation above
            raise RoleModeIncompatibleError(f"Unknown mode: {mode}")

    async def _query_daycare(
        self,
        actor_context: ActorContext,
        current_time: datetime,
    ) -> list[AuthorizedElderRow]:
        """Query authorized elders for DAYCARE mode.

        Steps:
        1. Verify TenantMembership is ACTIVE.
        2. Get actor's care_unit_ids.
        3. Query CareRelationships (DAYCARE_ASSIGNMENT) restricted to those units.

        Args:
            actor_context: The authenticated actor's context.
            current_time: Current UTC time.

        Returns:
            List of authorized elder rows.

        Raises:
            RoleModeIncompatibleError: If TenantMembership is not active.
        """
        # Step 1: Verify TenantMembership ACTIVE
        membership = await self._tenant_membership_repo.get_active_membership(
            actor_id=actor_context.actor_id,
            tenant_id=actor_context.tenant_id,
            role_code=actor_context.actor_role,
            current_time=current_time,
        )
        if membership is None:
            raise RoleModeIncompatibleError("Actor does not have an active TenantMembership.")

        # Step 2: Get actor's care_unit_ids
        care_unit_ids = await self._care_unit_membership_repo.get_care_unit_ids(
            actor_id=actor_context.actor_id,
            tenant_id=actor_context.tenant_id,
            role_code=actor_context.actor_role,
            current_time=current_time,
        )

        # Step 3: No care unit memberships = no access (deny by default)
        if not care_unit_ids:
            return []

        # Step 4: Query care relationships restricted to those care units
        return await self._care_relationship_repo.find_authorized_elders_by_actor(
            actor_id=actor_context.actor_id,
            relationship_types=["DAYCARE_ASSIGNMENT"],
            current_time=current_time,
            care_unit_ids=care_unit_ids,
        )

    async def _query_home_care(
        self,
        actor_context: ActorContext,
        current_time: datetime,
    ) -> list[AuthorizedElderRow]:
        """Query authorized elders for HOME-CARE mode.

        Queries CareAssignments for the worker.

        Args:
            actor_context: The authenticated actor's context.
            current_time: Current UTC time.

        Returns:
            List of authorized elder rows.
        """
        assignment_rows = await self._care_assignment_repo.find_authorized_elders_by_worker(
            worker_id=actor_context.actor_id,
            current_time=current_time,
        )
        # Convert AssignmentElderRow to AuthorizedElderRow (same NamedTuple shape)
        return [
            AuthorizedElderRow(
                elder_id=row.elder_id,
                display_name=row.display_name,
                care_unit_name=row.care_unit_name,
            )
            for row in assignment_rows
        ]

    async def _query_family(
        self,
        actor_context: ActorContext,
        current_time: datetime,
    ) -> list[AuthorizedElderRow]:
        """Query authorized elders for FAMILY mode.

        Queries CareRelationships with FAMILY_SHARE or LEGAL_REPRESENTATIVE types.

        Args:
            actor_context: The authenticated actor's context.
            current_time: Current UTC time.

        Returns:
            List of authorized elder rows.
        """
        return await self._care_relationship_repo.find_authorized_elders_by_actor(
            actor_id=actor_context.actor_id,
            relationship_types=["FAMILY_SHARE", "LEGAL_REPRESENTATIVE"],
            current_time=current_time,
        )

    def _apply_pagination(
        self,
        items: list[AuthorizedElderRow],
        cursor: str | None,
        limit: int,
    ) -> AuthorizedEldersResult:
        """Apply cursor-based pagination to the result list.

        Cursor is base64-encoded (display_name, elder_id) tuple.
        Filters items where (display_name, elder_id) > (cursor_name, cursor_id),
        then returns limit items plus has_more indicator.

        Args:
            items: Full list of authorized elder rows (already sorted).
            cursor: Optional cursor string to paginate from.
            limit: Maximum items to return.

        Returns:
            AuthorizedEldersResult with paginated items.
        """
        # Apply cursor filter
        if cursor is not None:
            cursor_name, cursor_id = decode_cursor(cursor)
            items = [
                item
                for item in items
                if (item.display_name, item.elder_id) > (cursor_name, cursor_id)
            ]

        # Determine has_more by fetching limit + 1
        has_more = len(items) > limit
        page_items = items[:limit]

        # Compute next_cursor from the last item in the page
        next_cursor: str | None = None
        if has_more and page_items:
            last = page_items[-1]
            next_cursor = encode_cursor(last.display_name, last.elder_id)

        return AuthorizedEldersResult(
            items=page_items,
            next_cursor=next_cursor,
            has_more=has_more,
        )
