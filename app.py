import os
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st
import google.generativeai as genai


# =========================
# 기본 설정
# =========================
st.set_page_config(
    page_title="ABAP Spec/Code 생성 에이전트_TEST",
    layout="wide"
)

GEMINI_MODEL_OPTIONS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash"
]
RULE_VERSION = "v1.7"
DB_FILE = "builder_logs.db"
RULES_DIR = "rules"


# =========================
# API 키 확인
# =========================
gemini_api_key = os.getenv("GEMINI_API_KEY")

if not gemini_api_key:
    st.error("GEMINI_API_KEY가 설정되어 있지 않습니다.")
    st.stop()

genai.configure(api_key=gemini_api_key)


# =========================
# DB 초기화
# =========================
def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        user_name TEXT,
        user_id TEXT,
        gemini_model_name TEXT,
        mode TEXT,
        requirement TEXT,
        structure_text TEXT,
        supplement_text TEXT,
        table_image_names TEXT,
        table_excel_names TEXT,
        function_image_names TEXT,
        spec_draft TEXT,
        spec_final TEXT,
        structured_spec TEXT,
        code TEXT,
        spec_feedback TEXT,
        code_feedback TEXT,
        rule_version TEXT,
        spec_confirmed TEXT
    )
    """)
    conn.commit()
    return conn


conn = init_db()


# =========================
# 파일 로드
# =========================
def load_text_file(path: str, fallback: str = "") -> str:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return fallback


spec_template_path = os.path.join(RULES_DIR, "CM_스펙템플릿.md")
abap_pattern_path = os.path.join(RULES_DIR, "CM_ABAP패턴.md")

spec_template_doc = load_text_file(spec_template_path, fallback="SPEC 템플릿 문서 없음")
abap_pattern_doc = load_text_file(abap_pattern_path, fallback="ABAP 패턴 문서 없음")


# =========================
# 시스템 규칙
# =========================
BASE_RULES = """
너는 우리 팀의 SAP FI ABAP 표준 개발 GPT다.

목표:
- 사용자의 요구사항을 구조화하여 표준 SPEC(설계서)로 정리한다.
- 확정된 SPEC을 기준으로 CODE / TEST / DEBUG 산출물을 생성한다.

공통 규칙:
1. 항상 한국어로 설명한다.
2. ABAP 코드는 원문 그대로 작성한다.
3. SPEC에 없는 기능은 생성하지 않는다.
4. SPEC에 정의되지 않은 테이블 / 필드 / Function 생성 금지
5. 추정 구현 대신 TBD 또는 TODO로 표시
6. "생략", "...", "필요시 구현" 표현 금지
7. 정의되지 않은 것은 기본적으로 금지로 본다.
8. 모든 산출물 끝에는 반드시 다음을 포함한다.
   - 참조 기준 문서
   - 가정사항 또는 TBD
   - Out of Scope
"""

SPEC_MODE_RULES = """
현재 모드는 [SPEC] 이다.

SPEC 작성 규칙:
- CM_스펙템플릿.md 구조를 따른다.
- 요구사항을 구조화한다.
- 설명된 행위를 기능(F-xxx)으로 변환
- 사용자 역할을 권한(A-xxx)으로 변환
- 제공되지 않은 테이블/필드/Function 추정 생성 금지
- 미확정 항목은 TBD 표시
- 초안 말미에 확정 필요 항목 제시
- 이 단계에서는 CODE 생성 금지

CBO / Z 객체 구조 규칙:
- Z 테이블, Z 구조, Z View는 사용자가 제공한 구조 정보만 기준으로 사용한다.
- 이미지/텍스트/엑셀로 제공되지 않은 필드는 추정하지 않는다.
- 구조 정보가 부족하면 TBD 또는 확인 필요로 표시한다.

반드시 첫 줄에 [MODE: SPEC] 표시
"""

FINAL_SPEC_RULES = """
현재 작업은 SPEC 확정 단계이다.

규칙:
- 기존 초안 SPEC을 유지하되 사용자 보완 입력을 반영한다.
- 보완된 항목은 더 이상 TBD로 남기지 않는다.
- 최종 SPEC 형태로 재정리한다.
- 첫 줄은 반드시 [MODE: SPEC]
- 문서 상태는 확정으로 반영한다.
"""

STRUCTURED_SPEC_RULES = """
SPEC 확정 이후 Structured Spec을 생성한다.

출력 형식:
[STRUCTURED_SPEC]

program
id
name
type
module

data_source
main_table
primary_key

selection_screen
parameters
select_options

output
alv_used
container_type
columns
editable_columns

functions
status_rules
authority_rules
validation_rules
out_of_scope
"""

CODE_MODE_RULES = """
현재 모드는 [CODE] 이다.

CODE 생성 규칙:
- 확정된 SPEC 또는 STRUCTURED_SPEC 기준으로만 생성
- INCLUDE 구조는 TOP, S01, C01, O01, I01, F01 순서 고정
- ALV는 CL_GUI_ALV_GRID 사용
- SALV 사용 금지
- 기능 정의 F-xxx → FORM 구현
- 상태 정의 S-xxx → status_check 로직
- 권한 정의 A-xxx → authority_check 로직
- 입력 검증, OKCODE 처리, 상태 전이 검증, 권한 검증, 저장 전 재검증 포함
- 스펙 없는 DB UPDATE/DELETE/INSERT/COMMIT/FUNCTION 생성 금지
- 제공되지 않은 FM 파라미터는 추정하지 않는다.

반드시 첫 줄에 [MODE: CODE] 표시
"""


# =========================
# Gemini 호출
# =========================
def ask_gemini_text_only(prompt: str, gemini_model_name: str) -> str:
    model = genai.GenerativeModel(gemini_model_name)
    response = model.generate_content(prompt)
    return response.text


def ask_gemini_with_upload_summary(prompt: str, gemini_model_name: str) -> str:
    note = """
[참고]
현재 업로드된 이미지/파일은 개수와 사용자 입력 설명 중심으로 반영한다.
이미지 원문 판독 결과를 절대 단정하지 말고, 사용자가 제공한 텍스트와 함께 보수적으로 해석한다.
"""
    return ask_gemini_text_only(note + "\n" + prompt, gemini_model_name)


# =========================
# 생성 함수
# =========================
def generate_spec_draft(
    requirement: str,
    structure_text: str,
    gemini_model_name: str,
    table_images=None,
    table_files=None
) -> str:
    structure_summary = f"""
[사용자 제공 구조 정보 - 텍스트]
{structure_text if structure_text.strip() else "없음"}

[사용자 제공 테이블/구조 캡처]
- 업로드 이미지 수: {len(table_images) if table_images else 0}

[사용자 제공 테이블/구조 파일]
- 업로드 파일 수: {len(table_files) if table_files else 0}
"""

    prompt = f"""
{BASE_RULES}

{SPEC_MODE_RULES}

[참조 문서: CM_스펙템플릿.md]
{spec_template_doc}

[사용자 요구사항]
{requirement}

{structure_summary}

지시사항:
- CM_스펙템플릿.md 구조를 최대한 유지하여 작성
- 초안 SPEC으로 작성
- 업로드된 테이블/구조 캡처와 파일 정보를 우선 사용
- 사용자가 명시하지 않은 DDIC/Z 객체 구조는 추정하지 말 것
- 구조 정보가 불충분하면 TBD 또는 확인 필요로 명시
- 확정 필요 항목을 마지막에 반드시 정리할 것
"""
    return ask_gemini_with_upload_summary(prompt, gemini_model_name)


def generate_final_spec(spec_draft: str, supplement_text: str, gemini_model_name: str) -> str:
    prompt = f"""
{BASE_RULES}

{FINAL_SPEC_RULES}

[참조 문서: CM_스펙템플릿.md]
{spec_template_doc}

[기존 초안 SPEC]
{spec_draft}

[사용자 보완 입력]
{supplement_text}

지시사항:
- 기존 SPEC 초안을 유지하되 사용자 보완 입력을 반영하여 업데이트하라
- 확정된 항목은 TBD로 남기지 말 것
- 최종 SPEC 형태로 재정리하라
"""
    return ask_gemini_text_only(prompt, gemini_model_name)


def generate_structured_spec(spec_text: str, gemini_model_name: str) -> str:
    prompt = f"""
{BASE_RULES}

{STRUCTURED_SPEC_RULES}

[입력 SPEC]
{spec_text}
"""
    return ask_gemini_text_only(prompt, gemini_model_name)


def generate_code(
    spec_text: str,
    structured_spec_text: str,
    gemini_model_name: str,
    function_images=None
) -> str:
    function_summary = f"""
[사용자 제공 Function Module 캡처]
- 업로드 이미지 수: {len(function_images) if function_images else 0}
"""

    prompt = f"""
{BASE_RULES}

{CODE_MODE_RULES}

[참조 문서: CM_ABAP패턴.md]
{abap_pattern_doc}

[확정 SPEC]
{spec_text}

[STRUCTURED_SPEC]
{structured_spec_text}

{function_summary}

지시사항:
- ABAP REPORT 프로그램 코드 초안 작성
- INCLUDE 구조 포함
- 업로드된 함수 캡처 정보가 있으면 그 인터페이스 기준으로 작성
- 제공되지 않은 Function 인터페이스는 추정하지 말 것
- 스펙 없는 기능은 절대 추가하지 말 것
"""
    return ask_gemini_with_upload_summary(prompt, gemini_model_name)


# =========================
# 로그 저장
# =========================
def save_log(
    user_name: str,
    user_id: str,
    gemini_model_name: str,
    mode: str,
    requirement: str,
    structure_text: str,
    supplement_text: str,
    table_image_names: str,
    table_excel_names: str,
    function_image_names: str,
    spec_draft: str,
    spec_final: str,
    structured_spec: str,
    code: str,
    spec_feedback: str,
    code_feedback: str,
    rule_version: str,
    spec_confirmed: str
):
    conn.execute("""
    INSERT INTO logs (
        created_at, user_name, user_id, gemini_model_name, mode,
        requirement, structure_text, supplement_text, table_image_names, table_excel_names, function_image_names,
        spec_draft, spec_final, structured_spec, code,
        spec_feedback, code_feedback, rule_version, spec_confirmed
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_name,
        user_id,
        gemini_model_name,
        mode,
        requirement,
        structure_text,
        supplement_text,
        table_image_names,
        table_excel_names,
        function_image_names,
        spec_draft,
        spec_final,
        structured_spec,
        code,
        spec_feedback,
        code_feedback,
        rule_version,
        spec_confirmed
    ))
    conn.commit()


def load_logs() -> pd.DataFrame:
    return pd.read_sql_query("""
        SELECT id, created_at, user_name, user_id, gemini_model_name, mode, rule_version, spec_confirmed
        FROM logs
        ORDER BY id DESC
    """, conn)


# =========================
# 세션 상태
# =========================
defaults = {
    "page_mode": "input",
    "spec_draft": "",
    "spec_final": "",
    "structured_spec": "",
    "code": "",
    "spec_confirmed": False,
    "requirement_text": "",
    "structure_text_saved": "",
    "supplement_text": "",
    "table_image_names": "",
    "table_excel_names": "",
    "function_image_names": "",
    "spec_feedback": "",
    "code_feedback": ""
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# =========================
# 범위 정의 옵션
# =========================
IN_SCOPE_OPTIONS = [
    "조회 기능", "신규 등록", "수정 기능", "삭제 기능",
    "상태 변경", "엑셀 업로드", "엑셀 다운로드", "ALV 조회",
    "승인 처리", "종결 처리"
]

OUT_OF_SCOPE_OPTIONS = [
    "전표 생성 제외", "BAPI/RFC 제외", "외부 시스템 연계 제외",
    "배치 처리 제외", "인터페이스 처리 제외", "첨부파일 기능 제외", "메일 발송 제외"
]


# =========================
# 조합 함수
# =========================
def build_scope_text(selected_items, etc_text):
    result = []
    if selected_items:
        result.extend(selected_items)
    if etc_text.strip():
        result.append(f"기타: {etc_text.strip()}")
    return ", ".join(result) if result else "없음"


def build_requirement_text(
    program_id, program_name, module, program_type,
    purpose, process_desc, main_functions,
    main_table, primary_key, field_list,
    selection_screen, output_columns, buttons, editable_columns,
    status_rules, authority_rules,
    in_scope, out_scope
):
    return f"""
[기본 정보]
- 프로그램 ID: {program_id}
- 프로그램명: {program_name}
- 업무 영역: {module}
- 프로그램 유형: {program_type}

[업무 개요]
- 프로그램 목적: {purpose}
- 업무 프로세스 설명: {process_desc}
- 주요 기능: {main_functions}

[데이터 정의]
- 대상 테이블: {main_table}
- Primary Key: {primary_key}
- 사용 필드 목록: {field_list}

[화면 구성]
- Selection Screen 항목: {selection_screen}
- 결과 화면 컬럼(ALV 출력 컬럼): {output_columns}
- 버튼 목록: {buttons}
- 편집 가능 컬럼: {editable_columns}

[상태 / 권한]
- 상태 정의: {status_rules}
- 권한 정의: {authority_rules}

[범위 정의]
- In Scope: {in_scope}
- Out of Scope: {out_scope}
"""


def build_supplement_text(
    confirm_program_type,
    confirm_main_table,
    confirm_primary_key,
    confirm_fields,
    confirm_db_change,
    confirm_status,
    confirm_authority,
    confirm_out_scope
):
    return f"""
[미확정 항목 보완]
- 프로그램 유형 확정: {confirm_program_type}
- 대상 테이블 확정: {confirm_main_table}
- Primary Key 확정: {confirm_primary_key}
- 사용 필드 목록 확정: {confirm_fields}
- DB 변경 여부: {confirm_db_change}
- 상태 정의 확정: {confirm_status}
- 권한 정의 확정: {confirm_authority}
- Out of Scope 확정: {confirm_out_scope}
"""


# =========================
# 헤더
# =========================
st.title("ABAP Spec/Code 생성 에이전트_TEST")
st.caption("SAP FI ABAP SPEC / CODE 생성 도구")

with st.sidebar:
    st.subheader("사용자 정보")
    user_name = st.text_input("사용자 이름", placeholder="예: 김효림")
    user_id = st.text_input("사번", placeholder="예: 2201003")

    gemini_model_name = st.selectbox(
        "Gemini 모델 선택",
        GEMINI_MODEL_OPTIONS,
        index=0
    )

    st.markdown(f"**지침 버전:** {RULE_VERSION}")
    st.markdown(f"**Gemini 모델:** {gemini_model_name}")
    st.markdown(f"**SPEC 템플릿 파일:** {'정상 로드' if spec_template_doc != 'SPEC 템플릿 문서 없음' else '미로드'}")
    st.markdown(f"**ABAP 패턴 파일:** {'정상 로드' if abap_pattern_doc != 'ABAP 패턴 문서 없음' else '미로드'}")
    st.info("현재 Gemini 기반으로 동작합니다.")

st.markdown("### 진행 단계")
c1, c2, c3, c4, c5 = st.columns(5)
c1.info("1. 요구사항 입력")
c2.success("2. SPEC 초안 생성 완료" if st.session_state.spec_draft else "2. SPEC 초안 생성 대기")
c3.success("3. 최종 SPEC 확정 완료" if st.session_state.spec_final else "3. 최종 SPEC 확정 대기")
c4.success("4. Structured Spec 완료" if st.session_state.structured_spec else "4. Structured Spec 대기")
c5.success("5. CODE 생성 완료" if st.session_state.code else "5. CODE 생성 대기")


# =========================
# PAGE 1: 입력
# =========================
if st.session_state.page_mode == "input":
    st.subheader("STEP 1. 요구사항 입력")

    with st.expander("1) 기본 정보", expanded=True):
        program_id = st.text_input("프로그램 ID", placeholder="예: ZNFIR0240")
        program_name = st.text_input("프로그램명", placeholder="예: 기존 유보금 관리(승인)")
        module = st.text_input("업무 영역", value="FI")
        program_type = st.selectbox("프로그램 유형", ["R", "S", "P"])

    with st.expander("2) 업무 개요", expanded=True):
        purpose = st.text_area(
            "프로그램 목적",
            height=90,
            placeholder="예: 기존 유보금 데이터를 조회하고, 진행상태에 따라 등록확인 및 종결승인을 처리하기 위한 프로그램"
        )
        process_desc = st.text_area(
            "업무 프로세스 설명",
            height=130,
            placeholder="예: 담당자가 유보금 데이터를 등록하면 승인자가 등록확인을 수행하고, 이후 종결요청 건에 대해 종결승인을 진행한다."
        )
        main_functions = st.text_area(
            "주요 기능",
            height=100,
            placeholder="예: 조회, 엑셀 업로드, 등록확인, 등록확인취소, 종결승인, 종결승인취소"
        )

    with st.expander("3) 데이터 정의", expanded=True):
        main_table = st.text_input("대상 테이블", placeholder="예: ZNFIT0530")
        primary_key = st.text_input("Primary Key", placeholder="예: BUKRS, RSRVNO")
        field_list = st.text_area("사용 필드 목록", height=100, placeholder="예: BUKRS, RSRVNO, STATUS, KUNNR, CFAMT")

        st.markdown("##### 테이블 / 구조 정보 업로드")
        structure_text = st.text_area("필드 목록 입력", height=140, placeholder="예:\nFIELDNAME | TYPE | KEY | 설명")
        table_images = st.file_uploader(
            "SE11 / 구조 캡처 업로드",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="table_images"
        )
        table_files = st.file_uploader(
            "필드 목록 Excel / CSV 업로드",
            type=["xlsx", "xls", "csv"],
            accept_multiple_files=True,
            key="table_files"
        )

    with st.expander("4) 화면 구성", expanded=False):
        selection_screen = st.text_area("Selection Screen 항목", height=100, placeholder="예: 회사코드, 진행상태, 사원번호, 영업팀")
        output_columns = st.text_area("결과 화면 컬럼 (ALV 출력 컬럼)", height=100, placeholder="예: 회사코드, 유보번호, 고객코드, 고객명, 유보금액, 진행상태, 메시지")
        buttons = st.text_area("버튼 목록", height=80, placeholder="예: 조회, 엑셀업로드, 등록확인, 등록확인취소, 종결승인")
        editable_columns = st.text_area("편집 가능 컬럼", height=80, placeholder="예: 작성중 상태에서만 비고, 유보율 수정 가능")

    with st.expander("5) 상태 / 권한", expanded=False):
        status_rules = st.text_area("상태 정의", height=100, placeholder="예: 작성중, 등록확인대기, 등록확인완료, 종결승인대기, 종결승인완료")
        authority_rules = st.text_area("권한 정의", height=100, placeholder="예: 담당자는 본인 데이터만 작성/조회 가능, 승인자는 본인 팀 데이터 승인 가능")

    with st.expander("6) 범위 정의", expanded=False):
        in_scope_selected = st.multiselect("In Scope 선택", IN_SCOPE_OPTIONS)
        in_scope_etc = st.text_input("In Scope 기타 직접 입력", placeholder="예: 승인이력 조회")
        out_scope_selected = st.multiselect("Out of Scope 선택", OUT_OF_SCOPE_OPTIONS)
        out_scope_etc = st.text_input("Out of Scope 기타 직접 입력", placeholder="예: 첨부파일 저장 기능 제외")

    in_scope_text = build_scope_text(in_scope_selected, in_scope_etc)
    out_scope_text = build_scope_text(out_scope_selected, out_scope_etc)

    requirement_text = build_requirement_text(
        program_id, program_name, module, program_type,
        purpose, process_desc, main_functions,
        main_table, primary_key, field_list,
        selection_screen, output_columns, buttons, editable_columns,
        status_rules, authority_rules,
        in_scope_text, out_scope_text
    )

    if st.button("SPEC 초안 생성", use_container_width=True):
        if not user_name or not user_id:
            st.warning("사용자 이름과 사번을 입력하세요.")
        elif not program_name or not purpose:
            st.warning("최소한 프로그램명과 프로그램 목적은 입력하세요.")
        else:
            with st.spinner("SPEC 초안 생성 중..."):
                st.session_state.requirement_text = requirement_text
                st.session_state.structure_text_saved = structure_text
                st.session_state.table_image_names = ", ".join([f.name for f in table_images]) if table_images else ""
                st.session_state.table_excel_names = ", ".join([f.name for f in table_files]) if table_files else ""

                st.session_state.spec_draft = generate_spec_draft(
                    requirement=requirement_text,
                    structure_text=structure_text,
                    gemini_model_name=gemini_model_name,
                    table_images=table_images,
                    table_files=table_files
                )
                st.session_state.spec_final = ""
                st.session_state.spec_confirmed = False
                st.session_state.structured_spec = ""
                st.session_state.code = ""
                st.session_state.page_mode = "spec_review"
                st.rerun()


# =========================
# PAGE 2: SPEC 검토/보완
# =========================
elif st.session_state.page_mode == "spec_review":
    st.subheader("STEP 2. SPEC 초안 검토")

    st.markdown(st.session_state.spec_draft)

    st.divider()
    st.subheader("STEP 3. 미확정 항목 보완 입력")

    confirm_program_type = st.selectbox("프로그램 유형 확정", ["R", "S", "P"])
    confirm_main_table = st.text_input("대상 테이블 확정")
    confirm_primary_key = st.text_input("Primary Key 확정")
    confirm_fields = st.text_area("사용 필드 목록 확정", height=100)
    confirm_db_change = st.selectbox("DB 변경 여부", ["Y", "N"])
    confirm_status = st.text_area("상태 정의 확정", height=100)
    confirm_authority = st.text_area("권한 정의 확정", height=100)
    confirm_out_scope = st.text_area("Out of Scope 확정", height=100)

    supplement_text = build_supplement_text(
        confirm_program_type,
        confirm_main_table,
        confirm_primary_key,
        confirm_fields,
        confirm_db_change,
        confirm_status,
        confirm_authority,
        confirm_out_scope
    )

    b1, b2 = st.columns(2)

    if b1.button("요구사항 다시 수정", use_container_width=True):
        st.session_state.page_mode = "input"
        st.rerun()

    if b2.button("보완 반영하여 최종 SPEC 생성", use_container_width=True):
        with st.spinner("최종 SPEC 생성 중..."):
            st.session_state.supplement_text = supplement_text
            st.session_state.spec_final = generate_final_spec(
                st.session_state.spec_draft,
                supplement_text,
                gemini_model_name=gemini_model_name
            )
            st.session_state.page_mode = "spec_final"
            st.rerun()


# =========================
# PAGE 3: 최종 SPEC 확정/다운로드
# =========================
elif st.session_state.page_mode == "spec_final":
    st.subheader("STEP 4. 최종 SPEC 확인")

    st.markdown(st.session_state.spec_final)

    st.download_button(
        label="최종 SPEC 다운로드",
        data=st.session_state.spec_final,
        file_name="SPEC_FINAL.md",
        mime="text/markdown",
        use_container_width=True
    )

    st.divider()
    st.checkbox("최종 SPEC를 확정합니다.", key="spec_confirmed")

    st.subheader("SPEC 피드백")
    st.session_state.spec_feedback = st.text_area(
        "최종 SPEC에 대한 피드백",
        height=100,
        value=st.session_state.get("spec_feedback", "")
    )

    b1, b2 = st.columns(2)

    if b1.button("보완 단계로 돌아가기", use_container_width=True):
        st.session_state.page_mode = "spec_review"
        st.rerun()

    if b2.button("Structured Spec 생성", use_container_width=True):
        if not st.session_state.spec_confirmed:
            st.warning("최종 SPEC를 먼저 확정하세요.")
        else:
            with st.spinner("Structured Spec 생성 중..."):
                st.session_state.structured_spec = generate_structured_spec(
                    st.session_state.spec_final,
                    gemini_model_name=gemini_model_name
                )
                st.session_state.page_mode = "code_result"
                st.rerun()


# =========================
# PAGE 4: CODE 생성/다운로드
# =========================
elif st.session_state.page_mode == "code_result":
    st.subheader("STEP 5. CODE 생성")

    with st.expander("Structured Spec", expanded=True):
        st.code(st.session_state.structured_spec, language="yaml")

    with st.expander("Function / 인터페이스 캡처 업로드", expanded=True):
        function_images = st.file_uploader(
            "Function Module / 인터페이스 캡처 업로드",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="function_images"
        )

    if st.button("CODE 생성", use_container_width=True):
        with st.spinner("CODE 생성 중..."):
            st.session_state.function_image_names = ", ".join([f.name for f in function_images]) if function_images else ""
            st.session_state.code = generate_code(
                st.session_state.spec_final,
                st.session_state.structured_spec,
                gemini_model_name=gemini_model_name,
                function_images=function_images
            )
            st.rerun()

    if st.session_state.code:
        st.divider()
        st.subheader("CODE 결과")
        st.code(st.session_state.code, language="abap")

        st.download_button(
            label="CODE 다운로드",
            data=st.session_state.code,
            file_name="ABAP_CODE.txt",
            mime="text/plain",
            use_container_width=True
        )

    st.divider()
    st.subheader("CODE 피드백")
    st.session_state.code_feedback = st.text_area(
        "생성된 CODE에 대한 피드백",
        height=120,
        value=st.session_state.get("code_feedback", "")
    )

    c_back, c_save = st.columns(2)

    if c_back.button("최종 SPEC 화면으로 돌아가기", use_container_width=True):
        st.session_state.page_mode = "spec_final"
        st.rerun()

    if c_save.button("로그 저장", use_container_width=True):
        if not user_name or not user_id:
            st.warning("사용자 이름과 사번을 입력하세요.")
        else:
            save_log(
                user_name=user_name,
                user_id=user_id,
                gemini_model_name=gemini_model_name,
                mode="CODE" if st.session_state.code else "STRUCTURED_SPEC",
                requirement=st.session_state.get("requirement_text", ""),
                structure_text=st.session_state.get("structure_text_saved", ""),
                supplement_text=st.session_state.get("supplement_text", ""),
                table_image_names=st.session_state.get("table_image_names", ""),
                table_excel_names=st.session_state.get("table_excel_names", ""),
                function_image_names=st.session_state.get("function_image_names", ""),
                spec_draft=st.session_state.spec_draft,
                spec_final=st.session_state.spec_final,
                structured_spec=st.session_state.structured_spec,
                code=st.session_state.code,
                spec_feedback=st.session_state.get("spec_feedback", ""),
                code_feedback=st.session_state.get("code_feedback", ""),
                rule_version=RULE_VERSION,
                spec_confirmed="Y" if st.session_state.spec_confirmed else "N"
            )
            st.success("로그가 저장되었습니다.")


st.divider()
st.subheader("사용 기록")
log_df = load_logs()
st.dataframe(log_df, use_container_width=True)