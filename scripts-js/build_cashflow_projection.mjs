import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

// Paths are relative to the workspace root: input from scripts-py/fetch_cashflow_data.py, workbook to reports/.
const root = new URL("../", import.meta.url);
const source = JSON.parse(await fs.readFile(new URL("data/soupop_cashflow_source.json", root), "utf8"));
const outputPath = fileURLToPath(new URL("reports/Soupop BNPL Cash Flow Projection.xlsx", root));
const previewDir = fileURLToPath(new URL("data/cashflow-preview", root));
await fs.mkdir(previewDir, { recursive: true });

const M = (n) => (n ?? 0) / 1_000_000;
const monthKey = (value) => String(value).slice(0, 7);
const monthDate = (key) => new Date(`${key}-01T00:00:00Z`);
const addMonths = (key, n) => {
  const d = monthDate(key);
  d.setUTCMonth(d.getUTCMonth() + n);
  return d;
};
const keyFromDate = (d) => d.toISOString().slice(0, 7);
const col = (n) => {
  let out = "";
  for (let x = n; x > 0; x = Math.floor((x - 1) / 26)) out = String.fromCharCode(65 + ((x - 1) % 26)) + out;
  return out;
};

const navy = "#17365D";
const blue = "#1F4E78";
const teal = "#0F766E";
const green = "#2F855A";
const paleGreen = "#E2F0D9";
const paleBlue = "#D9EAF7";
const paleAmber = "#FFF2CC";
const paleRed = "#FCE4D6";
const lightGray = "#F3F6F9";
const border = "#D7E0EA";
const white = "#FFFFFF";
const money = '#,##0.0;(#,##0.0);-';
const percent = "0.0%";
const dateFmt = "mmm-yy";

const q287 = new Map(source.metabase_question_287_nmv.map(([m, value]) => [monthKey(m), M(value)]));
const q280 = new Map(source.metabase_question_280_ar.map(([m, due, paid]) => [monthKey(m), [M(due), M(paid)]]));
const q290 = new Map(source.metabase_question_290_cashflow.map(([m, merchant, sub, repay, net, cumulative]) => [monthKey(m), {
  merchant: Math.abs(M(merchant)), subscription: M(sub), repayment: M(repay), net: M(net), cumulative: M(cumulative),
}]));
const observed = new Map(source.monthly_actuals.map(([m, nmv, customer, first, later, cashout, net]) => [monthKey(m), {
  nmv: M(nmv), customer: M(customer), first: M(first), later: M(later), cashout: M(cashout), net: M(net),
}]));

const historicalMonths = Array.from(q287.keys()).filter((m) => m >= "2025-01" && m <= "2026-09");
const historicalRows = historicalMonths.map((m) => {
  const observedRow = observed.get(m) ?? { customer: 0, first: 0, later: 0, cashout: 0, net: 0 };
  const legacy = q290.get(m) ?? { merchant: 0, subscription: 0, repayment: 0, net: 0 };
  const ar = q280.get(m) ?? [0, 0];
  return [monthDate(m), q287.get(m) ?? 0, ar[0], observedRow.customer, observedRow.first, observedRow.later, legacy.merchant, observedRow.customer - legacy.merchant, legacy.subscription + legacy.repayment, observedRow.customer - (legacy.subscription + legacy.repayment)];
});

const forecastKeys = ["2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03"];
const allTargetKeys = ["2026-09", ...forecastKeys];
const targetNmv = new Map([
  ["2026-09", q287.get("2026-09")],
  ["2026-10", 4400], ["2026-11", 7000], ["2026-12", 12000],
  ["2027-01", 21250], ["2027-02", 33000], ["2027-03", 40500],
]);
const investor = new Map(allTargetKeys.map((m) => [m, m === "2026-10" ? 4000 : 0]));

const termMixRows = source.term_mix_by_invoice_month.map(([
  month, totalNmv, totalInvoices, linkedNmv, fourNmv, loanNmv, sixNmv, belowFourNmv,
  fourSharePair, loanSharePair, fourShareTotal, loanShareTotal, sixShareTotal,
  linkageCoverage, fourInvoices, loanInvoices, sixInvoices,
]) => ({
  month: monthKey(month), totalNmv: M(totalNmv), totalInvoices, linkedNmv: M(linkedNmv),
  fourNmv: M(fourNmv), loanNmv: M(loanNmv), sixNmv: M(sixNmv), belowFourNmv: M(belowFourNmv),
  fourSharePair, loanSharePair, fourShareTotal, loanShareTotal, sixShareTotal,
  linkageCoverage, fourInvoices, loanInvoices, sixInvoices,
}));
const latestTermMix = termMixRows.at(-1);
const fourMonthFourNmv = termMixRows.reduce((sum, r) => sum + r.fourNmv, 0);
const fourMonthLoanNmv = termMixRows.reduce((sum, r) => sum + r.loanNmv, 0);
const fourMonthLoanMix = fourMonthLoanNmv / (fourMonthFourNmv + fourMonthLoanNmv);
const termMixByMonth = new Map(termMixRows.map((r) => [r.month, r]));
const loanTermRows = source.loan_term_distribution
  .filter(([month, installmentCount]) => installmentCount !== 4)
  .map(([month, installmentCount, invoices, nmv, shareOfLinkedNmv]) => ({
    month: monthKey(month), installmentCount, invoices, nmv: M(nmv), shareOfLinkedNmv,
    shareOfLoanNmv: M(nmv) / termMixByMonth.get(monthKey(month)).loanNmv,
  }));
const productMix = {
  bnpl: latestTermMix.fourSharePair,
  loan: latestTermMix.loanSharePair,
};

const profileRaw = source.term_installment_profiles.map(([model, number, count, amount, rawShare, avgDays, medianDays, modelNmv, modelInvoices]) => ({
  model, number, count, amount: M(amount), rawShare, avgDays, medianDays,
  modelNmv: M(modelNmv), modelInvoices, dueOffset: Math.round(medianDays / 30),
}));
for (const p of profileRaw) p.usedShare = p.rawShare;
const profileByModel = new Map();
for (const p of profileRaw) {
  if (!profileByModel.has(p.model)) profileByModel.set(p.model, []);
  profileByModel.get(p.model).push(p);
}
const profileMultiple = new Map(Array.from(profileByModel, ([model, rows]) => [model, rows.reduce((sum, p) => sum + p.rawShare, 0)]));
const modelMixKey = (model) => model === "BNPL - 4 installments" ? "bnpl" : "loan";
const assumptionProfileStartRow = 32;
for (let i = 0; i < profileRaw.length; i += 1) profileRaw[i].assumptionRow = assumptionProfileStartRow + i;

const curveMap = new Map(source.collection_curve.map(([bucket, count, amount, share]) => [bucket, { count, amount: M(amount), share }]));
const curve = [
  curveMap.get("Due month or earlier").share,
  curveMap.get("+1 month").share,
  curveMap.get("+2 months").share,
  curveMap.get("+3 months").share,
  curveMap.get("+4 months or later").share,
];
const unpaidShare = curveMap.get("Unpaid as of cutoff").share;
const priorSix = source.merchant_share_ratio;
const cashOutRatio = priorSix.reduce((sum, row) => sum + Number(row[2]), 0) / priorSix.reduce((sum, row) => sum + Number(row[1]), 0);

const openingArRows = source.opening_ar.map(([bucket, count, amount]) => ({ bucket, count, amount: M(amount) }));
const bucketMonth = (bucket) => {
  if (!bucket.startsWith("Due in ")) return null;
  const match = bucket.match(/(Sep|Oct|Nov|Dec)-26|(Jan|Feb|Mar)-27/);
  if (!match) return null;
  const names = { Jan: 0, Feb: 1, Mar: 2, Sep: 8, Oct: 9, Nov: 10, Dec: 11 };
  const name = match[1] || match[2];
  const year = bucket.endsWith("-27") ? 2027 : 2026;
  return new Date(Date.UTC(year, names[name], 1));
};

function openingForecast(bucket, amount, key) {
  const due = bucketMonth(bucket);
  if (!due) return 0;
  const dueKey = keyFromDate(due);
  const shift = (Date.parse(`${key}-01T00:00:00Z`) - due.getTime()) / (30.5 * 24 * 3600 * 1000);
  const offset = Math.round(shift);
  if (dueKey === "2026-09") {
    const denom = 1 - curve[0];
    return offset >= 1 && offset <= 4 ? amount * curve[offset] / denom : 0;
  }
  return offset >= 0 && offset <= 4 ? amount * curve[offset] : 0;
}

const openingSchedule = openingArRows.map((r) => ({ ...r, cash: forecastKeys.map((key) => openingForecast(r.bucket, r.amount, key)) }));
const openingCash = forecastKeys.map((_, i) => openingSchedule.reduce((sum, r) => sum + r.cash[i], 0));

const targetCohortRows = [];
for (const cohort of forecastKeys) {
  for (const p of profileRaw) {
    const productShare = productMix[modelMixKey(p.model)];
    const cash = forecastKeys.map((key) => {
      const dueKey = keyFromDate(addMonths(cohort, p.dueOffset));
      const offset = Math.round((Date.parse(`${key}-01T00:00:00Z`) - Date.parse(`${dueKey}-01T00:00:00Z`)) / (30.5 * 24 * 3600 * 1000));
      if (p.number === 1) return key === dueKey ? targetNmv.get(cohort) * productShare * p.usedShare : 0;
      return offset >= 0 && offset <= 4 ? targetNmv.get(cohort) * productShare * p.usedShare * curve[offset] : 0;
    });
    targetCohortRows.push({ cohort, ...p, productShare, dueKey: keyFromDate(addMonths(cohort, p.dueOffset)), cash });
  }
}
const targetCash = forecastKeys.map((_, i) => targetCohortRows.reduce((sum, r) => sum + r.cash[i], 0));
const forecastCashOut = forecastKeys.map((key) => targetNmv.get(key) * cashOutRatio);
const forecastInvestor = forecastKeys.map((key) => investor.get(key));
const forecastCustomerCash = forecastKeys.map((_, i) => targetCash[i] + openingCash[i]);
const forecastTotalCashIn = forecastKeys.map((_, i) => forecastCustomerCash[i] + forecastInvestor[i]);
const forecastNet = forecastKeys.map((_, i) => forecastTotalCashIn[i] - forecastCashOut[i]);
const beginningCash = [];
const endingCash = [];
for (let i = 0; i < forecastKeys.length; i += 1) {
  beginningCash.push(i === 0 ? 0 : endingCash[i - 1]);
  endingCash.push(beginningCash[i] + forecastNet[i]);
}

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const assumptions = workbook.worksheets.add("Assumptions");
const build = workbook.worksheets.add("Projection Build");
const historical = workbook.worksheets.add("Historical Actuals");
const behavior = workbook.worksheets.add("Repayment Behavior");
const notes = workbook.worksheets.add("Source & Notes");

for (const s of [summary, assumptions, build, historical, behavior, notes]) s.showGridLines = false;
summary.tabColor = navy;
assumptions.tabColor = teal;
build.tabColor = blue;
historical.tabColor = "#C9B37E";
behavior.tabColor = "#7E9FBF";

function title(sheet, cell, text, width) {
  sheet.getRange(cell).values = [[text]];
  sheet.getRange(cell).format = { font: { bold: true, color: navy, size: 15 }, verticalAlignment: "center" };
  const [start] = cell.split(":");
  const row = start.match(/\d+/)[0];
  sheet.getRange(`C${row}:${width}${row}`).format.borders = { bottom: { style: "medium", color: navy } };
}
function header(range) {
  range.format = { fill: navy, font: { bold: true, color: white }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, borders: { preset: "inside", style: "thin", color: white } };
}
function section(range, color = paleBlue) {
  range.format = { fill: color, font: { bold: true, color: navy }, borders: { preset: "outside", style: "thin", color: border } };
}
function regular(range) {
  range.format = { font: { color: "#1F2937", size: 10 }, verticalAlignment: "center" };
}
function moneyRange(range) { range.format.numberFormat = money; }
function dateRange(range) { range.format.numberFormat = dateFmt; }

// Summary
title(summary, "C2", "Soupop BNPL Cash-Flow Projection", "K");
summary.getRange("C3").values = [["All values are Million Toman. Forecast starts 1-Oct-2026; September is actual. Cash receipts use gateway confirmed_at, not payment creation or due date."]];
summary.getRange("C3").format = { font: { italic: true, color: "#52616B", size: 10 } };
section(summary.getRange("C5:D5")); summary.getRange("C5:D5").values = [["Key planning inputs", "Value"]];
const totalOpeningAr = openingArRows.reduce((s, r) => s + r.amount, 0);
const overdueExcluded = openingArRows.find((r) => r.bucket === "Overdue before Sep-26")?.amount ?? 0;
summary.getRange("C6:D15").values = [
  ["September actual NMV", q287.get("2026-09")],
  ["September NMV target", 3000],
  ["September Loan share of total NMV", latestTermMix.loanShareTotal],
  ["September Loan share of linked model NMV", latestTermMix.loanSharePair],
  ["September exact six-installment share of total NMV", latestTermMix.sixShareTotal],
  ["Four-month weighted Loan mix", fourMonthLoanMix],
  ["Merchant cash-out ratio used", cashOutRatio],
  ["Opening linked AR at 30-Sep-26", totalOpeningAr],
  ["Overdue AR not forecast", overdueExcluded],
  ["Investor cash-in on 1-Oct-26", 4000],
];
moneyRange(summary.getRange("D6:D7"));
summary.getRange("D8:D12").format.numberFormat = percent;
summary.getRange("D13:D15").format.numberFormat = money;
summary.getRange("C6:C15").format = { fill: lightGray, font: { bold: true }, borders: { preset: "inside", style: "thin", color: border } };
summary.getRange("D6:D15").format.borders = { preset: "inside", style: "thin", color: border };
section(summary.getRange("F5:K5"), paleGreen); summary.getRange("F5:K5").values = [["Observed collection curve for installments 2+", "", "", "", "", ""]];
summary.getRange("F6:K6").values = [["Due month or earlier", "+1 month", "+2 months", "+3 months", "+4 months+", "Unpaid at cutoff"]];
header(summary.getRange("F6:K6"));
summary.getRange("F7:K7").values = [[curve[0], curve[1], curve[2], curve[3], curve[4], unpaidShare]];
summary.getRange("F7:K7").format.numberFormat = percent;
summary.getRange("F8:K9").values = [["Cohorts: due Oct-25 through Jun-26", "", "", "", "", ""], ["Confirmed cash is shifted by this curve; due date alone is not treated as cash receipt.", "", "", "", "", ""]];
summary.getRange("F8:K9").format = { font: { italic: true, color: "#52616B", size: 9 } };
section(summary.getRange("C17:K17"), paleBlue); summary.getRange("C17:K17").values = [["Six-month cash projection", "", "", "", "", "", "", "", ""]];
summary.getRange("C18:K18").values = [["Month", "Target NMV", "Customer cash-in", "Investor cash-in", "Total cash-in", "Cash-out", "Net cash flow", "Ending cash", "Additional cash needed"]];
header(summary.getRange("C18:K18"));
for (let i = 0; i < forecastKeys.length; i += 1) {
  const r = 19 + i; const pc = col(4 + i);
  summary.getRange(`C${r}:K${r}`).formulas = [[
    `='Projection Build'!${pc}$3`, `='Projection Build'!${pc}$4`, `='Projection Build'!${pc}$7`, `='Projection Build'!${pc}$8`, `='Projection Build'!${pc}$9`, `='Projection Build'!${pc}$10`, `='Projection Build'!${pc}$11`, `='Projection Build'!${pc}$13`, `='Projection Build'!${pc}$14`,
  ]];
}
dateRange(summary.getRange("C19:C24")); moneyRange(summary.getRange("D19:K24"));
summary.getRange("C18:K24").format.borders = { preset: "inside", style: "thin", color: border };
summary.getRange("I19:I24").conditionalFormats.add("cellIs", { operator: "lessThan", formula: 0, format: { fill: paleRed, font: { color: "#9C0006", bold: true } } });
summary.getRange("K19:K24").conditionalFormats.add("cellIs", { operator: "greaterThan", formula: 0, format: { fill: paleAmber, font: { color: "#7F6000", bold: true } } });

// Assumptions
title(assumptions, "C2", "Model Inputs and Assumptions", "I");
assumptions.getRange("C3:I3").values = [["Historical calibration feeds this schedule. Blue cells are editable planning inputs; raw historical values remain in the other tabs.", "", "", "", "", "", ""]];
assumptions.getRange("C3:I3").format = { font: { italic: true, color: "#52616B", size: 10 } };
section(assumptions.getRange("C5:I5")); assumptions.getRange("C5:I5").values = [["NMV plan", "", "", "", "", "", ""]];
assumptions.getRange("C6:I6").values = [allTargetKeys.map(monthDate)]; header(assumptions.getRange("C6:I6")); dateRange(assumptions.getRange("C6:I6"));
assumptions.getRange("B7:B8").values = [["NMV (Million Toman)"], ["Investor cash-in (Million Toman)"]];
assumptions.getRange("C7:I7").values = [allTargetKeys.map((m) => targetNmv.get(m))];
assumptions.getRange("C8:I8").values = [allTargetKeys.map((m) => investor.get(m))];
assumptions.getRange("C7:I8").format = { fill: paleAmber, font: { color: "#0070C0" } };
moneyRange(assumptions.getRange("C7:I8"));
assumptions.getRange("B10:D10").values = [["Cash-out and starting cash", "Value", "Basis"]]; header(assumptions.getRange("B10:D10"));
assumptions.getRange("B11:D12").values = [["Merchant cash-out / NMV", cashOutRatio, "Weighted actual Apr-Sep 2026"], ["Opening cash balance", 0, "Planning assumption: bank ledger balance not supplied"]];
assumptions.getRange("C11:C12").format = { fill: paleAmber, font: { color: "#0070C0" } }; assumptions.getRange("C11").format.numberFormat = percent; moneyRange(assumptions.getRange("C12"));
section(assumptions.getRange("B15:J15"), paleGreen); assumptions.getRange("B15:J15").values = [["Product mix derived from monthly NMV", "", "", "", "", "", "", "", ""]];
assumptions.getRange("B16:J16").values = [["Month", "Total NMV", "Linked NMV", "BNPL 4 NMV", "Loan NMV", "BNPL share of linked", "Loan share of linked", "Exact six share of total", "Linkage coverage"]]; header(assumptions.getRange("B16:J16"));
assumptions.getRange("B17:J20").values = termMixRows.map((r) => [monthDate(r.month), r.totalNmv, r.linkedNmv, r.fourNmv, r.loanNmv, r.fourSharePair, r.loanSharePair, r.sixShareTotal, r.linkageCoverage]);
dateRange(assumptions.getRange("B17:B20")); moneyRange(assumptions.getRange("C17:F20")); assumptions.getRange("G17:J20").format.numberFormat = percent;
assumptions.getRange("B16:J20").format.borders = { preset: "inside", style: "thin", color: border };
section(assumptions.getRange("B22:D22"), paleBlue); assumptions.getRange("B22:D22").values = [["Forecast product mix", "NMV share used", "Basis"]];
assumptions.getRange("B23:D27").values = [
  ["BNPL - 4 installments", null, "Residual after the Loan share"],
  ["Loan - non-4 installment terms", productMix.loan, "September observed share of linked model NMV"],
  ["Loan exact six-installment component", latestTermMix.sixNmv / latestTermMix.loanNmv, "September exact-six NMV divided by September Loan NMV"],
  ["BNPL scheduled installments / model NMV", profileMultiple.get("BNPL - 4 installments"), "Observed Jun-Sep schedule total; retained without normalization"],
  ["Loan scheduled installments / model NMV", profileMultiple.get("Loan - non-4 installment terms"), "Observed Jun-Sep schedule total; retained without normalization"],
];
assumptions.getRange("C23").formulas = [["=1-C24"]];
assumptions.getRange("C23:C27").format.numberFormat = percent;
assumptions.getRange("C24").format = { fill: paleAmber, font: { color: "#0070C0" } };
assumptions.getRange("B22:D27").format.borders = { preset: "inside", style: "thin", color: border };
section(assumptions.getRange("B29:I29"), paleGreen); assumptions.getRange("B29:I29").values = [["Installment profiles by product model", "", "", "", "", "", "", ""]];
assumptions.getRange("B30:I30").values = [["Product model", "Installment #", "Observed amount / model NMV", "Share used", "Median days to due", "Due-month offset", "Observed installments", "Model NMV"]]; header(assumptions.getRange("B30:I30"));
for (const p of profileRaw) {
  const r = p.assumptionRow;
  assumptions.getRange(`B${r}:I${r}`).values = [[p.model, p.number, p.rawShare, p.usedShare, p.medianDays, p.dueOffset, p.count, p.modelNmv]];
}
const profileEndRow = assumptionProfileStartRow + profileRaw.length - 1;
assumptions.getRange(`D${assumptionProfileStartRow}:E${profileEndRow}`).format.numberFormat = percent;
moneyRange(assumptions.getRange(`I${assumptionProfileStartRow}:I${profileEndRow}`));
assumptions.getRange(`B30:I${profileEndRow}`).format.borders = { preset: "inside", style: "thin", color: border };
assumptions.getRange(`E${assumptionProfileStartRow}:E${profileEndRow}`).format = { fill: paleAmber, font: { color: "#0070C0" } };
assumptions.getRange(`D${assumptionProfileStartRow}:D${profileEndRow}`).format.font = { color: green };
const curveStartRow = profileEndRow + 3;
assumptions.getRange(`B${curveStartRow}:D${curveStartRow}`).values = [["Collection curve for installments 2+", "Share", "Treatment"]]; header(assumptions.getRange(`B${curveStartRow}:D${curveStartRow}`));
const curveLabels = ["Due month or earlier", "+1 month", "+2 months", "+3 months", "+4 months or later", "Unpaid as of cutoff"];
for (let i = 0; i < curveLabels.length; i += 1) assumptions.getRange(`B${curveStartRow + 1 + i}:D${curveStartRow + 1 + i}`).values = [[curveLabels[i], i < 5 ? curve[i] : unpaidShare, i < 5 ? "Included in cash forecast" : "Not forecast as cash receipt"]];
assumptions.getRange(`C${curveStartRow + 1}:C${curveStartRow + 6}`).format.numberFormat = percent; assumptions.getRange(`B${curveStartRow}:D${curveStartRow + 6}`).format.borders = { preset: "inside", style: "thin", color: border };
const calibrationStartRow = curveStartRow + 9;
assumptions.getRange(`B${calibrationStartRow}:D${calibrationStartRow + 2}`).values = [["Calibration notes", "", ""], ["Product mix", "Four monthly cohorts: Jun-Sep 2026", "Forecast uses the latest September mix; the four-month weighted mix is a reference, not an override."], ["Confirmed timing", "Use confirmed_at", "Question 290 is retained for historical comparison but uses payment creation timing."]];
section(assumptions.getRange(`B${calibrationStartRow}:D${calibrationStartRow}`), paleBlue); assumptions.getRange(`B${calibrationStartRow + 1}:D${calibrationStartRow + 2}`).format = { wrapText: true, verticalAlignment: "top", font: { color: "#4B5563", size: 9 } };

// Projection build
title(build, "C2", "Cash Projection Build", "I");
build.getRange("C3:I3").values = [["Month", ...forecastKeys.map(monthDate)]]; header(build.getRange("C3:I3")); dateRange(build.getRange("D3:I3"));
build.getRange("C4:C14").values = [["Target NMV"], ["Opening AR collections"], ["New target-cohort collections"], ["Customer repayment cash-in"], ["Investor cash-in"], ["Total cash-in"], ["Merchant cash-out"], ["Net cash flow"], ["Beginning cash"], ["Ending cash"], ["Additional cash needed"]];
section(build.getRange("C4:C14"), paleBlue);
for (let i = 0; i < forecastKeys.length; i += 1) {
  const c = col(4 + i); const sourceC = col(4 + i);
  build.getRange(`${c}4`).formulas = [[`='Assumptions'!${sourceC}$7`]];
  build.getRange(`${c}5`).formulas = [[`=SUM(${col(5 + i)}20:${col(5 + i)}${19 + openingSchedule.length})`]];
  build.getRange(`${c}6`).formulas = [[`=SUM(${col(10 + i)}39:${col(10 + i)}${38 + targetCohortRows.length})`]];
  build.getRange(`${c}7`).formulas = [[`=${c}5+${c}6`]];
  build.getRange(`${c}8`).formulas = [[`='Assumptions'!${sourceC}$8`]];
  build.getRange(`${c}9`).formulas = [[`=${c}7+${c}8`]];
  build.getRange(`${c}10`).formulas = [[`=${c}4*'Assumptions'!$C$11`]];
  build.getRange(`${c}11`).formulas = [[`=${c}9-${c}10`]];
  build.getRange(`${c}12`).formulas = [[i === 0 ? "='Assumptions'!$C$12" : `=${col(3 + i)}13`]];
  build.getRange(`${c}13`).formulas = [[`=${c}12+${c}11`]];
  build.getRange(`${c}14`).formulas = [[`=IF(${c}13<0,-${c}13,0)`]];
}
moneyRange(build.getRange("D4:I14")); build.getRange("C4:I14").format.borders = { preset: "inside", style: "thin", color: border };
build.getRange("D13:I13").conditionalFormats.add("cellIs", { operator: "lessThan", formula: 0, format: { fill: paleRed, font: { color: "#9C0006", bold: true } } });
build.getRange("D14:I14").conditionalFormats.add("cellIs", { operator: "greaterThan", formula: 0, format: { fill: paleAmber, font: { color: "#7F6000", bold: true } } });
section(build.getRange("C18:I18"), paleGreen); build.getRange("C18:I18").values = [["Opening AR collections from linked, unpaid installments", "", "", "", "", "", ""]];
build.getRange("C19:J19").values = [["Due bucket", "Outstanding AR", ...forecastKeys.map(monthDate)]]; header(build.getRange("C19:J19")); dateRange(build.getRange("E19:J19"));
for (let i = 0; i < openingSchedule.length; i += 1) {
  const r = 20 + i; const item = openingSchedule[i];
  build.getRange(`C${r}:D${r}`).values = [[item.bucket, item.amount]];
  for (let j = 0; j < forecastKeys.length; j += 1) build.getRange(`${col(5 + j)}${r}`).formulas = [[`=${col(4)}${r}*${item.amount === 0 ? 0 : (item.cash[j] / item.amount)}`]];
}
moneyRange(build.getRange(`D20:J${19 + openingSchedule.length}`)); build.getRange(`C19:J${19 + openingSchedule.length}`).format.borders = { preset: "inside", style: "thin", color: border };
build.getRange(`C${20 + openingSchedule.length}:D${21 + openingSchedule.length}`).values = [["AR note", "Overdue recovery excluded"], ["AR method", "Due month shifted using confirmed_at curve"]];
build.getRange(`C${20 + openingSchedule.length}:D${21 + openingSchedule.length}`).format = { font: { italic: true, color: "#52616B", size: 9 } };
const cohortHeaderRow = 35; const cohortStart = 39;
section(build.getRange(`C${cohortHeaderRow}:O${cohortHeaderRow}`), paleBlue); build.getRange(`C${cohortHeaderRow}:O${cohortHeaderRow}`).values = [["Cash from October-March NMV cohorts by product model", "", "", "", "", "", "", "", "", "", "", "", ""]];
build.getRange(`C${cohortHeaderRow + 1}:O${cohortHeaderRow + 1}`).values = [["Cohort month", "Target NMV", "Product model", "Model NMV share", "Installment #", "Installment share", "Due month", ...forecastKeys.map(monthDate)]]; header(build.getRange(`C${cohortHeaderRow + 1}:O${cohortHeaderRow + 1}`)); dateRange(build.getRange(`C${cohortHeaderRow + 1}:C${cohortHeaderRow + 1}`)); dateRange(build.getRange(`I${cohortHeaderRow + 1}:I${cohortHeaderRow + 1}`)); dateRange(build.getRange(`J${cohortHeaderRow + 1}:O${cohortHeaderRow + 1}`));
for (let i = 0; i < targetCohortRows.length; i += 1) {
  const r = cohortStart + i; const item = targetCohortRows[i];
  const targetColumn = col(4 + forecastKeys.indexOf(item.cohort));
  const mixRow = item.model === "BNPL - 4 installments" ? 23 : 24;
  build.getRange(`C${r}`).values = [[monthDate(item.cohort)]];
  build.getRange(`D${r}`).formulas = [[`='Assumptions'!${targetColumn}$7`]];
  build.getRange(`E${r}`).values = [[item.model]];
  build.getRange(`F${r}`).formulas = [[`='Assumptions'!$C$${mixRow}`]];
  build.getRange(`G${r}`).values = [[item.number]];
  build.getRange(`H${r}`).formulas = [[`='Assumptions'!$E$${item.assumptionRow}`]];
  build.getRange(`I${r}`).values = [[monthDate(item.dueKey)]];
  for (let j = 0; j < forecastKeys.length; j += 1) {
    const rate = item.number === 1 ? (keyFromDate(addMonths(item.cohort, item.dueOffset)) === forecastKeys[j] ? 1 : 0) : (() => {
      const d = Math.round((Date.parse(`${forecastKeys[j]}-01T00:00:00Z`) - Date.parse(`${item.dueKey}-01T00:00:00Z`)) / (30.5 * 24 * 3600 * 1000));
      return d >= 0 && d <= 4 ? curve[d] : 0;
    })();
    build.getRange(`${col(10 + j)}${r}`).formulas = [[`=$D${r}*$F${r}*$H${r}*${rate}`]];
  }
}
dateRange(build.getRange(`C${cohortStart}:C${cohortStart + targetCohortRows.length - 1}`)); moneyRange(build.getRange(`D${cohortStart}:D${cohortStart + targetCohortRows.length - 1}`)); build.getRange(`F${cohortStart}:F${cohortStart + targetCohortRows.length - 1}`).format.numberFormat = percent; build.getRange(`H${cohortStart}:H${cohortStart + targetCohortRows.length - 1}`).format.numberFormat = percent; dateRange(build.getRange(`I${cohortStart}:I${cohortStart + targetCohortRows.length - 1}`)); moneyRange(build.getRange(`J${cohortStart}:O${cohortStart + targetCohortRows.length - 1}`));
build.getRange(`C${cohortHeaderRow + 1}:O${cohortStart + targetCohortRows.length - 1}`).format.borders = { preset: "inside", style: "thin", color: border };

// Historical actuals
title(historical, "C2", "Historical Actuals and Timing Comparison", "L");
historical.getRange("C3:L3").values = [["Confirmed cash-in is based on gateway confirmed_at for items linked to eligible invoices. Question 290 is included as a reconciliation view because its cash timing uses gateway payment creation.", "", "", "", "", "", "", "", "", ""]];
historical.getRange("C3:L3").format = { font: { italic: true, color: "#52616B", size: 10 } };
historical.getRange("C5:L5").values = [["Month", "NMV", "Due installments", "Confirmed customer cash-in", "First installment", "Later installments", "Cash-out", "Revised net cash flow", "Question 290 cash-in", "Timing variance"]]; header(historical.getRange("C5:L5"));
historical.getRange(`C6:L${5 + historicalRows.length}`).values = historicalRows;
dateRange(historical.getRange(`C6:C${5 + historicalRows.length}`)); moneyRange(historical.getRange(`D6:L${5 + historicalRows.length}`)); historical.getRange(`C5:L${5 + historicalRows.length}`).format.borders = { preset: "inside", style: "thin", color: border };
historical.getRange(`L6:L${5 + historicalRows.length}`).conditionalFormats.add("cellIs", { operator: "notEqual", formula: 0, format: { fill: paleAmber, font: { color: "#7F6000" } } });

// Repayment behavior
title(behavior, "C2", "Repayment Behavior and Cohort Evidence", "L");
behavior.getRange("C3:L3").values = [["Product mix is based on invoice NMV. BNPL is the exact four-installment model; Loan is all non-four-installment terms and is disclosed by exact term below. Amounts are Million Toman.", "", "", "", "", "", "", "", "", ""]];
behavior.getRange("C3:L3").format = { font: { italic: true, color: "#52616B", size: 10 } };
section(behavior.getRange("C5:L5"), paleGreen); behavior.getRange("C5:L5").values = [["Four-month product mix by invoice NMV", "", "", "", "", "", "", "", "", ""]];
behavior.getRange("C6:L6").values = [["Month", "Total NMV", "Linked NMV", "BNPL 4 NMV", "Loan NMV", "BNPL share of linked", "Loan share of linked", "Exact six NMV", "Exact six share of total", "Linkage coverage"]]; header(behavior.getRange("C6:L6"));
behavior.getRange("C7:L10").values = termMixRows.map((r) => [monthDate(r.month), r.totalNmv, r.linkedNmv, r.fourNmv, r.loanNmv, r.fourSharePair, r.loanSharePair, r.sixNmv, r.sixShareTotal, r.linkageCoverage]);
dateRange(behavior.getRange("C7:C10")); moneyRange(behavior.getRange("D7:G10")); behavior.getRange("H7:I10").format.numberFormat = percent; moneyRange(behavior.getRange("J7:J10")); behavior.getRange("K7:L10").format.numberFormat = percent; behavior.getRange("C6:L10").format.borders = { preset: "inside", style: "thin", color: border };
section(behavior.getRange("C13:H13"), paleBlue); behavior.getRange("C13:H13").values = [["Exact Loan term distribution", "", "", "", "", ""]];
behavior.getRange("C14:H14").values = [["Month", "Max installments", "Invoices", "Loan NMV", "Share of Loan NMV", "Share of linked NMV"]]; header(behavior.getRange("C14:H14"));
behavior.getRange(`C15:H${14 + loanTermRows.length}`).values = loanTermRows.map((r) => [monthDate(r.month), r.installmentCount, r.invoices, r.nmv, r.shareOfLoanNmv, r.shareOfLinkedNmv]);
dateRange(behavior.getRange(`C15:C${14 + loanTermRows.length}`)); moneyRange(behavior.getRange(`F15:F${14 + loanTermRows.length}`)); behavior.getRange(`G15:H${14 + loanTermRows.length}`).format.numberFormat = percent; behavior.getRange(`C14:H${14 + loanTermRows.length}`).format.borders = { preset: "inside", style: "thin", color: border };
const productProfileStartRow = 17 + loanTermRows.length;
section(behavior.getRange(`C${productProfileStartRow}:J${productProfileStartRow}`), paleGreen); behavior.getRange(`C${productProfileStartRow}:J${productProfileStartRow}`).values = [["Observed repayment profile by product model", "", "", "", "", "", "", ""]];
behavior.getRange(`C${productProfileStartRow + 1}:J${productProfileStartRow + 1}`).values = [["Product model", "Installment #", "Observed amount / model NMV", "Share used", "Median days to due", "Due-month offset", "Installments", "Model NMV"]]; header(behavior.getRange(`C${productProfileStartRow + 1}:J${productProfileStartRow + 1}`));
behavior.getRange(`C${productProfileStartRow + 2}:J${productProfileStartRow + 1 + profileRaw.length}`).values = profileRaw.map((p) => [p.model, p.number, p.rawShare, p.usedShare, p.medianDays, p.dueOffset, p.count, p.modelNmv]);
behavior.getRange(`E${productProfileStartRow + 2}:F${productProfileStartRow + 1 + profileRaw.length}`).format.numberFormat = percent; moneyRange(behavior.getRange(`J${productProfileStartRow + 2}:J${productProfileStartRow + 1 + profileRaw.length}`)); behavior.getRange(`C${productProfileStartRow + 1}:J${productProfileStartRow + 1 + profileRaw.length}`).format.borders = { preset: "inside", style: "thin", color: border };
section(behavior.getRange(`L${productProfileStartRow}:M${productProfileStartRow}`), paleBlue); behavior.getRange(`L${productProfileStartRow}:M${productProfileStartRow}`).values = [["Collection curve", "Share"]];
behavior.getRange(`L${productProfileStartRow + 1}:M${productProfileStartRow + 6}`).values = curveLabels.map((label, i) => [label, i < 5 ? curve[i] : unpaidShare]); header(behavior.getRange(`L${productProfileStartRow + 1}:M${productProfileStartRow + 1}`)); behavior.getRange(`M${productProfileStartRow + 1}:M${productProfileStartRow + 6}`).format.numberFormat = percent; behavior.getRange(`L${productProfileStartRow}:M${productProfileStartRow + 6}`).format.borders = { preset: "inside", style: "thin", color: border };
const historicalCohortStartRow = productProfileStartRow + profileRaw.length + 5;
section(behavior.getRange(`C${historicalCohortStartRow}:J${historicalCohortStartRow}`), paleBlue); behavior.getRange(`C${historicalCohortStartRow}:J${historicalCohortStartRow}`).values = [["Historical cohort cash generated by invoice month", "", "", "", "", "", "", ""]];
behavior.getRange(`C${historicalCohortStartRow + 1}:J${historicalCohortStartRow + 1}`).values = [["Cohort month", "NMV", "Installment generated", "Same month", "+1 month", "+2 months", "Later", "Unpaid at cutoff"]]; header(behavior.getRange(`C${historicalCohortStartRow + 1}:J${historicalCohortStartRow + 1}`));
const cohortRows = source.cohort_actual_cash.map(([m, count, generated, same, plus1, plus2, later, unpaid]) => [monthDate(monthKey(m)), q287.get(monthKey(m)) ?? null, M(generated), M(same), M(plus1), M(plus2), M(later), M(unpaid)]);
behavior.getRange(`C${historicalCohortStartRow + 2}:J${historicalCohortStartRow + 1 + cohortRows.length}`).values = cohortRows;
dateRange(behavior.getRange(`C${historicalCohortStartRow + 2}:C${historicalCohortStartRow + 1 + cohortRows.length}`)); moneyRange(behavior.getRange(`D${historicalCohortStartRow + 2}:J${historicalCohortStartRow + 1 + cohortRows.length}`)); behavior.getRange(`C${historicalCohortStartRow + 1}:J${historicalCohortStartRow + 1 + cohortRows.length}`).format.borders = { preset: "inside", style: "thin", color: border };
behavior.getRange(`C${historicalCohortStartRow + 4 + cohortRows.length}:J${historicalCohortStartRow + 5 + cohortRows.length}`).values = [
  ["Interpretation", "The forecast applies the September product mix to distinct BNPL and Loan repayment schedules. Share used remains the observed installment amount relative to model NMV, so the schedule retains observed financing premiums rather than forcing it to 100%.", "", "", "", "", "", ""],
  ["Data quality", `15,066 installment records were resolved for the model. 785 records map to multiple invoices through an item bridge; direct payment transaction mapping is preferred where it is available.`, "", "", "", "", "", ""],
];
behavior.getRange(`C${historicalCohortStartRow + 4 + cohortRows.length}:J${historicalCohortStartRow + 5 + cohortRows.length}`).format = { wrapText: true, font: { italic: true, color: "#52616B", size: 9 }, verticalAlignment: "top" };

// Source and notes
title(notes, "C2", "Sources, Method and Limitations", "I");
section(notes.getRange("C4:I4"), paleBlue); notes.getRange("C4:I4").values = [["Sources", "", "", "", "", "", ""]];
notes.getRange("C5:I9").values = [
  ["Existing workbook", "Cash-in / cash-out legacy forecast. Sheet1 rows 22-27 use manual NMV and flat subscription/merchant-share rates.", "", "", "", "", ""],
  ["Metabase question 287", "NMV Monthly. September 2026 actual NMV = 3,314.8M Toman.", "", "", "", "", ""],
  ["Metabase question 290", "Cash In / Cash Out. It is used to reconcile cash-out and legacy payment-creation timing.", "", "", "", "", ""],
  ["Metabase question 280", "AR Amount Monthly. It supplies due-installment context; payment_id is not used as proof of cash receipt.", "", "", "", "", ""],
  ["Database linkage", "Invoice -> invoice transaction -> gateway payment -> installment. The actual-cash curve uses gateway confirmed_at as of 1-Oct-2026.", "", "", "", "", ""],
];
notes.getRange("C5:I9").format = { wrapText: true, verticalAlignment: "top", font: { size: 10 } };
section(notes.getRange("C12:I12"), paleGreen); notes.getRange("C12:I12").values = [["Method", "", "", "", "", "", ""]];
notes.getRange("C13:I18").values = [
  ["1", "Target NMV is split between the four-installment BNPL model and the non-four-installment Loan model using the September NMV amount mix.", "", "", "", "", ""],
  ["2", "Each product model creates installment amounts at its observed amount-to-NMV share and uses its own observed median due-month offset.", "", "", "", "", ""],
  ["3", "Due amount is shifted into actual cash-received months using the confirmed_at collection curve.", "", "", "", "", ""],
  ["4", "Opening AR is separately scheduled so it is not mistaken for future NMV cash.", "", "", "", "", ""],
  ["5", "Investor cash is an October-only financing inflow, not customer revenue.", "", "", "", "", ""],
  ["6", "Cash-out equals target NMV times the trailing observed merchant-settlement ratio. No unsupported payroll or other opex is added.", "", "", "", "", ""],
];
notes.getRange("C13:I18").format = { wrapText: true, verticalAlignment: "top", font: { size: 10 } };
section(notes.getRange("C21:I21"), paleAmber); notes.getRange("C21:I21").values = [["Important limitations", "", "", "", "", "", ""]];
notes.getRange("C22:I27").values = [
  ["Cash balance", "A source bank balance was not available. The 0.0M opening-cash input is explicit and editable.", "", "", "", "", ""],
  ["Overdue AR", "AR that was already overdue before September is shown but not converted into forecast receipts without an age-specific recovery curve.", "", "", "", "", ""],
  ["Payment timing", "The Metabase Cash In / Cash Out question groups installments by gateway payment created_at, whereas this model uses confirmed_at. Variances are visible in Historical Actuals.", "", "", "", "", ""],
  ["Mapping coverage", "Some installment items map to more than one invoice via the bridge table. Those items are not blindly assigned to a cohort.", "", "", "", "", ""],
  ["Product mix", "Loan means any linked invoice whose maximum observed installment number is not four. Exact six-installment amounts are displayed separately; smaller non-four terms are retained rather than reassigned.", "", "", "", "", ""],
  ["Timezone", "Monthly reporting and the 30-Sep-2026 cutoff use Asia/Tehran.", "", "", "", "", ""],
];
notes.getRange("C22:I27").format = { wrapText: true, verticalAlignment: "top", font: { size: 10 } };

// Common presentation refinements.
for (const sheet of [summary, assumptions, build, historical, behavior, notes]) {
  sheet.getUsedRange().format.verticalAlignment = "center";
  sheet.getRange("A1:B90").format.columnWidth = 3;
}
summary.getRange("C:C").format.columnWidth = 40; summary.getRange("D:K").format.columnWidth = 15;
assumptions.getRange("B:B").format.columnWidth = 31; assumptions.getRange("C:C").format.columnWidth = 16; assumptions.getRange("D:E").format.columnWidth = 18; assumptions.getRange("F:J").format.columnWidth = 17;
build.getRange("C:C").format.columnWidth = 34; build.getRange("D:O").format.columnWidth = 15; build.getRange("E:E").format.columnWidth = 31; build.getRange("C23:C31").format.columnWidth = 28;
historical.getRange("C:C").format.columnWidth = 13; historical.getRange("D:L").format.columnWidth = 18;
behavior.getRange("C:C").format.columnWidth = 29; behavior.getRange("D:L").format.columnWidth = 18; behavior.getRange("M:M").format.columnWidth = 25;
notes.getRange("C:C").format.columnWidth = 19; notes.getRange("D:I").format.columnWidth = 24;
for (const sheet of [historical, behavior]) sheet.freezePanes.freezeRows(5);
build.freezePanes.freezeRows(3);

workbook.recalculate();
const check = await workbook.inspect({ kind: "region", sheetId: "Projection Build", range: "C3:I14", maxChars: 5000 });
console.log(check.ndjson ?? check);
const mixCheck = await workbook.inspect({ kind: "table", sheetId: "Assumptions", range: "B15:J25", include: "values,formulas", maxChars: 6000 });
console.log(mixCheck.ndjson ?? mixCheck);
const formulaErrors = [];
for (const sheet of [summary, assumptions, build, historical, behavior, notes]) {
  const used = sheet.getUsedRange();
  for (const [rowIndex, row] of used.values.entries()) {
    for (const [columnIndex, value] of row.entries()) {
      if (typeof value === "string" && value.startsWith("#")) formulaErrors.push(`${sheet.name}!R${rowIndex + 1}C${columnIndex + 1}: ${value}`);
    }
  }
}
if (formulaErrors.length) throw new Error(`Formula errors found: ${formulaErrors.slice(0, 10).join("; ")}`);
const summaryPreview = await workbook.render({ sheetName: "Summary", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/summary.png`, new Uint8Array(await summaryPreview.arrayBuffer()));
const buildPreview = await workbook.render({ sheetName: "Projection Build", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/projection-build.png`, new Uint8Array(await buildPreview.arrayBuffer()));
const assumptionsPreview = await workbook.render({ sheetName: "Assumptions", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/assumptions.png`, new Uint8Array(await assumptionsPreview.arrayBuffer()));
const behaviorPreview = await workbook.render({ sheetName: "Repayment Behavior", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/repayment-behavior.png`, new Uint8Array(await behaviorPreview.arrayBuffer()));
const file = await SpreadsheetFile.exportXlsx(workbook);
await file.save(outputPath);
console.log(JSON.stringify({ outputPath, previewDir, forecast: forecastKeys.map((m, i) => ({ month: m, customerCash: forecastCustomerCash[i], investor: forecastInvestor[i], cashOut: forecastCashOut[i], net: forecastNet[i], endingCash: endingCash[i] })) }, null, 2));
