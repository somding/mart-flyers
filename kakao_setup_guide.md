# 카카오톡 공유 기능 설정 가이드

카카오톡 공유 기능을 정상적으로 사용하려면 **카카오 개발자 키(JavaScript Key)**가 필요합니다. 아래 절차를 따라 키를 발급받고 설정해 주세요.

## 1. 카카오 개발자 사이트 가입 및 앱 생성
1.  [Kakao Developers](https://developers.kakao.com/)에 접속하여 카카오 계정으로 로그인합니다.
2.  상단 메뉴의 **내 애플리케이션** > **애플리케이션 추가하기**를 클릭합니다.
3.  앱 이름(예: `마트전단지모음`)과 사업자명(본인 이름 등)을 입력하고 저장합니다.

## 2. JavaScript 키 확인
1.  생성된 애플리케이션을 클릭하여 들어갑니다.
2.  **요약 정보** 탭에서 **JavaScript 키**를 복사합니다.

## 3. 플랫폼 등록 (필수!)
카카오 API는 등록된 도메인에서만 작동합니다.
1.  왼쪽 메뉴에서 **플랫폼**을 클릭합니다.
2.  **Web** 항목의 **Web 플랫폼 등록**을 클릭합니다.
3.  **사이트 도메인**에 배포된 Vercel 주소(예: `https://mart-flyers.vercel.app`)와 로컬 주소(`http://localhost:8080`)를 모두 입력하고 저장합니다.
    *   줄바꿈으로 여러 개 입력 가능합니다.

## 4. 코드에 키 적용
1.  프로젝트 폴더의 `script.js` 파일을 엽니다.
2.  아래 부분을 찾아 `YOUR_JAVASCRIPT_KEY`를 복사한 키로 바꿔주세요.

```javascript
// script.js 약 130번째 줄
if (!Kakao.isInitialized()) {
    Kakao.init('여기에_복사한_키를_붙여넣으세요'); 
}
```

## 5. 배포
키를 수정한 후 다시 GitHub에 Push하면 적용됩니다.
```bash
git add script.js
git commit -m "Add Kakao API Key"
git push
```
