from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from rt.models import DuesPayment, Expense, Guard, Household, Shift
from rt.views import wa_link

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = User.objects.create_user("pengurus", password="x")
    client.force_login(user)
    return user


def test_wa_link_normalises_indonesian_numbers():
    assert wa_link("0812-3456-789", "halo kak").startswith("https://wa.me/628123456789?text=halo%20kak")
    assert wa_link("", "x") == ""


def test_public_pages_need_no_login(client, rates, houses):
    assert client.get("/jadwal/").status_code == 200
    assert client.get("/kas/").status_code == 200
    page = client.get("/kas/").content.decode()
    assert "Catat pengeluaran" not in page  # form only for pengurus


@pytest.mark.parametrize("url", ["/", "/warga/", "/iuran/", "/iuran/tunggakan/", "/petugas/"])
def test_admin_pages_redirect_to_login(client, url):
    r = client.get(url)
    assert r.status_code == 302 and r.url.startswith("/masuk/")


@pytest.mark.parametrize(
    "url", ["/", "/warga/", "/iuran/?year=2026", "/iuran/tunggakan/", "/petugas/", "/kas/"]
)
def test_admin_pages_render(client, staff, rates, houses, url):
    assert client.get(url).status_code == 200


def test_toggle_payment_via_htmx_returns_cell(client, staff, rates, houses):
    a1 = houses["a1"]
    r = client.post(f"/iuran/{a1.pk}/2026-02/", HTTP_HX_REQUEST="true")
    html = r.content.decode()
    assert r.status_code == 200 and html.startswith("<td") and 'class="c paid"' in html
    assert DuesPayment.objects.get(household=a1, month=date(2026, 2, 1)).recorded_by == staff
    # clicking again undoes it
    client.post(f"/iuran/{a1.pk}/2026-02/")
    assert not DuesPayment.objects.filter(household=a1).exists()
    # exempt household: error shown inside the cell, nothing saved
    r = client.post(f"/iuran/{houses['b1'].pk}/2026-02/")
    assert "tidak wajib" in r.content.decode()
    assert client.post(f"/iuran/{a1.pk}/nope/").status_code == 400
    assert client.get(f"/iuran/{a1.pk}/2026-02/").status_code == 405


def test_household_crud(client, staff, rates):
    r = client.post(
        "/warga/baru/",
        {
            "block": " c ",
            "number": 7,
            "head_name": "Pak Darto",
            "phone": "0811",
            "members": 3,
            "joined_on": "2026-01-01",
        },
    )
    hh = Household.objects.get(head_name="Pak Darto")
    assert r.status_code == 302 and hh.address == "C-7"
    page = client.get(f"/warga/{hh.pk}/").content.decode()
    assert "Tunggakan" in page and "wa.me/62811" in page
    bad = client.post(
        f"/warga/{hh.pk}/ubah/",
        {
            "block": "C",
            "number": 7,
            "head_name": "x",
            "members": 1,
            "joined_on": "2026-05-01",
            "left_on": "2026-01-01",
        },
    )
    assert "tidak boleh sebelum" in bad.content.decode()


def test_generate_and_swap_schedule(client, staff, guards):
    r = client.post("/jadwal/buat/", {"month": "2026-11", "per_night": 2, "seed": "abc"})
    assert r.status_code == 302 and Shift.objects.count() == 60
    page = client.get("/jadwal/?month=2026-11").content.decode()
    assert "Tukar 2 jadwal" in page and "Warga 0" in page

    a = Shift.objects.filter(date=date(2026, 11, 2)).first()
    b = (
        Shift.objects.filter(date=date(2026, 11, 9))
        .exclude(guard=a.guard)
        .exclude(guard__in=Shift.objects.filter(date=date(2026, 11, 2)).values("guard"))
        .first()
    )
    r = client.post("/jadwal/tukar/", {"month": "2026-11", "shift": [a.pk, b.pk]}, HTTP_HX_REQUEST="true")
    html = r.content.decode()
    assert html.startswith('<form id="calendar"')
    assert "Jadwal ditukar" in html or "tidak bisa" in html
    r = client.post("/jadwal/tukar/", {"month": "2026-11", "shift": [a.pk]})
    assert "tepat dua" in r.content.decode()


def test_generate_without_guards_warns(client, staff):
    r = client.post("/jadwal/buat/", {"month": "2026-11", "per_night": 2}, follow=True)
    assert "Belum ada petugas" in r.content.decode()


def test_guard_toggle_and_add(client, staff, guards, houses):
    g = guards[0]
    r = client.post(f"/petugas/{g.pk}/aktif/")
    assert "Aktifkan" in r.content.decode()
    g.refresh_from_db()
    assert not g.active
    client.post(
        "/petugas/",
        {
            "name": "Mas Yoga",
            "household": houses["a2"].pk,
            "active": "on",
            "unavailable_weekdays": ["5", "6"],
        },
    )
    assert Guard.objects.get(name="Mas Yoga").unavailable_weekdays == [5, 6]


def test_expense_add(client, staff):
    client.post(
        "/kas/pengeluaran/",
        {"spent_on": "2026-11-02", "category": "kebersihan", "amount": 50_000, "description": "Kerja bakti"},
    )
    e = Expense.objects.get()
    assert e.created_by == staff
    assert "Kerja bakti" in client.get("/kas/?year=2026").content.decode()
    r = client.post("/kas/pengeluaran/", {"category": "nope"}, follow=True)
    assert Expense.objects.count() == 1 and "category" in r.content.decode()


def test_seed_demo_command():
    call_command("seed_demo", password="secret")
    assert Household.objects.count() == 18
    assert Shift.objects.exists() and DuesPayment.objects.exists()
    call_command("seed_demo")  # idempotent
    assert Household.objects.count() == 18
