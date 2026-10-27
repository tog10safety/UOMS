"""
Shared abstract base models and the system-wide audit log.

Every domain model in UOMS should inherit from `BaseModel` so that we get
consistent UUID primary keys, timestamps, and soft-delete semantics across
Personnel, Vehicles, Aircraft, Missions, Armory, Inventory, and GIS records.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.core.rbac import Action, Module


class BaseModel(models.Model):
    """Abstract base providing a UUID PK and timestamps."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-delete flag.",
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class RolePermission(models.Model):
    """Configurable module and action permissions for each role."""

    id = models.BigAutoField(primary_key=True)
    role = models.CharField(max_length=20)
    module = models.CharField(max_length=30, choices=Module.choices)
    action = models.CharField(max_length=20, choices=Action.choices)
    is_granted = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "module", "action"],
                name="unique_role_module_action",
            ),
        ]
        indexes = [
            models.Index(fields=["role", "module", "action"]),
        ]

    def __str__(self):
        return (
            f"{self.role}: {self.module}.{self.action} "
            f"= {self.is_granted}"
        )


class AuditLog(models.Model):
    """Records who did what, when, and from where."""

    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        LOGIN = "LOGIN", "Login"
        LOGIN_FAILED = "LOGIN_FAILED", "Login Failed"
        LOGOUT = "LOGOUT", "Logout"
        APPROVE = "APPROVE", "Approve"
        REJECT = "REJECT", "Reject"
        ISSUE = "ISSUE", "Issue"
        RETURN = "RETURN", "Return"
        OTHER = "OTHER", "Other"

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        default=Action.OTHER,
    )
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    method = models.CharField(max_length=10, blank=True)
    path = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["model_name", "object_id"]),
        ]

    def __str__(self):
        actor = self.user.username if self.user else "anonymous"
        return (
            f"[{self.created_at:%Y-%m-%d %H:%M}] "
            f"{actor} {self.action} {self.model_name} "
            f"{self.object_id}"
        )

class Notification(BaseModel):
    """
    In-app notification for one user. UOMS had no general notification mechanism (only the MRM's feedback marker
    for safety officers), so this is the single shared one. Always create through `apps.core.notifications.notify`,
    which defers delivery until the surrounding database transaction has committed.
    """

    class Kind(models.TextChoices):
        MISSION_APPROVAL_REQUEST = 'MISSION_APPROVAL_REQUEST', 'Mission awaiting your approval'
        MISSION_APPROVED = 'MISSION_APPROVED', 'Mission approved'
        MISSION_REJECTED = 'MISSION_REJECTED', 'Mission rejected'
        MRM_PREPARATION_REQUEST = 'MRM_PREPARATION_REQUEST', 'MRM to prepare'
        GENERAL = 'GENERAL', 'General'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=40, choices=Kind.choices, default=Kind.GENERAL)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True, help_text='In-app path, e.g. /missions/<id>.')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    dedupe_key = models.CharField(
        max_length=120, blank=True,
        help_text='When set, the same user never receives two notifications with this key (prevents duplicates on retries).',
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'is_read', '-created_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'dedupe_key'], condition=~models.Q(dedupe_key=''), name='unique_notification_dedupe_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.user_id}: {self.title}'
