from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("warga/", views.household_list, name="households"),
    path("warga/baru/", views.household_form, name="household_new"),
    path("warga/<int:pk>/", views.household_detail, name="household_detail"),
    path("warga/<int:pk>/ubah/", views.household_form, name="household_edit"),
    path("iuran/", views.dues_matrix, name="dues"),
    path("iuran/<int:pk>/<str:ym>/", views.dues_toggle, name="dues_toggle"),
    path("iuran/tunggakan/", views.arrears_list, name="arrears"),
    path("jadwal/", views.schedule, name="schedule"),
    path("jadwal/buat/", views.schedule_generate, name="schedule_generate"),
    path("jadwal/tukar/", views.schedule_swap, name="schedule_swap"),
    path("petugas/", views.guard_list, name="guards"),
    path("petugas/<int:pk>/aktif/", views.guard_toggle, name="guard_toggle"),
    path("kas/", views.cash, name="cash"),
    path("kas/pengeluaran/", views.expense_add, name="expense_add"),
]
