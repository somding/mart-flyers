import asyncio
import json
import os
import aiohttp
from playwright.async_api import async_playwright

# Configuration
DATA_FILE = 'data.json'
IMAGES_DIR = 'images'

# URLs (Based on user input)
EMART_URL = 'https://eapp.emart.com/leaflet/leafletView_EL.do'
HOMEPLUS_URL = 'https://my.homeplus.co.kr/leaflet'
LOTTE_URL = 'https://www.mlotte.net/leaflet?leaflet_id=2000139'

import hashlib
from PIL import Image

def calculate_file_hash(filepath):
    """Calculates the MD5 hash of a file."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error calculating hash for {filepath}: {e}")
        return None

# ...

import re

# ...

async def download_image(session, url, filename):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                filepath = os.path.join(IMAGES_DIR, filename)
                content = await response.read()
                
                with open(filepath, 'wb') as f:
                    f.write(content)
                
                # Validation
                file_size = len(content)
                if file_size > 1000: # 1KB
                    if not (content.startswith(b'\xff\xd8\xff') or content.startswith(b'\x89PNG')):
                        os.remove(filepath)
                        return None
                    
                    try:
                        with Image.open(filepath) as img:
                            w, h = img.size
                            # STRICTER FILTER: 600px
                            if w < 500 or h < 500:
                                #print(f"Image too small ({w}x{h}): {url}")
                                os.remove(filepath)
                                return None
                    except Exception as e:
                        print(f"Image open failed: {e}")
                        os.remove(filepath)
                        return None
                        
                    return f"./{IMAGES_DIR}/{filename}"
                else:
                    os.remove(filepath)
                    return None
            else:
                 return None
    except Exception as e:
        print(f"Download error {url}: {e}")
    return None

async def scrape_emart(page, session):
    print(f"Scraping E-mart from {EMART_URL}...")
    images = []
    try:
        await page.goto(EMART_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        
        # 1. Capture DOM images to find a pattern
        img_elements = await page.query_selector_all('img')
        
        base_url = None
        
        for img in img_elements:
            src = await img.get_attribute('src')
            if src and ('jpg' in src or 'png' in src) and 'logo' not in src:
               if not src.startswith('http'):
                    src = 'https://eapp.emart.com' + src if src.startswith('/') else src
               
               # Check if this is a "Main" flyer image (likely large)
               # Use evaluate to check render size on page
               try:
                   w = await img.evaluate("el => el.naturalWidth")
                   h = await img.evaluate("el => el.naturalHeight")
                   if w > 500 or h > 500:
                       base_url = src
                       print(f"Found base E-mart flyer: {base_url} ({w}x{h})")
                       break
               except:
                   pass
        
        # 2. Brute Force Pattern
        if base_url:
            # Regex to find the last sequence of digits in the filename
            # e.g., ".../leaflet_01.jpg" -> match "01"
            match = re.search(r'(\d+)(?=\.\w+$)', base_url)
            if match:
                number_str = match.group(1)
                prefix = base_url[:match.start(1)]
                suffix = base_url[match.end(1):]
                width = len(number_str) # Keep zero padding length
                
                print(f"Detected pattern: {prefix}[N]{suffix}")
                
                # Try to download page 1 to 20
                count = 1
                for i in range(1, 21):
                    # Generate URL with zero padding
                    # Use existing width, or at least 2
                    pad = max(width, 2)
                    num_formatted = f"{i:0{pad}d}"
                    target_url = f"{prefix}{num_formatted}{suffix}"
                    
                    filename = f"emart_new_{count:02d}.jpg"
                    local_path = await download_image(session, target_url, filename)
                    
                    # If failed, try without zero padding? e.g. 1 instead of 01
                    if not local_path and pad > 1:
                         target_url_alt = f"{prefix}{i}{suffix}"
                         local_path = await download_image(session, target_url_alt, filename)

                    if local_path:
                        print(f"  > Scraped page {i}: {target_url}")
                        images.append(local_path)
                        count += 1
                        
                        # Avoid duplicates in list
                        # (handled by logic)
                    else:
                        # If we fail inside the sequence (e.g. got 1, failed 2, maybe 3 exists?), continue?
                        # Usually flyers differ. But if consecutive fails, stop.
                        # Actually, let's just try all 15. The browser won't mind.
                        pass
                        
    except Exception as e:
        print(f"Error scraping E-mart: {e}")
    
    return images

async def scrape_homeplus(page, session):
    print(f"Scraping Homeplus from {HOMEPLUS_URL}...")
    images = []
    try:
        await page.goto(HOMEPLUS_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        img_elements = await page.query_selector_all('img')
        
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            if src and ('leaflet' in src or 'flyer' in src or 'jpg' in src) and 'logo' not in src:
                 if not src.startswith('http'):
                    src = 'https://my.homeplus.co.kr' + src if src.startswith('/') else src
                 
                 print(f"Found potential Homeplus image: {src}")
                 filename = f"homeplus_new_{count:02d}.jpg"
                 local_path = await download_image(session, src, filename)
                 if local_path:
                    images.append(local_path)
                    count += 1
                    if count > 15: break

    except Exception as e:
        print(f"Error scraping Homeplus: {e}")
    return images

async def scrape_lotte(page, session):
    print(f"Scraping Lotte Mart from {LOTTE_URL}...")
    images = []
    try:
        await page.goto(LOTTE_URL, timeout=90000) # Increased timeout
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(8000) # Wait 8 seconds for JS to load
        
        # Check for both src and data-src (lazy loading)
        img_elements = await page.query_selector_all('img')
        
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            data_src = await img.get_attribute('data-src')
            real_src = src or data_src
            
            if real_src and ('jpg' in real_src or 'png' in real_src) and 'logo' not in real_src:
                 if not real_src.startswith('http'):
                    # Careful with relative path on Lotte
                    if real_src.startswith('//'):
                        real_src = 'https:' + real_src
                    elif real_src.startswith('/'):
                        real_src = 'https://www.mlotte.net' + real_src
                 
                 print(f"Found potential Lotte image: {real_src}")
                 filename = f"lotte_new_{count:02d}.jpg"
                 local_path = await download_image(session, real_src, filename)
                 if local_path:
                    images.append(local_path)
                    count += 1
                    if count > 20: break

    except Exception as e:
        print(f"Error scraping Lotte: {e}")
    return images

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # Set viewport to mobile to trigger mobile versions which often have cleaner flyers
        page = await browser.new_page(viewport={'width': 390, 'height': 844})
        
        async with aiohttp.ClientSession() as session:
            # Load existing data
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Helper to update mart data safely
            def update_mart_data(mart_index, new_images):
                if not new_images:
                    print(f"No new images found for {data[mart_index]['name']}")
                    return

                current_flyer_data = data[mart_index]['flyers']['current']
                current_image_paths = current_flyer_data.get('images', [])

                # strip query params if any (e.g. ?v=2)
                clean_current_paths = []
                for p in current_image_paths:
                    clean_p = p.split('?')[0] # remove query param
                    # Ensure path is relative to script execution
                    if clean_p.startswith('./'):
                        clean_p = clean_p[2:] # remove ./
                    if clean_p.startswith('/'):
                        clean_p = clean_p[1:]
                    clean_current_paths.append(clean_p)

                # Calculate hashes for current images
                current_hashes = []
                for p in clean_current_paths:
                    h = calculate_file_hash(p)
                    if h:
                        current_hashes.append(h)
                
                # Calculate hashes for new images
                new_hashes = []
                for p in new_images:
                    # new_images are returned as "./images/..."
                    clean_p = p
                    if clean_p.startswith('./'):
                        clean_p = clean_p[2:]
                    h = calculate_file_hash(clean_p)
                    if h:
                        new_hashes.append(h)
                
                # STRICT COMPARISON
                if current_hashes and new_hashes and current_hashes == new_hashes:
                    print(f"[{data[mart_index]['name']}] Images are content-identical. Skipping update.")
                    return

                print(f"[{data[mart_index]['name']}] content changed. Updating...")
                
                # Only archive if we have valid current images
                if current_image_paths:
                    data[mart_index]['flyers']['past']['images'] = current_image_paths
                
                # Update current
                data[mart_index]['flyers']['current']['images'] = new_images

            # ... scraper calls ...

            # E-mart
            new_emart = await scrape_emart(page, session)
            print(f"E-mart: Found {len(new_emart)} images.")
            update_mart_data(0, new_emart)

            # Homeplus
            new_homeplus = await scrape_homeplus(page, session)
            update_mart_data(1, new_homeplus)

            # Lotte
            new_lotte = await scrape_lotte(page, session)
            update_mart_data(2, new_lotte)

            # Save updated data
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            print("Data updated successfully.")
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
