import json
import os

INPUT = os.path.join(os.path.dirname(__file__), "..", "Datasets", "Sub District Boundary.geojson")
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "Datasets", "Sub_District_Boundary_JH.geojson")

STATE_CODE = "JH"


def main():
    with open(INPUT, encoding="utf-8") as f:
        data = json.load(f)

    jh_features = [
        ft for ft in data["features"]
        if ft.get("properties", {}).get("State") == STATE_CODE
    ]

    output = {
        "type": "FeatureCollection",
        "features": jh_features,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Extracted {len(jh_features)} features with State='{STATE_CODE}'")
    print(f"Saved to: {os.path.abspath(OUTPUT)}")


if __name__ == "__main__":
    main()
