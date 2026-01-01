from sqlalchemy import create_engine, inspect
from python.database import DATABASE_URL

engine = create_engine(DATABASE_URL)
inspector = inspect(engine)
columns = [c["name"] for c in inspector.get_columns("puzzles")]

if "template_id" in columns:
    print("SUCCESS: template_id column exists in puzzles table.")
else:
    print("FAILURE: template_id column MISSING in puzzles table.")

if "puzzle_templates" in inspector.get_table_names():
     print("SUCCESS: puzzle_templates table exists.")
else:
     print("FAILURE: puzzle_templates table MISSING.")
