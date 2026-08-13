# GeoapifyGeocode

A Home Assistant custom integration that reverse-geocodes selected `person` or `device_tracker` entities using the Geoapify Reverse Geocoding API.

For each selected entity, the integration creates a sensor whose state is the formatted address returned by Geoapify.

## Features

- UI configuration with Geoapify API-key validation
- Reauthentication when an API key is rejected
- Manual API-key reconfiguration
- Select `person` and `device_tracker` entities to geocode
- Configurable polling interval
- Movement threshold to reduce API requests
- Maximum result age so stationary locations are periodically refreshed
- Concurrent requests for multiple moving targets
- Rate-limit handling and cached fallback results
- Selected address and timezone attributes without storing the full raw API response in Home Assistant's recorder

## Installation with HACS

1. Open HACS in Home Assistant.
2. Go to **Integrations**.
3. Open the menu and select **Custom repositories**.
4. Add `https://github.com/ricobach/GeoapifyGeocode` as an **Integration** repository.
5. Install **GeoapifyGeocode**.
6. Restart Home Assistant.
7. Go to **Settings > Devices & services > Add integration** and search for **GeoapifyGeocode**.

## Configuration

During setup, enter your Geoapify API key and select one or more `person` or `device_tracker` entities.

Options:

- **Update interval**: how often target locations are checked. Default: 180 seconds.
- **Minimum movement**: distance a target must move before another Geoapify request is made. Default: 100 metres.
- **Maximum result age**: refresh even without enough movement once the cached result reaches this age. Default: 1800 seconds.
- **Tracked entities**: entities to expose as reverse-geocoded sensors.

## Sensor data

Each selected source entity gets a `<friendly name> Geocode` sensor.

The sensor state is the Geoapify formatted address. Depending on the result, attributes may include:

- country and country code
- state, county and city
- postcode, street and house number
- result type and distance
- timezone and timezone name
- source entity and source friendly name
- latitude and longitude

## API usage

Geoapify requests are made only when a target has moved far enough or when the cached result reaches the configured maximum age. The integration also keeps the last successful result as a fallback for transient Geoapify failures.

## Issues

Please report issues through the GitHub issue tracker for this repository.

## Disclaimer

This is an independent Home Assistant custom integration and is not an official Geoapify integration.
