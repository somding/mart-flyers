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

async def download_image(session, url, filename):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                filepath = os.path.join(IMAGES_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(await response.read())
                
                # Check if file is valid (not empty and is an image)
                file_size = os.path.getsize(filepath)
                if file_size > 1000: # At least 1KB
                    # Verify it's a real image by checking magic numbers
                    with open(filepath, 'rb') as f:
                        header = f.read(4)
                    
                    # JPEG (FF D8 FF), PNG (89 50 4E 47)
                    if header.startswith(b'\xff\xd8\xff') or header.startswith(b'\x89PNG'):
                        return f"./{IMAGES_DIR}/{filename}"
                    else:
                        print(f"Invalid image format (not JPG/PNG): {url}")
                        os.remove(filepath)
                else:
                    print(f"Downloaded file too small: {url} ({file_size} bytes)")
                    os.remove(filepath)
    except Exception as e:
        print(f"Failed to download {url}: {e}")
    return None

async def scrape_emart(page, session):
    print(f"Scraping E-mart from {EMART_URL}...")
    images = []
    try:
        await page.goto(EMART_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        
        # Scroll down to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        img_elements = await page.query_selector_all('img')
        
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            # Relaxed filter: just check extensions. Rely on file size check for actual validation.
            if src and ('jpg' in src or 'png' in src or 'jpeg' in src):
                if not src.startswith('http'):
                    src = 'https://eapp.emart.com' + src if src.startswith('/') else src
                    
                # Avoid duplicates in current run
                if any(src in url for url in images): continue

                filename = f"emart_new_{count:02d}.jpg"
                # Use evaluate to check render size if possible, or just download
                try:
                    width = await img.evaluate("el => el.naturalWidth")
                    if width < 300: # Skip small icons
                        continue
                except:
                    pass

                print(f"Found potential E-mart image: {src}")
                local_path = await download_image(session, src, filename)
                if local_path:
                    images.append(local_path)
                    count += 1
                    if count > 20: break 

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
        await page.goto(LOTTE_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(3000) # Wait extra for Lotte
        
        # Try to find images inside a specific container if possible, or just all images
        img_elements = await page.query_selector_all('img')
        
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            # Lotte specific check
            if src and ('leaflet' in src or 'jpg' in src) and 'logo' not in src:
                 if not src.startswith('http'):
                    # Careful with relative path on Lotte
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://www.mlotte.net' + src
                 
                 print(f"Found potential Lotte image: {src}")
                 filename = f"lotte_new_{count:02d}.jpg"
                 local_path = await download_image(session, src, filename)
                 if local_path:
                    images.append(local_path)
                    count += 1
                    if count > 15: break

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

                current_images = data[mart_index]['flyers']['current']['images']
                
                # Check for duplication (Prevent setting Past == Current)
                # Since scraper generates same filenames (emart_new_01.jpg), strict equality check works.
                if current_images == new_images:
                    print(f"New images are identical to current images for {data[mart_index]['name']}. Skipping update.")
                    return

                print(f"Updating {data[mart_index]['name']}...")
                # Only archive if current is not empty and different
                if current_images:
                    data[mart_index]['flyers']['past']['images'] = current_images
                
                data[mart_index]['flyers']['current']['images'] = new_images

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
