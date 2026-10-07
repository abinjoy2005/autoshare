from pathlib import Path

# Define the root directory
project_root = Path("autoshare")

# Define the directory structure and the files within them
structure = {
    "app": [
        "__init__.py", 
        "main.py", 
        "schemas.py", 
        "database.py",
        "models.py",
        "engine.py", 
        "websocket_manager.py"
    ],
    "static": [
        "index.html", 
        "styles.css", 
        "app.js"
    ],
    "": [
        "requirements.txt", 
        "run.py"
    ]
}

# Generate the folders and touch the files
for folder, files in structure.items():
    folder_path = project_root / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    
    for file in files:
        file_path = folder_path / file
        file_path.touch(exist_ok=True)

print("✅ AutoShare directory structure and files created successfully!")