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
            
            # Optimize the log before saving
            optimized_data = optimize_log_data(data)
            
            save_log_jsonl(log_path, optimized_data)

        return {"success": True, "kakuro_id": kakuro_id, "filename": f"{kakuro_id}.json"}
    except Exception as e:
        print(f"Error generating puzzle: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def optimize_log_data(data: list):
    """
    Groups consecutive uniqueness_conflict steps and profile steps.
    """
    if not data:
        return data
    
    optimized = []
    i = 0
    while i < len(data):
        step = data[i]
        stage = step.get("s")
        substage = step.get("ss")
        
        # 1. Cluster uniqueness conflicts
        if substage == "uniqueness_conflict":
            cluster_steps = []
            while i < len(data) and data[i].get("ss") == "uniqueness_conflict":
                cluster_steps.append(data[i])
                i += 1
            
            first = cluster_steps[0]
            solutions = []
            for s in cluster_steps:
                extra = s.get("d", {})
                ag = extra.get("ag", [])
                main_grid = s.get("g", [])
                main_lookup = {(r, c): v for r, c, v in main_grid}
                diff_count = 0
                for r, c, v in ag:
                    if main_lookup.get((r, c)) != v:
                        diff_count += 1
                solutions.append({
                    "ag": ag,
                    "diff_count": diff_count,
                    "hc": extra.get("hc", [])
                })
            
            total_dur = sum(s.get("dur", 0) for s in cluster_steps)
            optimized.append({
                "id": first["id"],
                "s": first["s"],
                "ss": "uniqueness_cluster",
                "m": f"Uniqueness Cluster: {len(cluster_steps)} attempts",
                "dur": round(total_dur, 2),
                "wh": first.get("wh"),
                "g": first.get("g"),
                "d": {"attempts": len(cluster_steps), "solutions": solutions}
            })
            
        # 2. Cluster performance profiles (can be MILLIONS of entries)
        elif stage == "p" or substage == "tm":
            profile_group = []
            msg = step.get("m", "")
            while i < len(data) and (data[i].get("s") == "p" or data[i].get("ss") == "tm") and data[i].get("m") == msg:
                profile_group.append(data[i])
                i += 1
                
            total_dur = sum(p.get("dur", 0) for p in profile_group)
            optimized.append({
                "id": profile_group[0]["id"],
                "s": "p",
                "ss": "tm",
                "m": f"{msg} (x{len(profile_group)})",
                "dur": round(total_dur, 4)
            })
            
        else:
            optimized.append(step)
            i += 1
            
    return optimized

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
    files = sorted(glob.glob(os.path.join(LOG_DIR, "*.json")), key=os.path.getmtime, reverse=True)
    return {"logs": [os.path.basename(f) for f in files]}

@app.get("/api/logs/{filename}")
async def get_log(filename: str, prof: int = 0):
    filepath = os.path.join(LOG_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log file not found")
    
    try:
        def read_jsonl(path):
            if not os.path.exists(path):
                return []
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return []
            
            data = []
            if content.startswith("["):
                # Legacy recovery logic... (omitted for brevity in this helper, but used below)
                pass
            
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                if not line or line in ["[", "]", "],"]: continue
                try:
                    if line.endswith(","): line = line[:-1]
                    data.append(json.loads(line))
                except: continue
            return data

        # 1. Read main file
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        
        data = []
        if content.startswith("["):
            # Legacy recovery
            content_clean = content.strip()
            if content_clean.endswith("]"):
                try: data = json.loads(content_clean)
                except: pass
            if not data:
                last_bracket = content_clean.rfind("}")
                while last_bracket != -1:
                    try:
                        probe = content_clean[:last_bracket+1].strip()
                        if not probe.endswith("]"): probe += "\n]"
                        data = json.loads(probe)
                        break
                    except: last_bracket = content_clean.rfind("}", 0, last_bracket)
        else:
            for line in content.splitlines():
                line = line.strip()
                if not line or line in ["[", "]", "],"]: continue
                try:
                    if line.endswith(","): line = line[:-1]
                    data.append(json.loads(line))
                except: continue

        main_data_len = len(data)
        
        # 2. Optionally read profiling file
        if prof:
            prof_path = os.path.join(LOG_DIR, "_" + filename)
            if os.path.exists(prof_path):
                prof_data = []
                with open(prof_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try:
                            prof_data.append(json.loads(line))
                        except: continue
                data.extend(prof_data)
                # Sort by id to restore original sequence
                data.sort(key=lambda x: x.get("id", 0))

        if not data:
            return {"steps": []}
            
        # 3. Optimize
        optimized = optimize_log_data(data)
        
        # 4. Save back main file if migrated or optimized (ONLY if NOT loading extra profiling data to avoid pollution)
        if not prof:
            was_legacy = content.startswith("[")
            if len(optimized) < main_data_len or was_legacy:
                try:
                    save_log_jsonl(filepath, optimized)
                    if was_legacy: print(f"✓ Migrated {filename} to JSONL")
                except Exception as e:
                    print(f"Warning: Failed to save optimized log {filename}: {e}")
            
        return {"steps": optimized}
    except Exception as e:
        print(f"Error loading log {filename}: {e}")
        # Try to return a partial list if possible
        return {"steps": [{"id": 0, "s": "error", "ss": "error", "m": f"Failed to parse log: {str(e)}"}]}

if __name__ == "__main__":
    print(f"Starting Kakuro Web Viewer on http://localhost:8000")
    print(f"Reading logs from: {LOG_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
