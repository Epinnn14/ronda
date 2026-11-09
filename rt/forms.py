from django import forms

from .models import Expense, Guard, Household


class HouseholdForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ["block", "number", "head_name", "phone", "members", "joined_on", "left_on", "exempt"]
        widgets = {
            "joined_on": forms.DateInput(attrs={"type": "date"}),
            "left_on": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_block(self):
        return self.cleaned_data["block"].strip().upper()

    def clean(self):
        data = super().clean()
        joined, left = data.get("joined_on"), data.get("left_on")
        if joined and left and left < joined:
            self.add_error("left_on", "Tanggal pindah tidak boleh sebelum mulai tinggal.")
        return data


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["spent_on", "category", "amount", "description"]
        widgets = {"spent_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "— pilih kategori —"), *Expense.Category.choices]


class GuardForm(forms.ModelForm):
    unavailable_weekdays = forms.TypedMultipleChoiceField(
        label="Tidak bisa hari",
        choices=list(enumerate(Guard.WEEKDAYS)),
        coerce=int,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Guard
        fields = ["name", "household", "active", "unavailable_weekdays"]


class GenerateRosterForm(forms.Form):
    per_night = forms.IntegerField(label="Petugas per malam", min_value=1, max_value=10, initial=3)
    seed = forms.CharField(
        label="Kode acak", max_length=40, required=False, help_text="kode yang sama = jadwal yang sama"
    )
