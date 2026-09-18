import datetime
import re
import time
import cloudscraper
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

st.title("📷 디시인사이드 갤러리 기간별 상세 수집기")
st.write(
    "원하는 **갤러리, 검색어, 수집 기간**을 설정하면 해당 기간 내 본문과 댓글을 수집합니다."
)

# 1. 사용자 입력 UI
gallery_id = st.text_input("갤러리 ID", value="digitalpicture")
keywords_raw = st.text_input(
    "검색어 (쉼표로 여러개 입력 가능)",
    value="니콘, 니끼끼, nikon, 나이콘, 황콘",
)

# 날짜 선택 UI
today = datetime.date.today()
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input(
        "수집 시작일", value=today - datetime.timedelta(days=7)
    )
with col2:
    end_date = st.date_input("수집 종료일", value=today)


def parse_dc_date(date_str):
    date_str = date_str.strip()
    if ":" in date_str and len(date_str) <= 5:
        return datetime.date.today()

    clean_str = re.sub(r"[^\d.]", "", date_str)
    parts = clean_str.split(".")

    if len(parts) >= 3:
        year = int(parts[0])
        if year < 100:
            year += 2000
        month = int(parts[1])
        day = int(parts[2])
        return datetime.date(year, month, day)

    return datetime.date.today()


if st.button("기간 내 데이터 수집 시작"):
    if start_date > end_date:
        st.error("시작일이 종료일보다 뒤에 있을 수 없습니다.")
    else:
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        st.info(
            f"검색어: {keywords} | 기간: {start_date} ~ {end_date} 범위 데이터 수집을 진행합니다."
        )

        results = []
        seen_links = set()
        status_text = st.empty()
        collected_count = 0

        # cloudscraper로 차단 우회 스크래퍼 생성
        scraper = cloudscraper.create_scraper(
            browser={
                "browser": "chrome",
                "platform": "windows",
                "desktop": True,
            }
        )

        for kw in keywords:
            page = 1
            st.write(f"🔍 **'{kw}'** 키워드 검색 시작...")

            while True:
                list_url = f"https://gall.dcinside.com/mgallery/board/lists/?id={gallery_id}&s_type=search_subject_memo&s_keyword={kw}&page={page}"

                try:
                    time.sleep(1.5)
                    res = scraper.get(list_url, timeout=15)

                    # 만약 403 차단이 뜨면 로그 출력
                    if res.status_code == 403:
                        st.error(
                            f"디시인사이드 IP 차단(403) 발생. 키워드 [{kw}] 대기 필요"
                        )
                        break

                    soup = BeautifulSoup(res.text, "html.parser")
                    tr_list = soup.select(".gall_list tbody tr.ub-content")

                    if not tr_list:
                        break

                    out_of_range_count = 0

                    for tr in tr_list:
                        num_tag = tr.select_one(".gall_num")
                        if not num_tag or not num_tag.text.strip().isdigit():
                            continue

                        title_tag = tr.select_one(".gall_tit a")
                        date_tag = tr.select_one(".gall_date")
                        if not title_tag or not date_tag:
                            continue

                        post_date = parse_dc_date(date_tag.text)

                        if post_date < start_date:
                            out_of_range_count += 1
                            continue

                        if post_date > end_date:
                            continue

                        link = (
                            "https://gall.dcinside.com" + title_tag["href"]
                        )
                        if link in seen_links:
                            continue

                        seen_links.add(link)
                        title = title_tag.text.strip()

                        # 본문 및 댓글 수집
                        time.sleep(1.5)
                        detail_res = scraper.get(link, timeout=15)
                        detail_soup = BeautifulSoup(
                            detail_res.text, "html.parser"
                        )

                        content_tag = detail_soup.select_one(".write_div")
                        content = (
                            content_tag.text.strip() if content_tag else ""
                        )

                        comments = [
                            c.text.strip()
                            for c in detail_soup.select(".usertxt")
                            if c.text.strip()
                        ]
                        comment_str = " | ".join(comments)

                        results.append(
                            {
                                "수집키워드": kw,
                                "작성일": post_date.strftime("%Y-%m-%d"),
                                "제목": title,
                                "본문": content,
                                "댓글": comment_str,
                                "링크": link,
                            }
                        )

                        collected_count += 1
                        status_text.text(
                            f"수집 중 ({collected_count}개 완료): [{post_date}] {title[:20]}..."
                        )

                    if out_of_range_count >= len(tr_list) - 2:
                        break

                    page += 1

                except Exception as e:
                    st.error(f"오류 발생 ({kw}, {page}페이지): {e}")
                    break

        df = pd.DataFrame(results)
        st.success(f"총 {len(df)}개 게시글 수집 완료!")

        st.dataframe(df)

        csv = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="CSV 파일 다운로드",
            data=csv,
            file_name=f"{gallery_id}_{start_date}~{end_date}_수집결과.csv",
            mime="text/csv",
        )
