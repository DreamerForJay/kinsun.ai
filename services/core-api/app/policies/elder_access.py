"""ElderAccessPolicy — unified authorization logic for Elder data access.

Implements deny-by-default policy evaluation. Each actor role has specific
authorization conditions that must ALL be satisfied for access to be granted.
The policy evaluates against live database state on every call (no caching).

Authorization branches:
- ELDER: the authenticated actor must be the actor linked to the Elder record;
  caregiver-only review actions remain denied
- FAMILY_MEMBER: CareRelationship (FAMILY_SHARE or LEGAL_REPRESENTATIVE) + scope check
- HOME_CARE_WORKER: CareAssignment (CONFIRMED/IN_PROGRESS, time window) + scope check
- DAYCARE_CARE_WORKER: TenantMembership + CareUnitMembership
    + CareRelationship (DAYCARE_ASSIGNMENT) + scope check
- SYSTEM_SERVICE: active TenantMembership + HOME_CARE_ASSIGNMENT relationship + scope
- ADMIN: Deferred (always deny)
- Unknown: Always deny

There is no LEGAL_REPRESENTATIVE actor branch. Per document 06 section 4.1 the
actor_type enum has no such member — being a legal representative is a
relationship to an elder, not a kind of actor. A legal representative
authenticates as a FAMILY_MEMBER, so that branch accepts either relationship
type. Dropping this would have silently revoked all access for legal
representatives.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.models.enums import ActorType, RelationshipType
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.repositories.care_relationship_repo import CareRelationshipRepository
from app.repositories.care_unit_membership_repo import CareUnitMembershipRepository
from app.repositories.tenant_membership_repo import TenantMembershipRepository

# --- Reason Codes ---

ALLOWED = "ALLOWED"
NO_VALID_RELATIONSHIP = "NO_VALID_RELATIONSHIP"
NO_VALID_ASSIGNMENT = "NO_VALID_ASSIGNMENT"
CROSS_TENANT = "CROSS_TENANT"
SCOPE_INSUFFICIENT = "SCOPE_INSUFFICIENT"
OUTSIDE_TIME_WINDOW = "OUTSIDE_TIME_WINDOW"
NO_TENANT_MEMBERSHIP = "NO_TENANT_MEMBERSHIP"
WRONG_CARE_UNIT = "WRONG_CARE_UNIT"
ADMIN_DEFERRED = "ADMIN_DEFERRED"
UNKNOWN_ROLE = "UNKNOWN_ROLE"
ACTOR_INACTIVE = "ACTOR_INACTIVE"
NOT_ELDER_SELF = "NOT_ELDER_SELF"

ELDER_SELF_PROHIBITED_ACTIONS = frozenset(
    {
        "care_event:review",
        "summary:review",
    }
)


# --- Data Classes ---


@dataclass(frozen=True)
class ElderAccessRequest:
    """Policy input — all values from trusted sources (ActorContext + URL path).

    Attributes:
        actor_id: The actor's UUID from ActorContext.
        actor_role: The actor's role from ActorContext (ActorType enum value).
        tenant_id: The actor's tenant from ActorContext.
        elder_id: The target elder UUID from the URL path parameter.
        requested_action: The action being requested (e.g. "elder:basic:read").
        current_time: UTC timestamp injected for testability (no internal clock reads).
    """

    actor_id: UUID
    actor_role: str
    tenant_id: UUID
    elder_id: UUID
    requested_action: str
    current_time: datetime
    actor_is_elder_self: bool = False


@dataclass(frozen=True)
class ElderAccessDecision:
    """Policy output — describes whether access is allowed and why.

    Attributes:
        allowed: Whether access is granted.
        reason_code: Machine-readable reason (ALLOWED, NO_VALID_RELATIONSHIP, etc.).
        expires_at: Earliest expiry time from the authorization source.
        granted_scope: The actual scope list from the authorization source.
        source_type: "relationship" or "assignment" (None if denied).
        source_id: The relationship_id or assignment_id (None if denied).
    """

    allowed: bool
    reason_code: str
    expires_at: datetime | None
    granted_scope: list[str]
    source_type: str | None
    source_id: UUID | None


# --- Policy Class ---


class ElderAccessPolicy:
    """Unified authorization policy for Elder data access.

    Implements deny-by-default evaluation. All repository dependencies
    are injected via constructor for testability.

    The policy is ASYNC because it calls repository methods that execute
    database queries. Authorization is re-evaluated on every call —
    no caching across requests.
    """

    def __init__(
        self,
        tenant_membership_repo: TenantMembershipRepository,
        care_unit_membership_repo: CareUnitMembershipRepository,
        care_relationship_repo: CareRelationshipRepository,
        care_assignment_repo: CareAssignmentRepository,
    ) -> None:
        """Initialize the policy with repository dependencies.

        Args:
            tenant_membership_repo: For checking actor's tenant membership.
            care_unit_membership_repo: For checking actor's care unit membership.
            care_relationship_repo: For querying care relationships (tenant-scoped).
            care_assignment_repo: For querying care assignments (tenant-scoped).
        """
        self._tenant_membership_repo = tenant_membership_repo
        self._care_unit_membership_repo = care_unit_membership_repo
        self._care_relationship_repo = care_relationship_repo
        self._care_assignment_repo = care_assignment_repo

    async def check_access(self, request: ElderAccessRequest) -> ElderAccessDecision:
        """Evaluate whether the actor is authorized to access the target elder.

        Authorization flow:
        1. Branch by actor_role
        2. Query relevant authorization source (relationship or assignment)
        3. Verify all conditions (status, time window, scope, tenant, IDs)
        4. Return decision with reason code

        Deny by default: if no explicit allow condition is met, access is denied.

        Args:
            request: The access request containing all trusted inputs.

        Returns:
            ElderAccessDecision indicating whether access is allowed,
            with reason code and authorization source details.
        """
        role = request.actor_role

        # Branch by actor role
        if role == ActorType.ELDER:
            if request.actor_is_elder_self:
                if request.requested_action in ELDER_SELF_PROHIBITED_ACTIONS:
                    return self._deny(SCOPE_INSUFFICIENT)
                return ElderAccessDecision(
                    allowed=True,
                    reason_code=ALLOWED,
                    expires_at=None,
                    granted_scope=[request.requested_action],
                    source_type="elder_self",
                    source_id=request.elder_id,
                )
            return self._deny(NOT_ELDER_SELF)
        if role == ActorType.FAMILY_MEMBER:
            return await self._check_family_member(request)
        elif role == ActorType.HOME_CARE_WORKER:
            return await self._check_home_care_worker(request)
        elif role == ActorType.DAYCARE_CARE_WORKER:
            return await self._check_daycare_care_worker(request)
        elif role == ActorType.SYSTEM_SERVICE:
            return await self._check_system_service(request)
        elif role == ActorType.ADMIN:
            return self._deny(ADMIN_DEFERRED)
        else:
            return self._deny(UNKNOWN_ROLE)

    # --- Private: Role-specific authorization branches ---

    #: Relationship types a FAMILY_MEMBER actor may hold over an elder.
    _FAMILY_RELATIONSHIP_TYPES = (
        RelationshipType.FAMILY_SHARE,
        RelationshipType.LEGAL_REPRESENTATIVE,
    )

    async def _check_family_member(self, request: ElderAccessRequest) -> ElderAccessDecision:
        """Check FAMILY_MEMBER authorization via CareRelationship.

        Accepts either FAMILY_SHARE or LEGAL_REPRESENTATIVE, because the
        baseline models legal representation as a relationship rather than an
        actor type.

        Conditions (all must hold for at least one relationship):
        - CareRelationship exists with one of the accepted relationship types
        - status=ACTIVE
        - effective_from <= current_time
        - effective_to IS NULL OR current_time < effective_to
        - actor_id, tenant_id, elder_id match
        - requested_action IN scope

        Every accepted type is examined before denying, so holding a
        FAMILY_SHARE relationship whose scope is too narrow does not mask a
        LEGAL_REPRESENTATIVE relationship that does grant the action.
        """
        found_any = False

        for relationship_type in self._FAMILY_RELATIONSHIP_TYPES:
            relationship = await self._care_relationship_repo.find_valid_for_actor(
                actor_id=request.actor_id,
                elder_id=request.elder_id,
                relationship_type=relationship_type.value,
                current_time=request.current_time,
            )

            if relationship is None:
                continue

            found_any = True
            decision = self._check_relationship_scope(request, relationship)
            if decision.allowed:
                return decision

        # A relationship existed but none covered the action → scope problem.
        # No relationship at all → the actor has no link to this elder.
        return self._deny(SCOPE_INSUFFICIENT if found_any else NO_VALID_RELATIONSHIP)

    async def _check_home_care_worker(self, request: ElderAccessRequest) -> ElderAccessDecision:
        """Check HOME_CARE_WORKER authorization via CareAssignment.

        Conditions (all must hold):
        - CareAssignment exists with status IN (CONFIRMED, IN_PROGRESS)
        - worker_id == actor_id
        - service_start <= current_time
        - current_time < service_end (strict <)
        - tenant_id matches
        - elder_id matches
        - requested_action IN service_scope
        """
        assignment = await self._care_assignment_repo.find_valid_for_worker(
            worker_id=request.actor_id,
            elder_id=request.elder_id,
            current_time=request.current_time,
        )

        if assignment is None:
            return self._deny(NO_VALID_ASSIGNMENT)

        return self._check_assignment_scope(request, assignment)

    async def _check_daycare_care_worker(self, request: ElderAccessRequest) -> ElderAccessDecision:
        """Check DAYCARE_CARE_WORKER authorization — three-way verification.

        Three conditions must ALL be satisfied:
        1. Active TenantMembership (actor + tenant)
        2. CareRelationship with type=DAYCARE_ASSIGNMENT (validates elder link)
        3. Active CareUnitMembership for the relationship's care_unit_id

        The order is designed to fail fast on cheap checks first:
        - TenantMembership is a simple lookup
        - CareRelationship query finds the relationship and its care_unit_id
        - CareUnitMembership uses the care_unit_id from the relationship
        """
        # Step 1: Check TenantMembership is ACTIVE
        membership = await self._tenant_membership_repo.get_active_membership(
            actor_id=request.actor_id,
            tenant_id=request.tenant_id,
            role_code=request.actor_role,
            current_time=request.current_time,
        )
        if membership is None:
            return self._deny(NO_TENANT_MEMBERSHIP)

        # Step 2: Query CareRelationship (DAYCARE_ASSIGNMENT)
        relationship = await self._care_relationship_repo.find_valid_for_actor(
            actor_id=request.actor_id,
            elder_id=request.elder_id,
            relationship_type=RelationshipType.DAYCARE_ASSIGNMENT.value,
            current_time=request.current_time,
        )
        if relationship is None:
            return self._deny(NO_VALID_RELATIONSHIP)

        # Step 3: Check CareUnitMembership for the Elder's Care Unit
        # The care_unit_id is obtained from the CareRelationship
        if relationship.care_unit_id is None:
            # Relationship has no care_unit_id — cannot verify unit membership
            return self._deny(WRONG_CARE_UNIT)

        is_unit_member = await self._care_unit_membership_repo.is_member(
            actor_id=request.actor_id,
            care_unit_id=relationship.care_unit_id,
            tenant_id=request.tenant_id,
            role_code=request.actor_role,
            current_time=request.current_time,
        )
        if not is_unit_member:
            return self._deny(WRONG_CARE_UNIT)

        # All three conditions passed — check scope
        return self._check_relationship_scope(request, relationship)

    async def _check_system_service(self, request: ElderAccessRequest) -> ElderAccessDecision:
        """Authorize a trusted service identity only through live tenant and elder scope."""
        membership = await self._tenant_membership_repo.get_active_membership(
            actor_id=request.actor_id,
            tenant_id=request.tenant_id,
            role_code=request.actor_role,
            current_time=request.current_time,
        )
        if membership is None:
            return self._deny(NO_TENANT_MEMBERSHIP)
        relationship = await self._care_relationship_repo.find_valid_for_actor(
            actor_id=request.actor_id,
            elder_id=request.elder_id,
            relationship_type=RelationshipType.HOME_CARE_ASSIGNMENT.value,
            current_time=request.current_time,
        )
        if relationship is None:
            return self._deny(NO_VALID_RELATIONSHIP)
        return self._check_relationship_scope(request, relationship)

    # --- Private: Scope checking helpers ---

    def _check_relationship_scope(
        self, request: ElderAccessRequest, relationship
    ) -> ElderAccessDecision:
        """Verify requested_action is in the relationship's scope.

        Args:
            request: The access request.
            relationship: The CareRelationship ORM instance.

        Returns:
            ALLOWED decision if scope matches, SCOPE_INSUFFICIENT otherwise.
        """
        scope = relationship.scope or []

        if not scope:
            return self._deny(SCOPE_INSUFFICIENT)

        if request.requested_action not in scope:
            return self._deny(SCOPE_INSUFFICIENT)

        return ElderAccessDecision(
            allowed=True,
            reason_code=ALLOWED,
            expires_at=relationship.effective_to,
            granted_scope=list(scope),
            source_type="relationship",
            source_id=relationship.id,
        )

    def _check_assignment_scope(
        self, request: ElderAccessRequest, assignment
    ) -> ElderAccessDecision:
        """Verify requested_action is in the assignment's service_scope.

        Args:
            request: The access request.
            assignment: The CareAssignment ORM instance.

        Returns:
            ALLOWED decision if scope matches, SCOPE_INSUFFICIENT otherwise.
        """
        scope = assignment.service_scope or []

        if not scope:
            return self._deny(SCOPE_INSUFFICIENT)

        if request.requested_action not in scope:
            return self._deny(SCOPE_INSUFFICIENT)

        return ElderAccessDecision(
            allowed=True,
            reason_code=ALLOWED,
            expires_at=assignment.service_end,
            granted_scope=list(scope),
            source_type="assignment",
            source_id=assignment.id,
        )

    # --- Private: Deny helper ---

    @staticmethod
    def _deny(reason_code: str) -> ElderAccessDecision:
        """Create a deny decision with the given reason code.

        Args:
            reason_code: Machine-readable reason for denial.

        Returns:
            ElderAccessDecision with allowed=False.
        """
        return ElderAccessDecision(
            allowed=False,
            reason_code=reason_code,
            expires_at=None,
            granted_scope=[],
            source_type=None,
            source_id=None,
        )
