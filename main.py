import os
import sys
import requests
import re
import m3u8
from bs4 import BeautifulSoup
from tqdm import tqdm
from pathlib import Path
from urllib.parse import urljoin
import json
from typing import Optional, List, Dict, Any
from playwright.sync_api import sync_playwright
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3


HEADERS = {
	"Accept": "*/*",
	"Accept-Language": "en-US,en;q=0.9",
	"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15",
	"Priority": "u=3, i",
	"referrerPolicy": "strict-origin-when-cross-origin"
}


def fetch_webpage(url: str) -> Optional[BeautifulSoup]:
	"""Fetch and parse a webpage, returning BeautifulSoup object or None on failure."""
	try:
		response = requests.get(url, headers=HEADERS, timeout=15)
		response.raise_for_status()
		return BeautifulSoup(response.text, "html.parser")
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


def extract_book_info(soup: BeautifulSoup) -> Dict[str, Any]:
	"""Extract book information and playlist items."""
	# Extract book title
	h1_tag = soup.find('h1', class_='text-4xl')
	book_title = h1_tag.text.strip() if h1_tag else "Unknown Book"
	
	# Extract author info
	author_tag = soup.find('p', class_='font-semibold text-lg text-gray-800')
	author = author_tag.text.strip() if author_tag else "Unknown Author"
	
	# Extract narrator info
	narrator_div = soup.find('div', class_='cover-overlay-narrator')
	narrator = narrator_div.find('span').text.strip() if narrator_div else "Unknown Narrator"
	
	# Extract book ID and token
	play_button = soup.find('button', {'data-action': 'play-now'})
	book_id = play_button.get('data-book-id', '') if play_button else ''
	token = play_button.get('data-token', '') if play_button else ''

	return {
		'title': book_title,
		'author': author,
		'narrator': narrator,
		'book_id': book_id,
		'token': token
	}

def extract_playlist_items(soup: BeautifulSoup) -> List[Dict[str, str]]:
	"""Extract all playlist items with their m3u8 URLs and titles."""
	playlist_items = []
	
	# Look for playlist items with HLS data
	for item in soup.select('li.playlist-item-hls'):
		track_src = item.get('data-track-src', '').strip()
		track_title = item.get('data-track-title', '').strip()
		
		# Extract title from the span if not in data attribute
		if not track_title:
			title_span = item.select_one('.item-title-hls')
			if title_span:
				track_title = title_span.text.strip()
		
		if track_src:
			if not track_src.startswith('http'):
				# Handle relative URLs, but keep the /api/v1/ path
				track_src = f'https://tokybook.com{track_src}'
			
			playlist_items.append({
				'url': track_src,
				'title': track_title or f"Chapter {len(playlist_items) + 1}"
			})
	
	return playlist_items


def download_m3u8_playlist(track: Dict[str, str], book_dir: Path, book_id: str, token: str, track_index: int = None) -> Dict[str, Any]:
	"""Download m3u8 playlist and save its information."""
	# Create directory for the track
	track_dir = book_dir / sanitize_filename(track['title'])
	track_dir.mkdir(exist_ok=True)

	# Prepare request headers with authentication
	request_headers = {
		"Accept": "*/*",
		"Accept-Language": "en-US,en;q=0.9",
		"Accept-Encoding": "gzip, deflate, br",
		"Referer": HEADERS["Referer"],
		"User-Agent": HEADERS["User-Agent"],
		"Priority": "u=3, i",
		"Sec-Fetch-Dest": "empty",
		"Sec-Fetch-Mode": "cors",
		"Sec-Fetch-Site": "same-origin",
		"X-Audiobook-Id": book_id,
		"X-Playback-Token": token
	}

	# Download m3u8 playlist
	print(f"Processing {track['title']}...")
	response = requests.get(
		track['url'],
		headers=request_headers
	)
	
	if response.status_code != 200:
		print(f"Failed to download playlist for {track['title']} (Status: {response.status_code})")
		print(f"Response: {response.text[:200]}")
		return None

	# Save playlist file
	playlist_path = track_dir / 'playlist.m3u8'
	playlist_path.write_text(response.text)

	# Parse m3u8 playlist
	playlist = m3u8.loads(response.text)
	
	# Save playlist info
	track_info = {
		'title': track['title'],
		'segments': [],
		'duration': sum(segment.duration for segment in playlist.segments)
	}

	# Add segment information and download them
	print(f"Downloading {len(playlist.segments)} segments...")
	progress = tqdm(playlist.segments, desc=track['title'], unit='segment')
	segments_dir = track_dir / 'segments'
	segments_dir.mkdir(exist_ok=True)
	
	for i, segment in enumerate(progress, 1):
		segment_url = urljoin(track['url'], segment.uri)
		segment_path = segments_dir / f"{i:04d}.ts"
		segment_info = {
			'index': i,
			'url': segment_url,
			'duration': segment.duration,
			'path': str(segment_path)
		}
		
		# Download segment if it doesn't exist
		if not segment_path.exists():
			try:
				response = requests.get(segment_url, headers=request_headers)
				response.raise_for_status()
				segment_path.write_bytes(response.content)
			except Exception as e:
				print(f"Error downloading segment {i}: {e}")
				continue
				
		track_info['segments'].append(segment_info)

	# Save track info
	with open(track_dir / 'track_info.json', 'w') as f:
		json.dump(track_info, f, indent=2)

	# Convert segments to single MP3 per chapter
	chapter_number = track_index if track_index is not None else 1
	chapter_name = f"Chapter {chapter_number:02d}"
	output_path = track_dir / f"{chapter_name}.mp3"
	if not output_path.exists():
		print(f"Converting {track['title']} to MP3 named {chapter_name}.mp3...")
		segments_list_file = track_dir / "segments.txt"
		with open(segments_list_file, "w") as f:
			for segment_info in track_info['segments']:
				segment_path = Path(segment_info['path']).absolute()
				f.write(f"file '{segment_path}'\n")
		# Run ffmpeg concat
		cmd = [
			'ffmpeg',
			'-f', 'concat',
			'-safe', '0',
			'-i', str(segments_list_file),
			'-c:a', 'libmp3lame',
			'-q:a', '2',
			'-vn',
			str(output_path)
		]
		print("Running ffmpeg command:", " ".join(cmd))
		from subprocess import run
		run(cmd, check=True)

		# Set ID3 title tag to chapter name
		try:
			audio = MP3(str(output_path), ID3=EasyID3)
			audio["title"] = chapter_name
			audio.save()
		except Exception as e:
			print(f"Failed to set ID3 tag: {e}")

		chapters_dir = book_dir / "Chapters"
		chapters_dir.mkdir(exist_ok=True)
		final_path = chapters_dir / output_path.name
		output_path.rename(final_path)
		track_info['mp3_path'] = str(final_path)
	else:
		print(f"MP3 already exists for {track['title']}")
		track_info['mp3_path'] = str(output_path)

	return track_info


def get_playlist_data(book_id: str, token: str) -> List[Dict[str, str]]:
	"""Get the playlist data using Playwright to simulate the play button click"""
	from playwright.sync_api import sync_playwright
	
	playlist_items = []
	
	url = HEADERS.get("Referer", "https://tokybook.com")
	with sync_playwright() as p:
		browser = p.chromium.launch(headless=True)
		context = browser.new_context(
			user_agent=HEADERS["User-Agent"]
		)
		page = context.new_page()
		
		try:
			print(f"Navigating to {url}...")
			# Navigate to the actual book page
			page.goto(url, wait_until="domcontentloaded")
			print("Waiting for play button...")
			
			# Wait for and click the play button
			play_button = page.wait_for_selector('button[data-action="play-now"]')
			play_button.click()
			print("Clicked play button, waiting for player data...")

			# Wait for and verify player is ready
			try:
				# First wait for player container
				player_container = page.wait_for_selector('.global-player-container', state='visible', timeout=10000)
				if not player_container:
					print("Player container not found")
					return []

				print("Waiting for playlist to load...")
				
				# Wait for either the playlist items or section to be visible
				print("Waiting for any playlist elements to become visible...")
				success = False
				
				try:
					# Try locator approach first
					locator = page.locator('.playlist-section-hls, .playlist-item-hls, .playlist-item')
					locator.wait_for(state='visible', timeout=15000)
					success = True
				except Exception:
					try:
						# Fallback to evaluating visibility in JavaScript
						is_visible = page.evaluate("""() => {
							const elements = document.querySelectorAll('.playlist-section-hls, .playlist-item-hls, .playlist-item');
							for (const el of elements) {
								if (el.offsetParent !== null) return true;
							}
							return false;
						}""")
						if is_visible:
							success = True
					except Exception:
						pass
				
				if not success:
					print("Playlist elements never became visible")
					page.screenshot(path="visibility_error.png")
					
				# Even if elements aren't visible, try to proceed with hidden elements
				print("Checking for playlist items...")
				
				# Force scroll the playlist section into view if it exists
				page.evaluate("""() => {
					const playlist = document.querySelector('.playlist-section-hls');
					if (playlist) playlist.scrollIntoView();
				}""")
				
				# Wait a bit more after scrolling
				page.wait_for_timeout(2000)
				
			except Exception as e:
				print(f"Error waiting for player elements: {e}")
				page.screenshot(path="player_error.png")
				print("Saved error state to player_error.png")
				return []

			# Get all playlist items, even if they're still loading
			try:
				items = page.query_selector_all('.playlist-item-hls, .playlist-item, li[data-track-src]')
				if items:
					print(f"Found {len(items)} potential playlist items")
				else:
					print("No playlist items found yet, taking screenshot for analysis")
					
				# Take screenshots for analysis
				# page.screenshot(path="playlist_debug.png")
				# print("Saved debug screenshot to playlist_debug.png")

			except Exception as e:
				print(f"Error checking playlist items: {e}")
				page.screenshot(path="error_state.png")
				print("Saved error state to error_state.png")
				
			# Get the full HTML after playlist loads
			content = page.content()
			print("Got page content, parsing playlist items...")
			
			# Parse the page content
			soup = BeautifulSoup(content, "html.parser")
			print("Parsing page content for playlist items...")
				
			# Extract playlist items using multiple potential selectors
			items = soup.select('.playlist-item-hls, .playlist-item, li[data-track-src]')
			print(f"Found {len(items)} items in HTML")
				
			# Try multiple approaches to extract information
			for item in items:
				track_src = None
				track_title = None
				
				# Try all possible source attributes
				for attr in ['data-track-src', 'data-src', 'src', 'data-url']:
					track_src = item.get(attr, '').strip()
					if track_src:
						print(f"Found track source using {attr}")
						break
				
				# Try all possible title attributes and elements
				for attr in ['data-track-title', 'data-title', 'title']:
					track_title = item.get(attr, '').strip()
					if track_title:
						break
						
				if not track_title:
					# Try various title selectors
					for selector in ['.item-title-hls', '.item-title', '.title', 'span']:
						title_elem = item.select_one(selector)
						if title_elem:
							track_title = title_elem.text.strip()
							if track_title:
								print(f"Found title using selector {selector}")
								break
				
				if track_src:
					if not track_src.startswith('http'):
						track_src = f'https://tokybook.com{track_src}'
					
					playlist_items.append({
						'url': track_src,
						'title': track_title or f"Chapter {len(playlist_items) + 1}"
					})
					print(f"Added track: {track_title or 'Unknown'}")
						
		except Exception as e:
			print(f"Error getting playlist data: {e}")
			
		browser.close()
	
	return playlist_items

def process_audiobook(url: str) -> None:
	"""Main function to process and download an audiobook's m3u8 playlists."""
	print("Fetching webpage...")
	soup = fetch_webpage(url)
	if not soup:
		print("Failed to fetch webpage.")
		sys.exit(1)

	# Extract book information
	book_info = extract_book_info(soup)
	book_title = book_info['title']

	# Create book directory
	book_dir = Path(sanitize_filename(book_title))
	book_dir.mkdir(exist_ok=True)
	print(f"\nProcessing audiobook: {book_title}")
	print(f"Author: {book_info['author']}")
	print(f"Narrator: {book_info['narrator']}")

	# Get playlist items from API
	if not book_info['book_id'] or not book_info['token']:
		print("Error: Could not find book ID or token. Make sure you're using a valid book URL.")
		sys.exit(1)

	print(f"Getting playlist data for book ID: {book_info['book_id']}")
	playlist_items = get_playlist_data(book_info['book_id'], book_info['token'])
	
	if not playlist_items:
		print("Error: No playlist items found.")
		sys.exit(1)

	print(f"\nFound {len(playlist_items)} tracks")

	# Save metadata
	book_info['tracks'] = []
	for idx, track in enumerate(playlist_items, 1):
		track_info = download_m3u8_playlist(track, book_dir, book_info['book_id'], book_info['token'], track_index=idx)
		if track_info:
			book_info['tracks'].append(track_info)	# Save book info
	with open(book_dir / 'book_info.json', 'w') as f:
		json.dump(book_info, f, indent=2)

	print(f"\nFinished processing {book_title}!")
	print(f"Processed {len(book_info['tracks'])} tracks")
	print(f"Book information saved to: {book_dir}/book_info.json")


def main():
	"""Entry point of the script."""
	url = input("Enter the tokybook audiobook page URL: ").strip()
	if not url:
		print("Please provide a valid URL.")
		sys.exit(1)
	
	HEADERS["Referer"] = url
	
	process_audiobook(url)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
