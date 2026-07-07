#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_catalog.py — генератор интерактивных каталогов запчастей из заводских PDF.

Использование:
    python3 tools/build_catalog.py <входы...> [опции]

Входы: .pdf, .zip, .zip.001 (разбитый архив — части найдутся сами), либо папка.
Повторный запуск с новым файлом ДОБАВЛЯЕТ его к уже собранному каталогу;
неизменённые источники не пересобираются (кэш по SHA1).

Примеры:
    # первая сборка
    python3 tools/build_catalog.py "БС-215+Каталог+запчастей.zip.001" --id bs215 --label "БС-215"
    # добавить новый каталог к готовому
    python3 tools/build_catalog.py "Новый каталог.pdf" --id new1 --label "НОВЫЙ"
    # удалить оборудование из каталога
    python3 tools/build_catalog.py --remove new1
    # что уже собрано
    python3 tools/build_catalog.py --list

Результат: <outdir>/index.html + data.js + img/*.jpg  (открывается офлайн).
"""
import argparse, hashlib, json, os, re, shutil, sys, tempfile, zipfile, datetime

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("Требуется PyMuPDF:  pip install pymupdf")

VERSION = "2.0"
CJK = re.compile(r'[一-鿿]')
DOTTED = re.compile(r'\.{5,}\s*\d+')          # строка оглавления «..... 243»
SMALLINT = re.compile(r'^\d{1,4}$')
POSINT = re.compile(r'^\d{1,3}$')

def clean(s): return re.sub(r'\s+', ' ', s).strip()

def sha1_file(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

TRANSLIT = str.maketrans({
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'j',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
    'х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'})
def slug(s):
    s = s.lower().translate(TRANSLIT)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return (s[:24].rstrip('-')) or 'cat'

# ---------------------------------------------------------------- входы ----
def join_split_zip(first_part, tmpdir):
    """X.zip.001 → склеить все части X.zip.NNN в один zip."""
    base = re.sub(r'\.\d{3}$', '', first_part)
    parts = []
    n = 1
    while True:
        p = f'{base}.{n:03d}'
        if not os.path.exists(p): break
        parts.append(p); n += 1
    if not parts:
        raise FileNotFoundError(f'части архива не найдены: {base}.001…')
    out = os.path.join(tmpdir, os.path.basename(base))
    with open(out, 'wb') as w:
        for p in parts:
            with open(p, 'rb') as r: shutil.copyfileobj(r, w)
    return out

def extract_pdfs(zpath, tmpdir):
    """Достать все PDF из zip (имена внутри бывают битые — переименовываем).
    Сначала пробуем zipfile; при экзотическом методе сжатия — системный unzip."""
    res = []
    stem = slug(os.path.splitext(os.path.basename(zpath))[0])
    try:
        with zipfile.ZipFile(zpath) as z:
            k = 0
            for info in z.infolist():
                if info.filename.lower().endswith('.pdf'):
                    dst = os.path.join(tmpdir, f'{stem}_{k}.pdf'); k += 1
                    with z.open(info) as src, open(dst, 'wb') as w:
                        shutil.copyfileobj(src, w)
                    res.append(dst)
        if res:
            return res
    except (NotImplementedError, zipfile.BadZipFile):
        pass
    # fallback: unzip умеет больше методов сжатия
    import subprocess
    exdir = os.path.join(tmpdir, stem + '_x'); os.makedirs(exdir, exist_ok=True)
    r = subprocess.run(['unzip', '-o', '-q', zpath, '-d', exdir],
                       capture_output=True, text=True)
    if r.returncode not in (0, 1):   # 1 = предупреждения, допустимо
        raise RuntimeError(f'unzip не смог распаковать {zpath}: {r.stderr[:200]}')
    k = 0
    for root, _dirs, files in os.walk(exdir):
        for name in sorted(files):
            if name.lower().endswith('.pdf'):
                dst = os.path.join(tmpdir, f'{stem}_{k}.pdf'); k += 1
                shutil.move(os.path.join(root, name), dst)
                res.append(dst)
    return res

def collect_inputs(paths, tmpdir):
    """→ [(pdf_path, source_label)]"""
    out = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.lower().endswith('.pdf'):
                    out.append((os.path.join(p, name), name))
                elif name.lower().endswith('.zip.001') or name.lower().endswith('.zip'):
                    out += [(x, name) for x in extract_pdfs(
                        join_split_zip(os.path.join(p, name), tmpdir) if name.endswith('.001')
                        else os.path.join(p, name), tmpdir)]
        elif re.search(r'\.zip\.\d{3}$', p, re.I):
            if not p.lower().endswith('.001'):
                p = re.sub(r'\.\d{3}$', '.001', p)
            out += [(x, os.path.basename(p)) for x in extract_pdfs(join_split_zip(p, tmpdir), tmpdir)]
        elif p.lower().endswith('.zip'):
            out += [(x, os.path.basename(p)) for x in extract_pdfs(p, tmpdir)]
        elif p.lower().endswith('.pdf'):
            out.append((p, os.path.basename(p)))
        else:
            print(f'  ! пропущен неизвестный вход: {p}')
    return out

# ------------------------------------------------------- анализ формата ----
def pick_partnum_pattern(doc):
    """Выбрать шаблон «номера детали» по статистике документа."""
    digits9 = re.compile(r'^\d{9,}$')
    alnum7  = re.compile(r'^\d{7,}[A-ZА-Я]?$')
    genrl   = re.compile(r'^[A-ZА-Я0-9][A-ZА-Я0-9.\-/]{5,}$')
    c9 = c7 = cg = 0
    step = max(1, len(doc)//40)
    for p in range(0, len(doc), step):
        for l in (s.strip() for s in doc[p].get_text().split('\n')):
            if digits9.match(l): c9 += 1
            if alnum7.match(l):  c7 += 1
            elif genrl.match(l) and sum(ch.isdigit() for ch in l) >= 5: cg += 1
    # alnum7 — надмножество digits9: берём его, если он даёт хоть что-то сверх
    # строгого шаблона (короткие/буквенные номера); ложные срабатывания отсекает
    # контекстный фильтр в parse_rows (строка без поз./кол-ва/имени отбрасывается).
    if c7 > c9:
        return alnum7, 'цифро-буквенный ≥7 знаков'
    if c9:
        return digits9, 'цифровой ≥9 знаков'
    return genrl, 'обобщённый (буквы/цифры/точки)'

def detect_order(doc, pn):
    """Порядок колонок после номера: имя→кол-во (КМЗ) или кол-во→имя (WP17)."""
    name_first = qty_first = 0
    step = max(1, len(doc)//30)
    for p in range(0, len(doc), step):
        lines = [l.strip() for l in doc[p].get_text().split('\n')]
        for i, s in enumerate(lines):
            if pn.match(s):
                j = i + 1
                while j < len(lines) and not lines[j]: j += 1
                if j < len(lines):
                    if SMALLINT.match(lines[j]): qty_first += 1
                    elif not pn.match(lines[j]): name_first += 1
    return 'qty_first' if qty_first > name_first else 'name_first'

def detect_format(doc):
    """'toc' — есть оглавление с точками и колонтитулы «Стр. N»; иначе 'headings'."""
    toc_lines = sum(len(DOTTED.findall(doc[p].get_text())) for p in range(min(8, len(doc))))
    pp = sum(1 for p in range(min(30, len(doc))) if re.search(r'Стр\.\s*\d+', doc[p].get_text()))
    return 'toc' if toc_lines >= 5 and pp >= 10 else 'headings'

# ------------------------------------------------------- парсинг таблиц ----
def parse_rows(text, pn, order):
    lines = [l.strip() for l in text.split('\n')]
    rows = []; i = 0
    while i < len(lines):
        s = lines[i]
        if pn.match(s):
            pos = ''
            k = i - 1
            while k >= 0 and not lines[k]: k -= 1
            if k >= 0 and POSINT.match(lines[k]): pos = lines[k]
            j = i + 1; qty = ''; name = []
            if order == 'qty_first':
                while j < len(lines) and not lines[j]: j += 1
                if j < len(lines) and SMALLINT.match(lines[j]): qty = lines[j]; j += 1
                while j < len(lines):
                    t = lines[j]
                    if not t: j += 1; continue
                    if SMALLINT.match(t) or pn.match(t) or CJK.search(t): break
                    name.append(t); j += 1
                    if len(name) >= 2: break
            else:
                while j < len(lines):
                    t = lines[j]
                    if not t: j += 1; continue
                    if SMALLINT.match(t): qty = t; break
                    if pn.match(t): break
                    name.append(t); j += 1
                    if len(name) >= 3: break
            nm = clean(' '.join(name))
            # контекстный фильтр: токен без позиции, количества и имени —
            # скорее всего не номер детали (колонтитул, обозначение документа)
            if pos or qty or nm:
                rows.append({'pos': pos, 'num': s, 'name': nm, 'qty': qty})
            i = j
        else:
            i += 1
    return rows

# --------------------------------------------------- разбиение на листы ----
def make_plates(pages):
    """Лист = страницы-чертежи (rows==0) + следующая за ними страница-таблица."""
    plates, pending = [], []
    for pg in pages:
        if pg['rows']:
            plates.append({'imgs': [d['img'] for d in pending] + [pg['img']],
                           'ppspan': [(pending[0]['pp'] if pending else pg['pp']), pg['pp']],
                           'rows': pg['rows']})
            pending = []
        else:
            pending.append(pg)
    if pending:
        plates.append({'imgs': [d['img'] for d in pending],
                       'ppspan': [pending[0]['pp'], pending[-1]['pp']], 'rows': []})
    return plates

# --------------------------------------------------------- формат «toc» ----
def parse_toc(doc):
    entries = []
    for p in range(min(8, len(doc))):
        t = doc[p].get_text()
        if not DOTTED.search(t): continue
        for line in t.split('\n'):
            m = re.match(r'(.*?)\s*\.{3,}\s*(\d+)\s*$', line.strip())
            if not m: continue
            head, page = m.group(1).strip(), int(m.group(2))
            nm = re.search(r'(\d{9,})\s*$', head)
            num = nm.group(1) if nm else None
            name = clean(head[:nm.start()] if nm else head)
            if name: entries.append((name, num, page))
    return sorted(entries, key=lambda e: e[2])

def build_toc_format(doc, eqid, imgdir, pn, order, dpi, quality):
    toc = parse_toc(doc)
    def unit_for(pp):
        cur = None
        for name, num, start in toc:
            if pp >= start: cur = (name, num)
            else: break
        return cur
    unit_pages, rendered = {}, 0
    for p in range(len(doc)):
        text = doc[p].get_text()
        m = re.search(r'Стр\.\s*(\d+)', text)
        if not m: continue
        pp = int(m.group(1))
        u = unit_for(pp)
        if u is None: continue
        rows = parse_rows(text, pn, order)
        fname = f'{eqid}_p{p:03d}.jpg'
        pix = doc[p].get_pixmap(dpi=dpi)
        open(os.path.join(imgdir, fname), 'wb').write(pix.tobytes('jpeg', jpg_quality=quality))
        rendered += 1
        unit_pages.setdefault(u, []).append({'img': fname, 'pp': pp, 'rows': rows})
    units = []
    for (name, num, _s) in toc:
        pages = unit_pages.get((name, num), [])
        if pages:
            units.append({'name': name, 'num': num or '', 'plates': make_plates(pages)})
    return units, rendered

# ---------------------------------------------------- формат «headings» ----
def page_heading(page, use_cjk):
    lines_txt = [l.strip() for l in page.get_text().split('\n')]
    if use_cjk:
        for l in lines_txt:
            if CJK.search(l) and ('(' in l or ')' in l): return clean(l)
        for l in lines_txt:
            if CJK.search(l): return clean(l)
        return None
    # без CJK: самая крупная строка в верхней половине страницы
    d = page.get_text('dict')
    best, best_size = None, 0.0
    h = page.rect.height
    for b in d.get('blocks', []):
        if b.get('type') != 0: continue
        for l in b['lines']:
            txt = clean(''.join(sp['text'] for sp in l['spans']))
            if not (4 <= len(txt) <= 120): continue
            if SMALLINT.match(txt) or DOTTED.search(txt): continue
            size = max(sp['size'] for sp in l['spans'])
            if l['bbox'][1] < h * 0.5 and size > best_size:
                best, best_size = txt, size
    return best

def build_headings_format(doc, eqid, imgdir, pn, order, dpi, quality):
    use_cjk = any(CJK.search(doc[p].get_text()) for p in range(len(doc)))
    last = None; unit_pages = {}; upl_order = []; rendered = 0
    for p in range(len(doc)):
        text = doc[p].get_text()
        if DOTTED.search(text): continue                 # страницы оглавления
        sec = page_heading(doc[p], use_cjk)
        if sec: last = sec
        if last is None: continue                        # предисловие до первого раздела
        rows = parse_rows(text, pn, order)
        if not rows and sec is None and not doc[p].get_images(): continue
        if last not in unit_pages:
            unit_pages[last] = []; upl_order.append(last)
        fname = f'{eqid}_p{p:03d}.jpg'
        pix = doc[p].get_pixmap(dpi=dpi)
        open(os.path.join(imgdir, fname), 'wb').write(pix.tobytes('jpeg', jpg_quality=quality))
        rendered += 1
        unit_pages[last].append({'img': fname, 'pp': p + 1, 'rows': rows})
    units = [{'name': s, 'num': '', 'plates': make_plates(unit_pages[s])}
             for s in upl_order if unit_pages[s]]
    return units, rendered

# --------------------------------------------------------------- заголовок -
def auto_title(doc, fallback):
    try:
        d = doc[0].get_text('dict')
        best, best_size = None, 0.0
        for b in d.get('blocks', []):
            if b.get('type') != 0: continue
            for l in b['lines']:
                txt = clean(''.join(sp['text'] for sp in l['spans']))
                if not (6 <= len(txt) <= 90) or not re.search(r'[А-Яа-яA-Za-z]', txt): continue
                size = max(sp['size'] for sp in l['spans'])
                if size > best_size: best, best_size = txt, size
        return best or fallback
    except Exception:
        return fallback

# ------------------------------------------------------------------ сборка -
def write_outputs(outdir, manifest):
    """data.js + index.html из шаблона."""
    build_dir = os.path.join(outdir, '.build')
    data = {'generated': datetime.date.today().isoformat(), 'version': VERSION,
            'order': manifest['order'], 'equip': {}}
    for eqid in manifest['order']:
        item = manifest['items'][eqid]
        units = json.load(open(os.path.join(build_dir, f'{eqid}.json'), encoding='utf-8'))
        data['equip'][eqid] = {'title': item['title'], 'sub': item.get('sub', ''),
                               'label': item.get('label', eqid.upper()), 'units': units}
    js = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    js = js.replace('</', '<\\/').replace(' ', '\\u2028').replace(' ', '\\u2029')
    open(os.path.join(outdir, 'data.js'), 'w', encoding='utf-8').write(
        'window.CATALOG=' + js + ';')
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer.html')
    shutil.copyfile(tpl, os.path.join(outdir, 'index.html'))

def main():
    ap = argparse.ArgumentParser(description='Генератор интерактивного каталога запчастей из PDF')
    ap.add_argument('inputs', nargs='*', help='PDF / ZIP / ZIP.001 / папка')
    ap.add_argument('-o', '--outdir', default='catalog_book')
    ap.add_argument('--id', help='идентификатор оборудования (только с одним входом)')
    ap.add_argument('--label', help='короткая подпись вкладки, напр. «БС-215»')
    ap.add_argument('--title', help='полное название оборудования')
    ap.add_argument('--sub', help='подзаголовок (обозначение документа, изготовитель)')
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--quality', type=int, default=68)
    ap.add_argument('--format', choices=['auto', 'toc', 'headings'], default='auto')
    ap.add_argument('--force', action='store_true', help='пересобрать даже без изменений')
    ap.add_argument('--remove', metavar='ID', help='удалить оборудование из каталога')
    ap.add_argument('--list', action='store_true', help='показать собранные каталоги')
    a = ap.parse_args()

    outdir = os.path.abspath(a.outdir)
    imgdir = os.path.join(outdir, 'img')
    build_dir = os.path.join(outdir, '.build')
    os.makedirs(imgdir, exist_ok=True); os.makedirs(build_dir, exist_ok=True)
    mpath = os.path.join(build_dir, 'manifest.json')
    manifest = json.load(open(mpath, encoding='utf-8')) if os.path.exists(mpath) \
        else {'version': 1, 'order': [], 'items': {}}

    if a.list:
        if not manifest['order']: print('Каталог пуст.')
        for eqid in manifest['order']:
            it = manifest['items'][eqid]
            st = it.get('stats', {})
            print(f"  {eqid:12s} {it.get('label',''):8s} {it['title']}  "
                  f"[{st.get('units','?')} узлов / {st.get('plates','?')} листов / {st.get('rows','?')} позиций]")
        return

    if a.remove:
        if a.remove not in manifest['items']:
            sys.exit(f'нет такого id: {a.remove}')
        manifest['order'].remove(a.remove); manifest['items'].pop(a.remove)
        for f in os.listdir(imgdir):
            if f.startswith(a.remove + '_'): os.remove(os.path.join(imgdir, f))
        j = os.path.join(build_dir, f'{a.remove}.json')
        if os.path.exists(j): os.remove(j)
        json.dump(manifest, open(mpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        write_outputs(outdir, manifest)
        print(f'Удалено: {a.remove}. Каталог пересобран.')
        return

    if not a.inputs:
        ap.print_help(); return
    if (a.id or a.title or a.label or a.sub) and len(a.inputs) > 1:
        sys.exit('--id/--label/--title/--sub допустимы только с одним входным файлом')

    with tempfile.TemporaryDirectory() as tmpdir:
        pdfs = collect_inputs(a.inputs, tmpdir)
        if not pdfs: sys.exit('PDF не найдены во входных данных')

        for pdf_path, source in pdfs:
            digest = sha1_file(pdf_path)
            eqid = a.id or slug(os.path.splitext(source)[0])
            prev = manifest['items'].get(eqid)
            if prev and not a.force and prev.get('sha1') == digest \
               and prev.get('dpi') == a.dpi and prev.get('quality') == a.quality:
                print(f'= {eqid}: без изменений (кэш), пропуск')
                continue

            doc = fitz.open(pdf_path)
            fmt = a.format if a.format != 'auto' else detect_format(doc)
            pn, pn_desc = pick_partnum_pattern(doc)
            order = detect_order(doc, pn)
            print(f'> {eqid}: {len(doc)} стр. | формат={fmt} | номер: {pn_desc} | '
                  f'колонки: {"кол-во→имя" if order=="qty_first" else "имя→кол-во"}')

            # убрать старые изображения этого оборудования
            for f in os.listdir(imgdir):
                if f.startswith(eqid + '_'): os.remove(os.path.join(imgdir, f))

            if fmt == 'toc':
                units, rendered = build_toc_format(doc, eqid, imgdir, pn, order, a.dpi, a.quality)
            else:
                units, rendered = build_headings_format(doc, eqid, imgdir, pn, order, a.dpi, a.quality)

            nrows = sum(len(pl['rows']) for u in units for pl in u['plates'])
            unnamed = sum(1 for u in units for pl in u['plates'] for r in pl['rows'] if not r['name'])
            plates = sum(len(u['plates']) for u in units)
            if not units:
                print(f'  !! не удалось выделить узлы — проверьте --format/--force, файл: {source}')
                continue
            json.dump(units, open(os.path.join(build_dir, f'{eqid}.json'), 'w', encoding='utf-8'),
                      ensure_ascii=False, separators=(',', ':'))

            title = a.title or (prev or {}).get('title') or auto_title(doc, os.path.splitext(source)[0])
            item = {'title': title,
                    'sub': a.sub or (prev or {}).get('sub') or source,
                    'label': a.label or (prev or {}).get('label') or eqid.upper(),
                    'source': source, 'sha1': digest, 'dpi': a.dpi, 'quality': a.quality,
                    'stats': {'units': len(units), 'plates': plates, 'rows': nrows,
                              'unnamed': unnamed, 'images': rendered}}
            manifest['items'][eqid] = item
            if eqid not in manifest['order']: manifest['order'].append(eqid)
            print(f'  + {len(units)} узлов, {plates} листов, {nrows} позиций '
                  f'({unnamed} без наименования), {rendered} изображений')

    json.dump(manifest, open(mpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    write_outputs(outdir, manifest)
    tot = sum(manifest['items'][e]['stats']['rows'] for e in manifest['order'])
    print(f'Готово: {outdir}/index.html | оборудования: {len(manifest["order"])} | позиций: {tot}')

if __name__ == '__main__':
    main()
