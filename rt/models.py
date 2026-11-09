from django.conf import settings
from django.db import models
from django.utils import timezone


def today():
    return timezone.localdate()


class Household(models.Model):
    """One house / kepala keluarga in the RT."""

    block = models.CharField("blok", max_length=8)
    number = models.PositiveSmallIntegerField("nomor")
    head_name = models.CharField("kepala keluarga", max_length=100)
    phone = models.CharField("no. HP", max_length=20, blank=True)
    members = models.PositiveSmallIntegerField("jumlah anggota", default=1)
    joined_on = models.DateField("mulai tinggal", default=today)
    left_on = models.DateField("pindah", null=True, blank=True)
    exempt = models.BooleanField(
        "bebas iuran", default=False, help_text="mis. pengurus atau warga yang dibebaskan musyawarah"
    )

    class Meta:
        ordering = ["block", "number"]
        constraints = [models.UniqueConstraint(fields=["block", "number"], name="unique_address")]
        verbose_name = "rumah"
        verbose_name_plural = "rumah"

    def __str__(self):
        return f"{self.address} · {self.head_name}"

    @property
    def address(self):
        return f"{self.block}-{self.number}"

    @property
    def is_active(self):
        return self.left_on is None or self.left_on >= today()


class DuesRate(models.Model):
    """Monthly dues amount, valid from a given month until the next rate."""

    amount = models.PositiveIntegerField("iuran per bulan (Rp)")
    effective_from = models.DateField("berlaku mulai", unique=True, help_text="tanggal 1 bulan berlaku")

    class Meta:
        ordering = ["-effective_from"]
        verbose_name = "tarif iuran"
        verbose_name_plural = "tarif iuran"

    def __str__(self):
        from rt.services.months import rupiah

        return f"{rupiah(self.amount)} sejak {self.effective_from:%m/%Y}"

    def save(self, *args, **kwargs):
        self.effective_from = self.effective_from.replace(day=1)
        super().save(*args, **kwargs)


class DuesPayment(models.Model):
    household = models.ForeignKey(Household, on_delete=models.PROTECT, related_name="payments")
    month = models.DateField("bulan iuran", help_text="selalu tanggal 1")
    amount = models.PositiveIntegerField()
    paid_on = models.DateField(default=today)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-month"]
        constraints = [models.UniqueConstraint(fields=["household", "month"], name="one_payment_per_month")]
        verbose_name = "pembayaran iuran"
        verbose_name_plural = "pembayaran iuran"

    def __str__(self):
        return f"{self.household.address} {self.month:%m/%Y}"


class Expense(models.Model):
    class Category(models.TextChoices):
        SECURITY = "keamanan", "Keamanan"
        CLEANING = "kebersihan", "Kebersihan"
        SOCIAL = "sosial", "Sosial / duka"
        EVENT = "acara", "Acara"
        INFRA = "fasilitas", "Fasilitas"
        OTHER = "lainnya", "Lainnya"

    spent_on = models.DateField("tanggal", default=today)
    category = models.CharField("kategori", max_length=20, choices=Category.choices)
    amount = models.PositiveIntegerField("jumlah (Rp)")
    description = models.CharField("keterangan", max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-spent_on", "-id"]
        verbose_name = "pengeluaran"
        verbose_name_plural = "pengeluaran"

    def __str__(self):
        return f"{self.spent_on} {self.description}"


class Guard(models.Model):
    """A resident who takes part in the night watch (ronda)."""

    WEEKDAYS = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]

    name = models.CharField("nama", max_length=100)
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="guards")
    active = models.BooleanField("aktif", default=True)
    unavailable_weekdays = models.JSONField(
        "tidak bisa hari", default=list, blank=True, help_text="0 = Senin … 6 = Minggu"
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "petugas ronda"
        verbose_name_plural = "petugas ronda"

    def __str__(self):
        return self.name

    @property
    def unavailable_labels(self):
        return ", ".join(self.WEEKDAYS[d] for d in sorted(self.unavailable_weekdays))


class Shift(models.Model):
    date = models.DateField()
    guard = models.ForeignKey(Guard, on_delete=models.CASCADE, related_name="shifts")

    class Meta:
        ordering = ["date", "guard__name"]
        constraints = [
            models.UniqueConstraint(fields=["date", "guard"], name="one_shift_per_guard_per_night")
        ]
        verbose_name = "jadwal ronda"
        verbose_name_plural = "jadwal ronda"

    def __str__(self):
        return f"{self.date} {self.guard}"
