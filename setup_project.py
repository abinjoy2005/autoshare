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
        "security.py",
        "websocket_manager.py",
        "routers/__init__.py",
        "routers/auth.py",
        "routers/drivers.py",
        "routers/rides.py",
    ],
    "static": [
        "index.html", 
        "styles.css",
        "app.js",
        "tailwind.input.css",
        "tailwind.css",
        "vendor/leaflet.js",
        "vendor/leaflet.css",
        "vendor/LEAFLET-LICENSE",
        "vendor/images/layers-2x.png",
        "vendor/images/layers.png",
        "vendor/images/marker-icon-2x.png",
        "vendor/images/marker-icon.png",
        "vendor/images/marker-shadow.png",
    ],
    "": [
        "requirements.txt", 
        "run.py",
        "vercel.json",
        ".env.example",
        ".gitignore",
        "package.json",
        "package-lock.json",
        "tailwind.config.js",
    ]
}

structure["migrations"] = ["001_initial_schema.sql", "README.md"]

# Generate the folders and touch the files
for folder, files in structure.items():
    folder_path = project_root / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    
    for file in files:
        file_path = folder_path / file
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch(exist_ok=True)

print("✅ AutoShare directory structure and files created successfully!")