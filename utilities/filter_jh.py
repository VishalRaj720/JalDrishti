import json

input_path = "Datasets/Aquifers.geojson"
output_path = "Datasets/Aquifers_Jharkhand.geojson"

with open(input_path, "r") as f:
    data = json.load(f)

jh_features = [f for f in data["features"] if f.get("properties", {}).get("state") == "JH"]

output = {**data, "features": jh_features}

with open(output_path, "w") as f:
    json.dump(output, f)

print(f"Found {len(jh_features)} features with state='JH' -> saved to {output_path}")
