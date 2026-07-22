"""個股完整分析報告 — PDF 匯出用。

Runs the same per-symbol pipeline the `/decision`/`/combined`/`/playbook` endpoints in
`app/api/v1/stocks.py` each separately re-assemble (price fetch → indicators → margin/
institutional history → granville/waves/layers/chips → decision → fundamentals → combined →
playbook), but does it **once** per symbol and keeps every layer's full detail (not just the
summary fields `scan.py` extracts for the AI market scan table) — this is a distinct, richer
aggregation purpose-built for a human/AI-readable report, not a modification of either existing
module.

PDF rendering is plain HTML/CSS fed to WeasyPrint — this project already produces richly
formatted analysis output as data (checklists, signal lists, layer contributions); templating
that as HTML is far less code than a canvas-based PDF library, and keeps the same red=bullish/
emerald=bearish/amber=neutral convention used everywhere else on the site.
"""

import asyncio
from datetime import datetime, timezone
from html import escape

from app.services import chips, combined, company, decision, fundamentals, granville, indicators, layers, playbook, twse, waves
from app.services.yahoo import StockNotFoundError, get_price_dataframe

CHIPS_DAYS = 20
PRICE_PERIOD = "2y"

RED = "#dc2626"
EMERALD = "#059669"
AMBER = "#d97706"
MUTED = "#6b7280"


async def analyze_full(symbol: str) -> dict:
    symbol = symbol.strip().upper()
    info = await asyncio.to_thread(company.get_company_info, symbol)

    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=PRICE_PERIOD)
    except StockNotFoundError as exc:
        return {"symbol": symbol, "name": info["name"] if info else symbol, "market": info["market"] if info else None, "error": str(exc)}

    ind = indicators.compute_all(df)
    margin_history, institutional_history = await asyncio.gather(
        asyncio.to_thread(twse.get_margin_history, symbol, CHIPS_DAYS),
        asyncio.to_thread(twse.get_institutional_history, symbol, CHIPS_DAYS),
    )
    granville_result = granville.analyze(df, ind)
    waves_result = waves.analyze(df)
    layers_result = layers.analyze_layers(ind)
    chips_result = chips.analyze(margin_history, institutional_history)
    decision_result = decision.analyze(granville_result, waves_result, layers_result, chips_result)
    fundamentals_result = await asyncio.to_thread(fundamentals.analyze, symbol)
    combined_result = combined.analyze(decision_result, fundamentals_result)
    playbook_result = playbook.analyze(ind, granville_result, waves_result, chips_result, decision_result, symbol=symbol)

    return {
        "symbol": symbol,
        "name": info["name"] if info else symbol,
        "market": info["market"] if info else None,
        "yahoo_symbol": yahoo_symbol,
        "data_date": ind["dates"][-1],
        "error": None,
        "granville": granville_result,
        "waves": waves_result,
        "layers": layers_result,
        "chips": chips_result,
        "decision": decision_result,
        "fundamentals": fundamentals_result,
        "combined": combined_result,
        "playbook": playbook_result,
    }


def _e(value) -> str:
    return escape(str(value)) if value is not None else "—"


def _fmt_num(value) -> str:
    """Checklist values mix small percentages/ratios with raw currency figures (e.g. free cash
    flow in NT$) — add thousands separators once a value is large enough that it's clearly the
    latter, otherwise leave small percentages/ratios exactly as computed."""
    if isinstance(value, (int, float)) and abs(value) >= 1000:
        return f"{value:,.0f}"
    return _e(value)


def _signal_color(side: str) -> str:
    return RED if side == "buy" else EMERALD if side == "sell" else MUTED


def _playbook_note_line(stance_label: str, action_note: str) -> str:
    """`action_note` already starts with `stance_label + '：'` for the V3.4 neutral-stance
    narratives (e.g. "觀望：目前股價…") but not for buy/sell — prepending the label
    unconditionally produced a doubled "觀望：觀望：…" for the neutral case."""
    if action_note.startswith(f"{stance_label}："):
        return _e(action_note)
    return f"{_e(stance_label)}：{_e(action_note)}"


def _verdict_color(code: str) -> str:
    if code in ("strong_buy", "buy"):
        return RED
    if code in ("strong_sell", "sell"):
        return EMERALD
    return AMBER


def _signals_table(signals: list[dict]) -> str:
    if not signals:
        return "<p class='muted'>本層無訊號觸發。</p>"
    rows = "".join(
        f"<tr><td style='color:{_signal_color(s['side'])}'>{_e(s['label'])}</td>"
        f"<td>{_e(s['reason'])}</td><td class='num'>{_e(s['confidence'])}%</td></tr>"
        for s in signals
    )
    return f"<table><thead><tr><th>訊號</th><th>說明</th><th>信心度</th></tr></thead><tbody>{rows}</tbody></table>"


def _render_one(report: dict, generated_at: str) -> str:
    symbol, name = report["symbol"], report["name"]
    market = report.get("market") or "—"

    if report.get("error"):
        return (
            f"<section class='report'><h1>{_e(symbol)} {_e(name)}（{_e(market)}）</h1>"
            f"<p class='muted'>產生時間：{generated_at}</p>"
            f"<p>無法取得分析資料：{_e(report['error'])}</p></section>"
        )

    d = report["decision"]
    fnd = report["fundamentals"]
    cmb = report["combined"]
    pb = report["playbook"]

    layer_rows = "".join(
        f"<tr><td>{_e(b['label'])}</td><td class='num'>{_e(b['weight'])}</td>"
        f"<td class='num'>{_e(b['signal_count'])}</td><td class='num'>{_e(b['score'])}</td>"
        f"<td>{_e({'fired': '已觸發', 'neutral': '中性', 'no_data': '無資料'}.get(b['status'], b['status']))}</td></tr>"
        for b in d["layer_breakdown"]
    )

    checklist_rows = "".join(
        f"<tr><td>{_e(c['label'])}</td><td class='num'>{_fmt_num(c['value'])}</td>"
        f"<td style='color:{RED if c['passed'] else (EMERALD if c['passed'] is False else MUTED)}'>"
        f"{'✓ 達標' if c['passed'] else ('✗ 未達標' if c['passed'] is False else '資料不足')}</td></tr>"
        for c in fnd["checklist"]
    )

    signal_layers_html = "".join(
        f"<h3>{_e(layer_label)}</h3>{_signals_table(sig_list)}"
        for layer_label, sig_list in (
            ("葛蘭碧法則", report["granville"]["signals"]),
            ("波浪理論", report["waves"]["signals"]),
            ("KD", report["layers"]["kd"]["signals"]),
            ("MACD", report["layers"]["macd"]["signals"]),
            ("均線乖離率", report["layers"]["bias"]["signals"]),
            ("RSI", report["layers"]["rsi"]["signals"]),
            ("成交量", report["layers"]["volume"]["signals"]),
            ("融資融券", report["chips"]["margin"]["signals"]),
            ("三大法人", report["chips"]["institutional"]["signals"]),
        )
    )

    invalidation_html = "".join(f"<li>{_e(cond)}</li>" for cond in pb["invalidation"]) or "<li>無</li>"

    return f"""
    <section class="report">
      <h1>{_e(symbol)} {_e(name)}（{_e(market)}）</h1>
      <p class="muted">資料日期：{_e(report['data_date'])}　產生時間：{generated_at}</p>

      <h2 style="color:{_verdict_color(d['verdict'])}">決策摘要：{_e(d['verdict_label'])}（分數 {_e(d['score'])}）　訊號品質：{_e(d['grade'])} 級</h2>
      <p>訊號完整度：{_e(d['coverage']['layers_fired'])}/{_e(d['coverage']['layers_with_data'])} 層已觸發
      （覆蓋率 {_e(d['coverage']['coverage_pct'])}%）</p>
      {f'<p class="muted">覆蓋率低於 {_e(decision.COVERAGE_CAP_THRESHOLD)}%，決策等級已由「{_e(d["raw_verdict"])}」封頂為中性，避免少數訊號拉高整體判斷。</p>' if d.get('verdict_capped') else ''}
      <table><thead><tr><th>層級</th><th>權重</th><th>訊號數</th><th>層分數</th><th>狀態</th></tr></thead>
      <tbody>{layer_rows}</tbody></table>

      <h2>技術面 × 基本面綜合判斷</h2>
      <p style="color:{_verdict_color(d['verdict'])}">{_e(cmb['combined_label'])}</p>

      <h2>基本面分析</h2>
      <p>評等：{_e(fnd.get('rating_label', '資料不足'))}</p>
      {'<table><thead><tr><th>項目</th><th>數值</th><th>結果</th></tr></thead><tbody>' + checklist_rows + '</tbody></table>' if fnd.get('has_data') else f'<p class="muted">{_e(fnd.get("summary", "查無財報資料（可能為 ETF 或非公司證券）。"))}</p>'}

      <h2>Investment Playbook</h2>
      <p style="color:{_verdict_color(d['verdict'])}">{_playbook_note_line(pb['stance_label'], pb['action_note'])}</p>
      <table style="margin-bottom: 1.2em;"><tbody>
        <tr><td>參考收盤價</td><td class="num">{_e(pb['reference_levels']['close'])}</td></tr>
        <tr><td>支撐</td><td class="num">{_e(pb['reference_levels']['support'])}</td></tr>
        <tr><td>壓力</td><td class="num">{_e(pb['reference_levels']['resistance'])}</td></tr>
        <tr><td>進場區間</td><td class="num">{_e(pb['entry_zone']['low']) + ' - ' + _e(pb['entry_zone']['high']) if pb['entry_zone'] else '—'}</td></tr>
        <tr><td>停損價</td><td class="num">{_e(pb['stop_loss'])}</td></tr>
        <tr><td>目標價</td><td class="num">{_e(pb['target'])}</td></tr>
        <tr><td>風險報酬比</td><td class="num">{_e(pb['risk_reward_ratio'])}</td></tr>
        <tr><td>部位建議</td><td>{_e(pb['position_sizing']['label'])}</td></tr>
      </tbody></table>
      <p><strong>失效條件：</strong></p>
      <ul>{invalidation_html}</ul>
      <p class="muted small">{_e(pb['disclaimer'])}</p>

      <h2 style="margin-top: 1.6em;">📊 歷史勝率科學驗證</h2>
      <table style="margin-bottom: 1.2em;"><tbody>
        <tr><td>20 日後上漲機率</td><td class="num">{f"{pb['backtest_20d_up_prob'] * 100:.1f}%" if pb['backtest_20d_up_prob'] is not None else '框架測試中'}</td></tr>
        <tr><td>20 日後平均報酬</td><td class="num">{f"{pb['backtest_avg_return'] * 100:+.1f}%" if pb['backtest_avg_return'] is not None else '框架測試中'}</td></tr>
        <tr><td>訊號勝率評等</td><td class="num">{_e(pb['signal_win_rate_grade']) if pb['signal_win_rate_grade'] is not None else '框架測試中'}</td></tr>
      </tbody></table>
      <p class="muted small">回測統計引擎尚未串接歷史訊號資料庫，本區塊為 V3.6 預留框架，待後續版本補上實際統計數據。</p>

      <h2>八層訊號明細</h2>
      {signal_layers_html}
    </section>
    """


def render_html(reports: list[dict]) -> str:
    """Builds the full HTML document a PDF is rendered from — split out from `render_pdf` so the
    templating logic can be exercised (and its output inspected) without WeasyPrint's native
    dependencies being available, e.g. in local dev environments where they aren't installed.
    """
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    bodies = [_render_one(r, generated_at) for r in reports]
    # First report's page-break is suppressed (`:first-of-type`) so the document doesn't open
    # with a blank leading page.
    style = """
    <style>
      @page { size: A4; margin: 1.5cm; }
      body { font-family: 'Noto Sans TC', sans-serif; font-size: 10pt; color: #111827; }
      h1 { font-size: 16pt; margin-bottom: 0.2em; }
      h2 { font-size: 12pt; margin-top: 1em; margin-bottom: 0.3em; }
      h3 { font-size: 10.5pt; margin-top: 0.8em; margin-bottom: 0.2em; }
      table { width: 100%; border-collapse: collapse; margin-bottom: 0.6em; }
      th, td { border-bottom: 1px solid #e5e7eb; padding: 3px 6px; text-align: left; font-size: 9pt; }
      td.num, th.num { text-align: right; }
      .num { text-align: right; }
      .muted { color: #6b7280; }
      .small { font-size: 7.5pt; }
      .report { page-break-before: always; }
      .report:first-of-type { page-break-before: avoid; }
    </style>
    """
    return f"<html><head><meta charset='utf-8'>{style}</head><body>{''.join(bodies)}</body></html>"


def render_pdf(reports: list[dict]) -> bytes:
    from weasyprint import HTML  # imported lazily — needs system libs (Pango/Cairo/GTK) only
    # present in the deployed container (see Dockerfile), not necessarily in every dev environment

    return HTML(string=render_html(reports)).write_pdf()


def _star_display(value: float | None) -> str:
    if value is None:
        return "—"
    full = int(value)
    half = "☆" if value - full >= 0.5 else ""
    return "★" * full + half or "—"


def _rank_display(rank: int | None) -> str:
    return _e(rank) if rank is not None else "—"


def render_teacher_recommendations_html(rows: list[dict]) -> str:
    """老師建議清單的 PDF——跟 `render_html` 分開一支，因為資料形狀是「一份清單多檔股票」
    （固定欄位的表格），不是 `_render_one` 那種「每檔股票一整份完整報告」，用同一支函式硬套
    反而要塞一堆 if，不如另開一支表格導向的 render，共用同樣的顏色常數/字體/A4 版面設定。
    """
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

    body_rows = "".join(
        f"""<tr>
          <td class="num">{_rank_display(r.get('system_rank'))}</td>
          <td class="num muted">{_rank_display(r.get('teacher_rank'))}</td>
          <td>{_e(r['symbol'])} {_e(r['name'])}</td>
          <td class="num">{_e(r.get('close'))}</td>
          <td>{_e(r.get('main_industry'))}</td>
          <td>{_star_display(r.get('long_term_rating'))}</td>
          <td>{_e(r.get('investment_category'))}</td>
          <td>{_star_display(r.get('ai_benefit_rating'))}</td>
          <td>{_e(r.get('volatility'))}</td>
          <td>{_e(r.get('suitable_strategy'))}</td>
          <td class="num" style="color:{_verdict_color(r.get('technical_verdict', 'neutral'))}">
            {_e(r.get('technical_score'))}
          </td>
          <td style="color:{_verdict_color(r.get('technical_verdict', 'neutral'))}">
            {_e(r.get('technical_verdict_label'))}（{_e(r.get('grade'))}）
          </td>
          <td class="num">{_e(r.get('confidence_pct'))}%</td>
          <td class="muted">{_star_display(r.get('fundamental_rating'))}</td>
          <td class="num">{_e(r.get('composite_score'))}</td>
        </tr>""" if not r.get("error") else
        f"""<tr><td class="num">—</td><td class="num muted">{_rank_display(r.get('teacher_rank'))}</td>
          <td>{_e(r['symbol'])} {_e(r['name'])}</td>
          <td colspan="12" class="muted">無法取得分析資料：{_e(r['error'])}</td></tr>"""
        for r in rows
    )

    style = """
    <style>
      @page { size: A4 landscape; margin: 1.2cm; }
      body { font-family: 'Noto Sans TC', sans-serif; font-size: 8.5pt; color: #111827; }
      h1 { font-size: 15pt; margin-bottom: 0.2em; }
      table { width: 100%; border-collapse: collapse; }
      th, td { border-bottom: 1px solid #e5e7eb; padding: 3px 5px; text-align: left; font-size: 8pt; }
      td.num, th.num { text-align: right; }
      .muted { color: #6b7280; }
    </style>
    """
    return f"""<html><head><meta charset='utf-8'>{style}</head><body>
      <h1>老師建議清單</h1>
      <p class="muted">產生時間：{generated_at}　共 {len(rows)} 檔<br/>
      系統排名＝0.6×技術分數＋0.4×AI綜合評判品質星等；AI綜合評判品質星等＝(長期評價+AI受惠程度)/2 換算成 -100..+100。
      老師排名為原始參考值，未納入計算。技術分級／訊號品質為決策系統的資料覆蓋率封頂顯示（詳見前端說明），覆蓋率過低時分級會顯示「中性」但技術分數本身不受影響，排名計算一律採用技術分數，不是分級。
      「基本面」為財報評等，僅供參考，未納入系統排名計算。</p>
      <table><thead><tr>
        <th class="num">系統排名</th><th class="num">老師排名</th><th>股票</th><th class="num">現價</th>
        <th>主要產業</th><th>長期評價</th><th>投資分類</th><th>AI受惠程度</th><th>波動程度</th><th>適合策略</th>
        <th class="num">技術分數</th><th>技術分級</th><th class="num">訊號品質</th><th>基本面（僅參考）</th><th class="num">綜合分數</th>
      </tr></thead><tbody>{body_rows}</tbody></table>
    </body></html>"""


def render_teacher_recommendations_pdf(rows: list[dict]) -> bytes:
    from weasyprint import HTML  # lazy import, same reasoning as render_pdf

    return HTML(string=render_teacher_recommendations_html(rows)).write_pdf()
