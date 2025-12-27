import pandas as pd

# Load the CSV file
df = pd.read_csv('right2023.csv')

# Convert relevant columns to numeric (handles '-' as NaN)
numeric_cols = ['pH', 'EC', 'CO3', 'HCO3', 'Cl', 'F', 'SO4', 'NO3', 'PO4',
                'Total Hardness', 'Ca', 'Mg', 'Na', 'K', 'Fe', 'As', 'U']

for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# BIS IS 10500:2012 Acceptable Limits (strict - no relaxation)
# Water is drinkable (1) only if ALL measured parameters are within these acceptable limits
acceptable_limits = {
    'pH': (6.5, 8.5),          # Range
    'EC': 1500,                # µS/cm (proxy for TDS ≤ ~960 mg/L, conservative)
    'Total Hardness': 200,     # mg/L as CaCO₃
    'Ca': 75,                  # mg/L
    'Mg': 30,                  # mg/L
    'Cl': 250,                 # mg/L
    'SO4': 200,                # mg/L
    'NO3': 45,                 # mg/L
    'F': 1.0,                  # mg/L
    'Fe': 0.3,                 # mg/L
    'As': 0.01,                # mg/L
    'U': 0.03                  # mg/L (if measured)
}

def is_drinkable(row):
    # Check pH range
    if pd.notna(row['pH']) and (row['pH'] < acceptable_limits['pH'][0] or row['pH'] > acceptable_limits['pH'][1]):
        return 0
    
    # Check each parameter if measured
    if pd.notna(row['EC']) and row['EC'] > acceptable_limits['EC']:
        return 0
    if pd.notna(row['Total Hardness']) and row['Total Hardness'] > acceptable_limits['Total Hardness']:
        return 0
    if pd.notna(row['Ca']) and row['Ca'] > acceptable_limits['Ca']:
        return 0
    if pd.notna(row['Mg']) and row['Mg'] > acceptable_limits['Mg']:
        return 0
    if pd.notna(row['Cl']) and row['Cl'] > acceptable_limits['Cl']:
        return 0
    if pd.notna(row['SO4']) and row['SO4'] > acceptable_limits['SO4']:
        return 0
    if pd.notna(row['NO3']) and row['NO3'] > acceptable_limits['NO3']:
        return 0
    if pd.notna(row['F']) and row['F'] > acceptable_limits['F']:
        return 0
    if pd.notna(row['Fe']) and row['Fe'] > acceptable_limits['Fe']:
        return 0
    if pd.notna(row['As']) and row['As'] > acceptable_limits['As']:
        return 0
    if pd.notna(row['U']) and row['U'] > acceptable_limits['U']:
        return 0
    
    return 1

# Apply classification
df['Drinkable'] = df.apply(is_drinkable, axis=1)

# Save updated CSV
df.to_csv('right2023_with_drinkable.csv', index=False)

# Summary
total = len(df)
drinkable = df['Drinkable'].sum()
non_drinkable = total - drinkable

print(f"Total samples: {total}")
print(f"Drinkable (1): {drinkable}")
print(f"Non-drinkable (0): {non_drinkable}")
print("\nSample of updated data (first 10 rows):")
print(df[['SNo.', 'Location', 'Drinkable']].head(10))