import json
import os

def filter_geojson_by_state(input_file, state_name):
    """
    Filters features in a GeoJSON file by state_name property.
    """
    if not os.path.exists(input_file):
        print(f"Error: File {input_file} not found.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return

    if 'features' not in data:
        print("Error: Invalid GeoJSON format (no 'features' key).")
        return

    # Filter features where state_name matches (case-insensitive)
    filtered_features = [
        feature for feature in data['features']
        if feature.get('properties', {}).get('state_name', '').lower() == state_name.lower()
    ]

    # Update the data object
    data['features'] = filtered_features

    # Save to a new file to avoid overwriting original data
    output_file = input_file.replace('.geojson', f'_{state_name.lower()}.geojson')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    print(f"Successfully filtered {len(filtered_features)} features.")
    print(f"Output saved to: {output_file}")

if __name__ == "__main__":
    # Path relative to project root or use absolute path
    # Current sample file path:
    input_path = r'c:\Users\letsm\OneDrive\Desktop\JalDrishti\Datasets\WaterQuality.geojson'
    target_state = 'Jharkhand'
    
    filter_geojson_by_state(input_path, target_state)
