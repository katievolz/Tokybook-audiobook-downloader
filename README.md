# **TokyoBook Audiobook Downloader**  

This script allows you to **automatically download** audiobook chapters from [TokyoBook](https://tokybook.com/) in one go.  
It extracts `.mp3` chapter links from a given audiobook page and downloads them into a **folder named after the book**.  

---

## **📥 Features**  
✅ Supports **TokyoBook.com** audiobooks  
✅ Creates a folder **named after the book**  
✅ Extracts and downloads **all chapters automatically**  
✅ Displays a **progress bar** while downloading  

---

## **🚀 How to Use**  

### **1 Install Requirements**  
Make sure you have Python **3.12+** installed. Then, install dependencies:  
```sh
pip3 install requests beautifulsoup4 tqdm lxml mutagen
```

### **2 Run the Script**  
Run the main.py script:  
```sh
python main.py
```
Enter the tokybook URL you want downloaded in the terminal window when it prompts you.

The chapters will be downloaded into a **folder named after the audiobook**.

---

## **🔍 How It Works**
1. **Scrapes the audiobook page** to get the book title and chapter links.  
2. **Creates a folder** named after the audiobook.  
3. **Downloads each chapter** as an `.mp3` file with a progress bar.  

---

## **📌 Notes**
- The script **only works with** [TokyoBook](https://tokybook.com/) audiobooks.  
- Chapter filenames are saved as **`Chapter 01.mp3`, `Chapter 02.mp3`, etc.**  
- If the book title contains **invalid characters**, they will be replaced automatically.  
- If you **re-run the script**, it will overwrite existing files if they already exist in the folder.