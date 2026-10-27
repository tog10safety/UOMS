"""
Seeds baseline reference data + a few demo records so the dashboard has
something to display right after a fresh install.

Usage:
    python manage.py seed_demo_data
"""
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import LineString, Point, Polygon
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.aircraft.models import Aircraft, Flight, FlightCrewAssignment
from apps.armory.models import AmmunitionStock, Firearm
from apps.gis.models import AORBoundary, Checkpoint, LandingZone, MapHazard, MapLayer, Route
from apps.inventory.models import InventoryItem, ItemCategory
from apps.missions.models import HazardAssessment, Mission, MissionApprovalLog
from apps.personnel.models import Personnel, Position, Rank, Section, Unit
from apps.risk.models import RiskAlert
from apps.vehicles.models import Trip, Vehicle, VehicleMaintenanceRecord

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed baseline reference data and demo records for UOMS.'

    @transaction.atomic
    def handle(self, *args, **options):
        from django.core.management import call_command
        call_command('seed_permissions')

        units = self._seed_units()
        sections = self._seed_sections(units)
        self._seed_users(units, sections)
        ranks = self._seed_ranks()
        positions = self._seed_positions()
        personnel = self._seed_personnel(ranks, units, positions)
        self._seed_vehicles(personnel)
        self._seed_aircraft(units)
        missions = self._seed_missions()
        self._seed_risk_alerts(missions)
        self._seed_trips_and_maintenance(personnel, missions)
        self._seed_flights(units, personnel, missions)
        self._seed_hazard_assessments(missions, personnel)
        self._seed_armory(units, personnel)
        self._seed_inventory(units, personnel)
        self._seed_gis(units, personnel)
        self.stdout.write(self.style.SUCCESS('Demo data seeded successfully.'))

    def _seed_sections(self, units):
        data = [
            ('Transportation', 'MTC-1'),
            ('Aviation Operations', 'AVN-1'),
        ]
        sections = {}
        for name, unit_code in data:
            unit = units.get(unit_code)
            if not unit:
                continue
            section, _ = Section.objects.get_or_create(name=name, unit=unit)
            sections[name] = section
        return sections

    def _seed_users(self, units, sections):
        if not User.objects.filter(username='admin').exists():
            self._admin_user = User.objects.create_superuser(
                username='admin', email='admin@uoms.local', password='ChangeMe!2024',
            )
            self.stdout.write('Created superuser "admin" / password "ChangeMe!2024" (change immediately).')
        else:
            self._admin_user = User.objects.get(username='admin')

        demo_accounts = [
            # username, role, unit code, section name
            ('commander1', 'COMMANDER', 'HQ-1', None),
            ('staff1', 'STAFF', 'MTC-1', 'Transportation'),
            ('operator1', 'OPERATOR', 'AVN-1', 'Aviation Operations'),
            ('viewer1', 'VIEWER', 'HQ-1', None),
        ]
        for username, role, unit_code, section_name in demo_accounts:
            if not User.objects.filter(username=username).exists():
                User.objects.create_user(
                    username=username, email=f'{username}@uoms.local',
                    password='ChangeMe!2024', role=role,
                    unit=units.get(unit_code),
                    section=sections.get(section_name) if section_name else None,
                )

    def _seed_ranks(self):
        data = [('Private', 'PVT', 10), ('Corporal', 'CPL', 8), ('Sergeant', 'SGT', 6),
                ('Lieutenant', 'LT', 4), ('Captain', 'CPT', 3), ('Major', 'MAJ', 2), ('Colonel', 'COL', 1)]
        ranks = {}
        for name, abbr, order in data:
            rank, _ = Rank.objects.get_or_create(abbreviation=abbr, defaults={'name': name, 'order': order})
            ranks[abbr] = rank
        return ranks

    def _seed_units(self):
        """
        Builds a realistic HPAF > Command > Wing > Group > Squadron tree.
        Existing unit codes (HQ-1, AVN-1, MTC-1) are preserved — everything
        elsewhere in this script that references them keeps working — they're
        simply slotted into the hierarchy alongside two new Command-level
        units and two new leaf units, to give the consolidation feature
        something real to consolidate.
        """
        units = {}

        def make(name, code, category, parent_code=None):
            unit, _ = Unit.objects.get_or_create(
                code=code,
                defaults={'name': name, 'category': category, 'parent_unit': units.get(parent_code)},
            )
            # Backfill category/parent on a pre-existing row from an earlier seed run.
            changed = False
            if not unit.category:
                unit.category = category
                changed = True
            if unit.parent_unit_id is None and parent_code and units.get(parent_code):
                unit.parent_unit = units[parent_code]
                changed = True
            if changed:
                unit.save(update_fields=['category', 'parent_unit'])
            units[code] = unit
            return unit

        make('Headquarters, Philippine Air Force', 'HPAF', Unit.Category.HPAF)
        make('Air Mobility Command', 'AMC', Unit.Category.COMMAND, 'HPAF')
        make('Ground Forces Command', 'GFC', Unit.Category.COMMAND, 'HPAF')

        make('Aviation Wing', 'AVN-1', Unit.Category.WING, 'AMC')
        make('1st Aviation Group', 'AVG-1', Unit.Category.GROUP, 'AVN-1')
        make('Aviation Squadron Alpha', 'AVS-A', Unit.Category.SQUADRON, 'AVG-1')
        make('Aviation Squadron Bravo', 'AVS-B', Unit.Category.SQUADRON, 'AVG-1')

        make('1st Infantry Battalion', 'HQ-1', Unit.Category.WING, 'GFC')
        make('Motor Transport Company', 'MTC-1', Unit.Category.SQUADRON, 'HQ-1')

        return units

    def _seed_positions(self):
        data = ['Squad Leader', 'Driver', 'Aircraft Commander', 'Armorer', 'Supply Officer']
        positions = {}
        for title in data:
            pos, _ = Position.objects.get_or_create(title=title)
            positions[title] = pos
        return positions

    def _seed_personnel(self, ranks, units, positions):
        data = [
            ('P-00001', 'Dela Cruz', 'Juan', ranks['SGT'], units['HQ-1'], positions['Squad Leader'], 'ACTIVE'),
            ('P-00002', 'Santos', 'Maria', ranks['CPL'], units['MTC-1'], positions['Driver'], 'ACTIVE'),
            ('P-00003', 'Reyes', 'Pedro', ranks['CPT'], units['AVN-1'], positions['Aircraft Commander'], 'DEPLOYED'),
            ('P-00004', 'Garcia', 'Ana', ranks['PVT'], units['HQ-1'], positions['Armorer'], 'TRAINING'),
        ]
        personnel = {}
        for svc_no, last, first, rank, unit, position, status in data:
            person, _ = Personnel.objects.get_or_create(
                service_number=svc_no,
                defaults={
                    'last_name': last, 'first_name': first, 'rank': rank,
                    'unit': unit, 'position': position, 'status': status,
                },
            )
            personnel[svc_no] = person
        return personnel

    def _seed_vehicles(self, personnel):
        data = [
            ('MTC-101', 'Available', personnel['P-00002'], (121.0437, 14.6760)),
            ('MTC-102', 'On Mission', None, (121.0500, 14.6800)),
        ]
        for plate, status_label, driver, coords in data:
            status = status_label.upper().replace(' ', '_')
            Vehicle.objects.get_or_create(
                plate_number=plate,
                defaults={
                    'status': status, 'assigned_driver': driver,
                    'vehicle_type': 'Truck', 'last_known_location': Point(*coords),
                },
            )

    def _seed_aircraft(self, units):
        data = [
            ('RP-C1234', 'Helicopter', 'GROUNDED', units['AVN-1']),
            ('RP-C5678', 'Fixed Wing', 'SCHEDULED', units['AVN-1']),
        ]
        aircraft = {}
        for tail, ac_type, status, unit in data:
            ac, _ = Aircraft.objects.get_or_create(
                tail_number=tail, defaults={'aircraft_type': ac_type, 'flying_status': status, 'base_unit': unit},
            )
            aircraft[tail] = ac
        return aircraft

    def _seed_missions(self):
        data = [
            ('Convoy Escort Alpha', 'ONGOING', (121.05, 14.68)),
            ('Aerial Reconnaissance Bravo', 'PLANNED', (121.02, 14.70)),
        ]
        missions = {}
        for name, status, coords in data:
            mission, _ = Mission.objects.get_or_create(
                name=name, defaults={'status': status, 'location': Point(*coords)},
            )
            missions[name] = mission
        return missions

    def _seed_hazard_assessments(self, missions, personnel):
        convoy = missions.get('Convoy Escort Alpha')
        if not convoy:
            return

        hazard, _ = HazardAssessment.objects.get_or_create(
            mission=convoy,
            hazard_description='Ambush along Route Delta due to known insurgent activity',
            defaults={
                'category': 'ENEMY_ACTION',
                'probability': 'OCCASIONAL',
                'severity': 'CRITICAL',
                'existing_controls': 'Armed escort, pre-mission route reconnaissance',
                'additional_controls': 'Add QRF on standby, coordinate with adjacent unit for route clearance',
                'residual_probability': 'SELDOM',
                'residual_severity': 'CRITICAL',
            },
        )

        weather_hazard, _ = HazardAssessment.objects.get_or_create(
            mission=convoy,
            hazard_description='Reduced visibility due to seasonal heavy rainfall',
            defaults={
                'category': 'WEATHER',
                'probability': 'LIKELY',
                'severity': 'MODERATE',
                'existing_controls': 'Reduced convoy speed, increased vehicle interval',
                'additional_controls': 'Delay departure if visibility drops below 200m',
                'residual_probability': 'UNLIKELY',
                'residual_severity': 'MODERATE',
            },
        )

        if convoy.risk_review_status == Mission.RiskReviewStatus.DRAFT:
            convoy.risk_review_status = Mission.RiskReviewStatus.SUBMITTED
            convoy.submitted_by = self._admin_user
            convoy.submitted_at = timezone.now()
            convoy.save(update_fields=['risk_review_status', 'submitted_by', 'submitted_at'])
            MissionApprovalLog.objects.get_or_create(
                mission=convoy, action='SUBMITTED', actor=self._admin_user,
                defaults={'comments': 'Auto-submitted by seed script for demo purposes.'},
            )

    def _seed_risk_alerts(self, missions):
        data = [
            ('Convoy Escort Alpha', 'Poor visibility due to weather', 'HIGH'),
            ('Aerial Reconnaissance Bravo', 'Unconfirmed airspace restriction', 'MEDIUM'),
        ]
        for mission_name, title, severity in data:
            RiskAlert.objects.get_or_create(
                title=title,
                defaults={'mission': missions.get(mission_name), 'severity': severity},
            )

    def _seed_trips_and_maintenance(self, personnel, missions):
        vehicle = Vehicle.objects.filter(plate_number='MTC-101').first()
        if not vehicle:
            return

        Trip.objects.get_or_create(
            vehicle=vehicle,
            origin='Camp HQ',
            destination='Checkpoint Delta',
            defaults={
                'driver': personnel['P-00002'],
                'mission': missions.get('Convoy Escort Alpha'),
                'purpose': 'Resupply run',
                'status': 'COMPLETED',
                'start_time': timezone.now() - timezone.timedelta(days=2, hours=3),
                'end_time': timezone.now() - timezone.timedelta(days=2),
                'start_odometer_km': 10230,
                'end_odometer_km': 10280,
            },
        )

        VehicleMaintenanceRecord.objects.get_or_create(
            vehicle=vehicle,
            maintenance_type='OIL_CHANGE',
            service_date=(timezone.now() - timezone.timedelta(days=10)).date(),
            defaults={
                'description': 'Routine oil and filter change',
                'performed_by': 'Motor Pool Workshop',
                'odometer_at_service_km': 10200,
            },
        )

    def _seed_flights(self, units, personnel, missions):
        aircraft = Aircraft.objects.filter(tail_number='RP-C5678').first()
        if not aircraft:
            return

        flight, _ = Flight.objects.get_or_create(
            flight_number='UOMS-F001',
            defaults={
                'aircraft': aircraft,
                'mission': missions.get('Aerial Reconnaissance Bravo'),
                'unit': units.get('AVN-1'),
                'origin': 'Clark Air Base',
                'destination': 'Basa Air Base',
                'scheduled_departure': timezone.now() + timezone.timedelta(hours=2),
                'scheduled_arrival': timezone.now() + timezone.timedelta(hours=3),
                'status': 'SCHEDULED',
                'caap_flight_plan_number': 'CAAP-2026-0451',
            },
        )

        pilot = personnel.get('P-00003')
        if pilot:
            FlightCrewAssignment.objects.get_or_create(
                flight=flight, personnel=pilot, defaults={'crew_role': 'PIC'},
            )

    def _seed_armory(self, units, personnel):
        armorer = personnel.get('P-00004')
        hq = units.get('HQ-1')

        Firearm.objects.get_or_create(
            serial_number='RA-556-00123',
            defaults={
                'firearm_type': 'Rifle', 'make': 'Colt', 'model': 'M4A1', 'caliber': '5.56mm',
                'status': 'SERVICEABLE', 'unit': hq, 'accountable_personnel': armorer,
            },
        )
        Firearm.objects.get_or_create(
            serial_number='PS-9mm-00456',
            defaults={
                'firearm_type': 'Pistol', 'make': 'Beretta', 'model': '92FS', 'caliber': '9mm',
                'status': 'SERVICEABLE', 'unit': hq, 'accountable_personnel': armorer,
            },
        )
        AmmunitionStock.objects.get_or_create(
            ammunition_type='5.56mm Ball', lot_number='LOT-2026-A1', unit=hq,
            defaults={'quantity_on_hand': 5000, 'unit_of_measure': 'rounds', 'storage_location': 'Armory Vault 1'},
        )
        AmmunitionStock.objects.get_or_create(
            ammunition_type='9mm Ball', lot_number='LOT-2026-B2', unit=hq,
            defaults={'quantity_on_hand': 80, 'unit_of_measure': 'rounds', 'storage_location': 'Armory Vault 1'},
        )

    def _seed_inventory(self, units, personnel):
        comms_cat, _ = ItemCategory.objects.get_or_create(name='Communications')
        medical_cat, _ = ItemCategory.objects.get_or_create(name='Medical')

        hq = units.get('HQ-1')
        squad_leader = personnel.get('P-00001')

        InventoryItem.objects.get_or_create(
            name='AN/PRC-152 Handheld Radio',
            property_number='COM-2026-0011',
            defaults={
                'category': comms_cat, 'item_type': 'EQUIPMENT', 'unit_of_measure': 'pcs',
                'quantity_on_hand': 1, 'condition': 'SERVICEABLE', 'unit': hq,
                'storage_location': 'Comms Locker', 'accountable_personnel': squad_leader,
            },
        )
        InventoryItem.objects.get_or_create(
            name='First Aid Kit, Individual',
            defaults={
                'category': medical_cat, 'item_type': 'SUPPLY', 'unit_of_measure': 'kits',
                'quantity_on_hand': 8, 'reorder_level': 10, 'condition': 'SERVICEABLE',
                'unit': hq, 'storage_location': 'Medical Supply Room',
            },
        )

    def _seed_gis(self, units, personnel):
        hq = units.get('HQ-1')

        for layer_type, name, color in [
            ('AOR_BOUNDARIES', 'AOR Boundaries', '#22d3ee'),
            ('CHECKPOINTS', 'Checkpoints', '#f59e0b'),
            ('LANDING_ZONES', 'Landing Zones', '#22c55e'),
            ('HAZARDS', 'Hazards', '#ef4444'),
            ('ROUTES', 'Routes', '#a78bfa'),
            ('MISSIONS', 'Mission Locations', '#f59e0b'),
            ('VEHICLES', 'Vehicle Positions', '#22d3ee'),
        ]:
            MapLayer.objects.get_or_create(layer_type=layer_type, defaults={'name': name, 'color': color})

        AORBoundary.objects.get_or_create(
            name='HQ Battalion AOR',
            defaults={
                'unit': hq, 'color': '#22d3ee',
                'boundary': Polygon((
                    (120.98, 14.64), (121.10, 14.64), (121.10, 14.74), (120.98, 14.74), (120.98, 14.64),
                )),
            },
        )

        # Two adjacent squadron-level AORs under Aviation Squadron Alpha/Bravo —
        # both subordinate to 1st Aviation Group -> Aviation Wing. Querying
        # /gis/aor-boundaries/consolidated/?unit=<AVG-1 or AVN-1 id> unions
        # these two into one consolidated boundary at the mother-unit level.
        squadron_alpha = units.get('AVS-A')
        squadron_bravo = units.get('AVS-B')
        if squadron_alpha:
            AORBoundary.objects.get_or_create(
                name='Aviation Squadron Alpha AOR',
                defaults={
                    'unit': squadron_alpha, 'color': '#f59e0b',
                    'boundary': Polygon((
                        (120.90, 14.50), (120.98, 14.50), (120.98, 14.58), (120.90, 14.58), (120.90, 14.50),
                    )),
                },
            )
        if squadron_bravo:
            AORBoundary.objects.get_or_create(
                name='Aviation Squadron Bravo AOR',
                defaults={
                    'unit': squadron_bravo, 'color': '#22c55e',
                    'boundary': Polygon((
                        (120.98, 14.50), (121.06, 14.50), (121.06, 14.58), (120.98, 14.58), (120.98, 14.50),
                    )),
                },
            )

        Checkpoint.objects.get_or_create(
            name='Checkpoint Delta',
            defaults={
                'checkpoint_type': 'INSPECTION', 'location': Point(121.048, 14.676),
                'unit': hq, 'is_operational': True,
            },
        )
        Checkpoint.objects.get_or_create(
            name='ECP North',
            defaults={
                'checkpoint_type': 'ENTRY', 'location': Point(121.03, 14.70),
                'unit': hq, 'is_operational': True,
            },
        )

        LandingZone.objects.get_or_create(
            name='LZ Hawk',
            defaults={
                'lz_type': 'HELICOPTER', 'location': Point(121.02, 14.705), 'status': 'ACTIVE',
                'unit': hq, 'capacity': '2x UH-1',
            },
        )

        MapHazard.objects.get_or_create(
            name='Suspected IED — Route Delta KM 12',
            defaults={
                'hazard_type': 'IED', 'location': Point(121.055, 14.682), 'radius_meters': 200,
                'severity': 'HIGH', 'reported_by': personnel.get('P-00001'), 'reported_at': timezone.now(),
            },
        )

        Route.objects.get_or_create(
            name='Route Delta (MSR)',
            defaults={
                'route_type': 'SUPPLY', 'unit': hq,
                'path': LineString((121.0437, 14.6760), (121.05, 14.68), (121.055, 14.682)),
            },
        )
