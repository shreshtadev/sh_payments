import pandas as pd
import os

data_path = os.path.join(os.path.dirname(__file__), "../", "data", "products.json")
invlaid_data_path = os.path.join(
    os.path.dirname(__file__), "../", "data", "inv_products.json"
)
# Load your JSON file
df = pd.read_json(data_path)

# Ensure HSNSACCODE is treated as string
df["HSNSACCODE"] = df["HSNSACCODE"].astype(str)
df["GSTRATEIGSTRATE"] = df["GSTRATEIGSTRATE"].astype(str)
df["GSTMASTERDISPNAME"] = df["GSTMASTERDISPNAME"].astype(str)

# Filter rows where HSNSACCODE is missing or only 4 characters long
filtered_df = df[
    (df["HSNSACCODE"].str.strip() == "")
    | (df["HSNSACCODE"].str.len() == 4)
    | (df["GSTRATEIGSTRATE"].str.strip() == "")
    | (df["GSTMASTERDISPNAME"].str.strip() == "")
]

# filtered_df.to_json(invlaid_data_path, orient="records", indent=2)

print(filtered_df.count(axis=0))
