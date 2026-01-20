import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import json
import glob
import sys
from typing import Optional, Dict, Any, List

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

        # Try to find the actual log file (could be .json or .jsonl from C++)
        filename = f"{kakuro_id}.jsonl"
        log_path = os.path.join(LOG_DIR, filename)
        if not os.path.exists(log_path):
            filename = f"{kakuro_id}.json"
            log_path = os.path.join(LOG_DIR, filename)

        # 3. Explicitly close the C++ logger if your wrapper allows, 
        # or wait for board object destruction. 
        # Then, append the summary to the log file.
        if os.path.exists(log_path):
            data = load_log_robust(log_path)
            
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
            
            save_log_jsonl(log_path, data)

        return {"success": True, "kakuro_id": kakuro_id, "filename": filename}
    except Exception as e:
        print(f"Error generating puzzle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def stream_and_aggregate_profiling(filepath: str) -> List[Dict]:
    """
    Reads a profiling file line-by-line (to handle large files) and aggregates stats.
    Returns a list containing a single summary step (or actual logic steps if found mixed in).
    """
    stats = {} # Key: message -> {count, total_dur, min, max}
    non_profiling_steps = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                # Robust parsing for line-delimited JSON
                try:
                    # Handle legacy format where lines might end with comma
                    if line.endswith(","): line = line[:-1]
                    # Handle legacy format start/end brackets
                    if line == "[" or line == "]": continue
                    
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Check if this is a profiling step
                is_profiling = (entry.get("s") == "p" or entry.get("ss") == "tm")
                
                if is_profiling:
                    msg = entry.get("m", "Unknown Operation")
                    dur = float(entry.get("dur", 0.0))
                    
                    if msg not in stats:
                        stats[msg] = {
                            "count": 0,
                            "total": 0.0,
                            "min": float('inf'),
                            "max": float('-inf')
                        }
                    
                    s = stats[msg]
                    s["count"] += 1
                    s["total"] += dur
                    if dur < s["min"]: s["min"] = dur
                    if dur > s["max"]: s["max"] = dur
                else:
                    # If a real logic step ended up in the profiling file, keep it
                    non_profiling_steps.append(entry)
    except Exception as e:
        print(f"Error streaming profiling file {filepath}: {e}")
        return []

    # Create the summary report
    if stats:
        report_data = []
        for msg, s in stats.items():
            avg = s["total"] / s["count"] if s["count"] > 0 else 0
            report_data.append({
                "operation": msg,
                "calls": s["count"],
                "total_ms": round(s["total"], 2),
                "avg_ms": round(avg, 4),
                "min_ms": round(s["min"], 4) if s["min"] != float('inf') else 0,
                "max_ms": round(s["max"], 4) if s["max"] != float('-inf') else 0
            })
        
        # Sort by total duration descending
        report_data.sort(key=lambda x: x["total_ms"], reverse=True)

        summary_step = {
            "id": 999998, # High ID to appear at end
            "s": "info",
            "ss": "profiling_report",
            "m": "Profiling Aggregation Report",
            "d": {"stats": report_data}
        }
        non_profiling_steps.append(summary_step)

    return non_profiling_steps

def load_log_robust(filepath: str) -> List[Dict]:
    """
    Reads a main log file, handling both JSON Array and JSONL formats.
    """
    if not os.path.exists(filepath):
        return []
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
        if not content: return []

        # Case 1: Standard JSON Array
        if content.startswith("["):
            # Try to fix truncated JSON arrays
            if not content.endswith("]"):
                # Find last valid object closer
                last_brace = content.rfind("}")
                if last_brace != -1:
                    content = content[:last_brace+1] + "\n]"
                else:
                    return [] # Unrecoverable
            try:
                return json.loads(content)
            except:
                pass # Fallback to line processing if array parse fails

        # Case 2: JSONL (Line delimited) or mixed
        data = []
        lines = content.splitlines() if "\n" in content else [content]
        for line in lines:
            line = line.strip()
            if not line or line in ["[", "]", "],"]: continue
            try:
                if line.endswith(","): line = line[:-1]
                data.append(json.loads(line))
            except: continue
        return data
    except Exception as e:
        print(f"Error loading log {filepath}: {e}")
        return []

def save_log_jsonl(filepath: str, data: list):
    """
    Saves a list of dicts as a JSONL file.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry) + "\n")

@app.get("/api/logs")
async def list_logs():
    if not os.path.exists(LOG_DIR):
        return {"logs": []}
    # List both .json (legacy) and .jsonl (new) files, excluding profiling files
    files = []
    for ext in ["*.json", "*.jsonl"]:
        files.extend(glob.glob(os.path.join(LOG_DIR, f"kakuro_{ext}")))
    files = sorted(files, key=os.path.getmtime, reverse=True)
    return {"logs": [os.path.basename(f) for f in files]}

@app.get("/api/logs/{filename}")
async def get_log(filename: str, prof: int = 0):
    filepath = os.path.join(LOG_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log file not found")
    
    try:
        # 1. Read main file (logic steps)
        data = load_log_robust(filepath)
        
        # 2. Optionally read profiling file
        if prof:
            # Profiling file is prefixed with underscore. 
            # It might have .json or .jsonl extension depending on transition state.
            basename, ext = os.path.splitext(filename)
            prof_candidates = [
                os.path.join(LOG_DIR, f"_{filename}"),
                os.path.join(LOG_DIR, f"_{basename}.json"),
                os.path.join(LOG_DIR, f"_{basename}.jsonl")
            ]


            prof_data = []
            for p_path in prof_candidates:
                if os.path.exists(p_path):
                    # Use the streaming aggregator
                    prof_data = stream_and_aggregate_profiling(p_path)
                    break
            
            data.extend(prof_data)

            # Sort mainly by ID, but ensure Summary/Profile reports stay at end
            def sort_key(x):
                # Ensure items with ID go by ID, items without (if any) go to end
                return x.get("id", 999999)
            
            data.sort(key=sort_key)


        return {"steps": data}
    except Exception as e:
        print(f"Error loading log {filename}: {e}")
        # Try to return a partial list if possible
        return {"steps": [{"id": 0, "s": "error", "ss": "error", "m": f"Failed to parse log: {str(e)}"}]}

if __name__ == "__main__":
    print(f"Starting Kakuro Web Viewer on http://localhost:8001")
    print(f"Reading logs from: {LOG_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=8001)
