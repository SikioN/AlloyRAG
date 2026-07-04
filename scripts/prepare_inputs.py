import os
import shutil
import zipfile
import subprocess
from pathlib import Path

# Target document extensions to extract and keep
DOCUMENT_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".docm", ".pptx", ".ppt", ".xlsx", ".xls", 
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml"
}

def extract_zip(archive_path: Path, extract_to: Path):
    """Extract zip archive using built-in zipfile module."""
    print(f"Extracting ZIP: {archive_path.name}...")
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        return True
    except Exception as e:
        print(f"Error extracting ZIP {archive_path.name}: {e}")
        return False

def extract_rar(archive_path: Path, extract_to: Path):
    """Extract rar archive using system commands (unrar or 7z)."""
    print(f"Extracting RAR: {archive_path.name}...")
    # Try unrar first, then 7z
    for cmd in [["unrar", "x", "-o+", str(archive_path), str(extract_to)],
                ["7z", "x", f"-o{extract_to}", "-y", str(archive_path)]]:
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Subprocess error running {cmd[0]}: {e}")
    print(f"Warning: Failed to extract RAR {archive_path.name}. Ensure 'unrar' or 'p7zip-full' (7z) is installed on the server.")
    return False

def process_directory(target_dir: Path):
    """Recursively unpack archives and flatten documents into target_dir root."""
    target_dir = Path(target_dir).resolve()
    if not target_dir.exists():
        print(f"Directory {target_dir} does not exist.")
        return

    print(f"Starting input preparation in: {target_dir}")
    
    # 1. Unpack archives recursively
    archives_found = True
    while archives_found:
        archives_found = False
        for path in list(target_dir.rglob("*")):
            if not path.is_file():
                continue
                
            suffix = path.suffix.lower()
            if suffix == ".zip":
                # Extract into a subfolder named after the archive
                extract_subdir = path.parent / f"extracted_{path.stem}"
                extract_subdir.mkdir(exist_ok=True)
                if extract_zip(path, extract_subdir):
                    path.unlink() # Delete archive
                    archives_found = True # Check again in case nested archives exist
            elif suffix == ".rar":
                extract_subdir = path.parent / f"extracted_{path.stem}"
                extract_subdir.mkdir(exist_ok=True)
                if extract_rar(path, extract_subdir):
                    path.unlink() # Delete archive
                    archives_found = True

    # 2. Flatten document files into the root of target_dir
    print("Flattening document files to the inputs root...")
    for path in list(target_dir.rglob("*")):
        if not path.is_file() or path.parent == target_dir:
            continue
            
        suffix = path.suffix.lower()
        if suffix in DOCUMENT_EXTENSIONS:
            dest_path = target_dir / path.name
            
            # Prevent filename collisions by appending a counter if a file with same name exists
            counter = 1
            while dest_path.exists():
                dest_path = target_dir / f"{path.stem}_{counter}{path.suffix}"
                counter += 1
                
            print(f"Moving: {path.relative_to(target_dir)} -> {dest_path.name}")
            shutil.move(str(path), str(dest_path))
        else:
            # Delete non-document file (like junk system files or extra formats)
            try:
                path.unlink()
            except Exception:
                pass

    # 3. Clean up empty subdirectories
    print("Cleaning up empty subdirectories...")
    for root, dirs, files in os.walk(target_dir, topdown=False):
        for dir_name in dirs:
            dir_path = Path(root) / dir_name
            try:
                # Delete empty directories
                if not os.listdir(dir_path):
                    dir_path.rmdir()
            except Exception:
                pass

    print("Input folders preparation completed successfully.")

if __name__ == "__main__":
    import sys
    # Use ./inputs by default
    input_folder = "./inputs"
    if len(sys.argv) > 1:
        input_folder = sys.argv[1]
    
    process_directory(Path(input_folder))
