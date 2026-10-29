"""Declared spherical geometry; distances are not road or walking routes."""

import math

RADIUS_KM = 6371.0


def distance(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    delta = math.radians(lon2 - lon1)
    value = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(delta / 2) ** 2
    return 2 * RADIUS_KM * math.atan2(math.sqrt(max(0.0, value)), math.sqrt(max(0.0, 1 - value)))


def shift(latitude, longitude, kilometers, bearing):
    lat, lon, angle = map(math.radians, [latitude, longitude, bearing])
    delta = kilometers / RADIUS_KM
    target_lat = math.asin(math.sin(lat) * math.cos(delta) + math.cos(lat) * math.sin(delta) * math.cos(angle))
    target_lon = lon + math.atan2(math.sin(angle) * math.sin(delta) * math.cos(lat), math.cos(delta) - math.sin(lat) * math.sin(target_lat))
    return math.degrees(target_lat), (math.degrees(target_lon) + 180) % 360 - 180
