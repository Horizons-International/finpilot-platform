"""Business logic for tenant-aware, cross-team implementation workspaces."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.implementation_workspace import (
    ImplementationWorkspace,
    ImplementationWorkspaceComment,
    ImplementationWorkspaceMember,
    ImplementationWorkspaceMilestone,
    ImplementationWorkspaceTask,
)
from app.models.user import User
from app.repositories.implementation_workspace_repository import (
    ImplementationWorkspaceRepository,
)
from app.schemas.implementation_workspace import (
    ImplementationWorkspaceCommentCreate,
    ImplementationWorkspaceCreate,
    ImplementationWorkspaceMemberCreate,
    ImplementationWorkspaceMilestoneCreate,
    ImplementationWorkspaceMilestoneUpdate,
    ImplementationWorkspaceStageUpdate,
    ImplementationWorkspaceTaskCreate,
    ImplementationWorkspaceTaskUpdate,
    ImplementationWorkspaceUpdate,
)
from app.utils.enums import UserStatus
from app.utils.errors import bad_request, conflict, forbidden, not_found
from app.utils.implementation_workspace_enums import (
    ImplementationMemberRole,
    ImplementationMemberType,
    ImplementationStage,
    ImplementationTaskCategory,
    ImplementationTaskPriority,
    ImplementationWorkStatus,
)


class ImplementationWorkspaceService:
    """Workspace use cases and their access-control rules."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ImplementationWorkspaceRepository(db)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _commit(self, workspace: ImplementationWorkspace | None = None) -> None:
        """Commit an authorized write under the workspace owner's tenant context.

        Customer and implementation-team members may belong to different tenants.
        Workspace membership is verified before reaching this method. The ORM
        tenant guard validates rows with a ``tenant_id`` against the active tenant,
        so temporarily switch only for the already-authorized owner-owned workspace
        mutation. Restore the authenticated user's tenant immediately afterward.
        """
        previous_tenant = self.db.info.get("tenant_id")
        if workspace is not None:
            self.db.info["tenant_id"] = workspace.tenant_id
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        finally:
            if previous_tenant is None:
                self.db.info.pop("tenant_id", None)
            else:
                self.db.info["tenant_id"] = previous_tenant

    def _get_workspace(
        self, workspace_id: UUID, user_id: UUID
    ) -> ImplementationWorkspace:
        workspace = self.repository.get_for_member(workspace_id, user_id)
        if workspace is None:
            # Deliberately do not reveal whether a non-member's workspace exists.
            raise not_found("Implementation workspace")
        return workspace

    def _require_role(
        self,
        workspace_id: UUID,
        user_id: UUID,
        allowed_roles: set[ImplementationMemberRole],
    ) -> tuple[ImplementationWorkspace, ImplementationWorkspaceMember]:
        workspace = self._get_workspace(workspace_id, user_id)
        membership = self.repository.get_member(workspace_id, user_id)
        if membership is None:
            raise not_found("Implementation workspace")
        if membership.role not in allowed_roles:
            raise forbidden("Your workspace role does not allow this action.")
        return workspace, membership

    def _ensure_member(self, workspace_id: UUID, user_id: UUID | None) -> None:
        if user_id is None:
            return
        if self.repository.get_member(workspace_id, user_id) is None:
            raise bad_request("Assignees must be workspace members.")

    @staticmethod
    def _enum_value(value):
        return value.value if hasattr(value, "value") else value

    # ------------------------------------------------------------------
    # Workspaces and implementation stage
    # ------------------------------------------------------------------

    def create_workspace(
        self, payload: ImplementationWorkspaceCreate, actor: User
    ) -> ImplementationWorkspace:
        if actor.is_platform_admin and payload.customer_tenant_id is None:
            raise bad_request(
                "Platform administrators must specify customer_tenant_id "
                "when creating a workspace."
            )
        customer_tenant_id = payload.customer_tenant_id or actor.tenant_id
        if not actor.is_platform_admin and customer_tenant_id != actor.tenant_id:
            raise forbidden(
                "Only platform administrators can create "
                "a workspace for another tenant."
            )
        if not self.repository.tenant_exists(customer_tenant_id):
            raise bad_request("The selected customer tenant does not exist.")

        workspace = ImplementationWorkspace(
            tenant_id=actor.tenant_id,
            customer_tenant_id=customer_tenant_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            start_date=payload.start_date,
            target_go_live_date=payload.target_go_live_date,
            created_by=actor.id,
            status=ImplementationStage.NOT_STARTED.value,
        )
        self.db.add(workspace)
        self.db.flush()

        creator_type = (
            ImplementationMemberType.CUSTOMER.value
            if actor.tenant_id == customer_tenant_id
            else ImplementationMemberType.INTERNAL.value
        )
        creator_membership = ImplementationWorkspaceMember(
            workspace_id=workspace.id,
            user_id=actor.id,
            member_type=creator_type,
            role=ImplementationMemberRole.MANAGER.value,
            invited_by=actor.id,
        )
        self.db.add(creator_membership)

        # Seed a standard plan so a new workspace is immediately actionable.
        milestone_definitions = [
            ("Configuration sign-off", "API setup and configuration are verified."),
            (
                "Integration validation",
                "Required integration paths have been validated.",
            ),
            (
                "Testing and UAT sign-off",
                "Technical tests and customer acceptance are complete.",
            ),
            (
                "Go-live approval",
                "Training, acceptance, and production readiness are approved.",
            ),
        ]
        milestones: list[ImplementationWorkspaceMilestone] = []
        for title, description in milestone_definitions:
            milestone = ImplementationWorkspaceMilestone(
                workspace_id=workspace.id,
                title=title,
                description=description,
                status=ImplementationWorkStatus.NOT_STARTED.value,
                created_by=actor.id,
            )
            self.db.add(milestone)
            milestones.append(milestone)
        self.db.flush()

        task_definitions = [
            (
                "Complete API setup and credentials",
                (
                    "Configure endpoints and verify approved "
                    "credentials in the target environment."
                ),
                ImplementationTaskCategory.TECHNICAL,
                milestones[0].id,
            ),
            (
                "Confirm environment and access configuration",
                (
                    "Validate sandbox/production configuration "
                    "and required network access."
                ),
                ImplementationTaskCategory.TECHNICAL,
                milestones[0].id,
            ),
            (
                "Complete integration connectivity tests",
                "Validate authentication, callbacks, and required data exchanges.",
                ImplementationTaskCategory.TECHNICAL,
                milestones[1].id,
            ),
            (
                "Execute end-to-end testing and resolve defects",
                "Record test results and agree on resolution for blocking issues.",
                ImplementationTaskCategory.TECHNICAL,
                milestones[2].id,
            ),
            (
                "Deliver administrator and end-user training",
                "Complete agreed training sessions and capture attendance or sign-off.",
                ImplementationTaskCategory.BUSINESS,
                milestones[3].id,
            ),
            (
                "Complete customer user acceptance testing",
                "Collect customer acceptance outcomes and document outstanding issues.",
                ImplementationTaskCategory.BUSINESS,
                milestones[2].id,
            ),
            (
                "Review and approve go-live readiness",
                (
                    "Confirm operational ownership, support "
                    "contacts, rollback plans, and approvals."
                ),
                ImplementationTaskCategory.BUSINESS,
                milestones[3].id,
            ),
        ]
        for title, description, category, milestone_id in task_definitions:
            self.db.add(
                ImplementationWorkspaceTask(
                    workspace_id=workspace.id,
                    milestone_id=milestone_id,
                    title=title,
                    description=description,
                    category=category.value,
                    status=ImplementationWorkStatus.NOT_STARTED.value,
                    priority=ImplementationTaskPriority.MEDIUM.value,
                    created_by=actor.id,
                )
            )

        self.db.flush()
        self._commit(workspace)
        return workspace

    def list_workspaces(self, user_id: UUID) -> list[ImplementationWorkspace]:
        return self.repository.list_for_user(user_id)

    def get_workspace(
        self, workspace_id: UUID, user_id: UUID
    ) -> ImplementationWorkspace:
        return self._get_workspace(workspace_id, user_id)

    def update_workspace(
        self,
        workspace_id: UUID,
        user_id: UUID,
        payload: ImplementationWorkspaceUpdate,
    ) -> ImplementationWorkspace:
        workspace, _ = self._require_role(
            workspace_id,
            user_id,
            {ImplementationMemberRole.MANAGER, ImplementationMemberRole.MEMBER},
        )
        updates = payload.model_dump(exclude_unset=True)
        non_nullable_fields = {
            "title",
            "api_setup_status",
            "integration_status",
            "testing_status",
            "training_status",
            "user_acceptance_testing_status",
            "go_live_readiness_status",
        }
        if any(key in updates and updates[key] is None for key in non_nullable_fields):
            raise bad_request(
                "Workspace title and implementation statuses cannot be null."
            )
        for key, value in updates.items():
            value = self._enum_value(value)
            setattr(workspace, key, value)
        if (
            workspace.start_date is not None
            and workspace.target_go_live_date is not None
            and workspace.target_go_live_date < workspace.start_date
        ):
            raise bad_request("Target go-live date cannot be before the start date.")
        self._commit(workspace)
        return workspace

    def update_stage(
        self,
        workspace_id: UUID,
        user_id: UUID,
        payload: ImplementationWorkspaceStageUpdate,
    ) -> ImplementationWorkspace:
        workspace, _ = self._require_role(
            workspace_id, user_id, {ImplementationMemberRole.MANAGER}
        )
        current_stage = ImplementationStage(workspace.status)
        next_stage = payload.status
        stages = list(ImplementationStage)
        current_index = stages.index(current_stage)
        next_index = stages.index(next_stage)
        if next_index == current_index:
            return workspace
        if next_index != current_index + 1:
            raise bad_request(
                f"Move implementation through the next "
                f"stage after {current_stage.value}."
            )
        if next_stage == ImplementationStage.READY_FOR_PRODUCTION:
            if (
                workspace.go_live_readiness_status
                != ImplementationWorkStatus.COMPLETED.value
            ):
                raise bad_request(
                    "Go-live readiness must be marked COMPLETED "
                    "before production readiness."
                )
            incomplete_count = self.db.scalar(
                select(func.count(ImplementationWorkspaceTask.id))
                .where(
                    ImplementationWorkspaceTask.workspace_id == workspace_id,
                    ImplementationWorkspaceTask.status
                    != ImplementationWorkStatus.COMPLETED.value,
                )
                .execution_options(
                    skip_tenant_filter=True,
                    tenant_scope_reason=(
                        "Check completion of tasks belonging to the authorized "
                        "workspace before advancing its go-live stage."
                    ),
                )
            )
            if incomplete_count:
                raise bad_request(
                    "All workspace tasks must be completed before production readiness."
                )
        workspace.status = next_stage.value
        self._commit(workspace)
        return workspace

    # ------------------------------------------------------------------
    # Collaborators
    # ------------------------------------------------------------------

    def list_members(self, workspace_id: UUID, user_id: UUID):
        self._get_workspace(workspace_id, user_id)
        return self.repository.list_members(workspace_id)

    def add_member(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        payload: ImplementationWorkspaceMemberCreate,
    ) -> ImplementationWorkspaceMember:
        workspace, _ = self._require_role(
            workspace_id, actor_id, {ImplementationMemberRole.MANAGER}
        )
        user = self.repository.get_user(payload.user_id)
        if user is None:
            raise not_found("User")
        if user.status != UserStatus.ACTIVE:
            raise bad_request(
                "Only active users can be added to an implementation workspace."
            )
        if user.tenant_id not in {workspace.tenant_id, workspace.customer_tenant_id}:
            raise bad_request(
                "Collaborators must belong to the implementation "
                "team or customer tenant."
            )
        if self.repository.get_member(workspace_id, user.id) is not None:
            raise conflict("This user is already a workspace member.")

        if workspace.tenant_id == workspace.customer_tenant_id:
            member_type = payload.member_type or ImplementationMemberType.CUSTOMER
        elif user.tenant_id == workspace.tenant_id:
            member_type = ImplementationMemberType.INTERNAL
        else:
            member_type = ImplementationMemberType.CUSTOMER
        if payload.member_type is not None and payload.member_type != member_type:
            raise bad_request(
                "The selected member type does not match the user's tenant."
            )

        member = ImplementationWorkspaceMember(
            workspace_id=workspace_id,
            user_id=user.id,
            member_type=member_type.value,
            role=payload.role.value,
            invited_by=actor_id,
        )
        self.db.add(member)
        self._commit(workspace)
        # A response needs the loaded user's public contact details.
        member.user = user
        return member

    def remove_member(self, workspace_id: UUID, actor_id: UUID, user_id: UUID) -> None:
        workspace, _ = self._require_role(
            workspace_id, actor_id, {ImplementationMemberRole.MANAGER}
        )
        member = self.repository.get_member(workspace_id, user_id)
        if member is None:
            raise not_found("Workspace member")
        if member.role == ImplementationMemberRole.MANAGER.value:
            members = self.repository.list_members(workspace_id)
            manager_count = sum(
                item.role == ImplementationMemberRole.MANAGER.value for item in members
            )
            if manager_count <= 1:
                raise bad_request("The last workspace manager cannot be removed.")
        self.db.delete(member)
        self._commit(workspace)

    # ------------------------------------------------------------------
    # Milestones
    # ------------------------------------------------------------------

    def create_milestone(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        payload: ImplementationWorkspaceMilestoneCreate,
    ) -> ImplementationWorkspaceMilestone:
        workspace, _ = self._require_role(
            workspace_id,
            actor_id,
            {ImplementationMemberRole.MANAGER, ImplementationMemberRole.MEMBER},
        )
        self._ensure_member(workspace_id, payload.assigned_to)
        milestone = ImplementationWorkspaceMilestone(
            workspace_id=workspace_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            due_date=payload.due_date,
            assigned_to=payload.assigned_to,
            created_by=actor_id,
        )
        self.db.add(milestone)
        self._commit(workspace)
        milestone.assigned_user = (
            self.repository.get_user(payload.assigned_to)
            if payload.assigned_to is not None
            else None
        )
        return milestone

    def update_milestone(
        self,
        workspace_id: UUID,
        milestone_id: UUID,
        actor_id: UUID,
        payload: ImplementationWorkspaceMilestoneUpdate,
    ) -> ImplementationWorkspaceMilestone:
        workspace, _ = self._require_role(
            workspace_id,
            actor_id,
            {ImplementationMemberRole.MANAGER, ImplementationMemberRole.MEMBER},
        )
        milestone = self.repository.get_milestone(workspace_id, milestone_id)
        if milestone is None:
            raise not_found("Implementation milestone")
        updates = payload.model_dump(exclude_unset=True)
        if any(key in updates and updates[key] is None for key in {"title", "status"}):
            raise bad_request("Milestone title and status cannot be null.")
        if "assigned_to" in updates:
            self._ensure_member(workspace_id, updates["assigned_to"])
        for key, value in updates.items():
            value = self._enum_value(value)
            setattr(milestone, key, value)
        if payload.status is not None:
            milestone.completed_at = (
                self._now()
                if payload.status == ImplementationWorkStatus.COMPLETED
                else None
            )
        self._commit(workspace)
        return milestone

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def list_tasks(self, workspace_id: UUID, user_id: UUID):
        self._get_workspace(workspace_id, user_id)
        return self.repository.list_tasks(workspace_id)

    def create_task(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        payload: ImplementationWorkspaceTaskCreate,
    ) -> ImplementationWorkspaceTask:
        workspace, _ = self._require_role(
            workspace_id,
            actor_id,
            {ImplementationMemberRole.MANAGER, ImplementationMemberRole.MEMBER},
        )
        self._ensure_member(workspace_id, payload.assigned_to)
        if (
            payload.milestone_id is not None
            and self.repository.get_milestone(workspace_id, payload.milestone_id)
            is None
        ):
            raise bad_request("Milestone must belong to the same workspace.")
        task = ImplementationWorkspaceTask(
            workspace_id=workspace_id,
            milestone_id=payload.milestone_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            category=payload.category.value,
            priority=payload.priority.value,
            status=ImplementationWorkStatus.NOT_STARTED.value,
            assigned_to=payload.assigned_to,
            due_date=payload.due_date,
            created_by=actor_id,
        )
        self.db.add(task)
        self._commit(workspace)
        task.assigned_user = (
            self.repository.get_user(payload.assigned_to)
            if payload.assigned_to is not None
            else None
        )
        return task

    def update_task(
        self,
        workspace_id: UUID,
        task_id: UUID,
        actor_id: UUID,
        payload: ImplementationWorkspaceTaskUpdate,
    ) -> ImplementationWorkspaceTask:
        workspace, _ = self._require_role(
            workspace_id,
            actor_id,
            {ImplementationMemberRole.MANAGER, ImplementationMemberRole.MEMBER},
        )
        task = self.repository.get_task(workspace_id, task_id)
        if task is None:
            raise not_found("Implementation task")
        updates = payload.model_dump(exclude_unset=True)
        non_nullable_fields = {"title", "category", "status", "priority"}
        if any(key in updates and updates[key] is None for key in non_nullable_fields):
            raise bad_request(
                "Task title, category, status, and priority cannot be null."
            )
        if "assigned_to" in updates:
            self._ensure_member(workspace_id, updates["assigned_to"])
        if "milestone_id" in updates and updates["milestone_id"] is not None:
            if (
                self.repository.get_milestone(workspace_id, updates["milestone_id"])
                is None
            ):
                raise bad_request("Milestone must belong to the same workspace.")
        for key, value in updates.items():
            value = self._enum_value(value)
            setattr(task, key, value)
        if payload.status is not None:
            task.completed_at = (
                self._now()
                if payload.status == ImplementationWorkStatus.COMPLETED
                else None
            )
        self._commit(workspace)
        if task.assigned_to is not None:
            task.assigned_user = self.repository.get_user(task.assigned_to)
        return task

    # ------------------------------------------------------------------
    # Collaboration comments
    # ------------------------------------------------------------------

    def list_comments(
        self, workspace_id: UUID, user_id: UUID, task_id: UUID | None = None
    ) -> list[ImplementationWorkspaceComment]:
        self._get_workspace(workspace_id, user_id)
        if (
            task_id is not None
            and self.repository.get_task(workspace_id, task_id) is None
        ):
            raise not_found("Implementation task")
        return self.repository.list_comments(workspace_id, task_id)

    def add_comment(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        payload: ImplementationWorkspaceCommentCreate,
    ) -> ImplementationWorkspaceComment:
        workspace, _ = self._require_role(
            workspace_id,
            actor_id,
            {ImplementationMemberRole.MANAGER, ImplementationMemberRole.MEMBER},
        )
        if (
            payload.task_id is not None
            and self.repository.get_task(workspace_id, payload.task_id) is None
        ):
            raise not_found("Implementation task")
        comment = ImplementationWorkspaceComment(
            workspace_id=workspace_id,
            task_id=payload.task_id,
            author_id=actor_id,
            body=payload.body.strip(),
        )
        self.db.add(comment)
        self._commit(workspace)
        comment.author = self.repository.get_user(actor_id)
        return comment
