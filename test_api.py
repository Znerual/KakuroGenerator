import requests
import json

try:
    response = requests.get("http://127.0.0.1:8000/generate")
    response.raise_for_status()
    data = response.json()
    print("Keys:", data.keys())
    if "grid" in data and len(data["grid"]) > 0:
        first_cell = data["grid"][0][0]
        print("First cell sample:", first_cell)
        print("Type of 'type' field:", type(first_cell.get("type")))
except Exception as e:
    print(e)
