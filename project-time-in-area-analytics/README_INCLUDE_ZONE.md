# Include Zone for Analytics

We make use of the same format for the include zone as the AXIS Object Analytics ACAP app does. That way, we can export the zone from there and use the same zone for this analytics too.

## Exporting the Include Zone

The [AOA VAPIX API is documented here](https://developer.axis.com/vapix/applications/axis-object-analytics-api/).

You can run the following command:

```bash
curl -X POST \
 --digest -u root:ACAPdev \
 -H "Content-Type: application/json" \
 -d '{"apiVersion": "1.2", "context": "zone_export", "method": "getConfiguration"}' \
 "http://${CAMERA_IP}/local/objectanalytics/control.cgi"
```

This will contain information about the configuration, including one or multiple include zones for a scenario:

```json
"vertices":[[-0.97,-0.97],[-0.97,0.97],[-0.1209,0.9616],[-0.03069,0.7259],[0.05851,0.5204],[0.04617,-0.9691]]
```

The example above is from the `data.scenarios[0].triggers[0].vertices` field.

## The coordinate system

The AXIS Object Analytics API uses a normalized coordinate system where all coordinates are in the range **[-1, 1]**:

- **X-axis**: `-1` (left edge) to `+1` (right edge)
- **Y-axis**: `-1` (bottom edge) to `+1` (top edge)

The center of the image is at coordinates `(0, 0)`.

## Visualizing the Zone

To visualize the zone on a camera snapshot, use the `visualize_zone.py` script in the `test_scripts` directory:

```bash
# Display the zone
python test_scripts/visualize_zone.py \
  -v '[[-0.97,-0.97],[-0.97,0.97],[-0.1209,0.9616],[-0.03069,0.7259],[0.05851,0.5204],[0.04617,-0.9691]]' \
  -i test_files/snapshot.jpg
```

This will overlay the zone polygon on the image with a semi-transparent green fill, showing exactly which area is being monitored.
