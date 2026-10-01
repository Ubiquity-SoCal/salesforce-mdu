/**
 * Builds the Word document for the MDU / AVR / California summary.
 *
 * Reads SalesForce/data/output/2026-09-28-mdu-avr-ca-summary.json (written by
 * the Python script of the same name) and writes the .docx to Koa's Desktop.
 *
 *   node 2026-09-28-mdu-avr-ca-summary-docx.js
 *
 * `docx` is deliberately NOT installed in this repo, so no node_modules tree
 * lands inside the SalesForce submodule. Install it somewhere scratch and point
 * NODE_PATH at it:
 *
 *   npm install docx --prefix /tmp/docxbuild
 *   NODE_PATH=/tmp/docxbuild/node_modules node 2026-09-28-...-docx.js
 *
 * House rules: no em dashes, tables carry columnWidths AND per-cell widths in
 * DXA, and the wide by-state table gets its own landscape section.
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageOrientation,
} = require("docx");

const SF_ROOT = path.resolve(__dirname, "..", "..");
const DATA = path.join(SF_ROOT, "data", "output",
  "2026-09-28-mdu-avr-ca-summary.json");
const DESKTOP = "C:\\Users\\cass\\OneDrive - Ubiquity Management\\Desktop";
const OUT = path.join(DESKTOP, "Salesforce MDU and AVR Summary 2026-09-28.docx");

const d = JSON.parse(fs.readFileSync(DATA, "utf8"));
const n = (x) => (x === null || x === undefined ? "" : x.toLocaleString("en-US"));

const PORTRAIT = 9360;   // Letter, 1in margins
const LANDSCAPE = 12960; // Letter landscape, 1in margins
const INK = "1A1A1A";
const MUTED = "5A5A5A";
const HEAD_BG = "EDF1F5";
const YTD_BG = "F7FAFC";
const RULE = "C9D2DB";

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 300, after: 120 },
    children: [new TextRun({ text, bold: true, size: 26, color: INK })],
  });
}
function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after === undefined ? 120 : opts.after },
    children: [new TextRun({
      text, size: opts.size || 20,
      color: opts.color || INK, italics: !!opts.italics,
    })],
  });
}
function bullet(text) {
  return new Paragraph({
    numbering: { reference: "dots", level: 0 },
    spacing: { after: 60 },
    children: [new TextRun({ text, size: 19, color: MUTED })],
  });
}

/**
 * Table with a shaded header. `widths` must sum to the section content width.
 * `shadeCols` gets the pale YTD tint so the 2026 columns read as a pair with
 * the all-time column beside them.
 */
function table(headers, rows, widths, aligns, shadeCols) {
  const b = { style: BorderStyle.SINGLE, size: 2, color: RULE };
  const shade = new Set(shadeCols || []);
  const cell = (text, i, isHead, isTotal) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: isHead
      ? { type: ShadingType.CLEAR, fill: HEAD_BG, color: "auto" }
      : (shade.has(i)
        ? { type: ShadingType.CLEAR, fill: YTD_BG, color: "auto" }
        : undefined),
    margins: { top: 50, bottom: 50, left: 80, right: 80 },
    children: [new Paragraph({
      alignment: (aligns && aligns[i] === "r")
        ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: [new TextRun({
        text: String(text), bold: !!isHead || !!isTotal,
        size: 18, color: INK,
      })],
    })],
  });
  return new Table({
    columnWidths: widths,
    width: { size: widths.reduce((a, x) => a + x, 0), type: WidthType.DXA },
    borders: { top: b, bottom: b, left: b, right: b },
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((t, i) => cell(t, i, true)),
      }),
      ...rows.map((r) => new TableRow({
        children: r.map((t, i) => cell(t, i, false,
          String(r[0]).toLowerCase() === "total")),
      })),
    ],
  });
}

const ca = d.california;
const body = [];

// ------------------------------------------------------------------- title
body.push(new Paragraph({
  spacing: { after: 40 },
  children: [new TextRun({
    text: "Salesforce MDU and AVR Summary",
    bold: true, size: 34, color: INK,
  })],
}));
body.push(new Paragraph({
  spacing: { after: 200 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: RULE } },
  children: [new TextRun({
    text: "28 September 2026. All figures from local snapshots, nothing pulled "
      + "live. Salesforce 2026-09-28, Vetro 2026-09-25, AVR cases 2026-09-11.",
    size: 19, color: MUTED,
  })],
}));

// ---------------------------------------------------------------- headline
body.push(h1("Headline"));
body.push(table(
  ["", "All time", "2026 YTD"],
  d.headline.map((h) => [h.metric, n(h.all_time), n(h.year)]),
  [5160, 2100, 2100], ["l", "r", "r"], [2]));

// --------------------------------------------------------------- MDU years
body.push(h1("MDU completions by year"));
body.push(table(
  ["Year signed", "Opportunities", "Units"],
  Object.entries(d.mdu.by_year).map(([y, v]) => [y, n(v.opps), n(v.units)]),
  [4360, 2500, 2500], ["l", "r", "r"]));
body.push(p(n(d.mdu.done_opps) + " completed of " + n(d.mdu.total_opps)
  + " MDU/SFU opportunities. Year is the latest signed agreement on the "
  + "opportunity, because CloseDate is auto-filled on insert and dates "
  + "creation, not completion.", { italics: true, color: MUTED }));

// ---------------------------------------------------------------- AVR
body.push(h1("AVRs, 2026 by month"));
const MON = { "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May",
  "06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct",
  "11": "Nov", "12": "Dec" };
const ms = Object.keys(d.avr.by_month).sort();
body.push(table(
  ["Month"].concat(ms.map((m) => MON[m.slice(5)])).concat(["Total"]),
  [["AVRs"].concat(ms.map((m) => n(d.avr.by_month[m])))
    .concat([n(d.avr.year)])],
  [1160].concat(ms.map(() => 800)).concat([1000]),
  ["l"].concat(ms.map(() => "r")).concat(["r"])));
body.push(p("September stops at the 11th, which is when the AVR case pull was "
  + "taken. AVRs are Salesforce Cases and the nightly index does not carry "
  + "them.", { italics: true, color: MUTED }));

// ---------------------------------------------------------------- CA
body.push(h1("California"));
body.push(p("Homes passed has no year dimension: it is a point-in-time state. "
  + "Vetro gives two signals and they disagree, so both are shown."));
body.push(table(
  ["Measure", "Addresses", "What it means"],
  [
    ["Service locations", n(ca.service_locations), "Everything Vetro holds in CA"],
    ["Serviceable", n(ca.addrstatus.serviceable),
      "Vetro says sellable. A planning designation, not a build record."],
    ["As-built fiber", n(ca.as_built),
      "Fiber drawn in the AsBuilt plan. Sparse where as-builts were never uploaded."],
    ["Future serviceable", n(ca.addrstatus.future_serviceable), "Designed, planned for later"],
    ["Serviceable on demand", n(ca.addrstatus.serviceable_on_demand), "Conduit without fiber"],
    ["Unserviceable", n(ca.addrstatus.unserviceable), "Usually a missing agreement"],
  ],
  [2200, 1400, 5760], ["l", "r", "l"]));
body.push(p("Two thirds of the serviceable addresses carry no as-built "
  + "geometry, so neither number is \"homes passed\" on its own.",
{ italics: true, color: MUTED }));

const actAddrAll = Object.values(ca.activation_by_year)
  .reduce((a, v) => a + v.addresses, 0);
body.push(table(
  ["Activations", "All time", "2026 YTD"],
  [
    ["Addresses activated: Ting drop completed " + n(ca.ting_drop)
      + " plus FiberFirst active " + n(ca.ff_active),
    n(ca.activations_total), "no date held"],
    ["Serving areas activated, of " + n(ca.serving_areas),
      n(ca.areas_activated), n(ca.areas_activated_2026)],
    ["Addresses inside those serving areas", n(actAddrAll),
      n(ca.addresses_activated_2026)],
  ],
  [5160, 2100, 2100], ["l", "r", "r"], [2]));

body.push(table(
  ["City", "Addresses", "Serviceable", "As-built", "Activated"],
  ca.by_city.map((c) => [c.city, n(c.addresses), n(c.serviceable),
    n(c.as_built), n(c.activations)]),
  [2760, 1650, 1650, 1650, 1650], ["l", "r", "r", "r", "r"]));
body.push(p("Every activation sits in the four deal markets: Carlsbad, "
  + "Encinitas, Oceanside, Solana Beach.", { italics: true, color: MUTED }));

// ---------------------------------------------------------- notes
body.push(h1("Notes"));
body.push(bullet("MDU done means record type MDU/SFU at stage PAL/ROE "
  + "Complete, Marketing/Bulk In Progress or Marketing/Bulk Complete."));
body.push(bullet("Signed means agreement status Completed or Cancelled with a "
  + "signed date. Cancelled counts because it was still signed."));
body.push(bullet(n(d.mdu.done_undated) + " completed opportunities carry no "
  + "signed agreement, so they cannot be dated and sit outside the year split. "
  + "Units are present on " + n(d.mdu.with_unit_value) + " of "
  + n(d.mdu.done_opps) + ", so " + n(d.mdu.done_units) + " is a floor."));
// The by-state AVR all-time total is one short of the headline, and saying so
// is cheaper than leaving a reader to find it.
const avrPlaced = d.by_state.reduce((a, r) => a + r.avr, 0);
if (avrPlaced !== d.avr.all_time) {
  body.push(bullet("By-state AVRs total " + n(avrPlaced) + " against "
    + n(d.avr.all_time) + " overall: one 2025 case has a truncated state in "
    + "the request body. The 2026 column ties exactly."));
}
body.push(bullet("Rebuild: SalesForce/scripts/analysis/"
  + "2026-09-28-mdu-avr-ca-summary.py then the matching .js."));

// ------------------------------------------------- landscape: by state
const W = [1000].concat(Array(10).fill(1196));
const byState = [
  h1("Everything by state"),
  p("MDU and agreement columns are counts. Shaded columns are 2026 year to "
    + "date.", { italics: true, color: MUTED }),
  table(
    ["State", "MDUs done", "2026", "Units", "2026 units", "ROEs signed",
      "2026", "PALs signed", "2026", "AVRs", "2026"],
    d.by_state.map((r) => [
      r.state, n(r.mdu_done), n(r.mdu_done_2026), n(r.mdu_units),
      n(r.mdu_units_2026), n(r.roe_signed), n(r.roe_signed_2026),
      n(r.pal_signed), n(r.pal_signed_2026), n(r.avr), n(r.avr_2026),
    ]).concat([(() => {
      const s = (k) => d.by_state.reduce((a, r) => a + r[k], 0);
      return ["Total", n(s("mdu_done")), n(s("mdu_done_2026")),
        n(s("mdu_units")), n(s("mdu_units_2026")), n(s("roe_signed")),
        n(s("roe_signed_2026")), n(s("pal_signed")), n(s("pal_signed_2026")),
        n(s("avr")), n(s("avr_2026"))];
    })()]),
    W, ["l"].concat(Array(10).fill("r")), [2, 4, 6, 8, 10]),
];

const doc = new Document({
  numbering: {
    config: [{
      reference: "dots",
      levels: [{
        level: 0, format: "bullet", text: "\u2022",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 200 } } },
      }],
    }],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      children: body,
    },
    {
      properties: {
        page: {
          // Portrait dimensions plus LANDSCAPE: docx-js swaps them itself.
          size: { width: 12240, height: 15840,
            orientation: PageOrientation.LANDSCAPE },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      children: byState,
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("wrote " + OUT);
  console.log("  " + buf.length.toLocaleString() + " bytes");
});
