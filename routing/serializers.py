from urllib.parse import urlencode

from django.urls import reverse
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class TripRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200, help_text="'City, ST' (e.g. 'Dallas, TX') or 'lat,lng'."
    )
    finish = serializers.CharField(
        max_length=200, help_text="'City, ST' (e.g. 'Denver, CO') or 'lat,lng'."
    )


class RoundedFloatField(serializers.FloatField):
    def __init__(self, *, digits: int = 1, **kwargs):
        self.digits = digits
        super().__init__(**kwargs)

    def to_representation(self, value):
        return round(float(value), self.digits)


class LocationSerializer(serializers.Serializer):
    label = serializers.CharField()
    latitude = serializers.FloatField(source="coordinates.latitude")
    longitude = serializers.FloatField(source="coordinates.longitude")


class FuelStopSerializer(serializers.Serializer):
    opis_id = serializers.IntegerField(source="station.opis_id")
    name = serializers.CharField(source="station.name")
    address = serializers.CharField(source="station.address")
    city = serializers.CharField(source="station.city")
    state = serializers.CharField(source="station.state")
    latitude = serializers.FloatField(source="station.coordinates.latitude")
    longitude = serializers.FloatField(source="station.coordinates.longitude")
    mile_marker = RoundedFloatField()
    off_route_miles = RoundedFloatField()
    price_per_gallon = serializers.DecimalField(
        source="station.price", max_digits=12, decimal_places=3
    )
    gallons = serializers.DecimalField(max_digits=10, decimal_places=3)
    cost = serializers.DecimalField(max_digits=12, decimal_places=2)


class TripPlanSerializer(serializers.Serializer):
    start = LocationSerializer()
    finish = LocationSerializer()
    distance_miles = RoundedFloatField(source="route.distance_miles")
    duration_hours = serializers.SerializerMethodField()
    total_gallons = serializers.DecimalField(
        source="fuel.total_gallons", max_digits=10, decimal_places=3
    )
    total_fuel_cost = serializers.DecimalField(
        source="fuel.total_cost", max_digits=12, decimal_places=2
    )
    fuel_before_first_stop = serializers.SerializerMethodField()
    fuel_stops = FuelStopSerializer(source="fuel.stops", many=True)
    route = serializers.SerializerMethodField()
    map_url = serializers.SerializerMethodField()

    def get_duration_hours(self, trip) -> float:
        return round(trip.route.duration_seconds / 3600, 1)

    def get_fuel_before_first_stop(self, trip) -> dict:
        """Fuel to reach the first station, when it is past the start (usually zero)."""
        return {
            "gallons": f"{trip.fuel.starting_gallons:.3f}",
            "cost": f"{trip.fuel.starting_cost:.2f}",
        }

    @extend_schema_field(
        {
            "type": "object",
            "description": "GeoJSON LineString, simplified for display; [longitude, latitude] pairs.",
            "example": {"type": "LineString", "coordinates": [[-96.76651, 32.79333]]},
        }
    )
    def get_route(self, trip) -> dict:
        return trip.route.to_geojson()

    def get_map_url(self, trip) -> str | None:
        request = self.context.get("request")
        if request is None:
            return None
        query = urlencode({"start": trip.start.label, "finish": trip.finish.label})
        return request.build_absolute_uri(f"{reverse('routing:route-map')}?{query}")
