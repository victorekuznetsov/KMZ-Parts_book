#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_standalone.py — упаковать собранный каталог в ОДИН html-файл для раздачи.

Берёт data.js + img/*.jpg из папки сборки и встраивает все чертежи как
data:-URI прямо в html-шаблон (tools/viewer.html). Получателю не нужны ни
Python, ни распаковка zip с сохранением структуры папок, ни отдельная папка
рядом — единственный .html открывается двойным кликом в любом браузере.

build_catalog.py вызывает эту упаковку автоматически при каждой сборке
(результат кладётся прямо в <outdir>/index.html — тот же файл, на который
уже могут вести внешние ссылки/закладки). Отдельно эта команда нужна, только
если хочется получить копию с другим именем/расположением.

Использование:
    python3 tools/pack_standalone.py
    python3 tools/pack_standalone.py --dir catalog_book -o "Каталог.html"
"""
import argparse, base64, json, os, re, sys

def pack(build_dir='catalog_book', out=None, template=None):
    """Встроить чертежи из <build_dir>/img в <build_dir>/data.js и записать
    самодостаточный html в out (по умолчанию <build_dir>/index.html).
    Возвращает (out_path, размер_МБ, кол-во_встроенных, кол-во_отсутствующих)."""
    data_path = os.path.join(build_dir, 'data.js')
    img_dir = os.path.join(build_dir, 'img')
    if template is None:
        template = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer.html')
    for p in (data_path, img_dir, template):
        if not os.path.exists(p):
            raise FileNotFoundError(f'не найдено: {p}')

    html = open(template, encoding='utf-8').read()
    data_js = open(data_path, encoding='utf-8').read()

    m = re.search(r'window\.CATALOG=(.*);\s*$', data_js.strip(), re.S)
    if not m:
        raise ValueError('не удалось разобрать data.js — формат не совпадает с ожидаемым')
    catalog = json.loads(m.group(1))

    names = set()
    for eq in catalog['equip'].values():
        for u in eq['units']:
            for pl in u['plates']:
                names.update(pl['imgs'])

    assets = {}
    missing = []
    for name in sorted(names):
        fp = os.path.join(img_dir, name)
        if not os.path.exists(fp):
            missing.append(name); continue
        with open(fp, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        assets[name] = 'data:image/jpeg;base64,' + b64

    assets_js = json.dumps(assets, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = html.replace('<script src="data.js"></script>', '')
    inline = f'<script>window.CATALOG={m.group(1)};\nwindow.CATALOG_ASSETS={assets_js};</script>\n'
    html = html.replace('<noscript>', inline + '<noscript>', 1)

    out = out or os.path.join(build_dir, 'index.html')
    open(out, 'w', encoding='utf-8').write(html)
    return out, os.path.getsize(out) / 1024 / 1024, len(assets), missing

def main():
    ap = argparse.ArgumentParser(description='Упаковать каталог в один самодостаточный html-файл')
    ap.add_argument('--dir', default='catalog_book', help='папка сборки (data.js+img/)')
    ap.add_argument('-o', '--out', default=None, help='выходной html (по умолчанию <dir>/index.html)')
    a = ap.parse_args()
    try:
        out, mb, n, missing = pack(a.dir, a.out)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f'{e} — сначала выполните tools/build_catalog.py')
    if missing:
        print(f'! предупреждение: {len(missing)} изображений не найдено (пропущены): {missing[:5]}…')
    print(f'Готово: {out}  ({mb:.1f} МБ, изображений встроено: {n})')
    print('Файл полностью самодостаточен — можно отправлять как есть, без zip и без Python.')

if __name__ == '__main__':
    main()
