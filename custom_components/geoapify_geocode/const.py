"""Constants for the GeoapifyGeocode integration."""

DOMAIN = "geoapify_geocode"
SUBENTRY_TYPE_TRACKED_ENTITY = "tracked_entity"

CONF_API_KEY = "api_key"
CONF_SOURCE_ENTITY = "source_entity"
# Legacy key retained only for migration from pre-subentry configurations.
CONF_TARGETS = "targets"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_MIN_DISTANCE_M = "min_distance_m"
CONF_MAX_AGE = "max_age"

DEFAULT_SCAN_INTERVAL = 180
DEFAULT_MIN_DISTANCE_M = 100
DEFAULT_MAX_AGE = 1800

ATTR_COUNTRY = "country"
ATTR_COUNTRY_CODE = "country_code"
ATTR_STATE = "state"
ATTR_COUNTY = "county"
ATTR_CITY = "city"
ATTR_POSTCODE = "postcode"
ATTR_STREET = "street"
ATTR_HOUSENUMBER = "housenumber"
ATTR_RESULT_TYPE = "result_type"
ATTR_DISTANCE = "distance"
ATTR_TIMEZONE = "timezone"
ATTR_TIMEZONE_NAME = "timezone_name"
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_LAT = "lat"
ATTR_LON = "lon"
