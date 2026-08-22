#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_docs.py — превратить руководства по эксплуатации/обслуживанию (PDF) в
данные для встроенного «читателя руководств» каталога.

Для каждого руководства: рендер страниц в JPEG (для точной передачи рисунков и
таблиц) + извлечение текста каждой страницы (для сквозного поиска) + простое
оглавление по крупным заголовкам. Результат — docs.js (window.DOCS) и папка
docs_img/. Отдельно от парт-каталога, т.к. вместе они превышают лимит размера.

Вход: PDF, ZIP, разбитый ZIP.001 (части склеиваются сами) — как в build_catalog.
Каждому файлу можно задать заголовок:  "путь::Короткий заголовок".

Использование:
    python3 tools/build_docs.py \
        "4 Технические характеристики бурового станка БС 215.pdf::Технические характеристики" \
        "БС-215.00.00.000-01 РЭ2-1-17.pdf::РЭ2 — Руководство по эксплуатации" \
        -o catalog_book
"""
import argparse, os, re, json, shutil, tempfile, zipfile, datetime, subprocess, hashlib
import fitz

def clean(s): return re.sub(r'\s+', ' ', s).strip()

TRANSLIT = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i',
 'й':'j','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u',
 'ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
def slugify(s):
    out = ''.join(TRANSLIT.get(ch, ch) for ch in s.lower())
    out = re.sub(r'[^0-9a-z]+', '', out)
    return out[:10] or 'doc'

def join_split_zip(first, tmp):
    base = re.sub(r'\.\d{3}$', '', first)
    parts, n = [], 1
    while os.path.exists(f'{base}.{n:03d}'):
        parts.append(f'{base}.{n:03d}'); n += 1
    out = os.path.join(tmp, os.path.basename(base))
    with open(out, 'wb') as w:
        for p in parts:
            with open(p, 'rb') as r: shutil.copyfileobj(r, w)
    return out

def pdf_from(path, tmp):
    """Вернуть путь к PDF: сам PDF, либо распаковать из zip/zip.001."""
    if path.lower().endswith('.pdf'):
        return path
    if re.search(r'\.zip\.\d{3}$', path, re.I):
        if not path.lower().endswith('.001'):
            path = re.sub(r'\.\d{3}$', '.001', path)
        path = join_split_zip(path, tmp)
    # распаковать zip
    exdir = os.path.join(tmp, slugify(os.path.basename(path)) + '_x'); os.makedirs(exdir, exist_ok=True)
    try:
        with zipfile.ZipFile(path) as z:
            z.extractall(exdir)
    except Exception:
        subprocess.run(['unzip', '-o', '-q', path, '-d', exdir], capture_output=True)
    for root, _d, files in os.walk(exdir):
        for f in sorted(files):
            if f.lower().endswith('.pdf'):
                return os.path.join(root, f)
    raise FileNotFoundError(f'PDF не найден в {path}')

def page_heading(page):
    """Крупнейшая осмысленная строка в верхней трети страницы — как заголовок раздела."""
    try:
        d = page.get_text('dict'); H = page.rect.height
        best, size = None, 0
        for b in d.get('blocks', []):
            if b.get('type') != 0: continue
            for l in b['lines']:
                txt = clean(''.join(sp['text'] for sp in l['spans']))
                if not (4 <= len(txt) <= 90): continue
                if re.fullmatch(r'[\d.\s]+', txt): continue
                sz = max(sp['size'] for sp in l['spans'])
                if l['bbox'][1] < H * 0.33 and sz > size:
                    best, size = txt, sz
        return best
    except Exception:
        return None

DPI, Q = 105, 63

def build_doc(pdf_path, title, docid, imgdir):
    doc = fitz.open(pdf_path)
    pages = []; outline = []
    for p in range(len(doc)):
        pg = doc[p]
        fname = f'{docid}_p{p+1:03d}.jpg'
        pix = pg.get_pixmap(dpi=DPI)
        open(os.path.join(imgdir, fname), 'wb').write(pix.tobytes('jpeg', jpg_quality=Q))
        text = clean(pg.get_text())
        pages.append({'img': fname, 'text': text})
        h = page_heading(pg)
        if h and (not outline or outline[-1]['title'] != h):
            outline.append({'title': h, 'page': p + 1})
    return {'id': docid, 'title': title, 'pages': pages, 'outline': outline}

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('inputs', nargs='+', help='"файл::Заголовок" (PDF/ZIP/ZIP.001)')
    ap.add_argument('-o', '--outdir', default='catalog_book')
    a = ap.parse_args()

    outdir = os.path.abspath(a.outdir)
    imgdir = os.path.join(outdir, 'docs_img'); os.makedirs(imgdir, exist_ok=True)
    # очистить старые картинки, чтобы не копить мусор
    for f in os.listdir(imgdir):
        if f.endswith('.jpg'): os.remove(os.path.join(imgdir, f))

    docs = []
    used_ids = set()
    with tempfile.TemporaryDirectory() as tmp:
        for spec in a.inputs:
            path, _, title = spec.partition('::')
            path = path.strip(); title = title.strip() or os.path.splitext(os.path.basename(path))[0]
            docid = slugify(title)
            k = docid; i = 2
            while k in used_ids: k = f'{docid}{i}'; i += 1
            docid = k; used_ids.add(docid)
            pdf = pdf_from(path, tmp)
            d = build_doc(pdf, title, docid, imgdir)
            docs.append(d)
            print(f'  {title[:42]:42} -> {len(d["pages"])} стр, {len(d["outline"])} заголовков')

    data = {'generated': datetime.date.today().isoformat(), 'docs': docs,
            'stats': {'docs': len(docs), 'pages': sum(len(d['pages']) for d in docs)}}
    js = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    open(os.path.join(outdir, 'docs.js'), 'w', encoding='utf-8').write('window.DOCS=' + js + ';')
    total_mb = sum(os.path.getsize(os.path.join(imgdir, f)) for f in os.listdir(imgdir)) / 1024 / 1024
    print(f'Готово: {len(docs)} руководств, {data["stats"]["pages"]} страниц, ~{total_mb:.1f} МБ изображений')
    print('docs.js записан. Соберите читатель: python3 tools/pack_docs.py')

if __name__ == '__main__':
    main()
