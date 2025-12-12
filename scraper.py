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
        
        img_elements = await page.query_selector_all('img')
        
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            if src and ('jpg' in src or 'png' in src) and 'logo' not in src and 'icon' not in src:
                if not src.startswith('http'):
                    src = 'https://eapp.emart.com' + src if src.startswith('/') else src
                
                print(f"Found potential E-mart image: {src}")
                filename = f"emart_new_{count:02d}.jpg"
                local_path = await download_image(session, src, filename)
                if local_path:
                    images.append(local_path)
                    count += 1
                    if count > 15: break

    except Exception as e:
        print(f"Error scraping E-mart: {e}")
    
    return images

async def scrape_homeplus(page, session):
    print(f"Scraping Homeplus from {HOMEPLUS_URL}...")
    images = []
    try:
        await page.goto(HOMEPLUS_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        
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
                    if count > 10: break

    except Exception as e:
        print(f"Error scraping Homeplus: {e}")
    return images

async def scrape_lotte(page, session):
    print(f"Scraping Lotte Mart from {LOTTE_URL}...")
    images = []
    try:
        await page.goto(LOTTE_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        
        # Lotte Mart logic
        img_elements = await page.query_selector_all('img')
        
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            # Lotte Mart often uses 'blob' or specific paths, but let's try generic first
            if src and ('jpg' in src or 'png' in src) and 'logo' not in src:
                 if not src.startswith('http'):
                    src = 'https://www.mlotte.net' + src if src.startswith('/') else src
                 
                 print(f"Found potential Lotte image: {src}")
                 filename = f"lotte_new_{count:02d}.jpg"
                 local_path = await download_image(session, src, filename)
                 if local_path:
                    images.append(local_path)
                    count += 1
                    if count > 10: break

    except Exception as e:
        print(f"Error scraping Lotte: {e}")
    return images

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        async with aiohttp.ClientSession() as session:
            # Load existing data
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Scrape and Update
            
            # E-mart
            # Note: Real scraping requires valid selectors. 
            # If we can't get them, we can't update. 
            # But the structure is here.
            new_emart_images = await scrape_emart(page, session)
            if new_emart_images:
                print("New E-mart images found. Archiving old flyer...")
                data[0]['flyers']['past']['images'] = data[0]['flyers']['current']['images']
                data[0]['flyers']['current']['images'] = new_emart_images

            # Homeplus
            new_homeplus_images = await scrape_homeplus(page, session)
            if new_homeplus_images:
                data[1]['flyers']['past']['images'] = data[1]['flyers']['current']['images']
                data[1]['flyers']['current']['images'] = new_homeplus_images

            # Lotte
            new_lotte_images = await scrape_lotte(page, session)
            if new_lotte_images:
                data[2]['flyers']['past']['images'] = data[2]['flyers']['current']['images']
                data[2]['flyers']['current']['images'] = new_lotte_images

            # Save updated data
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            print("Data updated successfully.")
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
