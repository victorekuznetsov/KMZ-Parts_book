#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Позиции прайс-листа, которых НЕТ в оцифрованных каталогах (БС-215/БС-230/WP17).

Использует тот же двойной ключ сопоставления «округлённый номер + наименование»,
что и apply_prices.py (см. его про потерю точности номера в исходном .xlsx).
Строка прайса считается «есть в каталоге», только если совпали и номер, и имя;
остальные попадают в выгрузку. Достоверный идентификатор в результате — колонка
«Наименование» (содержит обозначение изделия), а не неточный числовой номер.

Запуск (из корня репозитория):  python3 tools/price_not_in_catalog.py
"""
import sys, os, json, re
HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)
sys.path.insert(0, HERE)
import openpyxl
from apply_prices import norm_name, split_price_name, lossy_key

PRICE=os.path.join(ROOT,'Прайс-лист.xlsx')
BUILD=os.path.join(ROOT,'catalog_book','.build')

# --- каталог: множество (lossy_key -> set нормализованных имён) ---
from collections import defaultdict
cat_by_key=defaultdict(set)
cat_numbers=set()
manifest=json.load(open(os.path.join(BUILD,'manifest.json'),encoding='utf-8'))
for eqid in manifest['order']:
    units=json.load(open(os.path.join(BUILD,f'{eqid}.json'),encoding='utf-8'))
    for u in units:
        for pl in u['plates']:
            for r in pl['rows']:
                if r['num'].isdigit():
                    cat_numbers.add(r['num'])
                    k=lossy_key(r['num'])
                    if k is not None:
                        cat_by_key[k].add(norm_name(r['name']))

print(f'Каталог: {len(cat_numbers)} уникальных номеров, {len(cat_by_key)} ключей')

# --- прайс-лист ---
wb=openpyxl.load_workbook(PRICE,data_only=True)
ws=wb['Прайс итоговый']
header=[c.value for c in next(ws.iter_rows(min_row=1,max_row=1))]

def name_match(pname, cnames):
    if not pname: return False
    for cn in cnames:
        if not cn: continue
        if pname==cn or pname in cn or cn in pname:
            return True
    return False

not_in=[]  # строки прайса без совпадения в каталоге
matched=0
for row in ws.iter_rows(min_row=2,values_only=True):
    num, name, unit, price, status = row[1], row[2], row[3], row[4], row[5]
    if num is None and name is None: continue
    pname=split_price_name(name)
    k=lossy_key(num) if num is not None else None
    is_in = k is not None and k in cat_by_key and name_match(pname, cat_by_key[k])
    if is_in:
        matched+=1
    else:
        # честное число: целое, без экспоненты (в файле оно всё равно потеряло хвост)
        try: num_str=str(int(float(num))) if num is not None else ''
        except (ValueError,TypeError): num_str=str(num or '')
        # категория достоверности
        nm=str(name or '')
        if re.match(r'\s*(68|173)[.\-]', nm):
            cat='Серия БС (проверить)'   # 68.xx/173.xx — может быть узел не из 3 каталогов ИЛИ промах точности
        else:
            cat='Иное оборуд./расходники' # другой станок, двигатель, компрессор, ГСМ — точно не в этих каталогах
        not_in.append([row[0], num_str, (str(name).strip() if name else ''),
                       (str(unit).strip() if unit else ''),
                       (price if price is not None else ''),
                       (str(status).strip() if status else ''), cat])

# сортировка: по цене убыв. (None в конец)
not_in.sort(key=lambda r: (-(r[4] if isinstance(r[4],(int,float)) else -1)))
print(f'Совпало с каталогом: {matched}')
print(f'НЕТ в каталогах: {len(not_in)}')
from collections import Counter
cc=Counter(r[6] for r in not_in)
for k,v in cc.items(): print(f'   {k}: {v}')

# --- выгрузка в xlsx (номенклатурный номер и цена — текстом/числом аккуратно) ---
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
out=Workbook(); wsx=out.active; wsx.title='Нет в каталогах'
HEAD=['№ п/п','Номенклатурный номер*','Наименование','Ед. изм.','Цена, руб. без НДС','Статус','Категория']
WIDTH=[8,26,52,10,20,14,24]
fill=PatternFill('solid',fgColor='2F4A63'); hf=Font(color='FFFFFF',bold=True)
thin=Side(style='thin',color='D0D4DA'); bd=Border(left=thin,right=thin,top=thin,bottom=thin)
wsx.append(HEAD)
for c in range(1,len(HEAD)+1):
    cell=wsx.cell(1,c); cell.fill=fill; cell.font=hf; cell.border=bd
    cell.alignment=Alignment(vertical='center',wrap_text=True)
for r in not_in:
    wsx.append(r)
for i,w in enumerate(WIDTH,1):
    wsx.column_dimensions[get_column_letter(i)].width=w
# номенклатурный номер как текст, цена как число
for row in wsx.iter_rows(min_row=2,max_row=wsx.max_row,max_col=len(HEAD)):
    for cell in row: cell.border=bd; cell.alignment=Alignment(vertical='top',wrap_text=True)
    row[1].number_format='@'
    if isinstance(row[4].value,(int,float)): row[4].number_format='#,##0.00'
wsx.freeze_panes='A2'
wsx.auto_filter.ref=f'A1:{get_column_letter(len(HEAD))}{wsx.max_row}'
# примечание внизу
note=wsx.max_row+2
wsx.cell(note,1,'* Номенклатурный номер в исходном прайс-листе хранится как число и теряет точность на длинных номерах — '
                'достоверным идентификатором служит колонка «Наименование» (содержит обозначение изделия). '
                'Каталоги для сравнения: БС-215, БС-230, WP17.')
wsx.cell(note,1).font=Font(italic=True,size=9,color='808080')
out.save(os.path.join(ROOT,'Прайс_нет_в_каталогах.xlsx'))
print('Сохранено: Прайс_нет_в_каталогах.xlsx')
