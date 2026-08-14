# HA-GeoapifyGeocode

A Home Assistant custom integration that reverse-geocodes selected `person` or `device_tracker` entities using the Geoapify Reverse Geocoding API.

The integration itself is shown in Home Assistant as **GeoapifyGeocode**. For each selected source entity, it creates a sensor whose state is the formatted address returned by Geoapify.

## Features

- UI configuration with Geoapify API-key validation
- Reauthentication when an API key is rejected
- Manual API-key reconfiguration
- Select `person` and `device_tracker` entities to geocode
- Configurable polling interval
- Configurable movement threshold to reduce API requests
- Configurable maximum result age so stationary locations are periodically refreshed
- Concurrent requests for multiple moving targets
- Rate-limit handling and cached fallback results
- Selected address and timezone attributes without storing the full raw API response in Home Assistant's recorder
- Copies the source entity's `entity_picture` to the Geoapify sensor as a real Home Assistant entity picture for use in dashboards
- Preserves existing entity unique IDs across upgrades

## Requirements

- Home Assistant
- HACS, if installing through HACS
- A Geoapify API key
- At least one `person` or `device_tracker` entity that provides `latitude` and `longitude` attributes

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

After installation, the following options can be changed from the integration's options flow:

- **Update interval**: how often target locations are checked. Default: 180 seconds.
- **Minimum movement**: distance a target must move before another Geoapify request is made. Default: 100 metres.
- **Maximum result age**: refresh the reverse-geocoded result once the cached result reaches this age, even if the source has not moved far enough. Default: 1800 seconds.
- **Tracked entities**: `person` and `device_tracker` entities to expose as reverse-geocoded sensors.

The Geoapify API key can also be reconfigured. If Geoapify rejects the configured key, Home Assistant starts a reauthentication flow.

## Sensor data

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

## API usage and caching

Geoapify requests are made only when a target has moved at least the configured minimum distance or when the cached result reaches the configured maximum age.

The integration keeps the last successful reverse-geocoding result as a fallback for temporary Geoapify connection or response failures. Requests for multiple targets are performed concurrently with a bounded concurrency limit, and Geoapify rate-limit responses are handled with a retry delay.

## Updating

When installed through HACS, new releases can be installed through HACS in the normal way. Existing unique IDs are preserved so upgrading does not create duplicate sensors.

## Issues

Please report issues through the GitHub issue tracker:

`https://github.com/ricobach/HA-GeoapifyGeocode/issues`

## Disclaimer

This is an independent Home Assistant custom integration and is not an official Geoapify integration.
