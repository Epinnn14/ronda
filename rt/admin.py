from django.contrib import admin

from .models import DuesPayment, DuesRate, Expense, Guard, Household, Shift


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ["address", "head_name", "phone", "members", "joined_on", "left_on", "exempt"]
    list_filter = ["block", "exempt"]
    search_fields = ["head_name", "phone"]


@admin.register(DuesPayment)
class DuesPaymentAdmin(admin.ModelAdmin):
    list_display = ["household", "month", "amount", "paid_on", "recorded_by"]
    list_filter = ["month"]
    date_hierarchy = "paid_on"


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["spent_on", "category", "amount", "description"]
    list_filter = ["category"]
    date_hierarchy = "spent_on"


@admin.register(Guard)
class GuardAdmin(admin.ModelAdmin):
    list_display = ["name", "household", "active"]
    list_filter = ["active"]


admin.site.register(DuesRate)
admin.site.register(Shift)
admin.site.site_header = "Admin RT"
