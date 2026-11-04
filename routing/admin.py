from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import DropdownFilter, RangeNumericFilter
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import FuelStation


class StateFilter(DropdownFilter):
    title = "state"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        states = FuelStation.objects.order_by("state").values_list("state", flat=True).distinct()
        return [(state, state) for state in states]

    def queryset(self, request, queryset):
        return queryset.filter(state=self.value()) if self.value() else queryset


@admin.register(FuelStation)
class FuelStationAdmin(ModelAdmin):
    """Read-only: stations are rebuilt from data/fuel_prices.csv by ``load_stations``
    on every start, so edits here would be lost. Change the CSV instead."""

    list_display = ("name", "location", "price", "opis_id", "coordinates")
    list_filter = (StateFilter, ("retail_price", RangeNumericFilter))
    list_filter_submit = True  # Range filters need an explicit "Apply".
    search_fields = ("name", "city", "address", "=opis_id")
    ordering = ("retail_price",)
    list_per_page = 50

    @display(description="Location", ordering="city")
    def location(self, station: FuelStation) -> str:
        return f"{station.city}, {station.state}"

    @display(description="Price / gal", ordering="retail_price")
    def price(self, station: FuelStation) -> str:
        return f"${station.retail_price:.3f}"

    @display(description="Lat, lng")
    def coordinates(self, station: FuelStation) -> str:
        return f"{station.latitude:.4f}, {station.longitude:.4f}"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


# Re-register auth models with Unfold's styling.
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
