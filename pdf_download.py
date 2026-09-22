"""Locate English exam PDFs in the EBSi past-paper listing."""
import html
import re
from urllib.parse import urlencode, urlparse

from extractor import fetch


def find_pdfs(year, month, grade):
    if year < 2006:
        raise ValueError("EBSi 기출문제 목록은 2006년부터 제공됩니다.")
    subject_ids = {1: "17014", 2: "120013", 3: "80003"}
    query = urlencode({"targetCd": f"D{grade}00", "yearList": year,
                       "monthList": f"{month:02d}", "arOrd": "3",
                       "subjIdList": subject_ids[grade], "sort": "recent"})
    raw = fetch("https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperListAjax.ajax?" + query)
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError:
        document = raw.decode("cp949", "replace")
    entries = []
    for block in re.findall(r'<div class="qus_box[^\"]*">(.*?)(?=<div class="qus_box|</form>)', document, re.S):
        title_match = re.search(r'<div class="qus_tit">(.*?)</div>', block, re.S)
        if not title_match:
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).replace("\xa0", "").strip()
        variant_match = re.search(r"영어\s*([AB])(?![A-Za-z])", title)
        variant = variant_match.group(1) if variant_match else None
        files = {}
        for kind, function in (("q", "P"), ("a", "H")):
            match = re.search(r"goDownLoad" + function + r"\('([^']+\.pdf)'", block)
            if match:
                url = "https://wdown.ebsi.co.kr/W61001/01exam" + html.unescape(match.group(1))
                parsed = urlparse(url)
                if parsed.scheme != "https" or parsed.netloc != "wdown.ebsi.co.kr" or not parsed.path.startswith("/W61001/01exam/"):
                    raise ValueError("EBSi PDF 주소가 예상 범위를 벗어났습니다.")
                files[kind] = url
        entries.append({"title": title, "variant": variant, "files": files})
    if not entries:
        raise ValueError("선택한 시험의 영어 자료가 EBSi 목록에 없습니다.")
    if len(entries) > 1 and any("홀수형" in entry["title"] for entry in entries):
        entries = [entry for entry in entries if "홀수형" in entry["title"]]
    if len(entries) > 1 and any(not entry["variant"] for entry in entries):
        raise ValueError("여러 영어 시험지를 자동으로 구분할 수 없습니다.")
    return entries
