/* Импорт состава машины из таблицы Excel в <машина>/data/parts.js.

   Запуск из корня репозитория:
     node build/import_xlsx.js <машина> [файл.xlsx]

   Если файл не указан, берётся первый .xlsx в папке <машина>/.

   Формат таблицы (первая строка — заголовки, порядок столбцов любой,
   распознаются по названию; регистр и лишние пробелы не важны):

     Глава            код главы, напр. 020
     Глава-название   наименование главы (можно оставить пустым — возьмётся
                      из первой встреченной строки этой главы)
     Раздел           код раздела, напр. 020-0010
     Раздел-название  наименование раздела
     Рисунок          номер рисунка внутри раздела (по умолчанию 1)
     Чертёж           имя файла чертежа; несколько — через запятую или «;».
                      Путь достраивается как drawings/<имя>, если он не указан
     Поз.             номер позиции на чертеже
     Номер детали     каталожный артикул
     Наименование     наименование позиции (русское или английское)
     Наименование EN  наименование на английском (необязательно)
     Кол-во           количество на схеме
     Уровень          уровень вложенности позиции: 0, 1, 2 (необязательно)
     Примечание       примечание к позиции (необязательно)

   Строки без кода раздела пропускаются. Позиции без номера детали
   сохраняются (это подзаголовки и справочные строки чертежа), но не попадают
   ни в заказ, ни в выгрузки номеров.
*/
"use strict";
var fs = require("fs");
var path = require("path");
var readXlsx = require("./read_xlsx.js").readXlsx;

var ROOT = path.resolve(__dirname, "..");
var machineId = process.argv[2];
if (!machineId) {
  console.error("Использование: node build/import_xlsx.js <машина> [файл.xlsx]");
  process.exit(1);
}
var mdir = path.join(ROOT, machineId);
if (!fs.existsSync(mdir)) {
  console.error("Нет папки машины: " + path.relative(ROOT, mdir));
  process.exit(1);
}
var src = process.argv[3]
  ? path.resolve(process.argv[3])
  : (function () {
      var f = fs.readdirSync(mdir).filter(function (n) { return /\.xlsx$/i.test(n) && n[0] !== "~"; })[0];
      return f ? path.join(mdir, f) : null;
    })();
if (!src || !fs.existsSync(src)) {
  console.error("Не найден .xlsx с составом машины. Положите его в " + machineId + "/ " +
    "или укажите путь вторым аргументом.");
  process.exit(1);
}

// ---- разбор заголовков ---------------------------------------------------
var ALIASES = {
  chapter:     ["глава", "chapter", "группа"],
  chapterName: ["глава-название", "название главы", "chapter name"],
  section:     ["раздел", "section", "узел"],
  sectionName: ["раздел-название", "название раздела", "section name", "наименование раздела"],
  figure:      ["рисунок", "figure", "рис", "рис."],
  image:       ["чертёж", "чертеж", "drawing", "image", "схема"],
  ref:         ["поз.", "поз", "позиция", "ref", "№"],
  pn:          ["номер детали", "артикул", "part no", "part number", "pn"],
  name:        ["наименование", "название", "name"],
  nameEn:      ["наименование en", "name en", "english", "англ"],
  qty:         ["кол-во", "количество", "qty", "кол"],
  lvl:         ["уровень", "level", "lvl"],
  note:        ["примечание", "note", "nc"]
};
function norm(v) { return String(v == null ? "" : v).replace(/ /g, " ").trim(); }
function key(v) { return norm(v).toLowerCase().replace(/\s+/g, " "); }

var rows = readXlsx(src);
var hr = -1, col = {};
for (var i = 0; i < rows.length && hr < 0; i++) {
  var row = rows[i] || [], found = {};
  row.forEach(function (cell, c) {
    var k = key(cell);
    if (!k) return;
    Object.keys(ALIASES).forEach(function (f) {
      if (found[f] === undefined && ALIASES[f].indexOf(k) >= 0) found[f] = c;
    });
  });
  if (found.section !== undefined && (found.pn !== undefined || found.name !== undefined)) {
    hr = i; col = found;
  }
}
if (hr < 0) {
  console.error("Не найдена строка заголовков: нужны как минимум столбцы «Раздел» и " +
    "«Номер детали» (или «Наименование»). См. комментарий в начале этого файла.");
  process.exit(1);
}
function cell(row, f) { return col[f] === undefined ? "" : norm(row[col[f]]); }

// ---- сборка структуры ----------------------------------------------------
function imagePaths(raw) {
  if (!raw) return [];
  return raw.split(/[;,]/).map(function (x) { return x.trim(); }).filter(Boolean)
    .map(function (x) { return x.indexOf("/") >= 0 ? x : "drawings/" + x; });
}

var chapters = [], chapterSeen = {};
var sections = [], sectionByKey = {};
var skipped = 0, parts = 0;

for (var r = hr + 1; r < rows.length; r++) {
  var rw = rows[r] || [];
  var secCode = cell(rw, "section");
  if (!secCode) { skipped++; continue; }
  var chCode = cell(rw, "chapter") || secCode.split("-")[0];

  if (!chapterSeen[chCode]) {
    chapterSeen[chCode] = { code: chCode, zh: "", en: cell(rw, "chapterName") || chCode };
    chapters.push(chapterSeen[chCode]);
  } else if (!chapterSeen[chCode].en && cell(rw, "chapterName")) {
    chapterSeen[chCode].en = cell(rw, "chapterName");
  }

  var sec = sectionByKey[secCode];
  if (!sec) {
    sec = sectionByKey[secCode] = {
      code: secCode, chapter: chCode, zh: "", en: cell(rw, "sectionName") || secCode, figures: []
    };
    sections.push(sec);
  } else if (sec.en === secCode && cell(rw, "sectionName")) {
    sec.en = cell(rw, "sectionName");
  }

  var figNo = parseInt(cell(rw, "figure"), 10);
  if (isNaN(figNo) || figNo < 1) figNo = 1;
  while (sec.figures.length < figNo) sec.figures.push({ images: [], parts: [] });
  var fig = sec.figures[figNo - 1];

  imagePaths(cell(rw, "image")).forEach(function (p) {
    if (fig.images.indexOf(p) < 0) fig.images.push(p);
  });

  var lvl = parseInt(cell(rw, "lvl"), 10);
  fig.parts.push({
    nc: cell(rw, "note"),
    ref: cell(rw, "ref"),
    qty: cell(rw, "qty"),
    pn: cell(rw, "pn"),
    zh: cell(rw, "name"),
    en: cell(rw, "nameEn"),
    lvl: isNaN(lvl) ? 0 : lvl
  });
  parts++;
}

// рисунки без единой позиции и без чертежа — мусор от пустых строк таблицы
sections.forEach(function (s) {
  s.figures = s.figures.filter(function (f) { return (f.parts || []).length || (f.images || []).length; });
});

var out = { title_en: machineId.toUpperCase(), title_ru: "", chapters: chapters, sections: sections };
var dir = path.join(mdir, "data");
fs.mkdirSync(dir, { recursive: true });
fs.writeFileSync(path.join(dir, "parts.js"),
  "/* Состав машины " + machineId + ". Файл генерируется:\n" +
  "   node build/import_xlsx.js " + machineId + "  (источник: " + path.basename(src) + ") */\n" +
  "window.CATALOG = " + JSON.stringify(out) + ";\n");

var pns = {};
sections.forEach(function (s) {
  s.figures.forEach(function (f) { f.parts.forEach(function (p) { if (p.pn) pns[p.pn] = 1; }); });
});
console.log("Источник: " + path.relative(ROOT, src));
console.log("Записано: " + path.relative(ROOT, path.join(dir, "parts.js")));
console.log("  глав: " + chapters.length + ", разделов: " + sections.length +
  ", позиций: " + parts + ", уникальных номеров: " + Object.keys(pns).length +
  (skipped ? ", пропущено строк без раздела: " + skipped : ""));
console.log("Дальше: node build/gen_data.js");
