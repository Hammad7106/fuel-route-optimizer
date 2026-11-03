from django.db import models


class FuelStation(models.Model):
    """A truck stop with its retail fuel price, geocoded to its city."""

    opis_id = models.PositiveIntegerField(unique=True, help_text="OPIS truckstop ID.")
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.PositiveIntegerField()
    retail_price = models.DecimalField(
        max_digits=12, decimal_places=8, help_text="USD per gallon."
    )
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ["opis_id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state})"
