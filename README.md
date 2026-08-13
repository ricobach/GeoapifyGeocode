# GeoapifyGeocode

A Home Assistant custom integration that reverse-geocodes selected `person` or `device_tracker` entities using the Geoapify Reverse Geocoding API.

For each selected entity, the integration creates a sensor whose state is the formatted address returned by Geoapify. Additional attributes include country, timezone, source entity, latitude, longitude, and the raw Geoapify properties.

## Requirements

- Home Assistant
- A Geoapify API key
- One or more entities exposing `latitude` and `longitude` attributes

## Installation with HACS

1. Open HACS in Home Assistant.
2. Go to **Integrations**.
3. Open the menu and select **Custom repositories**.
4. Add `https://github.com/ricobach/GeoapifyGeocode` as an **Integration** repository.
5. Install **GeoapifyGeocode**.
6. Restart Home Assistant.
7. Go to **Settings > Devices & services > Add integration** and search for **GeoapifyGeocode**.

## Configuration

During setup, enter your Geoapify API key and select one or more entities to reverse geocode.

The integration can be reconfigured through its options:

- **Update interval**: how often target locations are checked.
- **Minimum movement**: minimum distance a target must move before another Geoapify API request is made.
- **Tracked entities**: entities to expose as reverse-geocoded sensors.

Defaults:

- Update interval: 180 seconds
- Minimum movement: 100 metres

## Sensor data

Each selected source entity gets a sensor named `<friendly name> Geocode`.

The sensor state is the Geoapify formatted address. Attributes can include:

- `country`
- `timezone`
- `timezone_name`
- `source_entity`
- `source_friendly_name`
- `lat`
- `lon`
- `raw_properties`

## API usage

The integration avoids unnecessary Geoapify requests by caching the last successful result and only requesting a new reverse-geocode result when the source entity has moved by at least the configured minimum distance.

## Issues

Please report issues through the GitHub issue tracker for this repository.

## Disclaimer

This is an independent Home Assistant custom integration and is not an official Geoapify integration.
