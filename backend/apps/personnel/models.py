"""
Personnel Management module models.

Personnel.status drives the Dashboard's "Personnel summary" widget, and
Personnel.unit/qualifications feed Vehicle/Aircraft/Mission assignment in
later phases.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


class Rank(BaseModel):
    """Military/organizational rank, ordered for sorting (e.g. seniority)."""

    name = models.CharField(max_length=100, unique=True)
    abbreviation = models.CharField(max_length=20, unique=True)
    order = models.PositiveIntegerField(default=0, help_text='Lower number = more senior, used for sorting.')

    class Meta(BaseModel.Meta):
        ordering = ['order', 'name']

    def __str__(self):
        return self.abbreviation


class Unit(BaseModel):
    """
    An organizational unit / Area of Responsibility (AOR), arranged in an
    echelon hierarchy: HPAF > Command > Wing > Group > Squadron.

    `parent_unit` is the "mother unit". A mother unit has visibility over
    every unit beneath it in the tree (see get_descendant_ids / apps.core
    .permissions.UnitScopedQuerysetMixin) and its AOR is treated as the
    consolidation (union) of its subordinates' AOR boundaries — see
    apps.gis.views.AORBoundaryViewSet.consolidated.
    """

    class Category(models.TextChoices):
        HPAF = 'HPAF', 'HPAF'
        COMMAND = 'COMMAND', 'Command'
        WING = 'WING', 'Wing'
        GROUP = 'GROUP', 'Group'
        SQUADRON = 'SQUADRON', 'Squadron'

    # Echelon depth, used to validate that a child unit sits strictly below
    # its parent in the hierarchy (lower number = higher echelon).
    CATEGORY_RANK = {
        Category.HPAF: 0,
        Category.COMMAND: 1,
        Category.WING: 2,
        Category.GROUP: 3,
        Category.SQUADRON: 4,
    }

    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=20, unique=True)
    category = models.CharField(
        max_length=20, choices=Category.choices, blank=True,
        help_text='Echelon: HPAF > Command > Wing > Group > Squadron.',
    )
    parent_unit = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='sub_units',
        help_text='The "mother unit" — one echelon up the hierarchy.',
    )
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        ordering = ['name']
        indexes = [models.Index(fields=['category']), models.Index(fields=['parent_unit'])]

    def __str__(self):
        return f'{self.code} — {self.name}'

    def clean(self):
        super().clean()
        if self.parent_unit and self.category and self.parent_unit.category:
            child_rank = self.CATEGORY_RANK.get(self.category)
            parent_rank = self.CATEGORY_RANK.get(self.parent_unit.category)
            if child_rank is not None and parent_rank is not None and child_rank <= parent_rank:
                raise ValidationError(
                    f'A {self.get_category_display()} cannot be subordinate to a '
                    f'{self.parent_unit.get_category_display()} — the parent must be a higher echelon.'
                )

    def get_descendant_ids(self, include_self=True):
        """
        All unit ids beneath this one in the hierarchy (recursively), i.e.
        everything this unit has "mother unit" visibility over. Organizational
        trees are small (tens of units), so a straightforward Python
        traversal is used rather than a recursive SQL CTE.
        """
        ids = {self.id} if include_self else set()
        frontier = [self.id]
        while frontier:
            children = list(Unit.objects.filter(parent_unit_id__in=frontier).values_list('id', flat=True))
            new_children = [c for c in children if c not in ids]
            ids.update(new_children)
            frontier = new_children
        return ids

    def get_all_descendants(self, include_self=True):
        return Unit.objects.filter(id__in=self.get_descendant_ids(include_self=include_self))


class Section(BaseModel):
    """A sub-organizational section within a Unit (e.g. 'Transportation', 'Aviation Ops')."""

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='sections')
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        ordering = ['unit__name', 'name']
        constraints = [
            models.UniqueConstraint(fields=['unit', 'name'], name='unique_section_name_per_unit'),
        ]

    def __str__(self):
        return f'{self.unit.code} / {self.name}'


class Position(BaseModel):
    """A duty/billet position, e.g. 'Squad Leader', 'Aircraft Commander'."""

    title = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        ordering = ['title']

    def __str__(self):
        return self.title


class Qualification(BaseModel):
    """A certification/qualification personnel can hold (e.g. 'Airborne', 'CDL')."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    validity_period_days = models.PositiveIntegerField(
        null=True, blank=True, help_text='If set, qualification expires this many days after issue.'
    )

    class Meta(BaseModel.Meta):
        ordering = ['name']

    def __str__(self):
        return self.name


class Personnel(BaseModel):
    """A service member/employee tracked by the Personnel Management module."""

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        ON_LEAVE = 'ON_LEAVE', 'On Leave'
        DEPLOYED = 'DEPLOYED', 'Deployed'
        TRAINING = 'TRAINING', 'Training'
        MEDICAL = 'MEDICAL', 'Medical'
        SEPARATED = 'SEPARATED', 'Separated'

    service_number = models.CharField(max_length=30, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    rank = models.ForeignKey(Rank, on_delete=models.PROTECT, related_name='personnel')
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='personnel')
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True, related_name='personnel')
    qualifications = models.ManyToManyField(Qualification, blank=True, related_name='personnel')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    date_of_birth = models.DateField(null=True, blank=True)
    contact_number = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    date_enlisted = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to='personnel_photos/', null=True, blank=True)
    linked_account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='personnel_record',
        help_text='Optional link to this person\'s login account.',
    )
    remarks = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        verbose_name_plural = 'Personnel'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['unit', 'status']),
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self):
        return f'{self.rank.abbreviation} {self.last_name}, {self.first_name} ({self.service_number})'

    @property
    def full_name(self):
        parts = [self.last_name, ', ', self.first_name]
        if self.middle_name:
            parts.append(f' {self.middle_name[0]}.')
        return ''.join(parts)
