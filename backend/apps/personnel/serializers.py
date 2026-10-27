from rest_framework import serializers

from .models import Personnel, Position, Qualification, Rank, Section, Unit


class RankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rank
        fields = ['id', 'name', 'abbreviation', 'order', 'is_active']


class UnitSerializer(serializers.ModelSerializer):
    parent_unit_name = serializers.CharField(source='parent_unit.name', read_only=True, default=None)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    subordinate_count = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = [
            'id', 'name', 'code', 'category', 'category_display', 'parent_unit', 'parent_unit_name',
            'subordinate_count', 'description', 'is_active',
        ]

    def get_subordinate_count(self, obj):
        # Descendant count excluding self.
        return len(obj.get_descendant_ids(include_self=False))

    def validate(self, attrs):
        category = attrs.get('category', getattr(self.instance, 'category', ''))
        parent_unit = attrs.get('parent_unit', getattr(self.instance, 'parent_unit', None))

        if parent_unit and category and parent_unit.category:
            child_rank = Unit.CATEGORY_RANK.get(category)
            parent_rank = Unit.CATEGORY_RANK.get(parent_unit.category)
            if child_rank is not None and parent_rank is not None and child_rank <= parent_rank:
                raise serializers.ValidationError(
                    f'A {Unit.Category(category).label} cannot be subordinate to a '
                    f'{Unit.Category(parent_unit.category).label} — the parent must be a higher echelon.'
                )

        # Prevent a unit from becoming its own ancestor (would create a cycle).
        if self.instance and parent_unit:
            if parent_unit.id == self.instance.id:
                raise serializers.ValidationError('A unit cannot be its own parent.')
            if parent_unit.id in self.instance.get_descendant_ids(include_self=False):
                raise serializers.ValidationError('Cannot set a subordinate unit as the parent — this would create a cycle.')

        return attrs


class SectionSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)

    class Meta:
        model = Section
        fields = ['id', 'name', 'code', 'unit', 'unit_name', 'description', 'is_active']


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ['id', 'title', 'description', 'is_active']


class QualificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Qualification
        fields = ['id', 'name', 'description', 'validity_period_days', 'is_active']


class PersonnelListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views / dashboard widgets."""

    full_name = serializers.CharField(read_only=True)
    rank_abbreviation = serializers.CharField(source='rank.abbreviation', read_only=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    position_title = serializers.CharField(source='position.title', read_only=True, default=None)
    has_account = serializers.SerializerMethodField()
    mrm_ready = serializers.SerializerMethodField()

    class Meta:
        model = Personnel
        fields = [
            'id', 'service_number', 'full_name', 'rank_abbreviation',
            'unit_name', 'position_title', 'status', 'is_active', 'has_account', 'mrm_ready',
        ]

    def get_has_account(self, obj):
        return obj.linked_account_id is not None

    def get_mrm_ready(self, obj):
        """True when this person has an active account that may author MRM forms (eligible to be a mission's MRM preparer)."""
        account = obj.linked_account
        if account is None or not account.is_active:
            return False
        from apps.mrm.access import can_author

        return can_author(account)


class PersonnelDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Personnel
        fields = [
            'id', 'service_number', 'first_name', 'last_name', 'middle_name', 'full_name',
            'rank', 'unit', 'position', 'qualifications', 'status', 'date_of_birth',
            'contact_number', 'email', 'date_enlisted', 'photo', 'linked_account',
            'remarks', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_service_number(self, value):
        qs = Personnel.objects.filter(service_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A personnel record with this service number already exists.')
        return value
