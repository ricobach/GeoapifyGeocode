# HA-GeoapifyGeocode

A Home Assistant custom integration that reverse-geocodes selected `person` or `device_tracker` entities using the Geoapify Reverse Geocoding API and derives GPS-based movement state from recent location history.

For every selected source entity, the integration creates:

- a geocode sensor whose state is the formatted address returned by Geoapify
- a movement binary sensor, such as `binary_sensor.rico_moving`, that uses recent GPS coordinates rather than zone names or only the immediately previous update

The Home Assistant integration is named **GeoapifyGeocode**. The GitHub repository is named **HA-GeoapifyGeocode**.

## Features

### Reverse geocoding

- UI configuration with Geoapify API-key validation
- Reauthentication when an API key is rejected
- Manual API-key reconfiguration
- Configurable polling interval and movement threshold for Geoapify requests
- Maximum result age so stationary locations are periodically refreshed
- Concurrent requests for multiple moving targets
- Rate-limit handling and cached fallback results
- Recorder-friendly address and timezone attributes
- Copies the source entity's `entity_picture` for dashboard use

### GPS movement detection

- Listens to live state and attribute updates from selected `person` and `device_tracker` entities
- Maintains only a small rolling GPS history in memory
- Uses latitude, longitude, and `gps_accuracy` when available
- Prefers a reference point around five minutes old instead of comparing only consecutive updates
- Works with frequent, sparse, or irregular GPS update intervals
- Uses Home Assistant's geographic distance utility
- Uses the combined GPS uncertainty of the current and reference measurements as part of the movement threshold
- Uses a configurable stationary hold time to reduce rapid state changes around the movement threshold
- Restores the recent GPS history from Home Assistant Recorder once during integration startup, then uses live in-memory updates during normal operation
- Does not create helper entities for individual GPS samples, so the rolling history itself does not add Recorder load

The movement binary sensor uses Home Assistant's `moving` device class. Its state is `on` when meaningful GPS displacement is detected, `off` when the target appears stationary, and `unknown` when there is not enough valid GPS history to make a reliable determination.

## Installation with HACS

1. Open HACS in Home Assistant.
2. Go to **Integrations**.
3. Open the menu and select **Custom repositories**.
4. Add `https://github.com/ricobach/HA-GeoapifyGeocode` as an **Integration** repository.
5. Install **GeoapifyGeocode**.
6. Restart Home Assistant.
7. Go to **Settings > Devices & services > Add integration** and search for **GeoapifyGeocode**.

## Configuration

During setup, enter your Geoapify API key and select one or more `person` or `device_tracker` entities.

Options can be changed from the integration's configuration page.

### Reverse-geocoding options

- **Geocode update interval**: how often target locations are checked. Default: 180 seconds.
- **Minimum movement before calling Geoapify**: minimum displacement before a new API request. Default: 100 metres.
- **Maximum geocode result age**: refresh even without enough movement once the cached result reaches this age. Default: 1800 seconds.

### Movement options

- **Movement history window**: amount of recent GPS history retained. Default: 600 seconds.
- **Movement comparison target age**: preferred age of the historical reference point. Default: 300 seconds.
- **Minimum movement reference age**: ignores samples that are too recent for a meaningful comparison. Default: 60 seconds.
- **Minimum meaningful GPS displacement**: lower bound for movement even when GPS accuracy is very good. Default: 20 metres.
- **Fallback GPS accuracy**: uncertainty used when the source does not provide `gps_accuracy`. Default: 25 metres per sample.
- **Moving-state hold time**: short hysteresis period after meaningful movement. Default: 120 seconds.
- **Tracked entities**: `person` and `device_tracker` entities for which sensors are created.

## Geocode sensor data

Each selected source entity gets a `<friendly name> Geocode` sensor.

The sensor state is the Geoapify formatted address. Depending on the result, attributes may include country and country code, state, county, city, postcode, street, house number, result type, distance, timezone, source entity, and latitude/longitude.

If the source entity has an `entity_picture`, the geocode sensor exposes it as a real Home Assistant entity picture. It is refreshed when the integration performs its normal coordinator update.

## Movement binary sensor

Each selected source gets a `<friendly name> Moving` binary sensor.

Movement is calculated from GPS coordinates only. The person's Home Assistant zone state such as `home`, `not_home`, or another zone name is not used to decide whether the person is moving.

Useful diagnostic attributes include:

- current latitude and longitude
- reference latitude and longitude
- reference age
- calculated displacement in metres
- current and reference GPS accuracy
- effective movement threshold
- number of GPS samples currently held
- timestamp of the last meaningful movement
- source entity

The in-memory GPS samples are not exposed as Home Assistant entities or attributes.

## Restart recovery and Recorder

During startup, the integration performs one Recorder history query for approximately the configured movement history window and rebuilds its in-memory GPS history from recorded states. The current live state is then added and normal event-based tracking starts.

After initialization, movement calculations use the in-memory rolling history and do not query Recorder on every location update. If Recorder is unavailable or contains no usable recent coordinates, the movement sensor starts with insufficient history and automatically becomes usable as live GPS updates arrive.

## API usage

Geoapify requests are made only when a target has moved far enough or when the cached geocode result reaches the configured maximum age. GPS movement detection itself is local and does not call Geoapify.

## Upgrade compatibility

Existing geocode sensor unique IDs are preserved. Movement sensors are new entities and are created automatically for configured tracked entities.

## Issues

Please report issues through the GitHub issue tracker for this repository.

## Disclaimer

This is an independent Home Assistant custom integration and is not an official Geoapify integration.
