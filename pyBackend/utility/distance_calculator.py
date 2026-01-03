import math

def calculate_distance(x1, y1, x2, y2):
    """
    Calculate the distance between two geographic points using the Haversine formula.
    
    Parameters:
    x1, x2 (float): Latitude coordinates in decimal degrees
    y1, y2 (float): Longitude coordinates in decimal degrees
    
    Returns:
    float: Distance in kilometers
    """
    # Earth's radius in kilometers
    R = 6371.0
    
    # Convert latitude and longitude from degrees to radians
    lat1_rad = math.radians(x1)
    lat2_rad = math.radians(x2)
    lon1_rad = math.radians(y1)
    lon2_rad = math.radians(y2)
    
    # Differences in coordinates
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    # Haversine formula
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Calculate distance
    distance = R * c
    
    return distance


def calculate_distance_miles(x1, y1, x2, y2):
    """
    Calculate the distance between two geographic points in miles.
    
    Parameters:
    x1, x2 (float): Latitude coordinates in decimal degrees
    y1, y2 (float): Longitude coordinates in decimal degrees
    
    Returns:
    float: Distance in miles
    """
    distance_km = calculate_distance(x1, y1, x2, y2)
    return distance_km * 0.621371  # Convert km to miles


# Example usage
if __name__ == "__main__":
    # Example: Distance between New Delhi and Mumbai
    delhi_lat, delhi_lon = 28.6139, 77.2090
    mumbai_lat, mumbai_lon = 19.0760, 72.8777
    
    distance_km = calculate_distance(delhi_lat, delhi_lon, mumbai_lat, mumbai_lon)
    distance_miles = calculate_distance_miles(delhi_lat, delhi_lon, mumbai_lat, mumbai_lon)
    
    print(f"Distance between Delhi and Mumbai:")
    print(f"  {distance_km:.2f} kilometers")
    print(f"  {distance_miles:.2f} miles")
    
    # Interactive mode
    print("\n" + "="*50)
    print("Calculate distance between two points")
    print("="*50)
    
    try:
        x1 = float(input("Enter latitude of point 1 (x1): "))
        y1 = float(input("Enter longitude of point 1 (y1): "))
        x2 = float(input("Enter latitude of point 2 (x2): "))
        y2 = float(input("Enter longitude of point 2 (y2): "))
        
        distance_km = calculate_distance(x1, y1, x2, y2)
        distance_miles = calculate_distance_miles(x1, y1, x2, y2)
        
        print(f"\nDistance between the two points:")
        print(f"  {distance_km:.2f} kilometers")
        print(f"  {distance_miles:.2f} miles")
        
    except ValueError:
        print("Error: Please enter valid numeric coordinates.")
