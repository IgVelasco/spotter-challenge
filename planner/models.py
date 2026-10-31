from django.db import models


class Station(models.Model):
    """A US truck stop from the supplied price list.

    Coordinates are the internal point of the station's town (see planner.geodata),
    because the source data gives highway exits rather than street addresses.
    """

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price_per_gallon = models.DecimalField(max_digits=10, decimal_places=8)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"
