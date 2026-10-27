"""
Latitude/longitude → MGRS (Military Grid Reference System) conversion.

Implemented as plain WGS84 ellipsoid math (Lat/Lon -> UTM -> MGRS) with no
external geodesy library dependency, so it works even in environments
where GDAL's projection database isn't fully configured. Accurate to
about 1 meter, which is more than sufficient for a UI display field.
"""
import math

_A = 6378137.0  # WGS84 semi-major axis (meters)
_F = 1 / 298.257223563  # WGS84 flattening
_K0 = 0.9996  # UTM scale factor

_E = math.sqrt(_F * (2 - _F))
_E2 = _E ** 2
_E4 = _E2 ** 2
_E6 = _E2 ** 3

_LATITUDE_BANDS = 'CDEFGHJKLMNPQRSTUVWX'  # excludes I and O; covers 80S to 84N

# MGRS 100km grid square column letters cycle every 3 UTM zones; row letters
# cycle every 2. These are the standard letter sets (I and O excluded).
_COL_LETTERS = [
    'ABCDEFGH',
    'JKLMNPQR',
    'STUVWXYZ',
]
_ROW_LETTERS_EVEN = 'ABCDEFGHJKLMNPQRSTUV'
_ROW_LETTERS_ODD = 'FGHJKLMNPQRSTUVABCDE'


def _utm_zone_number(lon):
    return int((lon + 180) / 6) + 1


def _latlon_to_utm(lat, lon):
    """Returns (easting, northing, zone_number, is_northern)."""
    zone_number = _utm_zone_number(lon)
    lon_origin = math.radians((zone_number - 1) * 6 - 180 + 3)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    n = _A / math.sqrt(1 - _E2 * math.sin(lat_rad) ** 2)
    t = math.tan(lat_rad) ** 2
    c = _E2 / (1 - _E2) * math.cos(lat_rad) ** 2
    ap = math.cos(lat_rad) * (lon_rad - lon_origin)

    m = _A * (
        (1 - _E2 / 4 - 3 * _E4 / 64 - 5 * _E6 / 256) * lat_rad
        - (3 * _E2 / 8 + 3 * _E4 / 32 + 45 * _E6 / 1024) * math.sin(2 * lat_rad)
        + (15 * _E4 / 256 + 45 * _E6 / 1024) * math.sin(4 * lat_rad)
        - (35 * _E6 / 3072) * math.sin(6 * lat_rad)
    )

    easting = (
        _K0 * n * (
            ap + (1 - t + c) * ap ** 3 / 6
            + (5 - 18 * t + t ** 2 + 72 * c - 58 * _E2 / (1 - _E2)) * ap ** 5 / 120
        )
        + 500000.0
    )

    northing = _K0 * (
        m + n * math.tan(lat_rad) * (
            ap ** 2 / 2 + (5 - t + 9 * c + 4 * c ** 2) * ap ** 4 / 24
            + (61 - 58 * t + t ** 2 + 600 * c - 330 * _E2 / (1 - _E2)) * ap ** 6 / 720
        )
    )

    is_northern = lat >= 0
    if not is_northern:
        northing += 10000000.0

    return easting, northing, zone_number, is_northern


def _latitude_band(lat):
    if lat < -80 or lat > 84:
        return None
    index = int((lat + 80) / 8)
    index = min(index, len(_LATITUDE_BANDS) - 1)
    return _LATITUDE_BANDS[index]


def _grid_square_id(zone_number, easting, northing, is_northern):
    col_set = _COL_LETTERS[(zone_number - 1) % 3]
    col_index = int(easting / 100000.0) - 1
    col_letter = col_set[col_index % len(col_set)]

    row_set = _ROW_LETTERS_EVEN if zone_number % 2 == 0 else _ROW_LETTERS_ODD
    row_index = int(northing / 100000.0) % len(row_set)
    row_letter = row_set[row_index]

    return f'{col_letter}{row_letter}'


def latlon_to_mgrs(lat, lon, precision=5):
    """
    Converts WGS84 lat/lon (decimal degrees) to an MGRS coordinate string,
    e.g. "51N UB 12345 67890" (precision=5 -> 1m resolution).

    Returns None for coordinates outside the UTM/MGRS coverage area
    (poles, i.e. below 80S or above 84N).
    """
    band = _latitude_band(lat)
    if band is None:
        return None

    easting, northing, zone_number, is_northern = _latlon_to_utm(lat, lon)
    grid_square = _grid_square_id(zone_number, easting, northing, is_northern)

    easting_in_square = int(easting % 100000)
    northing_in_square = int(northing % 100000)

    digits = precision
    easting_str = str(easting_in_square).zfill(5)[:digits]
    northing_str = str(northing_in_square).zfill(5)[:digits]

    return f'{zone_number}{band} {grid_square} {easting_str} {northing_str}'


# ---------------------------------------------------------------------------
# MGRS -> lat/lon (the inverse of latlon_to_mgrs)
# ---------------------------------------------------------------------------
import re

_MGRS_RE = re.compile(
    r'^\s*(\d{1,2})\s*([C-HJ-NP-X])\s*([A-HJ-NP-Z])\s*([A-HJ-NP-V])\s*((?:\d\s*){0,10})$',
    re.IGNORECASE,
)


class MGRSError(ValueError):
    """Raised with a user-readable message when an MGRS string cannot be interpreted."""


def _utm_to_latlon(easting, northing, zone_number, is_northern):
    x = easting - 500000.0
    y = northing if is_northern else northing - 10000000.0
    lon_origin = math.radians((zone_number - 1) * 6 - 180 + 3)

    m = y / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E4 / 64 - 5 * _E6 / 256))
    root = math.sqrt(1 - _E2)
    e1 = (1 - root) / (1 + root)
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
        + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
        + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    )
    ep2 = _E2 / (1 - _E2)
    sin1, cos1, tan1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    n1 = _A / math.sqrt(1 - _E2 * sin1 ** 2)
    t1, c1 = tan1 ** 2, ep2 * cos1 ** 2
    r1 = _A * (1 - _E2) / (1 - _E2 * sin1 ** 2) ** 1.5
    d = x / (n1 * _K0)

    lat = phi1 - (n1 * tan1 / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720
    )
    lon = lon_origin + (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120
    ) / cos1
    return math.degrees(lat), math.degrees(lon)


def mgrs_to_latlon(text):
    """
    Parses an MGRS reference such as "51N UB 12345 67890", "51NUB1234567890" or the coarser "51N UB 123 678"
    and returns (lat, lon) of the centre of the referenced grid cell (WGS84).

    Raises MGRSError with an explanatory message when the reference is malformed or impossible.
    """
    if not isinstance(text, str) or not text.strip():
        raise MGRSError('Enter an MGRS reference, e.g. 51P UH 12345 67890.')
    match = _MGRS_RE.match(text)
    if not match:
        raise MGRSError(
            f'"{text.strip()}" is not a valid MGRS reference. Use zone + band letter, two 100 km square letters '
            'and an even number of digits, e.g. 51P UH 12345 67890.'
        )
    zone_text, band, col_letter, row_letter, digits = match.groups()
    band, col_letter, row_letter = band.upper(), col_letter.upper(), row_letter.upper()
    digits = re.sub(r'\s+', '', digits)

    zone = int(zone_text)
    if not 1 <= zone <= 60:
        raise MGRSError(f'UTM zone {zone} does not exist (valid zones are 1–60).')
    if len(digits) % 2:
        raise MGRSError('The easting and northing must have the same number of digits (e.g. 12345 67890).')

    col_set = _COL_LETTERS[(zone - 1) % 3]
    if col_letter not in col_set:
        raise MGRSError(f'Square letter "{col_letter}" is not valid for zone {zone} (expected one of {col_set}).')
    row_set = _ROW_LETTERS_EVEN if zone % 2 == 0 else _ROW_LETTERS_ODD
    if row_letter not in row_set:
        raise MGRSError(f'Row letter "{row_letter}" is not a valid MGRS row letter.')

    half = len(digits) // 2
    precision_m = 10 ** (5 - half) if half else 100000
    easting_in = (int(digits[:half]) * precision_m if half else 0) + precision_m / 2.0
    northing_in = (int(digits[half:]) * precision_m if half else 0) + precision_m / 2.0

    easting = (col_set.index(col_letter) + 1) * 100000.0 + easting_in
    northing_base = row_set.index(row_letter) * 100000.0 + northing_in

    # The row letter repeats every 2,000 km of northing; pick the cycle that falls inside the latitude band.
    band_index = _LATITUDE_BANDS.index(band)
    band_mid_lat = min(-80 + band_index * 8 + 4, 78)  # band X (72–84) is 12° tall
    lon_origin_deg = (zone - 1) * 6 - 180 + 3
    _, mid_northing, _, is_northern = _latlon_to_utm(band_mid_lat, lon_origin_deg)
    if (band >= 'N') != is_northern:
        raise MGRSError(f'Latitude band {band} is inconsistent with the hemisphere.')
    cycle = round((mid_northing - northing_base) / 2000000.0)
    northing = northing_base + cycle * 2000000.0

    lat, lon = _utm_to_latlon(easting, northing, zone, is_northern)
    if _latitude_band(lat) != band:
        raise MGRSError(f'The grid square {col_letter}{row_letter} does not exist in latitude band {band} of zone {zone}.')
    if not (-180 <= lon <= 180):
        raise MGRSError('That reference falls outside the valid longitude range.')
    return round(lat, 7), round(lon, 7)
