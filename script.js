document.addEventListener('DOMContentLoaded', () => {
    // ==========================================
    // 🔗 DOM 요소 참조 (References)
    // ==========================================
    const martList = document.getElementById('mart-list');
    const modal = document.getElementById('flyer-modal');
    const modalTitle = document.getElementById('modal-title');
    const closeButton = document.querySelector('.close-button');
    const tabCurrent = document.getElementById('tab-current');
    const tabPast = document.getElementById('tab-past');
    const flyerContainer = document.getElementById('flyer-container');

    // 상태 관리 변수
    let currentMart = null;
    let marts = [];

    // 필수로 필요한 요소가 없으면 에러 로그를 남기고 중단 (안전 장치)
    if (!martList || !modal || !flyerContainer) {
        console.error("필수 DOM 요소를 찾을 수 없습니다. HTML 구조를 확인해주세요.");
        return;
    }

    // ==========================================
    // 📥 데이터 로드 (Data Loading)
    // ==========================================
    fetch('data.json')
        .then(response => {
            if (!response.ok) throw new Error('네트워크 응답이 올바르지 않습니다.');
            return response.json();
        })
        .then(data => {
            marts = data;
            renderMarts();
            // [UX 성능 최적화] 사용자가 클릭하기 전에 최신 전단지 1면을 미리 받아둡니다. (Preloading)
            preloadCovers(marts);
        })
        .catch(error => {
            console.error('데이터 로드 실패:', error);
            martList.innerHTML = '<p style="text-align:center; padding:50px;">데이터를 불러오는 데 실패했습니다.<br>잠시 후 다시 시도해주세요.</p>';
        });

    // ==========================================
    // 🚀 성능 최적화 (Preloading)
    // ==========================================
    function preloadCovers(marts) {
        // 브라우저가 쉬고 있을 때(Idle) 실행하여 메인 로딩을 방해하지 않음
        if ('requestIdleCallback' in window) {
            requestIdleCallback(() => {
                marts.forEach(mart => {
                    const images = mart.flyers?.current?.images;
                    if (images && images.length > 0) {
                        const img = new Image();
                        img.src = images[0]; // 1면 이미지 미리 로드 (브라우저 캐시에 저장)
                    }
                });
            });
        } else {
            // 구형 브라우저 폴백
            setTimeout(() => {
                marts.forEach(mart => {
                    const images = mart.flyers?.current?.images;
                    if (images && images.length > 0) {
                        new Image().src = images[0];
                    }
                });
            }, 1000);
        }
    }

    // ==========================================
    // 🎨 UI 렌더링 (Rendering)
    // ==========================================
    function renderMarts() {
        // 기존 리스트 초기화
        martList.innerHTML = '';

        marts.forEach(mart => {
            const card = document.createElement('div');
            card.className = 'mart-card';

            // 이름 분리 로직 (한글 / 영문)
            // 예: "이마트 (E-mart)" -> "이마트", "E-mart"
            let nameHtml = mart.name;
            // 정규식: 괄호 앞부분(한글)과 괄호 안(영문) 추출
            const match = mart.name.match(/([^(]+)\s*\(([^)]+)\)/);

            if (match) {
                // 분리된 스타일 적용
                nameHtml = `<span class="name-ko">${match[1].trim()}</span><span class="name-en">${match[2].trim()}</span>`;
            }

            card.innerHTML = `
                <div class="mart-logo-area">
                    <img src="${mart.logo}" alt="${mart.name}" class="mart-logo" loading="lazy">
                </div>
                <div class="mart-info">
                    <h3 class="mart-name">${nameHtml}</h3>
                    <p class="mart-desc">${mart.description}</p>
                    <a href="#" class="view-btn">전단지 보기</a>
                </div>
            `;

            // 카드 클릭 이벤트
            card.addEventListener('click', (e) => {
                e.preventDefault();
                openModal(mart);
            });

            martList.appendChild(card);
        });
    }

    // ==========================================
    // 🖼️ 모달창 로직 (Modal Logic)
    // ==========================================
    function openModal(mart) {
        currentMart = mart;

        // 모달 제목 설정 (한글/영문 분리)
        let nameHtml = mart.name;
        const match = mart.name.match(/([^(]+)\s*\(([^)]+)\)/);
        if (match) {
            nameHtml = `<span class="name-ko">${match[1].trim()}</span> <span class="name-en-modal" style="font-size:0.6em; color:#888;">${match[2].trim()}</span>`;
        }
        modalTitle.innerHTML = nameHtml;

        // 초기 탭: '최신 전단지'
        switchTab('current');

        // 모달 표시 애니메이션
        modal.classList.remove('hidden');
        // 약간의 지연을 주어 CSS transition이 작동하도록 함
        requestAnimationFrame(() => {
            modal.classList.add('show');
        });

        // 배경 스크롤 방지
        document.body.style.overflow = 'hidden';

        // 히스토리 상태 추가 (뒤로가기 버튼 지원)
        history.pushState({ modal: true }, '', window.location.pathname);
    }

    function switchTab(tab) {
        let flyerData;

        // 탭 활성화 상태 변경
        if (tab === 'current') {
            tabCurrent.classList.add('active');
            tabPast.classList.remove('active');
            flyerData = currentMart.flyers.current;
        } else {
            tabCurrent.classList.remove('active');
            tabPast.classList.add('active');
            flyerData = currentMart.flyers.past;

            // 예외 처리: 지난 전단지가 없을 경우
            if (!flyerData.images || flyerData.images.length === 0) {
                // 안내 메시지 표시
                flyerContainer.innerHTML = `
                    <div style="padding: 40px; color: #888;">
                        <p>지난 전단지 데이터가 없습니다.</p>
                        <p style="font-size:0.9em; margin-top:10px;">최신 전단지를 확인해주세요.</p>
                    </div>`;
                return;
            }
        }

        // 기존 전단지 이미지 비우기
        flyerContainer.innerHTML = '';

        // 스크롤 최상단 이동
        flyerContainer.scrollTop = 0;

        // 이미지 렌더링
        if (flyerData.images && flyerData.images.length > 0) {
            flyerData.images.forEach((imgSrc, index) => {
                const img = document.createElement('img');

                // 전단지는 정적 파일이므로 버전 관리는 scraper에서 파일명으로 처리됨.
                img.src = imgSrc;
                img.alt = `${currentMart.name} 전단지 Page ${index + 1}`;
                img.className = 'flyer-img';

                // [UX 최적화] 첫 장은 바로 로딩(Eager), 나머지는 지연 로딩(Lazy)
                if (index === 0) {
                    img.loading = 'eager';
                    img.setAttribute('fetchpriority', 'high');
                } else {
                    img.loading = 'lazy';
                }

                // 이미지 로딩 에러 핸들링
                img.onerror = function () {
                    this.onerror = null;
                    // 깔끔한 에러 플레이스홀더 (Placehold.co 사용)
                    // 실제 서비스에선 로컬 에러 이미지 사용 권장
                    this.src = 'https://placehold.co/600x400/f5f5f7/888888?text=Image+Not+Found';
                    this.style.border = '1px dashed #ccc';
                };

                flyerContainer.appendChild(img);
            });
        } else {
            flyerContainer.innerHTML = '<div style="padding:50px; color:#888;">등록된 전단지 이미지가 없습니다.</div>';
        }
    }

    // ==========================================
    // 🎮 이벤트 리스너 (Event Listeners)
    // ==========================================

    // 탭 전환
    if (tabCurrent) tabCurrent.addEventListener('click', () => switchTab('current'));
    if (tabPast) tabPast.addEventListener('click', () => switchTab('past'));

    // 모달 닫기 로직 (UI)
    function hideModalUI() {
        modal.classList.remove('show');
        // 애니메이션(0.3s)이 끝난 후 hidden 처리
        setTimeout(() => {
            modal.classList.add('hidden');
            flyerContainer.innerHTML = ''; // 메모리 정리
        }, 300);
        document.body.style.overflow = ''; // 스크롤 복구
    }

    // 모달 닫기 (히스토리 제어 포함)
    function closeModal() {
        // 히스토리에 모달 상태가 있으면 뒤로가기 실행 -> popstate 이벤트가 닫기 처리
        if (history.state && history.state.modal) {
            history.back();
        } else {
            // 히스토리가 없으면 (새로고침 등) 그냥 UI 닫기
            hideModalUI();
        }
    }

    // 브라우저 뒤로가기 버튼 처리
    window.addEventListener('popstate', (event) => {
        // 모달이 열려있으면 닫기
        if (modal.classList.contains('show')) {
            hideModalUI();
        }
    });

    // 닫기 버튼 클릭
    if (closeButton) {
        closeButton.addEventListener('click', closeModal);
    }

    // 배경 클릭 시 닫기
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    // ESC 키 누르면 닫기
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('show')) {
            closeModal();
        }
    });
});
