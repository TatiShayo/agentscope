import urllib.request
import json
import zipfile
import tarfile
import io
import os
import sys

def download_and_extract():
    url = "https://api.github.com/repos/jaegertracing/jaeger/releases/latest"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching release info: {e}")
        # Fallback to a known working URL if API limit or network issue occurs
        tag = "v1.60.0"
        fallback_url = f"https://github.com/jaegertracing/jaeger/releases/download/{tag}/jaeger-1.60.0-windows-amd64.zip"
        print(f"Attempting fallback download from: {fallback_url}")
        download_url(fallback_url)
        return

    assets = data.get("assets", [])
    download_link = None
    for asset in assets:
        name = asset.get("name", "")
        if "windows-amd64" in name and (name.endswith(".zip") or name.endswith(".tar.gz")):
            download_link = asset.get("browser_download_url")
            print(f"Found Jaeger asset: {name} -> {download_link}")
            break

    if not download_link:
        print("No windows-amd64 zip/tar.gz found in latest assets. Downloading fallback.")
        download_link = "https://github.com/jaegertracing/jaeger/releases/download/v1.60.0/jaeger-1.60.0-windows-amd64.zip"

    download_url(download_link)

def download_url(url):
    print(f"Downloading from {url}...")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req) as response:
        content = response.read()

    os.makedirs("jaeger_bin", exist_ok=True)
    
    if url.endswith(".zip"):
        print("Extracting zip archive...")
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            z.extractall("jaeger_bin")
    elif url.endswith(".tar.gz") or url.endswith(".tgz"):
        print("Extracting tar.gz archive...")
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as t:
            t.extractall("jaeger_bin")
    else:
        # Check if we can extract as zip anyway
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                z.extractall("jaeger_bin")
        except Exception:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as t:
                t.extractall("jaeger_bin")
    
    print("Extraction complete. Jaeger binary is inside 'jaeger_bin' directory.")

if __name__ == "__main__":
    download_and_extract()
