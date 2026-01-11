import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import json
import glob
import sys
from typing import Optional, Dict, Any

try:
    from python.kakuro_wrapper import KakuroBoard, CSPSolver, KakuroDifficultyEstimator
except ImportError:
    from kakuro_wrapper import KakuroBoard, CSPSolver, KakuroDifficultyEstimator

app = FastAPI()

class GenerateRequest(BaseModel):
    width: int = 10
    height: int = 10
    topology_params: Optional[Dict[str, Any]] = None
    fill_params: Optional[Dict[str, Any]] = None

LOG_DIR = "kakuro_logs"
if len(sys.argv) > 1:
    LOG_DIR = sys.argv[1]

# Ensure templates exist
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    template_path = os.path.join(TEMPLATE_DIR, "kakuro_viewer.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Viewer Template Not Found</h1>"

@app.post("/api/generate")
async def generate_puzzle_endpoint(req: GenerateRequest):
    try:
        board = KakuroBoard(req.width, req.height, use_cpp=True)
        solver = CSPSolver(board)
        success = solver.generate_puzzle(
            fill_params=req.fill_params,
            topo_params=req.topology_params
        )

        difficulty_estimator = KakuroDifficultyEstimator(board)
        diff  = difficulty_estimator.estimate_difficulty_detailed()

        # Convert the C++ difficulty object to a dictionary
        # (Assuming your wrapper exposes these fields)
        difficulty_data = {
            "rating": diff.rating,
            "score": round(diff.score, 2),
            "max_tier": int(diff.max_tier),
            "total_steps": diff.total_steps,
            "uniqueness": diff.uniqueness,
            "solution_count": diff.solution_count,
            "solve_path": [
                {
                    "technique": step.technique,
                    "weight": step.difficulty_weight,
                    "cells": step.cells_affected
                } for step in diff.solve_path
            ]
        }

        print(difficulty_data)
        
        
        if not success:
            raise HTTPException(status_code=500, detail="Puzzle generation failed")
            
        kakuro_id = board.get_kakuro_id()
        if not kakuro_id:
            raise HTTPException(status_code=500, detail="Failed to retrieve kakuro ID")
            
        final_grid_log = []
        # board.to_dict() returns list of rows of dicts
        for r, row in enumerate(board.to_dict()):
            for c, cell in enumerate(row):
                if cell["type"] == "WHITE":
                    final_grid_log.append([r, c, cell.get("value") or 0])

        filename = f"{kakuro_id}.json"
        log_path = os.path.join(LOG_DIR, filename)

        # 3. Explicitly close the C++ logger if your wrapper allows, 
        # or wait for board object destruction. 
        # Then, append the summary to the log file.
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                # If the C++ logger crashed or didn't close ']', fix it
                if not content.endswith("]"):
                    content += "\n]"
                data = json.loads(content)
            
            # Add a special "summary" entry
            summary_entry = {
                "id": 99999,
                "t": "Summary",
                "s": "summary", # Special stage identifier
                "ss": "final",
                "m": f"Difficulty Analysis: {diff.rating}",
                "difficulty": difficulty_data,
                "wh": [board.width, board.height], # Include dimensions
                "g": final_grid_log                 # Include the solved grid
            }
            data.append(summary_entry)
            
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(data, f)

        return {"success": True, "kakuro_id": kakuro_id, "filename": f"{kakuro_id}.json"}
    except Exception as e:
        print(f"Error generating puzzle: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def list_logs():
    if not os.path.exists(LOG_DIR):
        return {"logs": []}
    files = sorted(glob.glob(os.path.join(LOG_DIR, "*.json")), key=os.path.getmtime, reverse=True)
    return {"logs": [os.path.basename(f) for f in files]}

@app.get("/api/logs/{filename}")
async def get_log(filename: str):
    filepath = os.path.join(LOG_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log file not found")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        
        # Robustness: Handle broken JSON (missing closing bracket due to crash)
        if content and content.startswith("[") and not content.endswith("]"):
            # Try appending ']'
            try:
                data = json.loads(content + "]")
                return {"steps": data}
            except json.JSONDecodeError:
                # If that fails, maybe it ended with a comma?
                if content.endswith(","):
                    try:
                        data = json.loads(content.rstrip(",") + "]")
                        return {"steps": data}
                    except:
                        pass
        
        # Standard load attempt
        data = json.loads(content)
        return {"steps": data}
    except Exception as e:
        print(f"Error loading log {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load log: {str(e)}")

if __name__ == "__main__":
    print(f"Starting Kakuro Web Viewer on http://localhost:8000")
    print(f"Reading logs from: {LOG_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
