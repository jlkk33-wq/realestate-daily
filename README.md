# 내 부동산 데일리

장안동 관심 단지(장안힐스테이트·래미안장안2차·장안현대홈타운1차)와 광진구 구의·광장동 전세 실거래를 보는 개인용 웹앱입니다.

- 데이터: 국토교통부 실거래가 공개 API (`scripts/fetch.py`)
- 갱신: GitHub Actions가 매일 06:43(한국시간)에 실행 (`.github/workflows/update.yml`)
- 인증키: 저장소 Settings → Secrets and variables → Actions 의 `DATA_GO_KR_KEY`
- 시장 지표(`data/market.json`)는 아직 수동 갱신입니다.
