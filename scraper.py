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
LOTTE_URL = 'https://www.mlotte.net/leaflet'

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
                        # 가로/세로 300px 미만이면 삭제 (타일 이미지 고려하여 완화)
                        if w < 300 or h < 300:
                            # print(f"[-] 너무 작은 이미지 제거 ({w}x{h}): {filename}")
                            os.remove(filepath)
                            return None
                        
                        # [추가 필터] 스프라이트 이미지(아이콘 모음) 제거
                        if w > h * 2.5: # 비율 필터 약간 완화
                            # print(f"[-] 스프라이트/배너로 의심되어 제거 ({w}x{h}): {filename}")
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
    이마트 크롤링 (순차적 DOM 수집 - 순서 보장)
    
    기존의 네트워크 인터셉트 방식은 로딩 순서에 따라 이미지가 뒤섞이는 문제가 있었음.
    변경: 화면에 보이는 이미지를 순서대로 가져오고, '다음' 버튼을 눌러 이동하는 방식.
    """
    print(f"[이마트] 크롤링 시작...")
    page = await context.new_page()
    images = []
    
    try:
        await page.goto(EMART_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2000)
        
        # 1. 페이지 순회하며 순서대로 이미지 수집
        print("[이마트] 페이지 순회 중 (순차 수집)...")
        for i in range(20): # 최대 20페이지
            # 현재 페이지에서 가장 큰 이미지 찾기 (전단지 메인 이미지)
            # 모바일 뷰에서는 보통 전단지 이미지가 화면의 대부분을 차지함
            try:
                # 모든 이미지 중 크기가 큰 것(500px 이상)이자 로고가 아닌 것 선별
                visible_img_src = await page.evaluate('''() => {
                    const imgs = Array.from(document.querySelectorAll('img'));
                    const candidates = imgs.filter(img => {
                        const rect = img.getBoundingClientRect();
                        return rect.width > 300 && rect.height > 300 && 
                               !img.src.includes('logo') && !img.src.includes('icon');
                    });
                    // 화면 중앙에 가까운 이미지나 첫번째 큰 이미지 반환
                    return candidates.length > 0 ? candidates[0].src : null;
                }''')

                if visible_img_src:
                    # 중복 체크 (이미 리스트에 있으면 추가 안 함 - 근데 버튼 눌렀는데 안 바뀌었으면 끝난 거일수도)
                    # 하지만 이마트는 URL이 바뀜.
                    # 다운로드 예약
                    count = len(images) + 1
                    filename = f"emart_new_{count:02d}.jpg"
                    
                    # 이미 수집된 URL인지 확인
                    if not any(item['url'] == visible_img_src for item in images):
                        print(f"  [이마트] {count}페이지 발견: ...{visible_img_src[-20:]}")
                        images.append({'url': visible_img_src, 'filename': filename})
            except Exception as e:
                print(f"  이미지 탐색 실패: {e}")

            # 다음 버튼 클릭
            try:
                btn = await page.query_selector('.btn_next')
                if not btn: 
                    btn = await page.query_selector('.d-next')
                
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1000) # 페이지 전환 대기
                else:
                    print("  더 이상 다음 버튼이 없습니다.")
                    break
            except Exception:
                break
        
        print(f"[이마트] 총 {len(images)}개 페이지 URL 확보.")
        
        # 2. 순서대로 다운로드 (병렬 처리하되 파일명에 번호가 있으므로 순서 유지됨)
        tasks = []
        final_paths = []
        
        for item in images:
             tasks.append(download_image(session, item['url'], item['filename']))
        
        if tasks:
            results = await asyncio.gather(*tasks)
            final_paths = [r for r in results if r is not None]
            # 주의: gather 결과는 tasks 순서와 일치함. 즉 1페이지 -> 1번 파일 매칭됨.

    except Exception as e:
        print(f"[이마트] 오류 발생: {e}")
    finally:
        await page.close()
    
    return final_paths

async def scrape_homeplus(context, session):
    """
    홈플러스 크롤링 (좌표 기반 정렬 + 중복 제거)
    
    문제: DOM 순서나 로딩 순서가 뒤죽박죽이라 페이지 순서가 섞임.
    해결: 이미지의 화면상 Y좌표(Top)를 기준으로 정렬하여 위에서부터 차례대로 번호를 매김.
    """
    print(f"[홈플러스] 크롤링 시작...")
    page = await context.new_page()
    final_images = []
    
    try:
        await page.goto(HOMEPLUS_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        
        # 스크롤 최하단으로 이동 (Lazy Loading)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        # 이미지 태그와 좌표 정보를 함께 수집
        # JavaScript로 직접 필터링 및 데이터 추출 수행
        img_data = await page.evaluate('''() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            return imgs.map(img => {
                const rect = img.getBoundingClientRect();
                return {
                    src: img.src,
                    top: rect.top + window.scrollY, // 절대 좌표
                    width: rect.width,
                    height: rect.height
                };
            }).filter(item => {
                // 필터링: 크기가 적당하고, 전단지 관련 키워드가 있거나(확실치 않으면 src 검사는 완화), 로고가 아닌 것
                // 홈플러스는 'leaflet'이나 'jpg' 등이 포함됨.
                return item.width > 200 && 
                       item.height > 200 &&
                       !item.src.includes('logo') &&
                       (item.src.includes('leaflet') || item.src.includes('flyer') || item.src.includes('jpg'));
            });
        }''')
        
        # 중복 제거 및 정렬 준비
        unique_images = []
        seen_urls = set()
        
        # Y좌표 기준으로 정렬 (위 -> 아래)
        sorted_img_data = sorted(img_data, key=lambda x: x['top'])
        
        for item in sorted_img_data:
            src = item['src']
            
            # URL 스키마 보정
            if not src.startswith('http'):
               src = 'https://my.homeplus.co.kr' + src if src.startswith('/') else src
            
            if src in seen_urls:
                continue
            seen_urls.add(src)
            unique_images.append(src)
            
            if len(unique_images) >= 15: # 최대 15장
                break
        
        # 이제 순서대로 다운로드 작업 생성
        tasks = []
        count = 1
        for src in unique_images:
             filename = f"homeplus_new_{count:02d}.jpg"
             tasks.append(download_image(session, src, filename))
             count += 1
        
        if tasks:
            results = await asyncio.gather(*tasks)
            # 다운로드는 병렬이라 순서가 섞일 수 있지만, 파일명(homeplus_new_01)은 이미 정해져 있음.
            # 결과를 파일명 순으로 정렬하면 됨.
            valid_results = [r for r in results if r is not None]
            final_images = sorted(valid_results)

        print(f"[홈플러스] 좌표 정렬 완료. 총 {len(final_images)}장.")

    except Exception as e:
        print(f"[홈플러스] 오류 발생: {e}")
    finally:
        await page.close()
    
    return final_images

async def scrape_lotte(context, session):
    """
    롯데마트 크롤링 (단순 DOM 파싱 - 원복)
    복잡한 JS 로직 제거하고 가장 기초적인 방식으로 복귀.
    """
    print(f"[롯데마트] 크롤링 시작...")
    page = await context.new_page()
    images = []
    
    try:
        await page.goto(LOTTE_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(6000) # 로딩 대기 시간 증가
        
        # 스크롤 최하단으로 이동
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)
        
        img_elements = await page.query_selector_all('img')
        
        tasks = []
        seen_urls = set()
        count = 1
        
        for img in img_elements:
            src = await img.get_attribute('src')
            data_src = await img.get_attribute('data-src')
            real_src = data_src or src # data-src 우선
            
            # URL 문자열 필터 대폭 완화 (확장자 검사 제거)
            if real_src and 'logo' not in real_src and 'icon' not in real_src:
                 # 상대 경로 처리
                 if not real_src.startswith('http'):
                    if real_src.startswith('//'):
                        real_src = 'https:' + real_src
                    elif real_src.startswith('/'):
                        real_src = 'https://www.mlotte.net' + real_src
                 
                 # 중복 제거
                 if real_src in seen_urls:
                     continue
                 seen_urls.add(real_src)
                 
                 filename = f"lotte_new_{count:02d}.jpg"
                 tasks.append(download_image(session, real_src, filename))
                 count += 1
                 if count > 20: break
        
        if tasks:
            print(f"[롯데마트] {len(tasks)}개 이미지 발견. 다운로드 시작.")
            results = await asyncio.gather(*tasks)
            images = [r for r in results if r is not None]
            # 단순 방식은 파일명 순서 정렬을 따로 안 해도 gathered result가 task 순서를 따름
            # 하지만 안전하게 정렬은 한 번 해줌
            images = sorted(images)

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
        # 모바일 환경 흉내 (User-Agent 설정 필수)
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={'width': 390, 'height': 844},
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            locale='ko-KR',
            timezone_id='Asia/Seoul'
        )
        
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
