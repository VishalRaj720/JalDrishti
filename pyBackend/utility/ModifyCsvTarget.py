# import pandas as pd
# import numpy as np

# df = pd.read_csv("baseline_groundwater.csv")

# # Normalize helper
# def norm(x):
#     return (x - x.min()) / (x.max() - x.min())

# df["Vulnerability_Index"] = (
#     0.30 * norm(1 / df["Depth_to_water_table"]) +
#     0.25 * norm(df["Hydraulic_gradient"]) +
#     0.20 * norm(1 / df["Distance_from_ISR"]) +
#     0.15 * norm(df["U_pre"]) +
#     0.10 * norm(abs(df["EC_post"] - df["EC_pre"]))
# )

# df["Vulnerability_Index"] = df["Vulnerability_Index"].clip(0, 1)


import pandas as pd
import numpy as np

# Load raw baseline data
df = pd.read_csv("baseline_groundwater_raw.csv")

# -----------------------------
# Feature Engineering
# -----------------------------

# Seasonal change
df["EC_delta"] = df["EC_post"] - df["EC_pre"]
df["U_delta"] = df["U_post"] - df["U_pre"]

# Safe normalization
def normalize(series):
    return (series - series.min()) / (series.max() - series.min() + 1e-6)

# -----------------------------
# Vulnerability Index (Target)
# -----------------------------
df["Vulnerability_Index"] = (
    0.30 * normalize(1 / df["Depth_to_water_table"]) +
    0.25 * normalize(df["Hydraulic_gradient"]) +
    0.20 * normalize(1 / df["Distance_from_ISR"]) +
    0.15 * normalize(df["U_pre"]) +
    0.10 * normalize(abs(df["EC_delta"]))
)

df["Vulnerability_Index"] = df["Vulnerability_Index"].clip(0, 1)

# -----------------------------
# Select final columns for ML
# -----------------------------
final_columns = [
    "Latitude", "Longitude",
    "Distance_from_ISR",
    "Hydraulic_gradient",
    "Depth_to_water_table",
    "pH_pre", "EC_pre", "SO4_pre", "U_pre",
    "pH_post", "EC_post", "SO4_post", "U_post",
    "EC_delta", "U_delta",
    "Vulnerability_Index"
]

df_final = df[final_columns]

# Save formatted dataset
df_final.to_csv("groundwater_ml_ready.csv", index=False)

print("Dataset prepared and saved as groundwater_ml_ready.csv")

