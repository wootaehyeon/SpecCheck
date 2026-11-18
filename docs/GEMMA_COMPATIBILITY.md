# Gemma 부품 추천 개선

## 이번에 적용한 내용

추가 사양 데이터를 추천 경로에 연결했다. 사용자 PC와 정확히 일치하는 메인보드 사양을 검색하고, 실제 수집한 RAM 규격과 함께 후보를 검증한 뒤 Gemma에 그 근거와 제품 출처를 전달한다. Gemma 가중치는 아직 변경하지 않았다. 사양 검색·입력 보강과 모델 추가 학습은 구분한다.

현재 구매 추천 범위는 기존과 같은 메모리·저장장치 교체다. CPU 자료는 현재 구성의 소켓 확인에 사용하며 CPU/GPU 구매 추천 범위를 새로 추가한 것은 아니다.

### 데이터 출처

- [TechFuelHQ PC Builder Parts Dataset](https://github.com/iBlessi/pc-builder-parts): 126개 부품, CC BY 4.0. 원본·LICENSE·README를 `datasets/compatibility/techfuelhq/`에 보존했다. 데이터셋 저자의 사양 요약이며 모든 항목을 제조사에서 재검증한 자료라고 표시하지 않는다.
- 개별 출처 URL이 있는 메인보드 11개와 CPU 소켓 24개만 운영용 자료로 정규화했다. 출처 없는 항목, 가격·가성비·성능 등급 같은 편집자 의견과 자유 문장 notes는 운영 입력에서 제외한다.
- ASUS 공식 사양에서 PRIME B760-PLUS D4, PRIME B760-PLUS, TUF GAMING B550-PLUS의 메모리 규격·슬롯·최대 용량을 확인해 추가했다. 총 운영용 메인보드는 14개다. 출처 URL과 확인일은 `datasets/compatibility/manufacturer-boards.json`에 있다.
- 운영 지식 파일의 출처 표기: **TechFuelHQ PC Builder Parts Dataset (CC BY 4.0). https://techfuelhq.com/tools/pc-builder/**. 정규화·필터링·제조사 사양 보완을 수행한 파생 자료다.
- OEM·미등록 보드는 비슷한 모델로 대체 매칭하지 않는다. 예를 들어 B660M HD3P를 B660M DS3H로 바꾸어 조회하지 않는다. 이번에 B660M HD3P의 정확한 제조사 사양 페이지는 확보하지 못했으므로 해당 보드의 최대 용량이나 슬롯 규격을 만들어 넣지 않았다.

### 수집과 검증

Agent가 `Win32_PhysicalMemory.SMBIOSMemoryType`, `FormFactor`, 메모리 배열의 `MaxCapacityEx`를 추가 수집한다. 개인정보 필드는 추가하지 않았다. [Microsoft WMI 문서](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-physicalmemory)를 기준으로 원시 값도 보존한다.

- DDR4/DDR5는 메모리 종류 또는 확인된 보드 사양을 이용한다. 4800MT/s 이상이면 DDR5라고 추정하던 코드를 제거했다.
- DIMM은 물리 형태를 뜻하며 UDIMM/등록 메모리·ECC 지원을 전부 확인했다는 뜻이 아니다. QVL, CPU, BIOS, 혼용 안정성은 별도 확인으로 남긴다.
- 알려진 DDR 세대, DIMM/SODIMM, 전체 슬롯 수, 최대 총 용량과 충돌하는 후보를 제외한다. 보드 사양과 수집 정보가 충돌해도 구매 후보를 내지 않는다.
- 후보 키트 용량은 기존 모듈 교체 기준이다. 추가 장착 시에는 기존 메모리와 합산 용량·혼용 안정성을 확인하라고 표시한다.
- M.2 슬롯 개수만으로 빈 NVMe 슬롯을 보장하지 않는다. SATA/NVMe, 길이, 슬롯 점유·레인 공유 조건을 미확인 항목으로 유지한다.
- 지식 파일 SHA-256이 바뀌면 진단 캐시가 무효화된다. 파일 교체 후 서버를 재시작해야 프로세스 내 자료 캐시가 갱신된다.

### Gemma 응답 처리

Gemma에는 현재 CPU/보드 이름, 후보 규격, 검증 결과, 사양 출처 URL을 전달한다. 긴급 고장을 이유로 고성능·고가 제품을 우선하던 지시를 제거했다. 가격·예산이 없으면 가성비를 단정하지 않도록 했다.

모델은 입력 후보 ID 중에서만 선택한다. 후보의 필수 미확인 항목은 모델이 주의사항에서 누락해도 결과에 다시 포함한다. 조건부 후보에 대한 명시적 완전 호환 보장을 감지하면 기본 설명을 사용한다. 이 검사는 모든 자연어 오류를 잡는다는 보장은 아니다. 선택한 후보가 바뀌면 검색어·검색 링크도 함께 바뀐다.

## 추가 학습용 데이터

`datasets/compatibility/gemma/`에 실제 Gemma 요청·응답 형식의 JSONL을 생성했다.

- 학습용 55개 / 평가용 15개.
- 합성 PC 상태와 기존 검증 로직으로 만든 라벨이다. 전문가가 검토한 실제 사용자 선호·구매 성과 데이터가 아니다.
- 메인보드 계열을 기준으로 분리한다. 같은 보드의 D4/DDR5 변형도 같은 그룹에 묶는다.
- 각 행에 `source_urls`, `group_id`, `label_source`, `human_reviewed: false`를 기록한다.
- `manifest.json`에 사용한 지식·상품 카탈로그 해시와 `weights_trained: false`를 기록한다.
- 15개 평가 자료는 향후 생성 모델을 평가하기 위한 입력이다. 현재 Gemma 품질 점수를 측정한 결과가 아니다. 운영에서 해당 보드의 공개 사양 검색은 허용되므로 지식 자체를 숨긴 평가도 아니다.

현재 환경에서는 `127.0.0.1:11434` Ollama 서비스에 연결되지 않아 실제 Gemma 실행 전후 비교·추가 학습은 수행하지 못했다. RTX 3070 8GB가 확인되었지만 학습 가능한 원본 체크포인트·토크나이저·학습 환경은 별도로 필요하다. Ollama 추론용 모델에 이 JSONL을 넣는 것만으로 가중치가 학습되지는 않는다.

실제 미세조정 전에는 부품 전문가의 정답 검토, 비호환·자료 부족 사례, 사용자 예산·용도, 실제 장착·조치 결과를 보완해야 한다. 기본 모델과 미세조정 모델을 동일한 미사용 보드 평가셋에서 비교하고, 후보 밖 제품 생성·주의사항 누락·잘못된 호환 보장 비율을 측정한 후에 교체한다. [Google의 Gemma 튜닝 안내](https://ai.google.dev/gemma/docs/tune)를 참고한다.

## 재생성 및 적용

프로젝트 루트에서:

```powershell
cd backend
../.venv/Scripts/python.exe -m app.scripts.build_compatibility_knowledge
../.venv/Scripts/python.exe -m app.scripts.build_gemma_recommendation_data
../.venv/Scripts/python.exe -m pytest -q
```

정규화는 포함된 원본 파일로 수행하며 외부 접속이 필요 없다. 자료 변경 시 출처와 라이선스를 유지하고 두 생성 명령을 순서대로 실행한다. 배포 모델·데이터는 기존 Docker의 `backend/app` 및 `datasets` 복사에 포함된다.

서버 재시작 후 개선된 추천 흐름을 이용할 수 있다. 기존 스냅샷에 메모리 종류·형태가 없다면 업데이트한 Agent로 다시 스캔해야 측정값을 사용할 수 있다. Gemma 서비스가 없으면 검증된 후보와 기본 설명을 제공한다.
