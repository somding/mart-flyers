import asyncio
import json
import os
import aiohttp
from playwright.async_api import async_playwright

# Configuration
DATA_FILE = 'data.json'
IMAGES_DIR = 'images'

# URLs
EMART_URL = 'https://eapp.emart.com/leaflet/leafletView_EL.do'
HOMEPLUS_URL = 'https://my.homeplus.co.kr/leaflet'
LOTTE_URL = 'https://www.mlotte.net/leaflet?leaflet_id=2000139'

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
                            # STRICT FILTER: 500px
                            if w < 500 or h < 500:
                                os.remove(filepath)
                                return None
                    except Exception as e:
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
        dom_images = []
        
        for img in img_elements:
            src = await img.get_attribute('src')
            if src and ('jpg' in src or 'png' in src) and 'logo' not in src:
               if not src.startswith('http'):
                    src = 'https://eapp.emart.com' + src if src.startswith('/') else src
               
               try:
                   w = await img.evaluate("el => el.naturalWidth")
                   h = await img.evaluate("el => el.naturalHeight")
                   if w > 500 or h > 500:
                       dom_images.append(src)
                       if not base_url:
                           base_url = src
                           print(f"Found base E-mart flyer: {base_url} ({w}x{h})")
               except:
                   pass
        
        # 2. Brute Force Pattern
        pattern_success = False
        if base_url:
            match = re.search(r'(\d+)(?=\.\w+$)', base_url)
            if match:
                prefix = base_url[:match.start(1)]
                suffix = base_url[match.end(1):]
                
                print(f"Detected pattern: {prefix}[N]{suffix}")
                
                count = 1
                for i in range(1, 21):
                    # Try different padding formats
                    formats = [f"{i}", f"{i:02d}", f"{i:03d}"]
                    found_this_page = False
                    
                    for fmt in formats:
                        target_url = f"{prefix}{fmt}{suffix}"
                        filename = f"emart_new_{count:02d}.jpg"
                        
                        local_path = await download_image(session, target_url, filename)
                        if local_path:
                            print(f"  > Scraped page {i} (fmt={fmt})")
                            images.append(local_path)
                            count += 1
                            found_this_page = True
                            await asyncio.sleep(0.5) # Delay
                            break 
                    
                    if found_this_page:
                        pattern_success = True
        
        # 3. Fallback: If pattern failed or returned very few, use DOM images
        if len(images) < 2 and dom_images:
            print("Pattern scraping yielded few results. Using fallback DOM images.")
            count = 1
            for src in dom_images:
                # Deduplicate
                if any(src in url for url in images): continue
                
                filename = f"emart_fallback_{count:02d}.jpg"
                local_path = await download_image(session, src, filename)
                if local_path:
                    images.append(local_path)
                    count += 1

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
        await page.goto(LOTTE_URL, timeout=90000)
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(8000)
        
        img_elements = await page.query_selector_all('img')
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            data_src = await img.get_attribute('data-src')
            real_src = src or data_src
            
            if real_src and ('jpg' in real_src or 'png' in real_src) and 'logo' not in real_src:
                 if not real_src.startswith('http'):
                    if real_src.startswith('//'):
                        real_src = 'https:' + real_src
                    elif real_src.startswith('/'):
                        real_src = 'https://www.mlotte.net' + real_src
                 
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
        page = await browser.new_page(viewport={'width': 390, 'height': 844})
        
        async with aiohttp.ClientSession() as session:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            def update_mart_data(mart_index, new_images):
                if not new_images:
                    print(f"No new images found for {data[mart_index]['name']}")
                    return

                current_flyer_data = data[mart_index]['flyers']['current']
                current_image_paths = current_flyer_data.get('images', [])

                clean_current_paths = []
                for p in current_image_paths:
                    clean_p = p.split('?')[0]
                    if clean_p.startswith('./'):
                        clean_p = clean_p[2:]
                    if clean_p.startswith('/'):
                        clean_p = clean_p[1:]
                    clean_current_paths.append(clean_p)

                current_hashes = []
                missing_files = False
                for p in clean_current_paths:
                    h = calculate_file_hash(p)
                    if h:
                        current_hashes.append(h)
                    else:
                        missing_files = True 
                
                new_hashes = []
                for p in new_images:
                    clean_p = p
                    if clean_p.startswith('./'):
                        clean_p = clean_p[2:]
                    h = calculate_file_hash(clean_p)
                    if h:
                        new_hashes.append(h)
                
                if current_hashes and new_hashes and current_hashes == new_hashes:
                    print(f"[{data[mart_index]['name']}] Images are content-identical. Skipping update.")
                    return

                print(f"[{data[mart_index]['name']}] content changed. Updating...")
                
                # SAFETY LOCK: Only archive if files exist
                if not missing_files and current_hashes:
                    data[mart_index]['flyers']['past']['images'] = current_image_paths
                else:
                    print(f"Warning: Current files missing. SKIPPING ARCHIVE.")
                
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

            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            print("Data updated successfully.")
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
