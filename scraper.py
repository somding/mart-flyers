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
# ⚙️ 설정 (Configuration)
# ==========================================
DATA_FILE = 'data.json'
IMAGES_DIR = 'images'
USER_AGENT = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'

# 마트별 전단지 URL
EMART_URL = 'https://eapp.emart.com/leaflet/leafletView_EL.do'
HOMEPLUS_URL = 'https://my.homeplus.co.kr/leaflet'
LOTTE_URL = 'https://www.mlotte.net/leaflet?rst1=HYPER'

# ==========================================
# 🔧 유틸리티 함수 (Utility Functions)
# ==========================================

def calculate_file_hash(filepath):
    """
    (Deprecated) 파일의 MD5 해시값을 계산합니다.
    현재는 사용하지 않지만, 추후 엄격한 비교가 필요할 때를 대비해 남겨둡니다.
    """
    if not os.path.exists(filepath):
        return None
    try:
        # 이미지 픽셀 데이터만 해싱하여 메타데이터 변경 무시
        with Image.open(filepath) as img:
            pixel_data = img.tobytes()
            hash_md5 = hashlib.md5()
            hash_md5.update(pixel_data)
            return hash_md5.hexdigest()
    except Exception:
        pass
        
    try:
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None

def is_image_different(path1, path2):
    """
    두 이미지 파일이 '실질적으로' 다른지 비교합니다.
    서버의 재압축으로 인한 미세한 파일 크기 차이를 무시하기 위해
    파일 크기 오차가 3% 미만이고 해상도가 같으면 '같은 파일'로 간주합니다.
    
    Args:
        path1 (str): 첫 번째 파일 경로
        path2 (str): 두 번째 파일 경로
    Returns:
        bool: 다르면 True, 비슷하거나 같으면 False
    """
    if not os.path.exists(path1) or not os.path.exists(path2):
        return True # 파일이 하나라도 없으면 '다름' (변경됨)
    
    try:
        # 1. 파일 크기 비교
        size1 = os.path.getsize(path1)
        size2 = os.path.getsize(path2)
        
        # 0바이트 파일은 무효함
        if size1 == 0 or size2 == 0: return True
        
        # 크기 차이 비율 계산
        diff_ratio = abs(size1 - size2) / max(size1, size2)
        
        # 2. 유사도 판단 (3% 미만 차이 & 해상도 일치)
        if diff_ratio < 0.03:
            with Image.open(path1) as img1, Image.open(path2) as img2:
                if img1.size == img2.size:
                    return False # 크기도 비슷하고 해상도도 같음 -> 변경 없음
        
        return True # 차이가 크므로 다른 이미지임
    except Exception:
        # 파일 열기 실패 등 오류 발생 시 안전하게 '다름'으로 처리하여 업데이트 유도
        return True

async def download_image(session, url, filename):
    """
    이미지를 비동기로 다운로드하고 유효성을 검사합니다.
    너무 작거나(아이콘), 잘못된 형식의 이미지는 저장하지 않고 삭제합니다.
    """
    if not url: return None
    
    try:
        # 스키마 보정 (//example.com -> https://example.com)
        if url.startswith('//'):
            url = 'https:' + url
        elif url.startswith('/') and not url.startswith('http'):
            # 도메인을 알 수 없으므로 주의 필요, 호출부에서 full url 권장
            pass 

        async with session.get(url) as response:
            if response.status == 200:
                filepath = os.path.join(IMAGES_DIR, filename)
                content = await response.read()
                
                # 파일 쓰기
                with open(filepath, 'wb') as f:
                    f.write(content)
                
                # --- 품질 검사 (Validation) ---
                file_size = len(content)
                
                # 1. 크기 필터 (1KB 미만 삭제)
                if file_size < 1000:
                    os.remove(filepath)
                    return None
                
                # 2. 이미지 포맷 필터 (JPG/PNG 헤더 확인)
                if not (content.startswith(b'\xff\xd8\xff') or content.startswith(b'\x89PNG')):
                    os.remove(filepath)
                    return None
                
                # 3. 해상도 필터 (PIL 사용)
                try:
                    with Image.open(filepath) as img:
                        w, h = img.size
                        # 가로/세로 300px 미만이면 아이콘으로 간주하여 삭제
                        if w < 300 or h < 300:
                            os.remove(filepath)
                            return None
                        
                        # 비율 필터: 가로가 세로보다 너무 길면(배너 등) 삭제
                        if w > h * 3.0: 
                            os.remove(filepath)
                            return None
                except Exception:
                    os.remove(filepath)
                    return None
                    
                return f"./{IMAGES_DIR}/{filename}"
            else:
                 return None
    except Exception as e:
        print(f"[-] 다운로드 에러 ({url}): {e}")
        return None

# ==========================================
# 🛒 마트별 크롤링 함수 (Scraping)
# ==========================================

async def scrape_emart(context, session):
    """
    [이마트] 순차적 페이지 방문 방식
    - '다음' 버튼을 클릭하며 페이지를 넘기고, 중앙에 있는 큰 이미지를 수집합니다.
    """
    print(f"[이마트] 크롤링 시작...")
    page = await context.new_page()
    images = []
    
    try:
        await page.goto(EMART_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2000)
        
        print("[이마트] 페이지 순회 중...")
        for i in range(20): # 안전을 위해 최대 20페이지 제한
            try:
                # 현재 페이지에서 가장 유력한 전단지 이미지 추출
                visible_img_src = await page.evaluate('''() => {
                    const imgs = Array.from(document.querySelectorAll('img'));
                    // 300px 이상이고 로고가 아닌 이미지 필터링
                    const candidates = imgs.filter(img => {
                        const rect = img.getBoundingClientRect();
                        return rect.width > 300 && rect.height > 300 && 
                               !img.src.includes('logo') && !img.src.includes('icon');
                    });
                    return candidates.length > 0 ? candidates[0].src : null;
                }''')

                if visible_img_src:
                    # 임시 파일명 생성 (temp_emart_XX.jpg)
                    count = len(images) + 1
                    filename = f"temp_emart_{count:02d}.jpg"
                    
                    # 중복 URL 체크
                    if not any(item['url'] == visible_img_src for item in images):
                        print(f"  + {count}페이지 이미지 발견")
                        images.append({'url': visible_img_src, 'filename': filename})
            except Exception:
                pass

            # '다음' 버튼 클릭
            try:
                btn = await page.query_selector('.btn_next') or await page.query_selector('.d-next')
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1000)
                else:
                    break # 버튼 없으면 종료
            except Exception:
                break
        
        # 이미지 다운로드 (병렬)
        print(f"[이마트] 총 {len(images)}장 다운로드 시도...")
        tasks = [download_image(session, item['url'], item['filename']) for item in images]
        if tasks:
            results = await asyncio.gather(*tasks)
            # 성공한 파일 경로만 반환
            return [r for r in results if r is not None]

    except Exception as e:
        print(f"[이마트] 크롤링 중 오류: {e}")
    finally:
        await page.close()
    
    return []

async def scrape_homeplus(context, session):
    """
    [홈플러스] 좌표 정렬 방식
    - 이미지가 Lazy Loading 되므로 스크롤을 끝까지 내립니다.
    - DOM 순서가 섞여있으므로, 이미지의 Y좌표(Top) 순으로 정렬하여 올바른 순서를 맞춥니다.
    """
    print(f"[홈플러스] 크롤링 시작...")
    page = await context.new_page()
    final_images = []
    
    try:
        await page.goto(HOMEPLUS_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        
        # 스크롤 최하단 이동 (이미지 로딩 유도)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        # 이미지 정보(src, 좌표, 크기) 추출
        img_data = await page.evaluate('''() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            return imgs.map(img => {
                const rect = img.getBoundingClientRect();
                return {
                    src: img.src,
                    top: rect.top + window.scrollY,
                    width: rect.width,
                    height: rect.height
                };
            }).filter(item => {
                // 크기 > 200px, 로고 제외, leaflet/flyer/jpg 키워드 포함
                return item.width > 200 && 
                       item.height > 200 &&
                       !item.src.includes('logo') &&
                       (item.src.includes('leaflet') || item.src.includes('flyer') || item.src.includes('jpg'));
            });
        }''')
        
        # Y좌표 기준 정렬 및 중복 제거
        sorted_img_data = sorted(img_data, key=lambda x: x['top'])
        unique_urls = []
        seen = set()
        
        for item in sorted_img_data:
            src = item['src']
            if not src.startswith('http'): # 상대경로 보정
                 src = 'https://my.homeplus.co.kr' + src if src.startswith('/') else src
            
            if src not in seen:
                seen.add(src)
                unique_urls.append(src)
                if len(unique_urls) >= 15: break # 최대 15장
        
        # 다운로드 (순서 유지: temp 파일 번호 부여)
        print(f"[홈플러스] {len(unique_urls)}장 다운로드 시도...")
        tasks = []
        for idx, src in enumerate(unique_urls):
             filename = f"temp_homeplus_{idx+1:02d}.jpg"
             tasks.append(download_image(session, src, filename))
        
        if tasks:
            results = await asyncio.gather(*tasks)
            # 결과 정렬 (파일명 순)
            valid_results = [r for r in results if r is not None]
            final_images = sorted(valid_results)

    except Exception as e:
        print(f"[홈플러스] 오류: {e}")
    finally:
        await page.close()
    
    return final_images

async def scrape_lotte(context, session):
    """
    [롯데마트] URL 파라미터 방식
    - 올바른 파라미터(?rst1=HYPER)로 접속해 이미지를 수집합니다.
    """
    print(f"[롯데마트] 크롤링 시작...")
    page = await context.new_page()
    images = []
    
    try:
        await page.goto(LOTTE_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(3000)
        
        # 롯데마트는 body 스크롤이 아닐 수 있음, 그래도 시도
        try:
             await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except: pass
        
        img_elements = await page.query_selector_all('img')
        
        tasks = []
        seen_urls = set()
        count = 1
        
        for img in img_elements:
            src = await img.get_attribute('src')
            data_src = await img.get_attribute('data-src')
            real_src = data_src or src
            
            if real_src:
                 # 상대경로 -> 절대경로
                 if real_src.startswith('//'):
                     real_src = 'https:' + real_src
                 elif real_src.startswith('/'):
                     real_src = 'https://www.mlotte.net' + real_src
                 
                 # 필터링
                 if 'logo' in real_src or 'icon' in real_src: continue
                 if real_src in seen_urls: continue
                 
                 if 'jpg' in real_src or 'png' in real_src:
                    seen_urls.add(real_src)
                    filename = f"temp_lotte_{count:02d}.jpg"
                    tasks.append(download_image(session, real_src, filename))
                    count += 1
                    if count > 20: break
        
        if tasks:
            results = await asyncio.gather(*tasks)
            images = sorted([r for r in results if r is not None])

    except Exception as e:
        print(f"[롯데마트] 오류: {e}")
    finally:
        await page.close()
    
    return images

# ==========================================
# 🚀 메인 및 업데이트 로직 (Main Workflow)
# ==========================================

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # 모바일 환경 에뮬레이션
        context = await browser.new_context(
            viewport={'width': 390, 'height': 844},
            user_agent=USER_AGENT,
            locale='ko-KR'
        )
        
        async with aiohttp.ClientSession() as session:
            # 1. 데이터 로드 (파일 없으면 기본 구조 생성)
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                print(f"[Warning] {DATA_FILE} 파일을 찾을 수 없거나 손상되었습니다. 기본 구조를 사용하지만, 마트 설정이 없어 실패할 수 있습니다.")
                data = [] # 이 경우엔 사실상 실패, 복구 로직은 생략.

            # 2. 크롤링 실행 (비동기 병렬 처리)
            print(">>> 전체 마트 크롤링 시작...")
            # 순서: 이마트(0), 홈플러스(1), 롯데마트(2)
            results = await asyncio.gather(
                scrape_emart(context, session),
                scrape_homeplus(context, session),
                scrape_lotte(context, session)
            )
            
            # 3. 데이터 업데이트 및 아카이빙 로직
            #    new_images: 새로 다운로드된 임시 파일 리스트
            def update_mart_data(mart_index, new_images):
                mart_name = data[mart_index]['name']
                
                # 다운로드 실패 등으로 새 이미지가 없으면 패스
                if not new_images:
                    print(f"[{mart_name}] 수집된 이미지가 없습니다. 업데이트 중단.")
                    return

                # 파일명 접두사 결정 (저장될 이름)
                if mart_name.startswith('이마트'):   prefix = 'emart'
                elif mart_name.startswith('홈플러스'): prefix = 'homeplus'
                else:                               prefix = 'lotte'
                
                # 비교 대상: 지금 다운받은 temp 파일들
                temp_files = [p.replace('./', '') for p in new_images]
                
                # 비교 원본: 현재 살아있는(Current) 파일들
                current_flyer_info = data[mart_index]['flyers']['current']
                current_files = [p.split('?')[0].replace('./', '') for p in current_flyer_info.get('images', [])]

                # --- 변경 감지 로직 ---
                is_modified = False
                
                # 1) 장수가 다르면 무조건 변경
                if len(temp_files) != len(current_files):
                    is_modified = True
                    print(f"[{mart_name}] 업데이트 감지: 페이지 수 변경 ({len(current_files)} -> {len(temp_files)})")
                else:
                    # 2) 장수가 같으면 각 이미지의 내용을 파일 크기/해상도 등으로 비교
                    for t_path, c_path in zip(temp_files, current_files):
                        if is_image_different(t_path, c_path):
                            is_modified = True
                            print(f"[{mart_name}] 업데이트 감지: 이미지 내용 변경됨")
                            break
                
                # 변경 사항이 없으면 임시 파일 삭제 후 종료
                if not is_modified:
                    print(f"[{mart_name}] 최신 상태입니다. (변경 없음)")
                    for p in temp_files:
                        if os.path.exists(p): os.remove(p)
                    return

                # --- 업데이트 실행 (Archive & Promote) ---
                print(f"[{mart_name}] 업데이트를 적용합니다...")
                
                # 1. 아카이빙: 현재(Current) 파일을 과거(Past)로 이동
                #    파일명을 '_new_' -> '_' 로 변경하거나 '_past' 추가
                archived_files = []
                if current_files:
                    for old_path in current_files:
                        if not os.path.exists(old_path): continue
                        
                        # 파일명 변환 규칙
                        if '_new_' in old_path:
                            new_path = old_path.replace('_new_', '_')
                        else:
                            new_path = old_path.replace('.jpg', '_past.jpg')
                        
                        # 덮어쓰기 허용 (과거 파일 갱신)
                        if os.path.exists(new_path):
                            os.remove(new_path)
                            
                        try:
                            os.rename(old_path, new_path)
                            archived_files.append(f"./{new_path}")
                        except Exception as e:
                            print(f"  [Warning] 아카이빙 파일 이동 실패: {e}")

                    # JSON 데이터 갱신 (Past)
                    if archived_files:
                         data[mart_index]['flyers']['past']['images'] = archived_files
                         print(f"  -> 지난 전단지로 이동됨 ({len(archived_files)}장)")

                # 2. 최신화: 임시(Temp) 파일을 현재(Current)로 승격
                #    temp_prefix_XX.jpg -> prefix_new_XX.jpg
                final_current_files = []
                for idx, temp_path in enumerate(temp_files):
                    if not os.path.exists(temp_path): continue
                    
                    final_name = f"{IMAGES_DIR}/{prefix}_new_{idx+1:02d}.jpg"
                    
                    if os.path.exists(final_name):
                        os.remove(final_name)
                    
                    try:
                        os.rename(temp_path, final_name)
                        final_current_files.append(f"./{final_name}")
                    except Exception as e:
                         print(f"  [Error] 최신 파일 적용 실패: {e}")
                
                # JSON 데이터 갱신 (Current)
                data[mart_index]['flyers']['current']['images'] = final_current_files
                data[mart_index]['flyers']['current']['date'] = time.strftime("%Y-%m-%d") # 날짜 갱신
                print(f"  -> 최신 전단지 적용 완료 ({len(final_current_files)}장)")

            # 각 마트 데이터 갱신 실행
            update_mart_data(0, results[0]) # 이마트
            update_mart_data(1, results[1]) # 홈플러스
            update_mart_data(2, results[2]) # 롯데마트

            # 4. 최종 결과 저장
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            print(">>> 모든 데이터 처리가 안전하게 완료되었습니다.")
        
        await browser.close()

if __name__ == '__main__':
    start_time = time.time()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n[Error] 치명적인 오류 발생: {e}")
    finally:
        print(f"--- 총 실행 시간: {time.time() - start_time:.2f}초 ---")
