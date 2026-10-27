from django.core.management.base import BaseCommand, CommandError

from apps.mrm.legacy_import import DictSource, FlaskImporter, PostgresSource


class Command(BaseCommand):
    help = (
        'Import the legacy Flask MRM database (users, units, hazard registry, MRM forms, feedback, files) into UOMS. '
        'Safe to re-run. Use --dry-run first.'
    )

    def add_arguments(self, parser):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument('--dsn', help='PostgreSQL connection string of the legacy MRM database.')
        source.add_argument('--json-dir', help='Directory of <table>.json exports (users.json, mrm_forms.json, …).')
        parser.add_argument('--static-dir', help='Legacy Flask "static" folder (contains unit_logos/).')
        parser.add_argument('--signatures-dir', help='Legacy signatures folder.')
        parser.add_argument('--pdf-dir', help='Folder holding the legacy approved MRM PDFs.')
        parser.add_argument('--no-create-units', action='store_true', help='Do not create units that have no UOMS match.')
        parser.add_argument('--skip-personnel', action='store_true', help='Do not create Personnel records from user rank/serial number.')
        parser.add_argument('--identity-map', help='JSON file {legacy_username: existing UOMS username | "NEW"} resolving ambiguous accounts.')
        parser.add_argument('--identity-review-out', help='Write the unresolved-account review file here (edit it, then pass it back as --identity-map).')
        parser.add_argument('--trust-usernames', action='store_true', help='Accept a username-only match as the same person (NOT recommended).')
        parser.add_argument('--dry-run', action='store_true', help='Run everything, then roll it back and just print the report.')

    def handle(self, *args, **opts):
        try:
            source = PostgresSource(opts['dsn']) if opts['dsn'] else DictSource.from_json_dir(opts['json_dir'])
        except Exception as exc:  # connection / path problems
            raise CommandError(f'Cannot read the legacy data: {exc}')

        identity_map = None
        if opts['identity_map']:
            import json
            with open(opts['identity_map'], encoding='utf-8') as handle:
                identity_map = json.load(handle)

        importer = FlaskImporter(
            source, static_dir=opts['static_dir'], signatures_dir=opts['signatures_dir'], pdf_dir=opts['pdf_dir'],
            create_units=not opts['no_create_units'], create_personnel=not opts['skip_personnel'],
            dry_run=opts['dry_run'], log=self.stdout.write, identity_map=identity_map, trust_usernames=opts['trust_usernames'],
        )
        report = importer.run()

        self.stdout.write(self.style.SUCCESS('DRY RUN — nothing was saved.' if opts['dry_run'] else 'Import complete.'))
        for key in ('units_matched', 'units_created', 'users_matched', 'users_created', 'passwords_converted',
                    'passwords_need_reset', 'personnel_created', 'assignments', 'logos', 'hazards', 'forms',
                    'forms_skipped', 'tagged', 'feedback'):
            self.stdout.write(f'  {key.replace("_", " "):<22}{report[key]}')
        if report['identity_review']:
            self.stdout.write(self.style.WARNING(
                f'\n{len(report["identity_review"])} legacy account(s) could NOT be matched safely and were not imported '
                f'(forms that depend on them were skipped):'))
            for item in report['identity_review']:
                self.stdout.write(f'  - {item["legacy_username"]}: {item["reason"]}')
            if opts['identity_review_out']:
                import json
                template = {i['legacy_username']: '' for i in report['identity_review']}
                with open(opts['identity_review_out'], 'w', encoding='utf-8') as handle:
                    json.dump(template, handle, indent=2)
                self.stdout.write(f'  Fill in {opts["identity_review_out"]} (UOMS username, or "NEW") and re-run with --identity-map.')
        if report['placeholder_emails']:
            self.stdout.write(self.style.WARNING(
                f'\n{len(report["placeholder_emails"])} created account(s) have a placeholder email (@mrm-import.invalid) — correct them in User Management: '
                + ', '.join(report['placeholder_emails'][:20])))
        if report['risk_discrepancies']:
            self.stdout.write(self.style.WARNING(
                f'\n{len(report["risk_discrepancies"])} approved MRM(s) were approved at a LOWER decision tier than the official '
                f'risk matrix requires (legacy scoring bug). Their records were kept unchanged — review them:'))
            for item in report['risk_discrepancies']:
                self.stdout.write(f'  {item["mrm_number"]}: approved as {item["approved_as"]} ({item["legacy_percent"]}%), '
                                  f'matrix requires {item["official_matrix_requires"]} ({item["official_percent"]}%)')
        for title, key in (('Warnings', 'warnings'), ('Missing files', 'files_missing')):
            if report[key]:
                self.stdout.write(self.style.WARNING(f'\n{title}:'))
                for line in report[key][:50]:
                    self.stdout.write(f'  - {line}')
                if len(report[key]) > 50:
                    self.stdout.write(f'  … and {len(report[key]) - 50} more')
