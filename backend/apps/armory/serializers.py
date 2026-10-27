from rest_framework import serializers

from .models import AmmunitionIssuance, AmmunitionStock, ArmoryInspection, Firearm, FirearmIssuance


class FirearmSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    accountable_personnel_name = serializers.CharField(
        source='accountable_personnel.full_name', read_only=True, default=None
    )

    class Meta:
        model = Firearm
        fields = [
            'id', 'serial_number', 'firearm_type', 'make', 'model', 'caliber', 'status',
            'unit', 'unit_name', 'accountable_personnel', 'accountable_personnel_name',
            'acquisition_date', 'remarks', 'is_active', 'created_at',
        ]
        # status/accountable_personnel must only change via the issue/return/
        # inspection workflow actions (FirearmIssuanceViewSet, ArmoryInspectionViewSet),
        # not a direct edit — otherwise a user could bypass the controlled
        # status-transition workflow the spec requires.
        read_only_fields = ['id', 'status', 'accountable_personnel', 'created_at']


class AmmunitionStockSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True, default=None)
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = AmmunitionStock
        fields = [
            'id', 'ammunition_type', 'lot_number', 'unit', 'unit_name', 'quantity_on_hand',
            'unit_of_measure', 'storage_location', 'expiration_date', 'is_low_stock',
            'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_is_low_stock(self, obj):
        return obj.quantity_on_hand < 100


class FirearmIssuanceSerializer(serializers.ModelSerializer):
    firearm_serial = serializers.CharField(source='firearm.serial_number', read_only=True)
    issued_to_name = serializers.CharField(source='issued_to.full_name', read_only=True)
    issued_by_username = serializers.CharField(source='issued_by.username', read_only=True, default=None)

    class Meta:
        model = FirearmIssuance
        fields = [
            'id', 'firearm', 'firearm_serial', 'issued_to', 'issued_to_name', 'issued_by',
            'issued_by_username', 'issue_date', 'expected_return_date', 'return_date',
            'condition_on_issue', 'condition_on_return', 'status', 'purpose', 'remarks',
            'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'issued_by', 'created_at']


class FirearmReturnSerializer(serializers.Serializer):
    """Body for the /issuances/{id}/return/ action."""

    condition_on_return = serializers.CharField(required=False, allow_blank=True, default='')
    remarks = serializers.CharField(required=False, allow_blank=True, default='')


class AmmunitionIssuanceSerializer(serializers.ModelSerializer):
    ammunition_type = serializers.CharField(source='ammunition_stock.ammunition_type', read_only=True)
    issued_to_name = serializers.CharField(source='issued_to.full_name', read_only=True)

    class Meta:
        model = AmmunitionIssuance
        fields = [
            'id', 'ammunition_stock', 'ammunition_type', 'issued_to', 'issued_to_name',
            'issued_by', 'quantity', 'issue_date', 'purpose', 'remarks', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'issued_by', 'created_at']

    def validate(self, attrs):
        stock = attrs.get('ammunition_stock') or getattr(self.instance, 'ammunition_stock', None)
        quantity = attrs.get('quantity')
        if stock and quantity is not None and quantity > stock.quantity_on_hand:
            raise serializers.ValidationError(
                f'Cannot issue {quantity} rounds — only {stock.quantity_on_hand} on hand.'
            )
        return attrs


class ArmoryInspectionSerializer(serializers.ModelSerializer):
    firearm_serial = serializers.CharField(source='firearm.serial_number', read_only=True, default=None)
    inspected_by_name = serializers.CharField(source='inspected_by.full_name', read_only=True)

    class Meta:
        model = ArmoryInspection
        fields = [
            'id', 'firearm', 'firearm_serial', 'inspection_date', 'inspected_by',
            'inspected_by_name', 'result', 'findings', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
