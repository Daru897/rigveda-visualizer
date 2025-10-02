import requests
import os

url = "http://www.detlef108.de/RV-with-Padapatha-T-NA-UTF8.html"
save_path = "../data/raw/samhita_translit_full.html"

os.makedirs(os.path.dirname(save_path), exist_ok=True)

response = requests.get(url)
if response.status_code == 200:
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(response.text)
    print("✅ Downloaded successfully:", save_path)
else:
    print("❌ Failed to download, status:", response.status_code)

