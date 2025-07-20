import os
import requests
import re
from bs4 import BeautifulSoup
from tqdm import tqdm
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

# Replace with the actual audiobook page URL
book_url = input("Enter the tokybook audiobook page URL: ").strip()

# Fetch the audiobook page
response = requests.get(book_url)
soup = BeautifulSoup(response.text, "lxml")

# Extract audiobook title
book_title = soup.find("div", {"class": "inside-page-hero grid-container grid-parent"}).find("h1").text.strip()
book_title = re.sub(r'[<>:"/\\|?*]', "_", book_title)
print(f"downloading {book_title}")
os.makedirs(f"{book_title}", exist_ok=True)

# Find chapter MP3 links
chapter_links = []
for script in soup.find_all("script"):
	if "chapter_link_dropbox" in script.text:
		for line in script.text.split("\n"):
			if "chapter_link_dropbox" in line and ".mp3" in line:
				url = line.split('"')[3]
				welcom_url = "https://file.tokybook.com/upload/welcome-you-to-tokybook.mp3"
				if not url.startswith("https://files02.tokybook.com/audio/") and url != welcom_url:
					url = "https://files02.tokybook.com/audio/" + url.replace(" ", "%20").replace('\\', "/")
				if url != welcom_url:
					chapter_links.append(url)

# Download chapters and set metadata
for i, link in enumerate(chapter_links, start=1):
	chapter_title = f"Chapter {i:02}"
	file_name = os.path.join(book_title, f"{chapter_title}.mp3")
	chap_response = requests.get(link, stream=True)
	chap_size = int(chap_response.headers.get("content-length", 0))

	if chap_response.status_code == 200:
		with open(file_name, "wb") as f, tqdm(
			total=chap_size,
			unit="B",
			unit_scale=True,
			unit_divisor=1024,
			desc=f"downloading {chapter_title}.mp3:"
		) as progress:
			for chunk in chap_response.iter_content(chunk_size=2 ** 20):
				f.write(chunk)
				progress.update(len(chunk))

		# Set MP3 metadata: title = "Chapter XX"
		try:
			audio = MP3(file_name, ID3=EasyID3)
			audio["title"] = chapter_title
			audio.save()
		except Exception as e:
			print(f"Failed to edit metadata for {file_name}: {e}")
	else:
		print(f"failed to download {link} : {chap_response}")

print("All chapters downloaded!")
