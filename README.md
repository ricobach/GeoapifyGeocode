# HA-GeoapifyGeocode

A Home Assistant custom integration that reverse-geocodes selected `person` or `device_tracker` entities using the Geoapify Reverse Geocoding API and provides GPS-based movement detection for the same tracked entities.

The integration itself is shown in Home Assistant as **GeoapifyGeocode**. For each selected source entity, it creates a geocode sensor and a GPS movement binary sensor.

## Features

- UI configuration with Geoapify API-key validation
- Reauthentication when an API key is rejected
- Manual API-key reconfiguration
- Select `person` and `device_tracker` entities to track
- Reverse geocoding with configurable polling and API-request movement threshold
- Configurable maximum geocode result age
- Concurrent Geoapify requests for multiple targets
- Rate-limit handling and cached fallback results
- Selected address and timezone attributes without storing the full raw API response in Home Assistant's Recorder
- Copies the source entity's `entity_picture` to the Geoapify sensor as a real Home Assistant entity picture for dashboards
- GPS-based moving/stationary detection using a rolling recent-position history
- GPS-accuracy-aware movement thresholds to suppress normal location drift
- One-time Recorder history recovery after restart so movement detection can resume immediately
- Preserves existing geocode entity unique IDs across upgrades

## Requirements

- Home Assistant
- HACS, if installing through HACS
- A Geoapify API key
- At least one `person` or `device_tracker` entity that provides `latitude` and `longitude` attributes

`gps_accuracy` is used when the source entity provides it, but it is not required.

## Installation with HACS

1. Open **HACS** in Home Assistant.
2. Go to **Integrations**.
3. Open the menu and select **Custom repositories**.
4. Add `https://github.com/ricobach/HA-GeoapifyGeocode` as an **Integration** repository.
5. Install **GeoapifyGeocode**.
6. Restart Home Assistant if HACS asks you to do so.
7. Go to **Settings > Devices & services > Add integration** and search for **GeoapifyGeocode**.

## Configuration

During setup, enter your Geoapify API key and select one or more `person` or `device_tracker` entities.

The API key is validated during setup before the integration is created.

After installation, the following options can be changed from the integration's options flow.

### Reverse geocoding

- **Geocode update interval**: how often target locations are checked for reverse geocoding. Default: 180 seconds.
- **Minimum movement before calling Geoapify**: distance a target must move before another Geoapify request is made. Default: 100 metres.
- **Maximum geocode result age**: refresh the reverse-geocoded result once the cached result reaches this age even if the source has not moved far enough. Default: 1800 seconds.

### GPS movement detection

- **Movement history window**: amount of recent GPS history retained internally. Default: 600 seconds (10 minutes).
- **Movement comparison target age**: preferred age of the reference GPS point. Default: 300 seconds (5 minutes).
- **Minimum movement reference age**: prevents very recent points from being used as the comparison reference. Default: 60 seconds.
- **Minimum GPS movement distance**: absolute lower movement threshold even when GPS accuracy is very good. Default: 20 metres.
- **Fallback GPS accuracy**: accuracy used when the source entity does not provide `gps_accuracy`. Default: 25 metres.
- **Moving-to-stationary hold time**: short hysteresis period after meaningful movement to reduce state flapping. Default: 120 seconds.
- **Tracked entities**: `person` and `device_tracker` entities for both geocoding and movement detection.

The Geoapify API key can also be reconfigured. If Geoapify rejects the configured key, Home Assistant starts a reauthentication flow.

## Geocode sensor

Each selected source entity gets a `<friendly name> Geocode` sensor.

The sensor state is the formatted address returned by Geoapify. Depending on the reverse-geocoding result, attributes may include:

- country and country code
- state, county and city
- postcode, street and house number
- result type and distance
- timezone and timezone name
- source entity and source friendly name
- latitude and longitude

### Entity picture

If the selected `person` or `device_tracker` has an `entity_picture`, the Geoapify sensor exposes the same value through Home Assistant's real `entity_picture` property.

For example, if the source entity contains:

```yaml
entity_picture: /api/image/serve/d92aa3df171c0134d6bd65f0a57b1f59/512x512
```

the corresponding Geoapify sensor exposes the same `entity_picture`. This allows dashboards and cards that support entity pictures to use the source person's or device tracker's image directly.

There is no separate listener for picture changes. The picture is picked up as part of the integration's normal coordinator update cycle.

## GPS movement binary sensor

Each selected source entity also gets a `<friendly name> Moving` binary sensor with Home Assistant's `moving` device class.

The binary sensor is determined from GPS coordinates only. The person's Home Assistant zone state, such as `home`, `not_home`, or a zone name, is not used to decide whether the person is moving.

The movement engine listens for latitude/longitude attribute updates from the source entity and keeps a small rolling GPS history in memory. It chooses a sufficiently old reference point, preferring a point about five minutes older than the current position. This makes the calculation independent of whether the phone reports every few seconds, every minute, or irregularly.

Movement is considered meaningful only when the displacement exceeds both the configured minimum distance and the combined expected uncertainty of the current and reference GPS measurements. If `gps_accuracy` is missing, the configured fallback accuracy is used.

The sensor can be `unknown` when there is not enough valid GPS history to make a reliable decision. Old or invalid GPS data is not treated as stationary.

Diagnostic attributes can include:

- current latitude/longitude
- reference latitude/longitude
- reference age
- displacement in metres
- current and reference GPS accuracy
- effective movement threshold
- number of recent GPS samples
- timestamp of the last meaningful movement
- source entity

The internal rolling history is not exposed as Home Assistant entities or helpers. Live GPS updates are ingested into memory, while unchanged diagnostics are published no more than approximately once per minute; movement-state transitions are published immediately. This avoids turning high-frequency phone location updates into unnecessary Recorder growth.

### Restart recovery

During normal operation the movement calculation uses only the in-memory GPS history.

When the integration starts, it waits for Home Assistant Recorder to become available and performs a single history query for the configured recent history window. Attribute changes are included so latitude/longitude updates are recovered even when the source entity's main state did not change. The recovered GPS samples populate the in-memory history, after which Recorder is no longer queried for normal movement calculations.

If Recorder is unavailable or contains no usable recent GPS states, the movement sensor starts with an empty history and remains `unknown` until enough live GPS information has been collected.

## API usage and caching

Geoapify requests are made only when a target has moved at least the configured geocode minimum distance or when the cached result reaches the configured maximum age.

The integration keeps the last successful reverse-geocoding result as a fallback for temporary Geoapify connection or response failures. Requests for multiple targets are performed concurrently with a bounded concurrency limit, and Geoapify rate-limit responses are handled with a retry delay.

GPS movement detection itself does not call Geoapify and does not generate additional Geoapify API usage.

## Updating

When installed through HACS, new releases can be installed through HACS in the normal way. Existing geocode unique IDs are preserved so upgrading does not create duplicate geocode sensors.

## Issues

Please report issues through the GitHub issue tracker:

`https://github.com/ricobach/HA-GeoapifyGeocode/issues`

## Disclaimer

This is an independent Home Assistant custom integration and is not an official Geoapify integration.
