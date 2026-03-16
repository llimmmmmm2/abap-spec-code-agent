# CM_ABAP패턴.md
## 실행 가능한 표준 – Screen100 / ALV Grid 중심

Version: 1.0
Owner: KHL
Scope: SAP GUI ABAP Executable Program
연동 문서: CM_스펙템플릿.md

------------------------------------------------------------

## ■ 문서 목적

본 문서는 다음 목적을 가진다.

1. 팀 공통 ABAP 구현 표준을 정의한다.
2. GPT 코드 생성 시 일관된 구조와 구현 방식을 강제한다.

본 문서는 어떻게 구현할 것인가를 정의한다.
무엇을 만들 것인가는 반드시 CM_스펙템플릿.md를 따른다.

------------------------------------------------------------

## ■ 문서 우선순위

개발 및 코드 생성 시 적용 우선순위는 다음과 같다.

1. 20_SPEC (건별 확정 스펙)
2. 10_FI (업무 RULE 문서)
3. 00_CM (공통 구현 표준 문서)

적용 원칙

- 상위 문서와 충돌 시 하위 문서는 무효로 본다.
- 스펙에 명시되지 않은 기능은 구현하지 않는다.
- 업무 RULE에 정의되지 않은 상태, 전표, 외부 연계는 생성하지 않는다.
- 본 문서는 구현 표준 문서이다.

------------------------------------------------------------

## 1. 적용 대상

다음 프로그램을 대상으로 한다.

- ABAP Executable Program (REPORT)
- SAP GUI 기반 프로그램
- Screen 100 + ALV Grid 중심 프로그램
- R / S / P 유형 전체

------------------------------------------------------------

## 2. 프로그램 유형 정의

유형 | 의미 | DB 변경 | 외부 연계
---|---|---|---
R | 조회 전용 | 없음 | 없음
S | 상태 변경 / 저장 | 있음 | 없음
P | 문서 생성 / 외부 연계 | 있음 | 있음

### 2.1 유형별 강제 규칙

#### 2.1.1 R 유형

- UPDATE 금지
- INSERT 금지
- DELETE 금지
- COMMIT WORK 금지
- ENQUEUE 금지

#### 2.1.2 S 유형

- 상태 검증 필수
- 권한 검증 필수
- DB 변경 전 재검증 필수

#### 2.1.3 P 유형

- RETURN TABLE 검사 필수
- 실패 시 ROLLBACK WORK 필수
- 성공 시 생성 Key 메시지 표시 필수

------------------------------------------------------------

## 3. Include 구조 (절대 고정)

Include | 역할
---|---
TOP | Global Data
S01 | Selection Screen
C01 | Local Class
O01 | PBO Modules
I01 | PAI Modules
F01 | FORM Routines

### 3.1 규칙

- Include 순서 변경 금지
- 선언은 TOP에만 작성
- 비즈니스 로직은 F01에 집중

------------------------------------------------------------

## 4. Include별 역할 정의

### 4.1 TOP (Global Data)

- TABLES 선언
- 전역 DATA / TYPE / CONSTANTS 선언
- ALV / Container 객체 선언
- OKCODE 변수 선언 (gv_okcode / gv_save_ok)
- 화면 제어 플래그 선언

#### 4.1.1 핵심 규칙

- S01에서 FOR <table>-<field> 사용 시 해당 테이블은 반드시 TOP에 TABLES 선언한다.
- 상태값 하드코딩을 금지한다. 반드시 CONSTANTS를 사용한다.
- 스펙에 없는 전역 변수는 생성하지 않는다.

### 4.2 S01 (Selection Screen)

- PARAMETERS p_*
- SELECT-OPTIONS s_*
- SELECTION-SCREEN BLOCK 정의

#### 4.2.1 검증 원칙

- 필수값 검증은 AT SELECTION-SCREEN에서 수행한다.
- 스펙에 없는 조회조건은 생성하지 않는다.
- 기본값은 스펙 정의 시에만 설정한다.

### 4.3 Selection Screen 동적 제어 규칙

Selection Screen의 필드 활성/비활성, 숨김/표시는 반드시 다음 패턴을 사용한다.

- AT SELECTION-SCREEN OUTPUT
- LOOP AT SCREEN
- MODIFY SCREEN

#### 4.3.1 필수값 검증 시점

- 필수값 검증은 실행 시점에서만 수행한다.
- 단순 라디오 버튼 전환, 화면 표시 제어, 사용자 입력 보조 단계에서는 필수값 오류를 발생시키지 않는다.

#### 4.3.2 실행 시점 UCOMM 예

- ONLI
- PRIN

### 4.4 C01 (Local Class)

- ALV Event Handler Local Class 정의
- 이벤트 수신만 담당
- 실제 비즈니스 로직은 F01 FORM으로 위임한다.

### 4.5 O01 (PBO)

- Screen 100 PBO 처리
- Container 및 ALV 객체 생성
- Field Catalog / Layout 적용
- PF-STATUS 설정
- 최초 Display 제어

### 4.6 I01 (PAI)

- OKCODE 수신
- 기능 분기
- PERFORM 위임
- OKCODE CLEAR 필수

#### 4.6.1 OKCODE 처리 순서

1. gv_save_ok = gv_okcode
2. CLEAR gv_okcode
3. CASE gv_save_ok
4. 기능 분기 처리

### 4.7 F01 (FORM)

표준 FORM 구성 순서는 다음과 같다.

1. init
2. validate_input
3. get_data
4. build_fieldcat
5. build_layout
6. display_alv
7. handle_user_command
8. status_check
9. authority_check
10. save / post
11. message 처리

#### 4.7.1 분리 원칙

- 입력 검증 / 상태 검증 / 권한 검증은 반드시 별도 FORM으로 분리한다.
- 저장 로직에서는 재검증을 수행한다.
- 우회 저장을 금지한다.

------------------------------------------------------------

## 5. 메인 프로그램 이벤트 흐름

다음 이벤트 흐름을 기본 구조로 사용한다.

1. INITIALIZATION
2. AT SELECTION-SCREEN
3. AT SELECTION-SCREEN OUTPUT
4. START-OF-SELECTION
5. CALL SCREEN 100 (필요 시)

------------------------------------------------------------

## 6. Screen 100 사용 기준

다음 중 하나라도 해당하면 Screen 100을 사용한다.

- 버튼 기능 존재
- 상태 변경 기능 존재
- 편집 ALV 사용
- PAI 분기 필요
- 복수 Grid 구성

------------------------------------------------------------

## 7. ALV Grid 생성 표준

### 7.1 ALV 생성 순서

1. Container 생성
2. ALV 객체 생성
3. Field Catalog 생성
4. Layout 설정
5. 이벤트 등록
6. SET_TABLE_FOR_FIRST_DISPLAY 수행

------------------------------------------------------------

## 8. ALV Event Handler 구현 규칙

### 8.1 Event Handler Class 정의 위치

- Event Handler Local Class는 반드시 C01 Include에 정의한다.
- 클래스명은 LCL_EVENT_HANDLER를 기본 패턴으로 사용한다.

### 8.2 METHOD 선언 규칙

- Event Handler METHOD는 반드시 PUBLIC SECTION에 선언한다.
- Event Handler는 CLASS-METHODS 방식으로 선언한다.
- Event Handler METHOD에서는 직접 비즈니스 로직을 구현하지 않는다.
- 실제 처리 로직은 FORM으로 위임한다.

### 8.3 SET HANDLER 수행 위치

- SET HANDLER는 ALV Grid 객체 생성 이후 수행한다.
- SET HANDLER는 반드시 GO_ALV_GRID->SET_TABLE_FOR_FIRST_DISPLAY 호출 전에 수행한다.
- SET HANDLER는 초기 ALV 출력 처리 블록에서 직접 수행한다.
- SET HANDLER를 FORM REGISTER_EVENT 내부에 포함하지 않는다.

### 8.4 FORM REGISTER_EVENT 역할

- FORM REGISTER_EVENT는 이벤트 핸들러 바인딩을 수행하는 FORM이 아니다.
- FORM REGISTER_EVENT는 ALV의 표시/입력 관련 이벤트 속성 등록을 담당한다.

#### 8.4.1 포함 대상

1. TOP_OF_PAGE 문서 초기화
2. LIST_PROCESSING_EVENTS 등록
3. SET_READY_FOR_INPUT 설정
4. REGISTER_EDIT_EVENT 등록

### 8.5 초기 ALV 출력 순서

1. Field Catalog 구성
2. Layout 설정
3. CELLTAB 구성
4. Toolbar 제외 버튼 구성
5. Icon 값 구성
6. Container / ALV Object 생성
7. SET HANDLER 수행
8. FORM REGISTER_EVENT 수행
9. SET_TABLE_FOR_FIRST_DISPLAY 수행

### 8.6 구현 원칙

- Event Handler METHOD는 이벤트 수신과 FORM 위임만 담당한다.
- 실제 처리 로직은 FORM에서 수행한다.
- Event 바인딩과 Event 속성 등록은 역할을 구분한다.
  - SET HANDLER: 이벤트 핸들러 바인딩
  - REGISTER_EVENT: ALV 이벤트 / 입력 속성 등록

------------------------------------------------------------

## 9. ALV 편집 제어 규칙

### 9.1 컬럼 단위 editable 제어

- 컬럼 단위 editable 제어는 Field Catalog의 EDIT 속성을 사용한다.

### 9.2 셀 단위 editable 제어

- 셀 단위 editable 제어는 CELLTAB STYLE을 사용한다.

### 9.3 S 유형 프로그램 편집 제어 원칙

- S 유형 프로그램에서 수정 가능 여부는 단순 Edit Mode 여부만으로 결정하지 않는다.
- 다음 기준을 조합하여 판단한다.

1. 현재 상태
2. 사용자 역할 또는 권한
3. 기능 수행 모드
4. 필드별 수정 허용 범위

### 9.4 조회용 / 출력용 구조 분리

- DB 조회용 Internal Table은 FLAT 구조로 정의한다.
- ALV 출력용 Internal Table은 CELLTAB 등 DEEP 구조를 포함할 수 있다.
- DB 조회 결과를 ALV 출력 구조로 변환한 후 셀 제어 정보를 구성한다.

------------------------------------------------------------

## 10. ALV Toolbar / PF-STATUS 제어 규칙

툴바 제어 범위는 반드시 SPEC에 정의한다.

### 10.1 제어 대상

- ALV Toolbar
- PF-STATUS
- 둘 다 사용

### 10.2 ALV Toolbar 사용 규칙

- ALV Toolbar 버튼은 toolbar 이벤트에서 추가한다.
- ALV Toolbar 기능은 user_command 이벤트에서 처리한다.
- it_toolbar_excluding은 ALV 표준 버튼 제외 시 사용한다.

### 10.3 PF-STATUS 사용 규칙

- PF-STATUS가 필요한 경우 해당 GUI Status는 사용자가 직접 생성해야 한다.
- GPT는 PF-STATUS 이름과 사용 위치만 코드에 반영한다.
- 실제 GUI Status 객체 자체를 생성한 것으로 간주하지 않는다.
- PF-STATUS 사용 시 BACK / EXIT / CANC 기능 코드는 반드시 GUI Status에 포함되어야 한다.
- 화면 종료 처리는 BACK / EXIT / CANC OKCODE를 기준으로 구현한다.
- 스펙에 PF-STATUS 사용이 정의되지 않은 경우 임의로 적용하지 않는다.

### 10.4 필수 기능 코드

- BACK
- EXIT
- CANC

### 10.5 역할 분리 원칙

- ALV Toolbar와 PF-STATUS를 함께 사용하는 경우 역할을 구분한다.
- PF-STATUS는 화면 공통 기능을 담당한다.
- ALV Toolbar는 ALV 행 / 데이터 처리 기능을 담당한다.
- 스펙에 없는 버튼, 메뉴, 기능코드는 임의로 추가하지 않는다.

------------------------------------------------------------

## 11. 상태 기반 처리 표준

상태 변경 시 반드시 다음 순서를 따른다.

1. 대상 존재 확인
2. 현재 상태 확인
3. 허용된 전이인지 확인
4. 권한 확인
5. 저장 처리
6. 메시지 출력

------------------------------------------------------------

## 12. SELECT / 성능 표준

### 12.1 금지 규칙

- SELECT * 금지
- LOOP 안 SELECT 금지
- INITIAL ITAB에서 FOR ALL ENTRIES 사용 금지

### 12.2 필수 규칙

- 필요한 컬럼만 조회한다.
- WHERE 조건을 명확히 작성한다.
- 대량 처리 시 성능을 고려한다.

### 12.3 New Open SQL 작성 규칙

- Open SQL은 반드시 New Open SQL 기준으로 작성한다.
- SQL 구문 내 ABAP Host Variable 앞에는 반드시 @를 사용한다.

#### 12.3.1 적용 대상

- PARAMETERS
- SELECT-OPTIONS
- DATA 변수
- 내부 테이블
- Work Area
- Structure
- CONSTANTS

#### 12.3.2 적용 위치

- INTO
- APPENDING
- WHERE
- SET
- VALUES
- FROM @itab
- 기타 Open SQL 구문 내 ABAP 영역 참조부 전체

### 12.4 SELECT 대상 구조 규칙

- Open SQL의 SELECT INTO 대상 구조는 반드시 FLAT STRUCTURE여야 한다.
- DEEP TYPE이 포함된 구조는 SELECT INTO 대상 구조로 사용할 수 없다.

#### 12.4.1 금지 대상

- Internal Table
- STRING
- XSTRING
- Reference Type
- Deep Structure 포함 구조

#### 12.4.2 금지 예

TYPES: BEGIN OF ty_main,
         bukrs   TYPE bukrs,
         belnr   TYPE belnr_d,
         celltab TYPE lvc_t_styl,
       END OF ty_main.

SELECT ...
  INTO TABLE @gt_main.

#### 12.4.3 구현 원칙

- DB 조회용 구조와 ALV 출력용 구조는 반드시 분리한다.
- DB 조회용 구조는 FLAT 구조를 사용한다.
- ALV 출력용 구조는 필요 시 DEEP 구조를 사용할 수 있다.

예:
- GT_MAIN_DB -> DB 조회용 (FLAT)
- GT_MAIN -> ALV 출력용 (DEEP)

------------------------------------------------------------

## 13. DB 처리 표준

DB 처리 시 반드시 다음 순서를 따른다.

1. 대상 존재 확인
2. 상태 가능 여부 확인
3. 권한 확인
4. ENQUEUE 수행 (필요 시)
5. DB 처리
6. 성공 시 COMMIT WORK
7. 실패 시 ROLLBACK WORK
8. ALV Refresh

------------------------------------------------------------

## 14. 메시지 표준

TYPE | 의미
---|---
S | 성공
E | 오류
W | 경고
I | 안내

### 14.1 메시지 원칙

- 실패 원인을 명확히 표시한다.
- 사용자 조치 문구를 포함한다.
- 침묵 실패를 금지한다.

------------------------------------------------------------

## 15. 스펙 매핑 규칙 (필수)

모든 주요 FORM 상단에는 반드시 스펙 ID를 명시한다.

예:

* Spec Mapping: F-001, S-001, A-001

------------------------------------------------------------

## 16. 금지 규칙 (팀 공통)

- 스펙 없이 기능 변경 금지
- RULE 없는 상태 생성 금지
- LOOP 안 SELECT 금지
- COMMIT 없는 DB 변경 금지
- INITIAL ITAB에서 FAE 금지
- 존재하지 않는 DDIC / 테이블 추정 생성 금지
- 스펙 없는 전표 / BAPI / RFC 생성 금지
- "...", "생략" 표현 금지

------------------------------------------------------------

## 17. GPT 코드 생성 체크리스트

- INCLUDE 구조 준수
- OKCODE CLEAR 처리
- 상태 검증 / 권한 검증 분리
- DB 처리 전 재검증
- 스펙 매핑 주석 존재
- 유형별 강제 규칙 준수
- 금지 규칙 위반 없음
- Selection Screen 동적 제어는 AT SELECTION-SCREEN OUTPUT 패턴 준수