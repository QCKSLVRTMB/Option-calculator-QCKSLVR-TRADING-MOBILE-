import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(
    page_title="Калькулятор опционов QCKSLVR TRADING",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- CSS: отступ сверху + мобильные правила ----------
st.markdown("""
<style>
/* Опускаем контент ниже верхней панели Streamlit Cloud */
.block-container {padding-top: 3.5rem; padding-bottom: 2rem;}
@media (max-width: 640px){
  .block-container {padding-top: 4rem; padding-left: .6rem; padding-right: .6rem;}
  .stTabs [data-baseweb="tab"] {font-size: .85rem; padding: 8px 6px;}
  h1, .app-title {font-size: 1rem !important; line-height: 1.25;}
}
/* Заголовок приложения */
.app-title {
  font-size: 1.25rem; font-weight: 700; color: #1a3b4f;
  letter-spacing: .04em; text-transform: uppercase;
  margin: .25rem 0 1rem 0; padding-bottom: .5rem;
  border-bottom: 2px solid #e6edf4;
}
</style>
""", unsafe_allow_html=True)

# ---------- Заголовок ----------
st.markdown('<div class="app-title">КАЛЬКУЛЯТОР ОПЦИОНОВ QCKSLVR TRADING</div>',
            unsafe_allow_html=True)


# ================= Сообщения об ошибках без технических деталей =================

def err_series():
    return "Ошибка загрузки опционных серий. Неполадки с получением данных с сервера."

def err_info():
    return "Ошибка загрузки информации о серии. Неполадки с получением данных с сервера."

def err_board():
    return "Ошибка загрузки доски опционов. Неполадки с получением данных с сервера."

def err_smile():
    return "Данные улыбки волатильности недоступны."


# ================= MOEX API =================
API_BASE_URL = "https://iss.moex.com/iss/apps/option-calc/v1"
SECURITIES_URL = "https://iss.moex.com/iss/engines/futures/markets/options/securities.json?iss.meta=off"
ASSET_TYPE_MAP = {'Фьючерс':'futures','Акция':'share','Валюта':'currency','Товар':'commodity','Индекс':'index'}


@st.cache_data(ttl=1800, show_spinner=False)
def get_asset_code_and_type(asset_input: str, asset_type_ui: str):
    moex_type = ASSET_TYPE_MAP.get(asset_type_ui, 'futures')
    code_to_fetch = asset_input
    if moex_type != 'futures':
        try:
            resp = requests.get(SECURITIES_URL, timeout=10); resp.raise_for_status()
            data = resp.json()
            securities = data.get('securities', {}).get('data', [])
            columns = data.get('securities', {}).get('columns', [])
            ai = columns.index('ASSETCODE') if 'ASSETCODE' in columns else -1
            ui = columns.index('UNDERLYINGASSET') if 'UNDERLYINGASSET' in columns else -1
            ti = columns.index('UNDERLYINGTYPE') if 'UNDERLYINGTYPE' in columns else -1
            if ai != -1 and ui != -1 and ti != -1:
                for row in securities:
                    if row[ai] == asset_input:
                        if row[ti] != 'F': code_to_fetch = row[ui]
                        break
        except Exception:
            pass  # тихо игнорируем — код остаётся исходным
    return code_to_fetch, moex_type


@st.cache_data(ttl=300, show_spinner=False)
def fetch_optionseries(asset: str, asset_type_ui: str):
    code, moex_type = get_asset_code_and_type(asset, asset_type_ui)
    r = requests.get(f"{API_BASE_URL}/assets/{code}/optionseries",
                     params={'asset_type': moex_type}, timeout=15)
    r.raise_for_status()
    data = r.json()
    series = []
    items = data if isinstance(data, list) else data.get('data', [])
    for item in items:
        if 'optionseries_code' in item and 'expiration_date' in item:
            series.append({'code': item['optionseries_code'],
                           'expiry': item['expiration_date']})
    return series


@st.cache_data(ttl=300, show_spinner=False)
def fetch_series_info(asset: str, asset_type_ui: str, series_code: str):
    code, moex_type = get_asset_code_and_type(asset, asset_type_ui)
    url = f"{API_BASE_URL}/assets/{code}/optionseries/{series_code}"
    r = requests.get(url, params={'asset_type': moex_type}, timeout=15)
    if r.status_code != 200: r = requests.get(url, timeout=15)
    r.raise_for_status(); data = r.json()
    out = {
        "Опционная серия": data.get('optionseries_code','—'),
        "Базовый актив":   data.get('asset_code','—'),
        "Тип БА":          data.get('asset_type','—'),
        "Тикер":           data.get('futures_code','—'),
        "Тип серии":       data.get('series_type','—'),
        "Дата экспирации": data.get('expiration_date','—'),
        "Центральный страйк": data.get('central_strike','—'),
    }
    for side, label in (('call','Опционы Call'), ('put','Опционы Put')):
        if side in data:
            s = data[side]
            out[label] = {
                "Объём (руб.)": s.get('volume_rub',0),
                "Контрактов": s.get('volume_contracts',0),
                "Открытых позиций": s.get('openposition',0),
                "ОИ изменение": s.get('oichange',0),
            }
    return out


def fetch_central_strike(asset_code, series_code, asset_type):
    try:
        r = requests.get(f"{API_BASE_URL}/assets/{asset_code}/optionseries/{series_code}",
                         params={'asset_type': asset_type}, timeout=10)
        if r.status_code == 200: return r.json().get('central_strike')
    except Exception: pass
    return None


@st.cache_data(ttl=120, show_spinner=False)
def fetch_optionboard(asset: str, asset_type_ui: str, series_code: str):
    code, _ = get_asset_code_and_type(asset, asset_type_ui)
    board, used_type = None, None
    for at in ['share','futures','index','currency','commodity']:
        try:
            r = requests.get(f"{API_BASE_URL}/assets/{code}/optionseries/{series_code}/optionboard",
                             params={'asset_type': at}, timeout=15)
            if r.status_code == 200:
                board = r.json(); used_type = at; break
        except Exception: continue
    if not board: raise RuntimeError("board_unavailable")
    board['central_strike'] = fetch_central_strike(code, series_code, used_type)
    board['series_code'] = series_code
    return board


@st.cache_data(ttl=300, show_spinner=False)
def fetch_volatility_graph(asset: str, series_code: str, asset_type_ui: str):
    code, moex_type = get_asset_code_and_type(asset, asset_type_ui)
    try:
        r = requests.get(f"{API_BASE_URL}/assets/{code}/optionseries/{series_code}/volatility_graph",
                         params={'asset_type': moex_type}, timeout=15)
        r.raise_for_status(); return r.json()
    except Exception: return []


# ================= Мост HTML ↔ Python =================

def push_expiry_to_calculator(expiry_str: str, series_code: str = ""):
    js = f"""
    <script>
    (function(){{
      const value={expiry_str!r}; const series_code={series_code!r};
      function send(){{
        try{{
          const frames=window.parent.document.querySelectorAll('iframe');
          frames.forEach(f=>{{try{{f.contentWindow.postMessage(
            {{type:'setExpiry',value:value,series_code:series_code}},'*');}}catch(e){{}}}});
        }}catch(e){{}}
      }}
      send(); setTimeout(send,300); setTimeout(send,1000); setTimeout(send,2500);
    }})();
    </script>"""
    components.html(js, height=0)


# ================= Подсветка «выгодных» греков =================

FAV_COLOR = "#9ee49e"

def favorable_color(col: str, val, mode: str):
    if mode == 'off' or val is None or pd.isna(val):
        return None
    try: v = float(val)
    except (TypeError, ValueError): return None
    if mode == 'buyer':
        if col == 'Call_Delta' and v >=  0.5:  return FAV_COLOR
        if col == 'Put_Delta'  and v <= -0.5:  return FAV_COLOR
        if col in ('Call_Theta','Put_Theta') and v > -0.05: return FAV_COLOR
        if col == 'IV_%'       and v < 25:     return FAV_COLOR
    elif mode == 'seller':
        if col == 'Call_Delta' and v <=  0.3:  return FAV_COLOR
        if col == 'Put_Delta'  and v >= -0.3:  return FAV_COLOR
        if col in ('Call_Theta','Put_Theta') and v < -0.2: return FAV_COLOR
        if col == 'IV_%'       and v > 50:     return FAV_COLOR
    return None


def style_board(df: pd.DataFrame, central, mode: str):
    def apply(row):
        strike = row.get('Strike')
        is_central = central is not None and abs(strike - central) < 0.01
        call_bg = "#e1e3fb" if is_central else "#dbf3df"
        put_bg  = "#fee5cd" if is_central else "#ffcdce"
        strike_bg = "#e3e7ec"
        styles = []
        for col in row.index:
            bg, extra = "", ""
            if col.startswith('Call_'): bg = call_bg
            elif col.startswith('Put_'): bg = put_bg
            elif col in ('Strike', 'IV_%'):
                bg = strike_bg; extra = "font-weight:bold;"
            hl = favorable_color(col, row[col], mode)
            if hl:
                bg = hl; extra += "font-weight:800;"
            styles.append(f"background-color:{bg};{extra}")
        return styles
    return df.style.apply(apply, axis=1).format(precision=4, na_rep="—")


# ================= UI =================

tab_calc, tab_board = st.tabs(["Калькулятор", "Доска MOEX"])

# ---------- Вкладка 1: калькулятор ----------
with tab_calc:
    calc_html = Path("index.html").read_text(encoding="utf-8")
    components.html(calc_html, height=820, scrolling=True)
    st.caption("Совет: добавьте страницу на главный экран браузера — "
               "открывается как отдельное приложение.")

# ---------- Вкладка 2: доска MOEX ----------
with tab_board:
    st.markdown("##### Поиск серии опционов")
    c1, c2 = st.columns([3, 2])
    with c1:
        asset = st.text_input("Базовый актив", value="GAZR",
                              placeholder="GAZR, GAZP, SBRF, RTS...").strip().upper()
    with c2:
        asset_type_ui = st.selectbox("Вид базового актива",
            ["Фьючерс","Акция","Валюта","Товар","Индекс"])

    b1, b2 = st.columns([1, 1])
    with b1:
        load_btn = st.button("Загрузить серии", use_container_width=True, type="primary")
    with b2:
        if st.button("Сбросить кэш", use_container_width=True):
            st.cache_data.clear(); st.rerun()

    if "series_list" not in st.session_state:
        st.session_state.series_list = []

    if load_btn and asset:
        try:
            with st.spinner("Загрузка серий..."):
                st.session_state.series_list = fetch_optionseries(asset, asset_type_ui)
                if not st.session_state.series_list:
                    st.warning("По этому активу опционные серии не найдены. Проверьте тикер.")
        except Exception:
            st.error(err_series())
            st.session_state.series_list = []

    if st.session_state.series_list:
        options = [f"{s['expiry']} — {s['code']}" for s in st.session_state.series_list]
        chosen = st.selectbox("Дата экспирации (серия)", options, index=0)
        selected = st.session_state.series_list[options.index(chosen)]
        series_code = selected["code"]
        expiry_str = selected["expiry"]

        push_expiry_to_calculator(expiry_str, series_code)
        st.success(f"Дата {expiry_str} передана в калькулятор (серия {series_code}).")

        try:
            info = fetch_series_info(asset, asset_type_ui, series_code)
            with st.expander("Информация об опционной серии"):
                st.json(info, expanded=True)
        except Exception:
            st.warning(err_info())

        try:
            board = fetch_optionboard(asset, asset_type_ui, series_code)
        except Exception:
            st.error(err_board())
            board = None

        if board:
            calls = board.get('call') or []
            puts  = board.get('put')  or []
            central = board.get('central_strike')

            strikes = sorted({c['strike'] for c in calls} | {p['strike'] for p in puts})
            c_map = {c['strike']: c for c in calls}
            p_map = {p['strike']: p for p in puts}

            rows = []
            for k in strikes:
                c = c_map.get(k, {}); p = p_map.get(k, {})
                rows.append({
                    "Call_Ticker": c.get('secid','—'),
                    "Call_Rho": c.get('rho'), "Call_Theta": c.get('theta'),
                    "Call_Vega": c.get('vega'), "Call_Gamma": c.get('gamma'),
                    "Call_Delta": c.get('delta'), "Call_Theor": c.get('theorprice'),
                    "Call_Last": c.get('last'), "Call_Offer": c.get('offer'),
                    "Call_Bid": c.get('bid'),
                    "Strike": k,
                    "IV_%": c.get('volatility') or p.get('volatility'),
                    "Put_Bid": p.get('bid'), "Put_Offer": p.get('offer'),
                    "Put_Last": p.get('last'), "Put_Theor": p.get('theorprice'),
                    "Put_Delta": p.get('delta'), "Put_Gamma": p.get('gamma'),
                    "Put_Vega": p.get('vega'), "Put_Theta": p.get('theta'),
                    "Put_Rho": p.get('rho'), "Put_Ticker": p.get('secid','—'),
                })
            df = pd.DataFrame(rows)

            st.markdown("##### Доска опционов")
            h1, h2 = st.columns([2, 2])
            with h1:
                mode_label = st.radio(
                    "Подсветка «выгодных» греков",
                    ["Выкл","Для покупателя","Для продавца"],
                    horizontal=True, index=1,
                    help="Зелёные ячейки — значения, выгодные выбранной стороне сделки.",
                )
            with h2:
                compact = st.toggle("Компактный вид (ключевые столбцы)", value=False,
                                    help="Удобно для телефона. Выключите — увидите все столбцы.")

            mode = {'Выкл':'off','Для покупателя':'buyer','Для продавца':'seller'}[mode_label]

            if compact:
                cols = ["Strike","IV_%","Call_Bid","Call_Offer","Put_Bid","Put_Offer",
                        "Call_Delta","Call_Theta","Put_Delta","Put_Theta"]
                df_show = df[cols]
            else:
                df_show = df

            st.caption(f"Центральный страйк: {central if central is not None else '—'} · "
                       f"страйков: {len(df)} · режим подсветки: {mode_label}")

            st.dataframe(
                style_board(df_show, central, mode),
                use_container_width=True,
                height=520 if compact else 620,
            )

            # ---- Улыбка волатильности ----
            try:
                points = fetch_volatility_graph(asset, series_code, asset_type_ui)
            except Exception:
                points = []

            if points:
                # Заголовок выносим из plotly в st.subheader — иначе на узком экране
                # он накладывается на линии графика.
                st.markdown("##### Улыбка волатильности (IV по страйкам)")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=[p['strike'] for p in points],
                    y=[p['volatility'] for p in points],
                    mode='lines+markers',
                    line=dict(color='#2c7da0', width=2),
                    fill='tozeroy', fillcolor='rgba(44,125,160,0.1)',
                    name='IV, %',
                ))
                fig.update_layout(
                    title=None,  # без встроенного заголовка
                    xaxis_title="Страйк",
                    yaxis_title="IV, %",
                    height=340,
                    margin=dict(l=10, r=10, t=20, b=20),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(err_smile())
    else:
        st.info("Введите тикер базового актива и нажмите «Загрузить серии».")
