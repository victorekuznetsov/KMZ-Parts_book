/* Импорт данных из генератора catalog_book (tools/build_catalog.py) в формат
   единого каталога.

   Источник — рабочий кэш генератора, который восстанавливается из исходных PDF
   репозитория (см. README, «Полностью восстановить рабочий кэш»):
     ../catalog_book/data.js   window.CATALOG = {order, equip:{id:{label,title,units}}}
     ../catalog_book/img/*.jpg чертежи листов
   Результат — по одной машине на единицу оборудования:
     <машина>/data/parts.js    window.CATALOG = {chapters, sections}
     <машина>/drawings/*.jpg   те же чертежи, скопированные под машину

   Соответствие структур:
     equip           -> машина каталога
     units           -> разделы (узлы)
     plates          -> рисунки внутри раздела
     rows            -> позиции: pos->ref, num->pn, name->zh, qty->qty

   Узлы в каталогах КМЗ плоские, без глав. Группировать их по первым знакам
   номера узла бессмысленно (получается «Изделие 068000» на 38 разделов), а
   у WP17 номеров узлов нет вовсе, поэтому машина получает одну главу, а узлы
   идут в порядке документа — так же, как в исходном PDF и в catalog_book.

   Названия узлов WP17 приходят как «中文(English) (Русский)» — они
   разбираются: русское уходит в основное наименование, китайское с
   английским — во второстепенное (как двуязычные наименования у NHL).

   Запуск из корня репозитория:  node build/import_catalog_book.js
*/
"use strict";
var fs = require("fs");
var vm = require("vm");
var path = require("path");

var ROOT = path.resolve(__dirname, "..");
var SITE = ROOT;
var SRC = path.join(ROOT, "catalog_book");
var DATA = path.join(SRC, "data.js");
var IMG = path.join(SRC, "img");

if (!fs.existsSync(DATA)) {
  console.error("Нет " + path.relative(ROOT, DATA) + " — сначала соберите кэш генератора:");
  console.error('  python3 tools/build_catalog.py "БС-215+Каталог+запчастей.zip.001" --id bs215 --label "БС-215" --no-embed');
  console.error('  python3 tools/build_catalog.py "БС-230.00.00.000 РЭ2 Каталог запчастей.zip.001" --id bs230 --label "БС-230" --no-embed');
  console.error('  python3 tools/build_catalog.py "Каталог запчастей WP17 итог.pdf" --id wp17 --label "WP17" --no-embed');
  process.exit(1);
}

var ctx = { window: {} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(DATA, "utf8"), ctx, { filename: DATA });
var SRC_CAT = ctx.window.CATALOG;
if (!SRC_CAT || !SRC_CAT.equip) { console.error("В data.js нет window.CATALOG.equip"); process.exit(1); }

function norm(v) { return String(v == null ? "" : v).replace(/ /g, " ").trim(); }

// Код раздела: номер узла, если он есть, иначе порядковый номер узла.
// Коды должны быть уникальны внутри машины — это ключ навигации и ссылок.
function sectionCodes(units) {
  var used = {}, out = [];
  units.forEach(function (u, i) {
    var base = norm(u.num) || ("У" + ("00" + (i + 1)).slice(-3));
    var code = base, n = 2;
    while (used[code]) code = base + "-" + n++;
    used[code] = 1;
    out.push(code);
  });
  return out;
}

// Одна глава на машину: узлы каталогов КМЗ плоские (см. комментарий выше).
var CH_CODE = "01";
var CH_NAME = "Узлы и сборочные единицы";

// «中文(English) (Русский)» -> {ru, alt}. Если формат другой, имя как есть.
var TRI_RE = /^\s*([^()]*[\u4e00-\u9fff][^()]*)\(([^()]*)\)\s*\(([^()]*)\)\s*$/;
function splitName(raw) {
  var m = TRI_RE.exec(norm(raw));
  if (!m) return { ru: norm(raw), alt: "" };
  var ru = norm(m[3]), alt = norm(m[1]) + " · " + norm(m[2]);
  if (!ru) return { ru: norm(raw), alt: "" };
  // в исходнике русское наименование часто со строчной буквы
  return { ru: ru.charAt(0).toUpperCase() + ru.slice(1), alt: alt };
}

var report = [];
(SRC_CAT.order || Object.keys(SRC_CAT.equip)).forEach(function (id) {
  var e = SRC_CAT.equip[id];
  if (!e) return;
  var units = e.units || [];
  var codes = sectionCodes(units);

  var chapters = [{ code: CH_CODE, zh: CH_NAME, en: "" }];
  var sections = [];
  var imgs = {}, parts = 0, pns = {};

  units.forEach(function (u, i) {
    var figures = (u.plates || []).map(function (pl) {
      (pl.imgs || []).forEach(function (f) { imgs[f] = 1; });
      return {
        images: (pl.imgs || []).map(function (f) { return "drawings/" + f; }),
        parts: (pl.rows || []).map(function (r) {
          var pn = norm(r.num);
          if (pn) { parts++; pns[pn] = 1; }
          var nm = splitName(r.name);
          return {
            nc: "", ref: norm(r.pos), qty: norm(r.qty), pn: pn,
            zh: nm.ru, en: nm.alt, lvl: 0
          };
        })
      };
    });
    var un = splitName(u.name);
    sections.push({
      code: codes[i], chapter: CH_CODE, zh: un.ru, en: un.alt, figures: figures
    });
  });

  var mdir = path.join(SITE, id);
  fs.mkdirSync(path.join(mdir, "data"), { recursive: true });
  fs.mkdirSync(path.join(mdir, "drawings"), { recursive: true });
  fs.writeFileSync(path.join(mdir, "data", "parts.js"),
    "/* Состав " + (e.label || id) + ". Файл генерируется:\n" +
    "   node build/import_catalog_book.js (источник: catalog_book/data.js) */\n" +
    "window.CATALOG = " + JSON.stringify({
      title_en: e.label || id, title_ru: norm(e.title), chapters: chapters, sections: sections
    }) + ";\n");

  var copied = 0, missing = 0;
  Object.keys(imgs).forEach(function (f) {
    var from = path.join(IMG, f);
    if (!fs.existsSync(from)) { missing++; return; }
    fs.copyFileSync(from, path.join(mdir, "drawings", f));
    copied++;
  });

  report.push({
    id: id, label: e.label || id, chapters: chapters.length, sections: sections.length,
    parts: parts, pns: Object.keys(pns).length, imgs: copied, missing: missing
  });
});

console.log("Импорт из catalog_book/data.js:");
report.forEach(function (r) {
  console.log("  " + r.id + " (" + r.label + "): глав " + r.chapters + ", разделов " + r.sections +
    ", позиций с номером " + r.parts + ", уник. номеров " + r.pns +
    ", чертежей " + r.imgs + (r.missing ? " (не найдено: " + r.missing + ")" : ""));
});
console.log("Дальше: node build/gen_data.js");
