# HA-GeoapifyGeocode

A Home Assistant custom integration that reverse-geocodes configured `person` or `device_tracker` entities using the Geoapify Reverse Geocoding API and provides GPS-based movement detection for the same tracked entities.

The integration itself is shown in Home Assistant as **GeoapifyGeocode**. The Geoapify API key is configured once. Each tracked person or device tracker is then added as its own service/config subentry and gets its own GeoapifyGeocode device containing the related entities.

## Features

- One shared Geoapify API key for the integration
- One independently configurable tracked-person/device subentry per `person` or `device_tracker`
- One Home Assistant device per tracked person/device tracker
- Geocode and Moving entities grouped on that device
- UI configuration with Geoapify API-key validation
- Reauthentication when an API key is rejected
- Manual API-key reconfiguration
- Reverse geocoding with per-target polling and API-request movement thresholds
- Configurable maximum geocode result age
- Concurrent Geoapify requests for multiple targets
- Rate-limit handling and cached fallback results
- Selected address and timezone attributes without storing the full raw API response in Home Assistant Recorder
- Copies the source entity's `entity_picture` to Geoapify entities as a real Home Assistant entity picture for dashboards
- GPS-based moving/stationary detection using a rolling recent-position history
- GPS-accuracy-aware movement thresholds to suppress normal location drift
- One-time Recorder history recovery after restart so movement detection can resume immediately
- Automatic migration of older target-list configurations to tracked-entity subentries
- Preserves existing geocode entity unique IDs across upgrades

## Requirements

- Home Assistant with config-subentry support
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

## Configuration model

GeoapifyGeocode uses a parent/child configuration model.

The main **GeoapifyGeocode** config entry stores only the shared Geoapify API key. The key is validated before the integration is created and can later be reconfigured or reauthenticated without changing the tracked people.

Each tracked `person` or `device_tracker` is stored as its own **tracked entity** config subentry. After entering the API key during first setup, Home Assistant immediately offers to add the first tracked entity. Additional people can be added later using **Add service** on the GeoapifyGeocode integration page.

For example:

```text
GeoapifyGeocode
├── Rico
│   ├── Geocode
│   └── Moving
├── Nicholas
│   ├── Geocode
│   └── Moving
└── Priscila
    ├── Geocode
    └── Moving
```

Each tracked subentry creates its own Home Assistant device. Its Geocode and Moving entities are grouped on that device, making the integration behave like integrations where each configured person/location is shown as an individual service/device.

To change settings for one tracked person, reconfigure that tracked service. To track a different source entity, remove the existing tracked service and add a new one.

## Per-person settings

Each tracked person/device has independent settings.

### Reverse geocoding

- **Geocode update interval**: how often that source location is checked for reverse geocoding. Default: 180 seconds.
- **Minimum movement before calling Geoapify**: distance that source must move before another Geoapify request is made. Default: 100 metres.
- **Maximum geocode result age**: refresh the reverse-geocoded result once the cached result reaches this age even if the source has not moved far enough. Default: 1800 seconds.

When tracked entities have different polling intervals, the shared coordinator runs at the shortest configured interval and individually skips targets whose own interval has not yet elapsed.

### GPS movement detection

- **Movement history window**: amount of recent GPS history retained internally. Default: 600 seconds (10 minutes).
- **Movement comparison target age**: preferred age of the reference GPS point. Default: 300 seconds (5 minutes).
- **Minimum movement reference age**: prevents very recent points from being used as the comparison reference. Default: 60 seconds.
- **Minimum GPS movement distance**: absolute lower movement threshold even when GPS accuracy is very good. Default: 20 metres.
- **Fallback GPS accuracy**: accuracy used when the source entity does not provide `gps_accuracy`. Default: 25 metres.
- **Moving-to-stationary hold time**: short hysteresis period after meaningful movement to reduce state flapping. Default: 120 seconds.

## Devices and entities

Each tracked subentry gets one GeoapifyGeocode device named after the selected source entity's friendly name.

The device currently contains:

- **Geocode** sensor: the formatted reverse-geocoded address
- **Moving** binary sensor: GPS-derived moving/stationary state with Home Assistant's `moving` device class

Existing installations retain the previous entity unique IDs during migration, so the new device grouping should not create replacement geocode entities.

## Geocode sensor

The Geocode sensor state is the formatted address returned by Geoapify. Depending on the reverse-geocoding result, attributes may include:

- country and country code
- state, county and city
- postcode, street and house number
- result type and distance
- timezone and timezone name
- source entity and source friendly name
- latitude and longitude

### Entity picture

If the selected `person` or `device_tracker` has an `entity_picture`, the Geoapify entities expose the same value through Home Assistant's real `entity_picture` property.

For example, if the source entity contains:

```yaml
entity_picture: /api/image/serve/d92aa3df171c0134d6bd65f0a57b1f59/512x512
```

the corresponding Geoapify entity exposes the same `entity_picture`. This allows dashboards and cards that support entity pictures to use the source person's or device tracker's image directly.

There is no separate listener solely for picture changes. The picture is picked up when the related Geoapify entity is normally refreshed/written.

## GPS movement binary sensor

Each tracked source also gets a Moving binary sensor with Home Assistant's `moving` device class.

The binary sensor is determined from GPS coordinates only. The person's Home Assistant zone state, such as `home`, `not_home`, or a zone name, is not used to decide whether the person is moving.

The movement engine listens for latitude/longitude attribute updates from the source entity and keeps a small rolling GPS history in memory. It chooses a sufficiently old reference point, preferring a point about five minutes older than the current position by default. This makes the calculation independent of whether the phone reports every few seconds, every minute, or irregularly.

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

When the integration starts, it waits for Home Assistant Recorder to become available and performs a single history query covering the longest configured movement-history window. Attribute changes are included so latitude/longitude updates are recovered even when the source entity's main state did not change. The recovered GPS samples populate each tracked person's in-memory history, after which Recorder is no longer queried for normal movement calculations.

If Recorder is unavailable or contains no usable recent GPS states, the movement sensor starts with an empty history and remains `unknown` until enough live GPS information has been collected.

## API usage and caching

Geoapify requests are made only when a target's own polling interval is due and the target has moved at least its configured geocode minimum distance, or when its cached result reaches its configured maximum age.

The integration keeps the last successful reverse-geocoding result as a fallback for temporary Geoapify connection or response failures. Requests for multiple due targets are performed concurrently with a bounded concurrency limit, and Geoapify rate-limit responses are handled with a retry delay.

GPS movement detection itself does not call Geoapify and does not generate additional Geoapify API usage.

## Upgrading from older versions

Older GeoapifyGeocode versions stored all selected entities in one `targets` list with shared options.

When upgrading to the subentry-based version, each existing target is automatically converted into its own tracked-entity subentry. The previous shared values are copied into each subentry so behavior remains consistent immediately after migration. The shared API key remains on the parent GeoapifyGeocode config entry.

Existing geocode entity unique IDs are preserved.

## Updating

When installed through HACS, new releases can be installed through HACS in the normal way.

## Issues

Please report issues through the GitHub issue tracker:

`https://github.com/ricobach/HA-GeoapifyGeocode/issues`

## Disclaimer

This is an independent Home Assistant custom integration and is not an official Geoapify integration.
