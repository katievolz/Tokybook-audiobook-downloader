import os
import sys
import requests
import re
from bs4 import BeautifulSoup
from tqdm import tqdm
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from typing import Optional, List, Dict
from pathlib import Path


WELCOME_URL = "https://file.tokybook.com/upload/welcome-you-to-tokybook.mp3"
AUDIO_BASE_URL = "https://files02.tokybook.com/audio/"
HEADERS = {
	"User-Agent": "Mozilla/5.0 (compatible; TokybookDownloader/1.0; +https://github.com/katievolz/Tokybook-audiobook-downloader)"
}


def fetch_webpage(url: str) -> Optional[BeautifulSoup]:
	"""Fetch and parse a webpage, returning BeautifulSoup object or None on failure."""
	try:
		response = requests.get(url, headers=HEADERS, timeout=15)
		response.raise_for_status()
		return BeautifulSoup(response.text, "lxml")
	except Exception as e:
		print(f"Error fetching webpage: {e}")
		return None


def extract_book_title(soup: BeautifulSoup) -> Optional[str]:
	"""Extract book title from the page using multiple fallback methods."""
	# Try meta tags first
	meta_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "title"})
	if meta_title and meta_title.get("content"):
		return meta_title["content"].strip()

	# Try h1 in hero section
	hero = soup.find("div", {"class": "inside-page-hero grid-container grid-parent"})
	if hero and hero.find("h1"):
		return hero.find("h1").text.strip()

	# Try any h1
	if soup.find("h1"):
		return soup.find("h1").text.strip()

	# Fallback to title tag
	if soup.title:
		return soup.title.text.strip()
	
	return None


def sanitize_filename(name: str) -> str:
	"""Sanitize a string to be used as a filename."""
	return re.sub(r'[<>:"/\\|?*]', "_", name)


def extract_chapter_links(soup: BeautifulSoup) -> List[str]:
	"""Extract all chapter MP3 links from the page."""
	chapter_links = []
	seen_urls = set()

	def add_url(url: str) -> None:
		"""Add URL if valid and not seen before."""
		if url and url != WELCOME_URL and url not in seen_urls:
			if not url.startswith("http"):
				url = AUDIO_BASE_URL + url.replace(" ", "%20").replace('\\', "/")
			seen_urls.add(url)
			chapter_links.append(url)

	for script in soup.find_all("script"):
		if not script.string:
			continue

		# Look for direct MP3 URLs
		urls = re.findall(r'https?://[^"\'\s]+?\.mp3', script.string)
		for url in urls:
			add_url(url)

		# Look for chapter_link_dropbox patterns
		if "chapter_link_dropbox" in script.string:
			matches = re.findall(r'chapter_link_dropbox[^\n\r"\']*["\']([^"\']+?\.mp3)["\']', script.string)
			for url in matches:
				add_url(url)

	# Search in audio tags and links
	for tag in soup.find_all(["audio", "source", "a"], src=True):
		add_url(tag.get("src"))

	for link in soup.find_all("a", href=True):
		if link["href"].endswith(".mp3"):
			add_url(link["href"])

	return chapter_links


def download_file(url: str, filepath: Path, desc: str) -> bool:
	"""Download a file with progress bar, returns True if successful."""
	try:
		response = requests.get(url, stream=True, headers=HEADERS, timeout=30)
		response.raise_for_status()
		
		file_size = int(response.headers.get("content-length", 0))
		
		with open(filepath, "wb") as f, tqdm(
			total=file_size,
			unit="B",
			unit_scale=True,
			unit_divisor=1024,
			desc=desc
		) as progress:
			for chunk in response.iter_content(chunk_size=2**20):
				if not chunk:
					continue
				f.write(chunk)
				progress.update(len(chunk))
		return True
	except Exception as e:
		print(f"Error downloading {url}: {e}")
		return False


def set_mp3_metadata(filepath: Path, title: str) -> None:
	"""Set MP3 file metadata."""
	try:
		audio = MP3(filepath, ID3=EasyID3)
		audio["title"] = title
		audio.save()
	except Exception as e:
		print(f"Failed to set metadata for {filepath}: {e}")


def process_audiobook(url: str) -> None:
	"""Main function to process and download an audiobook."""
	# Fetch and parse webpage
	soup = fetch_webpage(url)
	if not soup:
		print("Failed to fetch webpage.")
		sys.exit(1)

	# Extract and validate book title
	book_title = extract_book_title(soup)
	if not book_title:
		print("Could not find book title.")
		sys.exit(1)

	book_dir = Path(sanitize_filename(book_title))
	book_dir.mkdir(exist_ok=True)
	print(f"Downloading {book_title}...")

	# Extract and validate chapter links
	chapter_links = extract_chapter_links(soup)
	if not chapter_links:
		print("No chapter links found.")
		sys.exit(1)

	# Download chapters
	for i, link in enumerate(chapter_links, 1):
		chapter_title = f"Chapter {i:02}"
		mp3_path = book_dir / f"{chapter_title}.mp3"
		
		if download_file(link, mp3_path, f"Downloading {chapter_title}"):
			set_mp3_metadata(mp3_path, chapter_title)

	print(f"\nFinished downloading {book_title}!")


def main():
	"""Entry point of the script."""
	url = input("Enter the tokybook audiobook page URL: ").strip()
	if not url:
		print("Please provide a valid URL.")
		sys.exit(1)
	
	process_audiobook(url)


if __name__ == "__main__":
	main()