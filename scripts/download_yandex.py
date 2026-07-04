import os
import sys
import json
import urllib.request
import zipfile
from pathlib import Path

def download_yandex_disk_folder(public_link: str, target_dir: Path):
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(exist_ok=True)
    
    print(f"Fetching download URL for public link: {public_link}...")
    api_url = f"https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={urllib.parse.quote(public_link)}"
    
    try:
        # 1. Fetch Yandex API response
        with urllib.request.urlopen(api_url) as response:
            data = json.loads(response.read().decode())
            download_url = data.get("href")
            
        if not download_url:
            print("Error: Could not retrieve download URL from Yandex Disk API.")
            return False
            
        # 2. Download zip file
        zip_path = target_dir / "yandex_disk_archive.zip"
        print(f"Downloading archive to {zip_path.name}...")
        
        # Monitor download progress
        def progress_report(block_num, block_size, total_size):
            read_so_far = block_num * block_size
            if total_size > 0:
                percent = min(100, int(read_so_far * 100 / total_size))
                sys.stdout.write(f"\rDownloading: {percent}% ({read_so_far // (1024 * 1024)} MB of {total_size // (1024 * 1024)} MB)")
            else:
                sys.stdout.write(f"\rDownloading: {read_so_far // (1024 * 1024)} MB")
            sys.stdout.flush()
            
        urllib.request.urlretrieve(download_url, zip_path, reporthook=progress_report)
        print("\nDownload finished successfully.")
        
        # 3. Unpack archive
        print("Extracting ZIP archive...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
            
        # 4. Clean up zip archive
        zip_path.unlink()
        print(f"Folder downloaded and extracted into {target_dir} successfully.")
        return True
        
    except Exception as e:
        print(f"\nError downloading from Yandex Disk: {e}")
        return False

if __name__ == "__main__":
    # Yandex Disk link from request
    link = "https://disk.yandex.ru/d/npigiuw4Rbe9Pg"
    if len(sys.argv) > 1:
        link = sys.argv[1]
        
    dest = "./inputs"
    if len(sys.argv) > 2:
        dest = sys.argv[2]
        
    download_yandex_disk_folder(link, Path(dest))
