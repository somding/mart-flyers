import asyncio
import json
import os
import aiohttp
import hashlib
import re
import time
from playwright.async_api import async_playwright
from PIL import Image

# ==========================================
# 설정 (Configuration)
# ==========================================
DATA_FILE = 'data.json'
IMAGES_DIR = 'images'

# 각 마트별 모바일 전단지 URL
EMART_URL = 'https://eapp.emart.com/leaflet/leafletView_EL.do'
HOMEPLUS_URL = 'https://my.homeplus.co.kr/leaflet'
LOTTE_URL = 'https://www.mlotte.net/leaflet?leaflet_id=2000139'

# ==========================================
# 유틸리티 함수 (Utility Functions)
# ==========================================

def calculate_file_hash(filepath):
    """
    파일의 MD5 해시값을 계산합니다.
    이미지 중복 여부를 정밀하게 판단하기 위해 사용됩니다.
    
    Args:
        filepath (str): 파일 경로
    Returns:
        str: MD5 해시 문자열 (파일이 없으면 None)
    """
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"[-] 해시 계산 오류 ({filepath}): {e}")
        return None

async def download_image(session, url, filename):
    """
    URL에서 이미지를 비동기로 다운로드하고 유효성을 검사합니다.
    
    기능:
    1. HTTP 요청으로 이미지 다운로드
    2. 파일 크기 검사 (1KB 미만 삭제)
    3. 이미지 헤더 검사 (JPG/PNG 확인)
    4. 해상도 검사 (500px 미만 아이콘 삭제)
    
    Returns:
        str: 저장된 파일의 상대 경로 (실패 시 None)
    """
    try:
        # HTTP 요청
        async with session.get(url) as response:
            if response.status == 200:
                filepath = os.path.join(IMAGES_DIR, filename)
                content = await response.read()
                
                # 일단 저장
                with open(filepath, 'wb') as f:
                    f.write(content)
                
                # --- 유효성 검사 (Validation) ---
                file_size = len(content)
                
                # 1. 파일 크기 (1KB 미만은 더미 파일로 간주)
                if file_size < 1000:
                    os.remove(filepath)
                    return None
                
                # 2. 매직 넘버 (JPG/PNG 헤더 확인)
                if not (content.startswith(b'\xff\xd8\xff') or content.startswith(b'\x89PNG')):
                    # print(f"[-] 유효하지 않은 이미지 포맷: {filename}")
                    os.remove(filepath)
                    return None
                
                # 3. 해상도 (Resolution) - 아이콘 제거
                try:
                    with Image.open(filepath) as img:
                        w, h = img.size
                        # 가로/세로 500px 미만이면 삭제 (아이콘, 버튼 등)
                        if w < 500 or h < 500:
                            # print(f"[-] 너무 작은 이미지 제거 ({w}x{h}): {filename}")
                            os.remove(filepath)
                            return None
                except Exception:
                    os.remove(filepath)
                    return None
                    
                # 성공 시 경로 반환
                return f"./{IMAGES_DIR}/{filename}"
            else:
                 return None
    except Exception as e:
        print(f"[-] 다운로드 실패 {url}: {e}")
    return None

# ==========================================
# 마트별 크롤링 함수 (Scraping Functions)
# ==========================================

async def scrape_emart(context, session):
    """
    이마트 크롤링 (네트워크 가로채기 + 버튼 클릭)
    
    전략:
    - '.btn_next' 버튼을 반복적으로 클릭하여 모든 페이지를 로딩시킴.
    - 페이지 로딩 중 발생하는 네트워크 요청을 가로채서(Intercept) 이미지 URL 수집.
    - 수집된 URL들을 병렬로 일괄 다운로드.
    """
    print(f"[이마트] 크롤링 시작...")
    page = await context.new_page()
    intercepted_urls = set()
    
    # 1. 네트워크 요청 감지 핸들러
    def handle_response(response):
        try:
            url = response.url
            content_type = response.headers.get('content-type', '')
            # 이미지 타입이고, jpg/png 인 경우만 수집
            if 'image' in content_type and ('jpg' in url or 'png' in url or 'jpeg' in url):
                 # 로고, 아이콘, 버튼 등은 URL 이름으로 1차 필터링
                 if 'logo' not in url and 'icon' not in url and 'button' not in url:
                    intercepted_urls.add(url)
        except:
            pass

    page.on("response", handle_response)

    images = []
    try:
        await page.goto(EMART_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        
        # 2. '다음' 버튼 클릭하며 페이지 순회
        print("[이마트] 페이지 순회 중 (Next 버튼 클릭)...")
        for i in range(20): # 최대 20페이지 안전장치
            await page.wait_for_timeout(1000) # 렌더링 대기
            
            try:
                # 버튼 찾기 (.btn_next 또는 .d-next 클래스)
                btn = await page.query_selector('.btn_next')
                if not btn: 
                    btn = await page.query_selector('.d-next')
                
                # 버튼이 있고 보이면 클릭
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1000) # 요청 발생 대기
                else:
                    # 버튼 없으면 끝
                    break
            except Exception:
                break
        
        # 마지막 요청 대기
        await page.wait_for_timeout(2000)
        print(f"[이마트] 감지된 이미지 URL: {len(intercepted_urls)}개")
        
        # 3. 수집된 URL 병렬 다운로드
        tasks = []
        sorted_urls = sorted(list(intercepted_urls)) # 순서 보장을 위해 정렬
        count = 1
        
        for src in sorted_urls:
             filename = f"emart_new_{count:02d}.jpg"
             tasks.append(download_image(session, src, filename))
             count += 1
             if count > 20: break
        
        # asyncio.gather로 동시 실행
        results = await asyncio.gather(*tasks)
        
        # 결과 중 None(실패/필터링됨) 제외
        images = [r for r in results if r is not None]

    except Exception as e:
        print(f"[이마트] 오류 발생: {e}")
    finally:
        await page.close()
    
    return images

async def scrape_homeplus(context, session):
    """
    홈플러스 크롤링 (DOM 파싱)
    전략: 스크롤을 끝까지 내려 Lazy Loading 이미지를 모두 로딩 후 img 태그 수집.
    """
    print(f"[홈플러스] 크롤링 시작...")
    page = await context.new_page()
    images = []
    try:
        await page.goto(HOMEPLUS_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        
        # 스크롤 최하단으로 이동
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        img_elements = await page.query_selector_all('img')
        
        # URL 수집
        tasks = []
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            if src and ('leaflet' in src or 'flyer' in src or 'jpg' in src) and 'logo' not in src:
                 if not src.startswith('http'):
                    src = 'https://my.homeplus.co.kr' + src if src.startswith('/') else src
                 
                 filename = f"homeplus_new_{count:02d}.jpg"
                 tasks.append(download_image(session, src, filename))
                 count += 1
                 if count > 15: break
        
        if tasks:
            results = await asyncio.gather(*tasks)
            images = [r for r in results if r is not None]

    except Exception as e:
        print(f"[홈플러스] 오류 발생: {e}")
    finally:
        await page.close()
    
    return images

async def scrape_lotte(context, session):
    """
    롯데마트 크롤링 (DOM 파싱 + Lazy Loading 대응)
    전략: src 속성뿐만 아니라 data-src 속성도 확인하여 이미지 URL 추출.
    """
    print(f"[롯데마트] 크롤링 시작...")
    page = await context.new_page()
    images = []
    try:
        await page.goto(LOTTE_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(5000) # JS 렌더링 여유 있게 대기
        
        img_elements = await page.query_selector_all('img')
        
        tasks = []
        count = 1
        for img in img_elements:
            src = await img.get_attribute('src')
            data_src = await img.get_attribute('data-src') # Lazy Loading 속성 확인
            real_src = src or data_src
            
            if real_src and ('jpg' in real_src or 'png' in real_src) and 'logo' not in real_src:
                 # 상대 경로 처리
                 if not real_src.startswith('http'):
                    if real_src.startswith('//'):
                        real_src = 'https:' + real_src
                    elif real_src.startswith('/'):
                        real_src = 'https://www.mlotte.net' + real_src
                 
                 filename = f"lotte_new_{count:02d}.jpg"
                 tasks.append(download_image(session, real_src, filename))
                 count += 1
                 if count > 20: break
        
        if tasks:
            results = await asyncio.gather(*tasks)
            images = [r for r in results if r is not None]

    except Exception as e:
        print(f"[롯데마트] 오류 발생: {e}")
    finally:
        await page.close()
    
    return images


# ==========================================
# 메인 로직 (Main Logic)
# ==========================================

async def main():
    async with async_playwright() as p:
        # 모바일 뷰포트로 브라우저 실행 (모바일 페이지가 구조가 단순함)
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={'width': 390, 'height': 844})
        
        async with aiohttp.ClientSession() as session:
            # 1. 기존 데이터 로드
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 2. 3개 마트 병렬(Parallel) 크롤링 실행
            # 동시에 실행하여 전체 소요 시간을 단축함
            print(">>> 3개 마트 동시 크롤링 시작...")
            results = await asyncio.gather(
                scrape_emart(context, session),
                scrape_homeplus(context, session),
                scrape_lotte(context, session)
            )
            
            new_emart_images = results[0]
            new_homeplus_images = results[1]
            new_lotte_images = results[2]
            
            print(f">>> 크롤링 완료. 결과: 이마트({len(new_emart_images)}), 홈플러스({len(new_homeplus_images)}), 롯데({len(new_lotte_images)})")

            # 3. 데이터 업데이트 (안전장치 포함)
            def update_mart_data(mart_index, new_images):
                mart_name = data[mart_index]['name']
                
                if not new_images:
                    print(f"[{mart_name}] 새 이미지가 없습니다. 업데이트 건너뜀.")
                    return

                # 현재 저장된 이미지들의 파일 존재 여부 및 해시 확인
                current_flyer = data[mart_index]['flyers']['current']
                current_paths = [p.split('?')[0].replace('./', '') for p in current_flyer.get('images', [])]
                
                current_hashes = []
                missing_files = False # 로컬 파일 유실 여부 플래그
                
                for p in current_paths:
                    h = calculate_file_hash(p)
                    if h:
                        current_hashes.append(h)
                    else:
                        missing_files = True 
                
                # 새 이미지들의 해시 계산
                new_hashes = []
                for p in new_images:
                    h = calculate_file_hash(p.replace('./', ''))
                    if h:
                        new_hashes.append(h)
                
                # 중복 검사 (내용이 100% 똑같으면 업데이트 안 함)
                if current_hashes and new_hashes and current_hashes == new_hashes:
                    print(f"[{mart_name}] 변경 사항 없음 (이미지 내용 동일).")
                    return

                print(f"[{mart_name}] 업데이트 진행!")
                
                # [안전장치] 현재 파일이 실제로 존재할 때만 '지난 전단지'로 아카이빙
                # 파일이 없는데 아카이빙하면 지난 전단지도 엑박이 됨
                if not missing_files and current_hashes:
                    data[mart_index]['flyers']['past']['images'] = current_flyer.get('images', [])
                else:
                    print(f"[{mart_name}] 경고: 현재 로컬 파일이 일부 누락되어 아카이빙을 건너뜁니다.")
                
                # 최신 데이터 덮어쓰기
                data[mart_index]['flyers']['current']['images'] = new_images

            # 순차적으로 데이터 갱신
            update_mart_data(0, new_emart_images)
            update_mart_data(1, new_homeplus_images)
            update_mart_data(2, new_lotte_images)

            # 4. JSON 저장
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            print(">>> 모든 작업 완료. data.json 저장됨.")
        
        await browser.close()

if __name__ == '__main__':
    start_time = time.time()
    asyncio.run(main())
    print(f"--- 실행 시간: {time.time() - start_time:.2f}초 ---")
