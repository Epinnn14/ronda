import random
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from rt.models import DuesPayment, DuesRate, Expense, Guard, Household
from rt.services import dues, roster
from rt.services.months import month_start, months_between

NAMES = [
    "Budi Santoso",
    "Siti Aminah",
    "Agus Wibowo",
    "Dewi Lestari",
    "Hendra Gunawan",
    "Rina Marlina",
    "Joko Susilo",
    "Sri Wahyuni",
    "Bambang Pamungkas",
    "Yuliani",
    "Eko Prasetyo",
    "Nur Hasanah",
    "Teguh Raharjo",
    "Wulan Sari",
    "Dedi Kurniawan",
    "Ratna Dewi",
    "Arif Hidayat",
    "Lina Marlina",
]


class Command(BaseCommand):
    help = "Fill the database with a demo RT: 18 houses, dues history, expenses, guards and a roster."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="ronda-demo", help="password for the demo 'pengurus' user")

    def handle(self, *args, password, **opts):
        if Household.objects.exists():
            self.stdout.write("Database sudah berisi data, demo dilewati.")
            return
        rng = random.Random(5)
        today = timezone.localdate()
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="pengurus", defaults={"is_staff": True, "is_superuser": True}
        )
        user.set_password(password)
        user.save()

        DuesRate.objects.create(amount=30_000, effective_from=date(today.year - 1, 1, 1))
        DuesRate.objects.create(amount=40_000, effective_from=date(today.year, 1, 1))

        houses = []
        for i, name in enumerate(NAMES):
            block, number = ("A", i + 1) if i < 9 else ("B", i - 8)
            joined = (
                date(today.year - 3, 1, 1)
                if i % 5
                else date(today.year, rng.randint(1, max(1, today.month - 1)), 10)
            )
            houses.append(
                Household.objects.create(
                    block=block,
                    number=number,
                    head_name=name,
                    members=rng.randint(1, 6),
                    joined_on=joined,
                    phone=f"0812{rng.randint(10_000_000, 99_999_999)}",
                    exempt=(i == 0),
                )
            )
        houses[0].head_name = "Budi Santoso (Ketua RT)"
        houses[0].save()

        rates = list(DuesRate.objects.all())
        for hh in houses:
            diligence = rng.choice([1.0, 1.0, 0.95, 0.85, 0.6])
            for m in dues.expected_months(hh, today, rates):
                if rng.random() < diligence:
                    paid_on = m + timedelta(days=rng.randint(0, 20))
                    DuesPayment.objects.create(
                        household=hh,
                        month=m,
                        amount=dues.rate_for(m, rates),
                        paid_on=min(paid_on, today),
                        recorded_by=user,
                    )

        extras = [
            ("fasilitas", 85_000, "Lampu jalan gang B"),
            ("sosial", 250_000, "Santunan duka"),
            ("keamanan", 60_000, "Baterai senter & HT"),
            ("fasilitas", 120_000, "Perbaikan pos ronda"),
        ]
        for m in months_between(date(today.year - 1, 1, 1), today):
            day = min(m + timedelta(days=4), today)
            Expense.objects.create(
                spent_on=day,
                category="kebersihan",
                amount=150_000,
                description="Angkut sampah bulanan",
                created_by=user,
            )
            if m.month == 8:
                Expense.objects.create(
                    spent_on=m + timedelta(days=16),
                    category="acara",
                    amount=650_000,
                    description="Lomba 17 Agustus",
                    created_by=user,
                )
            elif rng.random() < 0.5:
                cat, amount, desc = rng.choice(extras)
                Expense.objects.create(
                    spent_on=min(m + timedelta(days=rng.randint(5, 25)), today),
                    category=cat,
                    amount=amount,
                    description=desc,
                    created_by=user,
                )

        guard_names = [
            "Pak Agus",
            "Mas Hendra",
            "Pak Joko",
            "Mas Bambang",
            "Pak Eko",
            "Mas Teguh",
            "Pak Dedi",
            "Mas Arif",
            "Pak Slamet",
            "Mas Rizky",
            "Pak Wawan",
            "Mas Fajar",
        ]
        unavailable = [[], [], [4], [5, 6], [], [0], [], [], [2], [], [], [6]]
        for hh, name, un in zip(houses[1:13], guard_names, unavailable, strict=True):
            Guard.objects.create(name=name, household=hh, unavailable_weekdays=un)

        roster.generate_month(month_start(today), per_night=3, seed="demo")
        self.stdout.write(self.style.SUCCESS(f"Demo siap. Login: pengurus / {password}"))
