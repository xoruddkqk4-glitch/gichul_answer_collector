"""Find an English mock exam answer image and conservatively read its 45 cells."""
import html
import io
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode, urlparse

from PIL import Image
from pypdf import PdfReader
import pymupdf

ROOT = Path(__file__).resolve().parent
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AnswerCollector/1.0)"}


def fetch(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def runs(values):
    groups = []
    for value in values:
        if not groups or value > groups[-1][-1] + 1:
            groups.append([value])
        else:
            groups[-1].append(value)
    return groups


def cell_vectors(data):
    image = Image.open(io.BytesIO(data)).convert("L")
    width, height = image.size
    if width < 400 or height < 350:
        raise ValueError("정답표 이미지 크기가 예상과 다릅니다.")
    pixels = image.load()
    horizontal = runs(y for y in range(height) if sum(pixels[x, y] < 200 for x in range(width)) > width * .65)
    if len(horizontal) < 10:
        raise ValueError("정답표의 9개 행을 찾지 못했습니다.")
    horizontal = horizontal[-10:]
    top, bottom = horizontal[0][0], horizontal[-1][-1]
    vertical = runs(x for x in range(width) if sum(pixels[x, y] < 200 for y in range(top, bottom + 1)) > (bottom - top) * .75)
    if len(vertical) != 11:
        raise ValueError("정답표의 5개 열을 찾지 못했습니다.")
    vectors = []
    for row in range(9):
        for column in range(5):
            left = vertical[column * 2 + 1][-1] + 3
            right = vertical[column * 2 + 2][0] - 3
            upper = horizontal[row][-1] + 3
            lower = horizontal[row + 1][0] - 3
            cell = image.crop((left, upper, right, lower)).point(lambda p: 0 if p < 200 else 255)
            bbox = Image.eval(cell, lambda p: 255 - p).getbbox()
            if not bbox:
                raise ValueError("빈 정답 칸이 있습니다.")
            glyph = cell.crop(bbox).resize((24, 24), Image.Resampling.BILINEAR)
            vectors.append(bytes(1 if value < 160 else 0 for value in glyph.getdata()))
    return vectors


def templates():
    entries = json.loads((ROOT / "templates.json").read_text(encoding="utf-8"))
    return [(answer, bytes(int(bit) for bit in f"{int(bits, 16):0576b}")) for answer, bits in entries]


def classify(vectors, samples):
    answers = []
    for index, vector in enumerate(vectors):
        scores = {}
        for answer, sample in samples:
            score = sum(a != b for a, b in zip(vector, sample))
            scores[answer] = min(score, scores.get(answer, 999))
        ranking = sorted(scores.items(), key=lambda pair: pair[1])
        if ranking[0][1] > 155 or ranking[1][1] - ranking[0][1] < 12:
            raise ValueError(f"{index + 1}번 정답을 확실하게 판독하지 못했습니다. 검토가 필요합니다.")
        answers.append(ranking[0][0])
    return answers


def numbered_answer_lines(first_page):
    """Read number/choice rows printed before explanations on the first page."""
    answers = {}
    started = False
    for line in first_page.splitlines():
        choices = re.findall(r"[\u2460-\u2464]", line)
        if len(choices) < (1 if started else 5):
            if started:
                break
            continue
        pairs = re.findall(r"(?<!\d)((?:\d\s*){1,2})\s*\.?\s*([\u2460-\u2464])", line)
        if len(pairs) == len(choices):
            row = [(int("".join(number.split())), ord(choice) - 0x245F) for number, choice in pairs]
        else:
            numbers = [int(number) for number in re.findall(r"(?<!\d)(\d{1,2})\.", line)]
            if len(numbers) != len(choices):
                raise ValueError("해설 PDF의 정답표 행을 판독하지 못했습니다.")
            row = list(zip(numbers, [ord(choice) - 0x245F for choice in choices]))
        started = True
        for number, answer in row:
            if number in answers or not 1 <= number <= 50:
                raise ValueError("해설 PDF의 정답 번호가 중복되거나 범위를 벗어났습니다.")
            answers[number] = answer
    if len(answers) not in (45, 50) or set(answers) != set(range(1, len(answers) + 1)):
        raise ValueError("해설 PDF에서 연속된 45개 또는 50개 정답을 확인하지 못했습니다.")
    return [answers[number] for number in range(1, len(answers) + 1)]


def pdf_answers(data):
    """Read the answer table printed before explanations on the first page."""
    try:
        first_page = PdfReader(io.BytesIO(data)).pages[0].extract_text() or ""
    except Exception as error:
        raise ValueError("해설 PDF에서 정답표를 읽지 못했습니다.") from error
    try:
        return numbered_answer_lines(first_page)
    except ValueError:
        # Some older PDFs have a broken character map for circled digits in pypdf.
        with pymupdf.open(stream=data, filetype="pdf") as document:
            text = document[0].get_text()
        if not text.strip():
            raise ValueError("EBSi 해설 PDF가 스캔본이어서 텍스트 정답을 추출할 수 없습니다.")
        pairs = re.findall(r"(?m)^([1-9]\d?)\s*\n\s*([\u2460-\u2464])\s*$", text[:2500])
        values = {int(number): ord(choice) - 0x245F for number, choice in pairs}
        if len(values) in (45, 50) and set(values) == set(range(1, len(values) + 1)):
            return [values[number] for number in range(1, len(values) + 1)]
        return numbered_answer_lines(text)


def find_answer_sets(year, month, grade):
    if year < 2006:
        raise ValueError("EBSi 기출문제 목록은 2006년부터 제공됩니다. 2002~2005년 자료는 EBSi에서 조회할 수 없습니다.")
    subject_ids = {1: "17014", 2: "120013", 3: "80003"}
    if grade not in subject_ids:
        raise ValueError("학년은 고1~고3 중에서 선택하세요.")
    page = f"https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperList.ebs?targetCd=D{grade}00"
    query = urlencode({
        "targetCd": f"D{grade}00", "yearList": year, "monthList": f"{month:02d}",
        "arOrd": "3", "subjIdList": subject_ids[grade], "sort": "recent",
    })
    listing_url = f"https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperListAjax.ajax?{query}"
    try:
        document = fetch(listing_url).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError("이 시험의 자료 페이지가 없습니다.") from error
        raise
    image_links = re.findall(r"goDownLoadJ\('([^']+)'", document)
    pdf_links = re.findall(r"goDownLoadH\('([^']+)'", document)
    titles = [html.unescape(re.sub(r"<[^>]+>", "", title)).replace("\xa0", "").strip()
              for title in re.findall(r'<div class="qus_tit">(.*?)</div>', document, re.S)]
    if not titles:
        raise ValueError("EBSi 목록에 이 학년·시행 연도·월의 영어 시험이 없습니다.")
    if not image_links and not pdf_links:
        raise ValueError("시험은 있지만 EBSi 목록에 다운로드 가능한 정답표나 해설 PDF가 없습니다.")

    variant_indices = {}
    for index, title in enumerate(titles):
        match = re.search(r"영어\s*([AB])(?![A-Za-z])", title)
        if match:
            variant_indices[match.group(1)] = index
    if len(titles) == 2 and set(variant_indices) == {"A", "B"}:
        selections = [("A", variant_indices["A"]), ("B", variant_indices["B"])]
    elif len(titles) == 2 and any("홀수형" in title for title in titles) and any("짝수형" in title for title in titles):
        selections = [(None, next(i for i, title in enumerate(titles) if "홀수형" in title))]
    elif len(titles) == 1:
        selections = [(None, 0)]
    else:
        raise ValueError("같은 달에 영어 시험이 여러 개 있어 자동으로 구분할 수 없습니다.")

    def checked_url(url, extensions):
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "wdown.ebsi.co.kr" or not parsed.path.lower().endswith(extensions):
            raise ValueError("EBSi 자료 링크의 주소 또는 파일 형식이 지원 범위를 벗어났습니다.")
        return url

    results = []
    failures = []
    for variant, index in selections:
        label = f"영어 {variant}형" if variant else ("홀수형" if len(titles) > 1 else "영어")
        try:
            image_link = image_links[index] if len(image_links) == len(titles) else (image_links[0] if len(titles) == 1 and image_links else None)
            pdf_link = pdf_links[index] if len(pdf_links) == len(titles) else (pdf_links[0] if len(pdf_links) == 1 and (len(titles) == 1 or label == "홀수형") else None)
            image_url = checked_url(html.unescape(image_link).replace("http://wdown.ebsi.co.kr/", "https://wdown.ebsi.co.kr/", 1) if image_link else None, (".png", ".jpg", ".jpeg"))
            pdf_url = checked_url("https://wdown.ebsi.co.kr/W61001/01exam" + html.unescape(pdf_link) if pdf_link else None, (".pdf",))
            if not image_url and not pdf_url:
                raise ValueError("정답 자료 링크가 없습니다.")
            errors = []
            answer_values = None
            source_file = None
            if pdf_url:
                try:
                    answer_values = pdf_answers(fetch(pdf_url))
                    source_file = pdf_url
                except (ValueError, urllib.error.URLError) as error:
                    errors.append(str(error))
            if answer_values is None and image_url:
                try:
                    answer_values = classify(cell_vectors(fetch(image_url)), templates())
                    source_file = image_url
                except (ValueError, urllib.error.URLError) as error:
                    errors.append(str(error))
            if answer_values is None:
                raise ValueError("정답표를 판독하지 못했습니다. " + "; ".join(errors))
            result = {
                "year": year, "month": month, "grade": f"고{grade}", "subject": "영어",
                "questionCount": len(answer_values),
                "answers": [{"number": n, "answer": answer} for n, answer in enumerate(answer_values, 1)],
                "sourcePage": page, "sourceFile": source_file,
            }
            if variant:
                result["variant"] = variant
            results.append(result)
        except (ValueError, urllib.error.URLError) as error:
            failures.append({"label": label, "error": str(error)})
    if not results:
        raise ValueError("; ".join(f"{item['label']}: {item['error']}" for item in failures))
    return {"results": results, "errors": failures}
