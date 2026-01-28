import requests
import json
import uuid

BASE_URL = "http://127.0.0.1:8000"

def test_anonymous_rating():
    puzzle_id = str(uuid.uuid4())
    print(f"Testing Anonymous Save for Puzzle ID: {puzzle_id}")
    
    payload = {
        "id": puzzle_id,
        "width": 10,
        "height": 10,
        "difficulty": "medium",
        "grid": [], # Empty grid fine for valid model? main.py checks model_dump... 
                    # Actually SaveRequest model expects specific fields.
                    # Let's mock a minimal grid
        "grid": [[{"type": "WHITE", "value": 1}] for _ in range(10)], # minimal dummy
        "userGrid": [],
        "status": "solved",
        "rowNotes": [],
        "colNotes": [],
        "cellNotes": {},
        "notebook": "",
        "rating": 5,
        "difficultyVote": 7,
        "userComment": "Anonymous verified!",
        "template_id": None
    }
    
    # Send WITHOUT auth headers
    try:
        response = requests.post(f"{BASE_URL}/save", json=payload)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Anonymous save accepted.")
        else:
            print("FAILURE: Anonymous save rejected.")
            
    except Exception as e:
        print(f"Error connecting to server: {e}")
        print("Ensure the server is running on localhost:8000")

if __name__ == "__main__":
    test_anonymous_rating()
