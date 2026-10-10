from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from dryMe.services.reconciliation import reconcile_pending_attempts


class Command(BaseCommand):
    help = (
        "Ask Safaricom (STK Query) what happened to payment prompts that are still PENDING "
        "and apply the answer. Safe to run repeatedly and alongside webhooks. "
        "Schedule it every few minutes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-age-minutes", type=int, default=2,
            help="Skip prompts younger than this (customer may still be entering their PIN). Default 2.",
        )
        parser.add_argument(
            "--max-age-hours", type=int, default=48,
            help="Don't query prompts older than this; they're only reported as stale. Default 48.",
        )
        parser.add_argument(
            "--limit", type=int, default=50,
            help="Max Safaricom queries per run, oldest first. Default 50.",
        )
        parser.add_argument(
            "--sleep", type=float, default=1.0,
            help="Seconds between queries, to respect Daraja rate limits. Default 1.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Query Safaricom and report what would change, without changing anything.",
        )

    def handle(self, *args, **options):
        summary = reconcile_pending_attempts(
            min_age=timedelta(minutes=options["min_age_minutes"]),
            max_age=timedelta(hours=options["max_age_hours"]),
            limit=options["limit"],
            sleep=options["sleep"],
            dry_run=options["dry_run"],
        )

        for line in summary.lines():
            self.stdout.write(line)

        # Every single query failed → credentials / network / Safaricom outage.
        # Exit non-zero so your scheduler (and its alerts) notice.
        if summary.checked and summary.errors == summary.checked:
            raise CommandError("All STK queries failed — check Daraja credentials, MPESA_BASE_URL and connectivity.")

        needs_refund = summary.duplicate_payments + summary.orphaned_payments
        if needs_refund:
            self.stdout.write(self.style.WARNING(
                f"{needs_refund} payment(s) need a refund — filter Payment attempts by refund_needed=Yes in admin."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))