import requests
from bs4 import BeautifulSoup
import time
import os
from pathlib import Path

def download_entire_rigveda():
    base_url = "https://www.sacred-texts.com/hin/rigveda/"
    
    # Get Downloads folder path (works on Windows, Mac, Linux)
    downloads_path = Path.home() / "Downloads"
    output_file = downloads_path / "rigveda_complete.txt"
    
    # All books with their file patterns
    books = {
        1: "rv01", 2: "rv02", 3: "rv03", 4: "rv04", 5: "rv05",
        6: "rv06", 7: "rv07", 8: "rv08", 9: "rv09", 10: "rv10"
    }
    
    all_content = "THE RIG VEDA - Complete Translation by Ralph T.H. Griffith\n"
    all_content += "Source: sacred-texts.com\n"
    all_content += "=" * 70 + "\n\n"
    
    total_hymns = 0
    
    for book_num, book_prefix in books.items():
        print(f"Downloading Book {book_num}...")
        book_content = f"\n{'='*60}\nBOOK {book_num}\n{'='*60}\n\n"
        book_hymns = 0
        
        # Try to download hymns - using a reasonable range
        for hymn_num in range(1, 191):  # Most books have 100+ hymns
            filename = f"{book_prefix}{hymn_num:03d}.htm"
            url = base_url + filename
            
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Get page title or identifier
                    title = soup.find('title')
                    page_title = title.get_text().strip() if title else f"Hymn {hymn_num}"
                    
                    # Extract main text content
                    text = soup.get_text()
                    
                    # Clean up the text
                    lines = []
                    for line in text.split('\n'):
                        line = line.strip()
                        if line and len(line) > 2:  # Filter out very short lines
                            lines.append(line)
                    
                    clean_text = '\n'.join(lines)
                    
                    book_content += f"HYMN {hymn_num}: {page_title}\n"
                    book_content += "-" * 40 + "\n"
                    book_content += f"{clean_text}\n\n"
                    
                    book_hymns += 1
                    total_hymns += 1
                    print(f"  ✓ Downloaded {filename}")
                    
                elif response.status_code == 404:
                    # If we get 404, try a few more then stop
                    if hymn_num > 10:  # Only stop after first 10+ hymns
                        failed_count = 0
                        # Check next 5 hymns to confirm end of book
                        for next_hymn in range(hymn_num + 1, hymn_num + 6):
                            next_url = base_url + f"{book_prefix}{next_hymn:03d}.htm"
                            try:
                                next_response = requests.get(next_url, timeout=5)
                                if next_response.status_code != 200:
                                    failed_count += 1
                            except:
                                failed_count += 1
                        
                        if failed_count >= 4:  # If 4 out of 5 next hymns fail
                            print(f"  → Reached end of Book {book_num} at hymn {hymn_num-1}")
                            break
                
                time.sleep(0.3)  # Be respectful to the server
                
            except requests.exceptions.RequestException as e:
                print(f"  ✗ Error downloading {filename}: {e}")
                continue
            except Exception as e:
                print(f"  ✗ Unexpected error with {filename}: {e}")
                continue
        
        all_content += book_content
        print(f"Book {book_num}: Downloaded {book_hymns} hymns")
    
    # Save to Downloads folder
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(all_content)
        
        print(f"\n" + "="*60)
        print(f"DOWNLOAD COMPLETE!")
        print(f"File saved to: {output_file}")
        print(f"Total hymns downloaded: {total_hymns}")
        print(f"File size: {len(all_content):,} characters")
        print(f"File size: {len(all_content.encode('utf-8')):,} bytes")
        print("="*60)
        
    except Exception as e:
        print(f"Error saving file: {e}")
        # Fallback: save to current directory
        with open("rigveda_complete.txt", "w", encoding="utf-8") as f:
            f.write(all_content)
        print("File saved to current directory as 'rigveda_complete.txt'")

# Alternative function for testing with just one book first
def download_single_book_test():
    """Download just one book for testing"""
    base_url = "https://www.sacred-texts.com/hin/rigveda/"
    downloads_path = Path.home() / "Downloads"
    output_file = downloads_path / "rigveda_book1_test.txt"
    
    print("Testing with Book 1 only...")
    
    all_content = "RIG VEDA - Book 1 (Test Download)\n" + "="*50 + "\n\n"
    
    for hymn_num in range(1, 11):  # Just first 10 hymns for testing
        filename = f"rv01{hymn_num:03d}.htm"
        url = base_url + filename
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                text = soup.get_text()
                
                # Clean up
                lines = [line.strip() for line in text.split('\n') if line.strip() and len(line) > 2]
                clean_text = '\n'.join(lines)
                
                all_content += f"HYMN {hymn_num}\n{'-'*30}\n{clean_text}\n\n"
                print(f"  Downloaded {filename}")
            
            time.sleep(0.3)
            
        except Exception as e:
            print(f"  Error with {filename}: {e}")
    
    # Save to Downloads
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(all_content)
    
    print(f"\nTest complete! File saved to: {output_file}")

if __name__ == "__main__":
    print("Rig Veda Downloader")
    print("1. Download entire Rig Veda (10 books)")
    print("2. Test with Book 1 only (first 10 hymns)")
    
    choice = input("Choose option (1 or 2): ").strip()
    
    if choice == "2":
        download_single_book_test()
    else:
        download_entire_rigveda()