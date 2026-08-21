/* Minimal .xlsx -> rows (array of arrays) reader for Node, no deps.
   Uses zlib.inflateRawSync for deflate entries. Exported for gen_prices.js. */
"use strict";
var fs = require("fs");
var zlib = require("zlib");

function readZipEntries(buf) {
  var i = buf.length - 22;
  for (; i >= 0; i--) if (buf.readUInt32LE(i) === 0x06054b50) break;
  if (i < 0) throw new Error("not a zip/xlsx");
  var count = buf.readUInt16LE(i + 10), off = buf.readUInt32LE(i + 16);
  var entries = {}, p = off;
  for (var n = 0; n < count; n++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) break;
    var method = buf.readUInt16LE(p + 10);
    var compSize = buf.readUInt32LE(p + 20);
    var nameLen = buf.readUInt16LE(p + 28);
    var extraLen = buf.readUInt16LE(p + 30);
    var commentLen = buf.readUInt16LE(p + 32);
    var lho = buf.readUInt32LE(p + 42);
    var name = buf.slice(p + 46, p + 46 + nameLen).toString("utf8");
    var lNameLen = buf.readUInt16LE(lho + 26), lExtraLen = buf.readUInt16LE(lho + 28);
    var start = lho + 30 + lNameLen + lExtraLen;
    var comp = buf.slice(start, start + compSize);
    entries[name] = method === 0 ? comp : zlib.inflateRawSync(comp);
    p += 46 + nameLen + extraLen + commentLen;
  }
  return entries;
}

function colIndex(ref) {
  var m = /^([A-Z]+)/.exec(ref || ""); if (!m) return 0;
  var s = m[1], n = 0;
  for (var i = 0; i < s.length; i++) n = n * 26 + (s.charCodeAt(i) - 64);
  return n - 1;
}

// tiny XML helpers via regex (sheets here are simple)
function parseSharedStrings(xml) {
  if (!xml) return [];
  var out = [];
  var siRe = /<si>([\s\S]*?)<\/si>/g, m;
  while ((m = siRe.exec(xml))) {
    var inner = m[1], txt = "", tm, tRe = /<t[^>]*>([\s\S]*?)<\/t>/g;
    while ((tm = tRe.exec(inner))) txt += tm[1];
    out.push(unescapeXml(txt));
  }
  return out;
}
function unescapeXml(s) {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/&amp;/g, "&");
}

function readXlsx(path) {
  var buf = fs.readFileSync(path);
  var entries = readZipEntries(buf);
  var dec = function (b) { return b ? b.toString("utf8") : null; };
  var shared = parseSharedStrings(dec(entries["xl/sharedStrings.xml"]));
  // find first worksheet
  var sheetName = Object.keys(entries).filter(function (k) {
    return /^xl\/worksheets\/sheet\d+\.xml$/.test(k);
  }).sort()[0] || "xl/worksheets/sheet1.xml";
  var sheetXml = dec(entries[sheetName]);
  var rows = [];
  var rowRe = /<row[^>]*>([\s\S]*?)<\/row>/g, rm;
  while ((rm = rowRe.exec(sheetXml))) {
    var cellsXml = rm[1], arr = [], cm;
    var cRe = /<c\s+([^>]*?)(\/>|>([\s\S]*?)<\/c>)/g;
    while ((cm = cRe.exec(cellsXml))) {
      var attrs = cm[1], body = cm[3] || "";
      var rRef = (/r="([^"]+)"/.exec(attrs) || [])[1] || "";
      var t = (/t="([^"]+)"/.exec(attrs) || [])[1] || "";
      var v = "";
      if (t === "s") {
        var vi = /<v>([\s\S]*?)<\/v>/.exec(body);
        if (vi) v = shared[parseInt(vi[1], 10)] || "";
      } else if (t === "inlineStr") {
        var ti = /<t[^>]*>([\s\S]*?)<\/t>/.exec(body);
        v = ti ? unescapeXml(ti[1]) : "";
      } else if (t === "str") {
        var vs = /<v>([\s\S]*?)<\/v>/.exec(body);
        v = vs ? unescapeXml(vs[1]) : "";
      } else {
        var ve = /<v>([\s\S]*?)<\/v>/.exec(body);
        v = ve ? ve[1] : "";
      }
      arr[colIndex(rRef)] = v;
    }
    rows.push(arr);
  }
  return rows;
}

module.exports = { readXlsx: readXlsx };

if (require.main === module) {
  var rows = readXlsx(process.argv[2]);
  console.log("rows:", rows.length);
  for (var i = 0; i < Math.min(8, rows.length); i++) console.log(i, JSON.stringify(rows[i]));
}
