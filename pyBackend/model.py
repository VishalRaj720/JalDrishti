# # Add target variable
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


# # Train Random Forest Model
# from sklearn.model_selection import train_test_split
# from sklearn.ensemble import RandomForestRegressor
# from sklearn.metrics import r2_score, mean_squared_error

# features = [
#     "Distance_from_ISR",
#     "Hydraulic_gradient",
#     "Depth_to_water_table",
#     "pH_pre", "EC_pre", "SO4_pre", "U_pre",
#     "pH_post", "EC_post", "SO4_post", "U_post"
# ]

# X = df[features]
# y = df["Vulnerability_Index"]

# X_train, X_test, y_train, y_test = train_test_split(
#     X, y, test_size=0.25, random_state=42
# )

# model = RandomForestRegressor(
#     n_estimators=300,
#     max_depth=10,
#     random_state=42
# )

# model.fit(X_train, y_train)

# y_pred = model.predict(X_test)

# print("R2 Score:", r2_score(y_test, y_pred))
# print("RMSE:", mean_squared_error(y_test, y_pred, squared=False))


# # Feature Importance (must include)
# importances = pd.Series(
#     model.feature_importances_,
#     index=features
# ).sort_values(ascending=False)

# print(importances)


import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score

# Load formatted dataset
df = pd.read_csv("groundwater_ml_ready.csv")

# -----------------------------
# Features & Target
# -----------------------------
features = [
    "Distance_from_ISR",
    "Hydraulic_gradient",
    "Depth_to_water_table",
    "pH_pre", "EC_pre", "SO4_pre", "U_pre",
    "pH_post", "EC_post", "SO4_post", "U_post",
    "EC_delta", "U_delta"
]

X = df[features]
y = df["Vulnerability_Index"]

# -----------------------------
# Train-test split
# -----------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=42
)

# -----------------------------
# Model
# -----------------------------
model = RandomForestRegressor(
    n_estimators=300,
    max_depth=10,
    random_state=42
)

model.fit(X_train, y_train)

# -----------------------------
# Evaluation
# -----------------------------
y_pred = model.predict(X_test)

print("R2 Score:", r2_score(y_test, y_pred))
print("RMSE:", mean_squared_error(y_test, y_pred, squared=False))

# -----------------------------
# Predict full dataset (for maps)
# -----------------------------
df["Predicted_Vulnerability"] = model.predict(X)

df.to_csv("groundwater_with_predictions.csv", index=False)

print("Predictions saved to groundwater_with_predictions.csv")
