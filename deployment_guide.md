# 웹 배포 가이드 (Deployment Guide)

이 프로젝트는 정적 웹사이트(HTML, CSS, JS, 이미지)이므로, 별도의 복잡한 서버 설정 없이 무료 호스팅 서비스를 통해 쉽게 배포할 수 있습니다. 가장 추천하는 세 가지 방법을 안내해 드립니다.

## 1. Netlify Drop (가장 쉬움, 회원가입 필요 없음/간단)

가장 빠르게 배포할 수 있는 방법입니다.

1.  [Netlify Drop](https://app.netlify.com/drop) 사이트에 접속합니다.
2.  `mart-flyers` 폴더 전체를 드래그하여 페이지의 "Drag and drop your site output folder here" 영역에 놓습니다.
3.  업로드가 완료되면 즉시 랜덤한 URL이 생성되어 배포됩니다.
4.  (선택) Netlify에 가입하면 사이트 주소를 변경하거나 지속적으로 관리할 수 있습니다.

## 2. GitHub Pages (개발자 추천)

GitHub 계정이 있다면 가장 정석적인 방법입니다.

1.  GitHub에 새로운 리포지토리(Repository)를 생성합니다 (예: `mart-flyers`).
2.  로컬의 `mart-flyers` 폴더를 해당 리포지토리에 푸시(Push)합니다.
    ```bash
    git init
    git add .
    git commit -m "Initial commit"
    git branch -M main
    git remote add origin <당신의_리포지토리_URL>
    git push -u origin main
    ```
3.  리포지토리의 **Settings** > **Pages** 메뉴로 이동합니다.
4.  **Source**를 `Deploy from a branch`로 설정하고, Branch를 `main` / `/ (root)`로 선택한 뒤 Save를 누릅니다.
5.  잠시 후 상단에 배포된 URL이 표시됩니다.

## 3. Vercel (빠른 속도, 한국 리전 지원)

1.  [Vercel](https://vercel.com)에 회원가입(GitHub 계정 연동 추천)을 합니다.
2.  대시보드에서 **Add New...** > **Project**를 클릭합니다.
3.  GitHub 리포지토리를 연결하여 `mart-flyers`를 Import 합니다.
4.  별도의 설정 없이 **Deploy** 버튼을 누르면 자동으로 빌드 및 배포가 완료됩니다.

## 주의사항 (이미지 용량)
현재 프로젝트는 고화질 전단지 이미지를 포함하고 있어 전체 용량이 다소 클 수 있습니다.
- 무료 호스팅 서비스들은 대역폭 제한이 있을 수 있으므로, 상업적 용도라면 이미지 최적화(압축)나 외부 이미지 호스팅(S3, Cloudinary 등)을 고려해야 할 수도 있습니다.
- 하지만 개인적인 용도나 포트폴리오용으로는 위 방법들로 충분합니다.
