#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_prices.py — сопоставить прайс-лист (.xlsx) с уже собранным каталогом
и вписать цены в кэш .build/<id>.json (перед перегенерацией index.html).

Проблема источника: колонка "Номенклатурный номер" в прайс-листе хранится как
число (не текст), а наши номера деталей — 17-18-значные. Excel физически не
может хранить такую точность (предел ~15-16 значащих цифр) — последние 3-5
цифр в файле УЖЕ обнулены при его создании (проверено по сырому XML). Из-за
этого сопоставление только по номеру даёт ~79% ложных совпадений (проверено).

Решение: сопоставлять по ДВУМ признакам одновременно — округлённому номеру
(как ключ группировки-кандидатов) И наименованию (как проверка, что это
действительно та же деталь). Назначаем цену только когда оба совпадают;
иначе — не гадаем, деталь остаётся без цены.

Использование:
    python3 tools/apply_prices.py "Прайс-лист.xlsx" -o catalog_book
"""
import argparse, json, os, re, sys
import openpyxl

CODE_PREFIX = re.compile(r'^\s*([\dA-Za-zА-Яа-я]{1,4}(?:[.\-][\dA-Za-zА-Яа-я]{1,4}){1,5})\s+(.+?)\s*$')
NORM = re.compile(r'[^0-9A-ZА-ЯЁ ]+')

def norm_name(s):
    if not s: return ''
    s = str(s).upper().replace('Ё', 'Е')
    s = NORM.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def split_price_name(raw):
    """'68.10.00.100-01    УСТАНОВКА НАСОСНАЯ' -> 'УСТАНОВКА НАСОСНАЯ'
    Если явного числового префикса нет — вся строка и есть название."""
    raw = str(raw or '').replace('\xa0', ' ').strip()
    m = CODE_PREFIX.match(raw)
    if m and re.search(r'\d', m.group(1)):
        return norm_name(m.group(2))
    return norm_name(raw)

def lossy_key(n):
    """Тот же округляющий шаг точности (12 значащих цифр), что уже произошёл
    в исходном xlsx — группируем оба набора чисел одинаково, чтобы у них были
    общие кандидаты для сопоставления."""
    try:
        return float(f"{float(n):.11e}")
    except (ValueError, TypeError):
        return None

def load_price_rows(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb['Прайс итоговый'] if 'Прайс итоговый' in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        num, name, price = row[1], row[2], row[4]
        if num is None or price is None: continue
        try:
            price = float(str(price).replace('\xa0', '').replace(',', '.'))
        except ValueError:
            continue
        key = lossy_key(num)
        if key is None: continue
        rows.append({'key': key, 'name': split_price_name(name), 'price': price})
    return rows

def load_catalog_rows(build_dir, eqid):
    path = os.path.join(build_dir, '.build', f'{eqid}.json')
    if not os.path.exists(path): return None
    units = json.load(open(path, encoding='utf-8'))
    out = []
    for u in units:
        for pl in u['plates']:
            for r in pl['rows']:
                if r['num'].isdigit():
                    out.append({'row': r, 'key': lossy_key(r['num']), 'name': norm_name(r['name'])})
    return units, out

def match(price_rows, catalog_rows):
    from collections import defaultdict
    by_key = defaultdict(list)
    for pr in price_rows:
        by_key[pr['key']].append(pr)

    matched = 0; ambiguous_left = 0
    examples = []
    for cr in catalog_rows:
        cands = by_key.get(cr['key'], [])
        if not cands: continue
        # точное совпадение имени -> берём; иначе подстрочное совпадение в любую сторону
        exact = [c for c in cands if c['name'] == cr['name'] and c['name']]
        pick = exact[0] if exact else None
        if pick is None and cr['name']:
            sub = [c for c in cands if c['name'] and (c['name'] in cr['name'] or cr['name'] in c['name'])]
            if len(sub) == 1:
                pick = sub[0]
        if pick is not None:
            cr['row']['price'] = round(pick['price'], 2)
            matched += 1
            if len(examples) < 12:
                examples.append((cr['row']['num'], cr['name'], pick['name'], pick['price']))
        elif len(cands) > 1:
            ambiguous_left += 1
    return matched, ambiguous_left, examples

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pricefile')
    ap.add_argument('-o', '--outdir', default='catalog_book')
    a = ap.parse_args()

    price_rows = load_price_rows(a.pricefile)
    print(f'Прайс-лист: {len(price_rows)} строк с ценой')

    manifest_path = os.path.join(a.outdir, '.build', 'manifest.json')
    if not os.path.exists(manifest_path):
        sys.exit(f'нет {manifest_path} — сначала соберите каталог build_catalog.py')
    manifest = json.load(open(manifest_path, encoding='utf-8'))

    total_matched = 0; total_rows = 0
    for eqid in manifest['order']:
        loaded = load_catalog_rows(a.outdir, eqid)
        if not loaded: continue
        units, catalog_rows = loaded
        matched, ambiguous_left, examples = match(price_rows, catalog_rows)
        total_matched += matched; total_rows += len(catalog_rows)
        print(f'{eqid}: {matched}/{len(catalog_rows)} позиций получили цену '
              f'(ещё {ambiguous_left} — номер похож, но название не подтвердило, цена НЕ назначена)')
        for num, cname, pname, price in examples[:5]:
            print(f'    {num}  «{cname}» ~ «{pname}»  ->  {price:,.2f} ₽'.replace(',', ' '))
        json.dump(units, open(os.path.join(a.outdir, '.build', f'{eqid}.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, separators=(',', ':'))

    print(f'\nИТОГО: {total_matched}/{total_rows} позиций каталога получили подтверждённую цену '
          f'({total_matched/total_rows*100:.0f}%)')
    print('Кэш .build/*.json обновлён. Теперь пересоберите index.html '
          '(build_catalog.py с теми же PDF — попадёт в кэш и подхватит цены).')

if __name__ == '__main__':
    main()
