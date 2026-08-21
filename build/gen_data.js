/* Сборка данных единого каталога КМЗ из подпапок машин.
   Читает:
     build/machines.json        — описание парка и список машин
     <машина>/data/parts.js     — состав машины (window.CATALOG), см. import_xlsx.js
     *.xlsx в корне репозитория — прайс-листы (см. ниже)
   Пишет:
     data/app.js                — window.APP  (брендинг, ключи хранилища)
     data/catalogs.js           — window.MACHINES, window.CATALOGS
     data/prices.js             — window.PRICES_BY
     <машина>/data/prices.js    — window.PRICES (для родного каталога машины)

   Прайсы задаются явно в build/machines.json:
     priceCurrent — действующий прайс: цена в поле cp, столбец «Текущий»;
     priceAgreed  — прайс на согласование: цена в поле p, столбец «Несогласованный».
   Оба необязательны. Если ни один не задан, файлы ищутся по имени: с «на
   согласование» — как priceAgreed, любой другой .xlsx в корне — как
   priceCurrent (так было в каталоге NHL). В корне этого репозитория лежат и
   другие .xlsx (выгрузки номеров), поэтому явное указание надёжнее.

   Столбцы прайса распознаются по заголовку: артикул («Артикул» или
   «Номенклатурный номер»), цена, наименование, группа, взаимозаменяемый
   артикул, статус позиции.

   Запуск из корня репозитория:  node build/gen_data.js
*/
"use strict";
var fs = require("fs");
var vm = require("vm");
var path = require("path");
var readXlsx = require("./read_xlsx.js").readXlsx;

var ROOT = path.resolve(__dirname, "..");
var CFG = JSON.parse(fs.readFileSync(path.join(__dirname, "machines.json"), "utf8"));
var MACHINES = (CFG.machines || []).filter(function (m) { return m && m.id; });

function loadGlobal(file, name) {
  var ctx = { window: {} };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(file, "utf8"), ctx, { filename: file });
  return ctx.window[name];
}

// ---- прайс-листы ---------------------------------------------------------
function normArt(x) {
  if (x == null) return "";
  var s = String(x).replace(/ /g, " ").trim();
  if (/\.0$/.test(s)) s = s.slice(0, -2);
  return s;
}
function toPrice(x) {
  if (x == null || x === "") return null;
  var s = String(x).replace(/ /g, "").replace(/\s/g, "").replace(",", ".");
  var v = parseFloat(s);
  return isNaN(v) ? null : Math.round(v * 100) / 100;
}
// Ищет строку заголовка со столбцом «Артикул» и раскладывает остальные
// столбцы по названию; ключами карты становятся и артикул, и взаимозамена.
function buildPriceMap(rows) {
  function isArt(v) { return v === "артикул" || v.indexOf("номенклатурный номер") >= 0; }
  var hr = -1, col = { art: 0, xref: -1, name: -1, price: -1, group: -1, status: -1 };
  for (var i = 0; i < rows.length && hr < 0; i++) {
    var row = rows[i] || [];
    for (var c = 0; c < row.length; c++) {
      if (typeof row[c] === "string" && isArt(row[c].trim().toLowerCase())) { hr = i; break; }
    }
    if (hr === i) {
      row.forEach(function (cell, c2) {
        var v = (typeof cell === "string" ? cell : "").trim().toLowerCase();
        if (isArt(v)) col.art = c2;
        else if (v.indexOf("заменя") >= 0) col.xref = c2;
        else if (v.indexOf("наимен") >= 0) col.name = c2;
        else if (v.indexOf("цена") >= 0) col.price = c2;
        else if (v.indexOf("группа") >= 0) col.group = c2;
        else if (v.indexOf("статус") >= 0) col.status = c2;
      });
    }
  }
  if (hr < 0) throw new Error("не найден столбец «Артикул» / «Номенклатурный номер» в прайсе");
  function cellOf(rw, i) { return i >= 0 && rw[i] != null ? String(rw[i]).replace(/ /g, " ").trim() : ""; }
  var out = {};
  for (var r = hr + 1; r < rows.length; r++) {
    var rw = rows[r] || [], art = normArt(rw[col.art]);
    if (!art) continue;
    var rec = {
      p: toPrice(rw[col.price]),
      g: rw[col.group] != null ? String(rw[col.group]).replace(/ /g, " ").trim() : "",
      x: normArt(rw[col.xref]),
      n: rw[col.name] != null ? String(rw[col.name]).replace(/ /g, " ").trim() : ""
    };
    if (!(art in out)) out[art] = rec;
    if (rec.x && !(rec.x in out)) out[rec.x] = { p: rec.p, g: rec.g, x: rec.x, n: rec.n };
  }
  return out;
}

var xlsxFiles = fs.readdirSync(ROOT).filter(function (n) { return /\.xlsx$/i.test(n) && n[0] !== "~"; });
var agreedFile, curFile;
if (CFG.priceAgreed || CFG.priceCurrent) {          // задано явно
  agreedFile = CFG.priceAgreed || undefined;
  curFile = CFG.priceCurrent || undefined;
  [["priceAgreed", agreedFile], ["priceCurrent", curFile]].forEach(function (pair) {
    if (pair[1] && !fs.existsSync(path.join(ROOT, pair[1])))
      throw new Error("в build/machines.json " + pair[0] + " указывает на отсутствующий файл: " + pair[1]);
  });
} else {                                            // поиск по имени
  agreedFile = xlsxFiles.filter(function (n) { return /на\s*согласовани/i.test(n); })[0];
  curFile = xlsxFiles.filter(function (n) { return n !== agreedFile; })[0];
}
var PRICE_MAP = agreedFile ? buildPriceMap(readXlsx(path.join(ROOT, agreedFile))) : {};
var CUR_MAP = curFile ? buildPriceMap(readXlsx(path.join(ROOT, curFile))) : {};
console.log(agreedFile
  ? "Прайс на согласование: " + agreedFile + " — записей: " + Object.keys(PRICE_MAP).length
  : "Прайс на согласование не найден (файл «...на согласование....xlsx» в корне) — столбец «Несогласованный» пуст");
console.log(curFile
  ? "Действующий прайс: " + curFile + " — записей: " + Object.keys(CUR_MAP).length
  : "Действующий прайс не найден — столбец «Текущий» пуст");

// ---- каталоги машин ------------------------------------------------------
// Пути к чертежам в <машина>/data/parts.js даны относительно папки машины;
// в общем каталоге они должны быть относительно корня сайта.
function rewriteImages(catalog, base) {
  (catalog.sections || []).forEach(function (s) {
    (s.figures || []).forEach(function (f) {
      f.images = (f.images || []).map(function (img) {
        if (!img) return img;
        if (/^(https?:)?\/\//.test(img) || img.indexOf(base + "/") === 0) return img;
        return base + "/" + img;
      });
    });
  });
  return catalog;
}

var CATALOGS = {};
var PRICES_BY = {};
var stats = [];
var machinesOut = [];

MACHINES.forEach(function (m) {
  var dir = path.join(ROOT, m.id, "data");
  var file = path.join(dir, "parts.js");
  if (!fs.existsSync(file)) {
    console.warn("! пропущена машина " + m.id + ": нет файла " + path.relative(ROOT, file));
    return;
  }
  var cat = loadGlobal(file, "CATALOG") || { chapters: [], sections: [] };
  rewriteImages(cat, m.id);

  CATALOGS[m.id] = { chapters: cat.chapters || [], sections: cat.sections || [] };
  machinesOut.push({
    id: m.id,
    name: m.name || m.id,
    subtitle: m.subtitle || "",
    currency: m.currency || "RUB",
    hashPrefix: m.hashPrefix || "#",
    nativeUrl: m.nativeUrl || "",
    nativeLabel: m.nativeLabel || "",
    title_en: cat.title_en || m.name || m.id,
    title_ru: cat.title_ru || "",
    driveChapters: m.driveChapters || [],
    enginePdfChapters: m.enginePdfChapters || [],
    engineEpcChapters: m.engineEpcChapters || [],
    engineSite: m.engineSite || "",
    engineLabel: m.engineLabel || ""
  });

  // цены только по номерам, которые реально есть в каталоге, — карта остаётся мелкой
  var prices = {}, total = 0, priced = 0, pricedCur = 0, seen = {};
  (cat.sections || []).forEach(function (s) {
    (s.figures || []).forEach(function (f) {
      (f.parts || []).forEach(function (p) {
        if (!p.pn || seen[p.pn]) return;
        seen[p.pn] = 1; total++;
        var rec = PRICE_MAP[normArt(p.pn)];
        var curRec = CUR_MAP[normArt(p.pn)] || (rec && rec.x && CUR_MAP[rec.x]);
        if (!rec && !curRec) return;
        var cp = curRec ? curRec.p : null;
        rec = rec || { p: null, g: curRec.g, x: curRec.x, n: curRec.n, st: curRec.st };
        prices[p.pn] = { p: rec.p, g: rec.g, x: rec.x, n: rec.n, cp: cp,
                         st: rec.st || (curRec && curRec.st) || "" };
        if (rec.p != null) priced++;
        if (cp != null) pricedCur++;
      });
    });
  });
  PRICES_BY[m.id] = prices;
  fs.writeFileSync(path.join(dir, "prices.js"), "window.PRICES = " + JSON.stringify(prices) + ";\n");

  stats.push(m.id + ": уник. номеров " + total +
    ", с несогласованной ценой " + priced + (total ? " (" + Math.round(priced / total * 100) + "%)" : "") +
    ", с текущей " + pricedCur);
});

// ---- запись --------------------------------------------------------------
fs.mkdirSync(path.join(ROOT, "data"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "data", "app.js"),
  "/* Брендинг и ключи хранилища единого каталога.\n" +
  "   Файл генерируется: node build/gen_data.js (источник — build/machines.json). */\n" +
  "window.APP = " + JSON.stringify({
    key: CFG.key || "kmz",
    brand: CFG.brand || "КМЗ",
    fleet: CFG.fleet || "Всё оборудование КМЗ",
    filePrefix: CFG.filePrefix || CFG.brand || "КМЗ",
    currency: CFG.currency || "RUB",
    landingText: CFG.landingText || ""
  }, null, 2) + ";\n");
fs.writeFileSync(path.join(ROOT, "data", "catalogs.js"),
  "/* Состав каталогов всех машин. Файл генерируется: node build/gen_data.js */\n" +
  "window.MACHINES = " + JSON.stringify(machinesOut) + ";\n" +
  "window.CATALOGS = " + JSON.stringify(CATALOGS) + ";\n");
fs.writeFileSync(path.join(ROOT, "data", "prices.js"),
  "/* Цены по машинам. Файл генерируется: node build/gen_data.js */\n" +
  "window.PRICES_BY = " + JSON.stringify(PRICES_BY) + ";\n");

console.log("Записано: data/app.js, data/catalogs.js, data/prices.js и <машина>/data/prices.js");
console.log("Машин в каталоге: " + machinesOut.length);
stats.forEach(function (s) { console.log("  " + s); });
if (!machinesOut.length) {
  console.log("\nНи одной машины не собрано. Проверьте build/machines.json и наличие");
  console.log("файлов <машина>/data/parts.js — см. README.md, раздел «Загрузка данных».");
}
