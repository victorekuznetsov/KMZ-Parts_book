#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_standalone.py — упаковать собранный каталог в ОДИН html-файл для раздачи.

Берёт catalog_book/ (index.html + data.js + img/*.jpg) и встраивает все
чертежи как data:-URI прямо в файл. Получателю не нужны ни Python, ни
распаковка zip с сохранением структуры папок — единственный .html открывается
двойным кликом в любом браузере и не зависит от соседних файлов.

Использование:
    python3 tools/pack_standalone.py
    python3 tools/pack_standalone.py -o "Каталог.html" --dir catalog_book
"""
import argparse, base64, json, os, re, sys

def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split('\n\n')[0])
    ap.add_argument('--dir', default='catalog_book', help='папка сборки (index.html+data.js+img/)')
    ap.add_argument('-o', '--out', default=None, help='имя выходного html (по умолчанию <dir>_standalone.html)')
    a = ap.parse_args()

    d = a.dir
    idx_path = os.path.join(d, 'index.html')
    data_path = os.path.join(d, 'data.js')
    img_dir = os.path.join(d, 'img')
    for p in (idx_path, data_path, img_dir):
        if not os.path.exists(p):
            sys.exit(f'не найдено: {p} — сначала выполните tools/build_catalog.py')

    html = open(idx_path, encoding='utf-8').read()
    data_js = open(data_path, encoding='utf-8').read()

    m = re.search(r'window\.CATALOG=(.*);\s*$', data_js.strip(), re.S)
    if not m:
        sys.exit('не удалось разобрать data.js — формат не совпадает с ожидаемым')
    catalog = json.loads(m.group(1))

    # какие файлы реально используются
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
    if missing:
        print(f'! предупреждение: {len(missing)} изображений не найдено (пропущены): {missing[:5]}…')

    assets_js = json.dumps(assets, ensure_ascii=False, separators=(',', ':'))
    assets_js = assets_js.replace('</', '<\\/')

    # убрать внешнюю ссылку на data.js — данные и картинки будут инлайн
    html = html.replace('<script src="data.js"></script>', '')
    inline = f'<script>window.CATALOG={m.group(1)};\nwindow.CATALOG_ASSETS={assets_js};</script>\n'
    html = html.replace('<noscript>', inline + '<noscript>', 1)

    out = a.out or (d.rstrip('/\\') + '_standalone.html')
    open(out, 'w', encoding='utf-8').write(html)
    size_mb = os.path.getsize(out) / 1024 / 1024
    print(f'Готово: {out}  ({size_mb:.1f} МБ, изображений встроено: {len(assets)})')
    print('Файл полностью самодостаточен — можно отправлять как есть, без zip и без Python.')

if __name__ == '__main__':
    main()
