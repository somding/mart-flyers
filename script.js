const marts = [
    {
        id: 'emart',
        name: '이마트 (E-mart)',
        description: '대한민국 1등 할인점, 이마트의 최신 전단지를 확인하세요.',
        logo: './images/emart_logo.svg',
        flyers: {
            current: {
                title: '최신 전단지 보기',
                images: [
                    './images/emart_01.jpg?v=2', './images/emart_02.jpg?v=2', './images/emart_03.jpg?v=2', './images/emart_04.jpg?v=2',
                    './images/emart_05.jpg?v=2', './images/emart_06.jpg?v=2', './images/emart_07.jpg?v=2', './images/emart_08.jpg?v=2',
                    './images/emart_09.jpg?v=2', './images/emart_10.jpg?v=2', './images/emart_11.jpg?v=2', './images/emart_12.jpg?v=2',
                    './images/emart_13.jpg?v=2', './images/emart_14.jpg?v=2'
                ],
                type: 'image'
            },
            past: {
                title: '지난 전단지',
                images: [],
                type: 'image'
            }
        }
    },
    {
        id: 'homeplus',
        name: '홈플러스 (Homeplus)',
        description: '생활에 플러스가 됩니다. 홈플러스의 알뜰 정보를 만나보세요.',
        logo: './images/homeplus_logo.png',
        flyers: {
            current: {
                title: '최신 전단지 보기',
                images: [
                    './images/homeplus_01.jpg', './images/homeplus_02.jpg', './images/homeplus_03.jpg',
                    './images/homeplus_04.jpg', './images/homeplus_05.jpg', './images/homeplus_06.jpg'
                ],
                type: 'image'
            },
            past: {
                title: '지난 전단지',
                images: [],
                type: 'image'
            }
        }
    },
    {
        id: 'lottemart',
        name: '롯데마트 (Lotte Mart)',
        description: '행복한 쇼핑, 롯데마트의 다양한 혜택을 놓치지 마세요.',
        logo: './images/lotte_mart_logo.svg',
        flyers: {
            current: {
                title: '최신 전단지 보기',
                images: [
                    './images/lotte_01.jpg', './images/lotte_02.jpg', './images/lotte_03.jpg',
                    './images/lotte_04.jpg', './images/lotte_05.jpg'
                ],
                type: 'image'
            },
            past: {
                title: '지난 전단지',
                images: [],
                type: 'image'
            }
        }
    }
];

document.addEventListener('DOMContentLoaded', () => {
    const martList = document.getElementById('mart-list');
    const modal = document.getElementById('flyer-modal');
    const modalTitle = document.getElementById('modal-title');
    const closeButton = document.querySelector('.close-button');
    const tabCurrent = document.getElementById('tab-current');
    const tabPast = document.getElementById('tab-past');

    // New Elements
    const flyerContainer = document.getElementById('flyer-container');

    let currentMart = null;

    // Render Mart Cards
    marts.forEach(mart => {
        const card = document.createElement('div');
        card.className = 'mart-card';
        card.innerHTML = `
            <div class="mart-logo-area">
                <img src="${mart.logo}" alt="${mart.name}" class="mart-logo">
            </div>
            <div class="mart-info">
                <h3 class="mart-name">${mart.name}</h3>
                <p class="mart-desc">${mart.description}</p>
                <a href="#" class="view-btn">전단지 보기</a>
            </div>
        `;

        card.addEventListener('click', (e) => {
            e.preventDefault();
            openModal(mart);
        });

        martList.appendChild(card);
    });

    // Modal Logic
    function openModal(mart) {
        currentMart = mart;
        modalTitle.textContent = mart.name;

        // Reset to Current Tab
        switchTab('current');

        modal.classList.remove('hidden');
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
    }

    function switchTab(tab) {
        let flyerData;
        if (tab === 'current') {
            tabCurrent.classList.add('active');
            tabPast.classList.remove('active');
            flyerData = currentMart.flyers.current;
        } else {
            tabCurrent.classList.remove('active');
            tabPast.classList.add('active');
            flyerData = currentMart.flyers.past;

            // Fallback: If past flyer is empty, show current flyer
            if (!flyerData.images || flyerData.images.length === 0) {
                flyerData = currentMart.flyers.current;
                // Optional: Add a message saying "No past flyer available, showing current flyer"
                const message = document.createElement('p');
                message.textContent = '지난 전단지가 없어 최신 전단지를 보여드립니다.';
                message.style.color = '#888';
                message.style.marginBottom = '10px';
                flyerContainer.appendChild(message);
            }
        }

        // Clear previous content
        flyerContainer.innerHTML = '';

        // Render all images
        flyerData.images.forEach(imgSrc => {
            const img = document.createElement('img');
            img.src = imgSrc;
            img.alt = '전단지 이미지';
            img.className = 'flyer-img';

            // Error handling for each image
            img.onerror = function () {
                this.onerror = null;
                this.src = 'https://placehold.co/600x400?text=이미지+로딩+실패';
            };

            flyerContainer.appendChild(img);
        });
    }

    tabCurrent.addEventListener('click', () => switchTab('current'));

    tabPast.addEventListener('click', () => switchTab('past'));

    function closeModal() {
        modal.classList.remove('show');
        setTimeout(() => {
            modal.classList.add('hidden');
            flyerContainer.innerHTML = ''; // Clear content on close
        }, 300);
        document.body.style.overflow = '';
    }

    if (closeButton) {
        closeButton.addEventListener('click', closeModal);
    }

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('show')) {
            closeModal();
        }
    });
});
