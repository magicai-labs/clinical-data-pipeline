# PubChem 클라이언트

모듈: `src/clinpipe/pubchem/`

이 패키지는 PubChem API를 감싸서 다음 기능을 제공합니다:

- 기본 화합물 조회
- 분류 노드(HNID)
- 임상시험 관련 PUG-View 주석
- REST payload에 NCT ID가 없을 때의 웹 fallback 조회

## PubChemClient

모듈: `src/clinpipe/pubchem/client.py`

메서드:

- `cids_by_name(name) -> List[int]`
- `compound_properties(cid) -> Dict`
  - `CanonicalSMILES`
  - `InChIKey`
  - `IUPACName`
- `synonyms(cid, max_items=50) -> List[str]`

## PubChemClassificationClient

모듈: `src/clinpipe/pubchem/classification_nodes.py`

메서드:

- `get_ids(hnid, id_type="cids", fmt="TXT") -> List[int]`
- `get_cids(hnid, fmt="TXT") -> List[int]`

HNID 헬퍼:

모듈: `src/clinpipe/pubchem/clinical_trials_nodes.py`

- `download_clinical_trials_cids(out_dir="out_hnid", include_sources=True)`
  - 반환 dict 키: `clinical_trials`, `clinicaltrials_gov`, `eu_register`, `japan_niph`

## PubChemPugViewClient

모듈: `src/clinpipe/pubchem/pug_view.py`

메서드:

- `get_compound_record(cid) -> JSON`
- `nct_ids_for_cid(cid) -> List[str]`

PUG-View JSON payload에서 URL/텍스트 스캔으로 NCT ID를 추출합니다.

fallback 순서(PUG-View 기본 payload가 비어 있을 때):

1. heading 기반 PUG-View 조회 (clinical trials / drug and medication 섹션 포함)
2. PubChem web clinicaltrials endpoint fallback (`/sdq/sphinxql.cgi`)
3. PubChem compound HTML fallback

source 경로까지 함께 가져오는 메서드:

- `nct_ids_for_cid_with_source(cid) -> (List[str], str)`

## PubChemWebFallbackClient

모듈: `src/clinpipe/pubchem/web_fallback/`

메서드:

- `get_sdq_payload(cid, collection="clinicaltrials", limit=200, order=None) -> Dict`
- `get_clinicaltrials_sdq_payload(cid) -> Dict`
- `get_eu_register_sdq_payload(cid) -> Dict`
- `get_japan_niph_sdq_payload(cid) -> Dict`
- `get_normalized_trials(cid, collection="clinicaltrials", limit=200) -> List[Dict]`
- `get_normalized_trials_union(cid, collections=(...), limit_per_collection=200) -> (List[Dict], List[str])`
- `get_compound_page_html(cid) -> str`
- `nct_ids_for_cid_with_source(cid) -> (List[str], str)`
- `nct_ids_for_cid(cid) -> List[str]`

이 클라이언트는 특정 CID에서 REST 응답이 불완전할 때 fallback 레이어로 사용합니다.

## 워크플로 실행 메트릭

전체 및 증분 수집 워크플로는 데이터 무변경이나 실행 실패를 포함해 매 실행마다 `run_metrics.json`을 작성합니다. 운영 관측 기록이 스냅샷 커밋을 만들거나 소스/데이터 이력을 부풀리지 않도록 메트릭은 `main`과 분리합니다. `metrics` 브랜치에는 간단한 README와 `runs/YYYY/MM/{mode}_{run_id}_{run_attempt}.json` 형식의 실행별 파일만 저장합니다.

각 파일에는 워크플로 식별자와 시간, 실행 파라미터, 샤드/CID 수, 스캔·신규·변경·무변경·오류 행 수, 실행 전후 체크섬, 최종 파일 크기와 행 수, 데이터/히스토리 변경 여부, 정리된 스냅샷 수, 변경 asset과 경고가 기록됩니다. 알 수 없는 숫자는 0이 아니라 `null`입니다. 같은 파일은 워크플로 실행 화면의 Artifacts에서 90일 동안 `run-metrics-{mode}-{run_id}-{run_attempt}` 이름으로 받을 수 있습니다.

무변경 실행도 metrics 브랜치에는 기록되지만 `main`의 데이터 스냅샷은 계속 내용이 변경된 경우에만 커밋됩니다. 논문 분석의 재현성을 위해 이 파일들을 집계하기 전에 관찰 시작일과 종료일을 고정하고 보고해야 합니다.

정규화된 trial row 공통 스키마:
- `collection` (사람이 읽기 쉬운 원천 이름)
- `collection_code` (원본 SDQ collection 코드)
- `id` (`ctid` 또는 `eudractnumber`)
- `date` (`date` 또는 `updatedate`를 `date`로 통합)
- `title`
- `phase`
- `status`
- `id_url` (원천 trial 하이퍼링크)
- `cids`

합집합 스키마 모드:
- ctgov/eu/jp 컬렉션 row를 함께 병합
- 공통 키와 컬렉션별 키를 모두 유지
- 모든 row에 동일 키가 있도록 정렬(없는 값은 `None`)

## 예시

CID 및 동의어 조회:

```python
from clinpipe.pubchem import PubChemClient

pub = PubChemClient()
cids = pub.cids_by_name("aspirin")
props = pub.compound_properties(cids[0])
syms = pub.synonyms(cids[0], max_items=20)
```

PUG-View로 NCT ID 조회:

```python
from clinpipe.pubchem import PubChemPugViewClient

pv = PubChemPugViewClient()
print(pv.nct_ids_for_cid(2244))
```
