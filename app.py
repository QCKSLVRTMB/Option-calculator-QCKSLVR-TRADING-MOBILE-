import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import numpy as np
import json
import math
import re
import uuid
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime, date, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

st.set_page_config(
    page_title="MOEX Options & Black-Scholes",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 🔧 Однократный сброс кэша при старте сессии
if "cache_cleared_v3" not in st.session_state:
    st.cache_data.clear()
    st.session_state["cache_cleared_v3"] = True

# ================= МОБИЛЬНЫЙ CSS =================
st.markdown("""
<style>
.block-container {
    padding-top: 0.4rem !important;
    padding-bottom: 0.6rem !important;
    padding-left: 0.55rem !important;
    padding-right: 0.55rem !important;
    max-width: 100% !important;
}
/* Скрываем шапку/футер/меню Streamlit — нативный вид в APK */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {display: none;}

/* Вкладки — компактные, горизонтальный скролл */
div[data-testid="stTabs"] > div:first-child {
    overflow-x: auto !important;
    flex-wrap: nowrap !important;
    scrollbar-width: none;
    gap: 2px;
    padding-bottom: 2px;
}
div[data-testid="stTabs"] > div:first-child::-webkit-scrollbar {display: none;}
div[data-testid="stTabs"] button[role="tab"] {
    padding: 5px 9px !important;
    font-size: 0.78rem !important;
    white-space: nowrap;
    min-height: 34px;
}

/* Уменьшаем зазоры между колонками */
div[data-testid="stHorizontalBlock"] {gap: 0.35rem !important;}

/* Кнопки и inputs — крупные тач-таргеты */
input, select, textarea {
    font-size: 16px !important;
}
div[data-testid="stButton"] > button {
    min-height: 38px;
    font-size: 0.85rem;
}

/* Метрики компактнее */
div[data-testid="stMetric"] > div {padding: 4px 8px !important;}
div[data-testid="stMetricValue"] {font-size: 1.05rem !important;}
div[data-testid="stMetricLabel"] {font-size: 0.72rem !important;}

/* Popover «три точки» */
div[data-testid="stPopover"] > button {
    border-radius: 50%;
    height: 38px;
    width: 38px;
    padding: 0;
    font-size: 22px;
    font-weight: bold;
    border: 1px solid #cfdfe9;
    background: white;
    color: #1e5a7a;
    line-height: 1;
}
div[data-testid="stPopover"] > button:hover {background: #eef2f5;}

/* Компактные expander / container */
details {margin-bottom: 0.35rem;}
div[data-testid="stExpander"] > details > summary {
    padding: 6px 10px !important;
    font-size: 0.82rem;
}

/* Dataframe шрифт */
div[data-testid="stDataFrame"] {font-size: 12px;}

/* Убираем лишний верхний gap у заголовков */
h1 {font-size: 1.15rem !important; margin-top: 0 !important;}
h2 {font-size: 1rem !important;}
h3 {font-size: 0.92rem !important; margin-top: 0.4rem !important;}
</style>
""", unsafe_allow_html=True)

# ================= MOEX API =================
API_BASE_URL = "https://iss.moex.com/iss/apps/option-calc/v1"
SECURITIES_URL = ("https://iss.moex.com/iss/engines/futures/markets/options/"
                  "securities.json?iss.meta=off")

ASSET_TYPE_MAP = {
    'Фьючерс': 'futures', 'Акция': 'share', 'Валюта': 'currency',
    'Товар': 'commodity', 'Индекс': 'index',
}

DEFAULT_COMM_OPTIONS_PCT = 3.0
DEFAULT_COMM_OPTIONS_MIN = 0.02
DEFAULT_COMM_FUTURES_PCT = 0.1
DEFAULT_COMM_STOCKS_PCT  = 0.3

HTML_PLACEHOLDER = "/*__INJECT_PLACEHOLDER__*/{}"

# ================= Справочник инструментов MOEX =================
MOEX_INSTRUMENTS = {
    "Индексы": {
        "RTS": ("Индекс", "Индекс РТС"), "MIX": ("Индекс", "Индекс МосБиржи"),
        "RVI": ("Индекс", "Индекс волатильности RVI"),
        "MOEXCNY": ("Индекс", "Индекс МосБиржи в юанях"),
        "RGBI": ("Индекс", "Индекс RGBI"), "MMI": ("Индекс", "Индекс металлов"),
        "FNI": ("Индекс", "Индекс финансов"), "OGI": ("Индекс", "Индекс нефти и газа"),
        "MXI": ("Индекс", "Индекс МосБиржи (мини)"), "RTSM": ("Индекс", "Индекс РТС (мини)"),
    },
    "Акции": {
        "GAZP": ("Акция", "Газпром"), "SBER": ("Акция", "Сбербанк о.с."),
        "SBERP": ("Акция", "Сбербанк п.с."), "LKOH": ("Акция", "ЛУКОЙЛ"),
        "ROSN": ("Акция", "Роснефть"), "NOTK": ("Акция", "НОВАТЭК"),
        "TATN": ("Акция", "Татнефть о.с."), "TATNP": ("Акция", "Татнефть п.с."),
        "SNGSP": ("Акция", "Сургутнефтегаз п.с."), "MTSS": ("Акция", "МТС"),
        "MGNT": ("Акция", "Магнит"), "GMKN": ("Акция", "Норникель"),
        "NLMK": ("Акция", "НЛМК"), "CHMF": ("Акция", "Северсталь"),
        "ALRS": ("Акция", "АЛРОСА"), "VTBR": ("Акция", "ВТБ"),
        "MOEX": ("Акция", "Московская Биржа"), "AFKS": ("Акция", "АФК Система"),
        "IRAO": ("Акция", "Интер РАО"), "HYDR": ("Акция", "РусГидро"),
        "RTKM": ("Акция", "Ростелеком"), "PLZL": ("Акция", "Полюс"),
        "MAGN": ("Акция", "ММК"), "YDEX": ("Акция", "Яндекс"),
        "PHOR": ("Акция", "ФосАгро"), "RUAL": ("Акция", "РУСАЛ"),
        "FEES": ("Акция", "ФСК ЕЭС"), "TRNFP": ("Акция", "Транснефть п.с."),
        "AFLT": ("Акция", "Аэрофлот"), "SIBN": ("Акция", "Газпром нефть"),
        "PIKK": ("Акция", "ПИК"), "FLOT": ("Акция", "Совкомфлот"),
        "CBOM": ("Акция", "МКБ"), "SGZH": ("Акция", "Сегежа"),
        "BSPB": ("Акция", "Банк Санкт-Петербург"), "KMAZ": ("Акция", "КАМАЗ"),
        "ASTR": ("Акция", "Группа Астра"), "SVCB": ("Акция", "Совкомбанк"),
    },
    "Фьючерсы": {
        "GAZR": ("Фьючерс", "Газпром (фьючерс)"),
        "SBRF": ("Фьючерс", "Сбербанк о.с. (фьючерс)"),
        "SBPR": ("Фьючерс", "Сбербанк п.с. (фьючерс)"),
        "LKOH": ("Фьючерс", "ЛУКОЙЛ (фьючерс)"),
        "ROSN": ("Фьючерс", "Роснефть (фьючерс)"),
        "NOTK": ("Фьючерс", "НОВАТЭК (фьючерс)"),
        "TATN": ("Фьючерс", "Татнефть о.с. (фьючерс)"),
        "TATP": ("Фьючерс", "Татнефть п.с. (фьючерс)"),
        "SNGR": ("Фьючерс", "Сургутнефтегаз о.с. (фьючерс)"),
        "SNGP": ("Фьючерс", "Сургутнефтегаз п.с. (фьючерс)"),
        "MTSS": ("Фьючерс", "МТС (фьючерс)"), "MGNT": ("Фьючерс", "Магнит (фьючерс)"),
        "GMKN": ("Фьючерс", "Норникель (фьючерс)"), "NLMK": ("Фьючерс", "НЛМК (фьючерс)"),
        "CHMF": ("Фьючерс", "Северсталь (фьючерс)"), "ALRS": ("Фьючерс", "АЛРОСА (фьючерс)"),
        "VTBR": ("Фьючерс", "ВТБ (фьючерс)"), "MOEX": ("Фьючерс", "МосБиржа (фьючерс)"),
        "AFKS": ("Фьючерс", "АФК Система (фьючерс)"), "IRAO": ("Фьючерс", "Интер РАО (фьючерс)"),
        "HYDR": ("Фьючерс", "РусГидро (фьючерс)"), "RTKM": ("Фьючерс", "Ростелеком (фьючерс)"),
        "PLZL": ("Фьючерс", "Полюс (фьючерс)"), "MAGN": ("Фьючерс", "ММК (фьючерс)"),
        "YDEX": ("Фьючерс", "Яндекс (фьючерс)"), "PHOR": ("Фьючерс", "ФосАгро (фьючерс)"),
        "RUAL": ("Фьючерс", "РУСАЛ (фьючерс)"), "FEES": ("Фьючерс", "ФСК ЕЭС (фьючерс)"),
        "TRNF": ("Фьючерс", "Транснефть п.с. (фьючерс)"), "AFLT": ("Фьючерс", "Аэрофлот (фьючерс)"),
        "SIBN": ("Фьючерс", "Газпром нефть (фьючерс)"), "PIKK": ("Фьючерс", "ПИК (фьючерс)"),
        "FLOT": ("Фьючерс", "Совкомфлот (фьючерс)"), "CBOM": ("Фьючерс", "МКБ (фьючерс)"),
        "SGZH": ("Фьючерс", "Сегежа (фьючерс)"), "BSPB": ("Фьючерс", "БСП (фьючерс)"),
        "KMAZ": ("Фьючерс", "КАМАЗ (фьючерс)"), "ASTR": ("Фьючерс", "Астра (фьючерс)"),
        "SVCB": ("Фьючерс", "Совкомбанк (фьючерс)"),
    },
    "Валюты": {
        "Si": ("Валюта", "Доллар / Рубль"), "Eu": ("Валюта", "Евро / Рубль"),
        "CNY": ("Валюта", "Юань / Рубль"), "TRY": ("Валюта", "Лира / Рубль"),
        "HKD": ("Валюта", "Гонконг. доллар / Рубль"), "AED": ("Валюта", "Дирхам / Рубль"),
        "KZT": ("Валюта", "Тенге / Рубль"), "AMD": ("Валюта", "Драм / Рубль"),
        "BYN": ("Валюта", "Бел. рубль / Рубль"), "ED": ("Валюта", "Евро / Доллар"),
        "AUDU": ("Валюта", "AUD / USD"), "GBPU": ("Валюта", "GBP / USD"),
        "UCAD": ("Валюта", "USD / CAD"), "UCHF": ("Валюта", "USD / CHF"),
        "UJPY": ("Валюта", "USD / JPY"), "UCNY": ("Валюта", "USD / CNY"),
    },
    "Товары": {
        "BR": ("Товар", "Нефть Brent"), "CL": ("Товар", "Нефть Light Sweet"),
        "GOLD": ("Товар", "Золото"), "SILV": ("Товар", "Серебро"),
        "PLD": ("Товар", "Палладий"), "PLT": ("Товар", "Платина"),
        "ALMN": ("Товар", "Алюминий"), "Co": ("Товар", "Медь"),
        "Nl": ("Товар", "Никель"), "Zn": ("Товар", "Цинк"),
        "NG": ("Товар", "Природный газ"), "WHEAT": ("Товар", "Пшеница"),
        "SUGR": ("Товар", "Сахар"),
    },
}

TV_TICKER_MAP = {
    "Акция": {"GAZP": "MOEX:GAZP", "SBER": "MOEX:SBER", "SBERP": "MOEX:SBERP",
              "LKOH": "MOEX:LKOH", "ROSN": "MOEX:ROSN", "NOTK": "MOEX:NOTK",
              "TATN": "MOEX:TATN", "TATNP": "MOEX:TATNP", "SNGSP": "MOEX:SNGSP",
              "MTSS": "MOEX:MTSS", "MGNT": "MOEX:MGNT", "GMKN": "MOEX:GMKN",
              "NLMK": "MOEX:NLMK", "CHMF": "MOEX:CHMF", "ALRS": "MOEX:ALRS",
              "VTBR": "MOEX:VTBR", "MOEX": "MOEX:MOEX", "AFKS": "MOEX:AFKS",
              "IRAO": "MOEX:IRAO", "HYDR": "MOEX:HYDR", "RTKM": "MOEX:RTKM",
              "PLZL": "MOEX:PLZL", "MAGN": "MOEX:MAGN", "YDEX": "MOEX:YDEX",
              "PHOR": "MOEX:PHOR", "RUAL": "MOEX:RUAL", "FEES": "MOEX:FEES",
              "TRNFP": "MOEX:TRNFP", "AFLT": "MOEX:AFLT", "SIBN": "MOEX:SIBN",
              "PIKK": "MOEX:PIKK", "FLOT": "MOEX:FLOT", "CBOM": "MOEX:CBOM",
              "SGZH": "MOEX:SGZH", "BSPB": "MOEX:BSPB", "KMAZ": "MOEX:KMAZ",
              "ASTR": "MOEX:ASTR", "SVCB": "MOEX:SVCB"},
    "Фьючерс": {"GAZR": "MOEX:GZ1!", "GZ": "MOEX:GZ1!", "SBRF": "MOEX:SR1!",
                "SR": "MOEX:SR1!", "SBPR": "MOEX:SP1!", "SP": "MOEX:SP1!",
                "LKOH": "MOEX:LK1!", "LK": "MOEX:LK1!", "ROSN": "MOEX:RN1!",
                "RN": "MOEX:RN1!", "NOTK": "MOEX:NK1!", "NK": "MOEX:NK1!",
                "TATN": "MOEX:TT1!", "TT": "MOEX:TT1!", "SNGR": "MOEX:SN1!",
                "SN": "MOEX:SN1!", "MTSS": "MOEX:MT1!", "MT": "MOEX:MT1!",
                "MGNT": "MOEX:MG1!", "MG": "MOEX:MG1!", "GMKN": "MOEX:GM1!",
                "GK": "MOEX:GM1!", "NLMK": "MOEX:NM1!", "NM": "MOEX:NM1!",
                "CHMF": "MOEX:CH1!", "CH": "MOEX:CH1!", "ALRS": "MOEX:AL1!",
                "AL": "MOEX:AL1!", "VTBR": "MOEX:VB1!", "VB": "MOEX:VB1!",
                "MOEX": "MOEX:ME1!", "ME": "MOEX:ME1!", "AFKS": "MOEX:AK1!",
                "AK": "MOEX:AK1!", "IRAO": "MOEX:IR1!", "IR": "MOEX:IR1!",
                "HYDR": "MOEX:HY1!", "HY": "MOEX:HY1!", "RTKM": "MOEX:RT1!",
                "RT": "MOEX:RT1!", "PLZL": "MOEX:PL1!", "PL": "MOEX:PL1!",
                "MAGN": "MOEX:MM1!", "YDEX": "MOEX:YD1!", "YD": "MOEX:YD1!",
                "PHOR": "MOEX:PH1!", "PH": "MOEX:PH1!", "RUAL": "MOEX:RL1!",
                "RL": "MOEX:RL1!", "FEES": "MOEX:FS1!", "FS": "MOEX:FS1!",
                "TRNF": "MOEX:TN1!", "TN": "MOEX:TN1!", "AFLT": "MOEX:AF1!",
                "AF": "MOEX:AF1!", "PIKK": "MOEX:PI1!", "PI": "MOEX:PI1!",
                "FLOT": "MOEX:FL1!", "FL": "MOEX:FL1!", "KMAZ": "MOEX:KM1!",
                "KM": "MOEX:KM1!", "ASTR": "MOEX:AS1!", "AS": "MOEX:AS1!",
                "SVCB": "MOEX:SC1!", "SC": "MOEX:SC1!", "RTS": "MOEX:RI1!",
                "RI": "MOEX:RI1!", "MIX": "MOEX:MIX1!", "RVI": "MOEX:VI1!",
                "VI": "MOEX:VI1!", "RGBI": "MOEX:RB1!", "RB": "MOEX:RB1!",
                "MOEXCNY": "MOEX:CR1!", "Si": "MOEX:SI1!", "Eu": "MOEX:EU1!",
                "CNY": "MOEX:CR1!", "CR": "MOEX:CR1!", "TRY": "MOEX:TRY1!",
                "BR": "MOEX:BR1!", "GOLD": "MOEX:GD1!", "GD": "MOEX:GD1!",
                "SILV": "MOEX:SV1!", "SV": "MOEX:SV1!", "NG": "MOEX:NG1!",
                "CL": "MOEX:CL1!"},
    "Индекс": {"RTS": "MOEX:RI1!", "RI": "MOEX:RI1!", "MIX": "MOEX:MIX1!",
               "RVI": "MOEX:VI1!", "VI": "MOEX:VI1!", "RGBI": "MOEX:RB1!",
               "RB": "MOEX:RB1!", "MOEXCNY": "MOEX:CR1!", "CR": "MOEX:CR1!",
               "MXI": "MOEX:MIX1!", "RTSM": "MOEX:RTSM1!", "MMI": "MOEX:MMI1!",
               "FNI": "MOEX:FNI1!", "OGI": "MOEX:OGI1!"},
    "Валюта": {"Si": "MOEX:SI1!", "Eu": "MOEX:EU1!", "CNY": "MOEX:CR1!",
               "CR": "MOEX:CR1!", "TRY": "MOEX:TRY1!", "HKD": "MOEX:HKD1!",
               "AED": "MOEX:AED1!", "KZT": "MOEX:KZT1!", "AMD": "MOEX:AMD1!",
               "BYN": "MOEX:BYN1!", "ED": "MOEX:ED1!", "AUDU": "MOEX:AUDU1!",
               "GBPU": "MOEX:GBPU1!", "UCAD": "MOEX:UCAD1!", "UCHF": "MOEX:UCHF1!",
               "UJPY": "MOEX:UJPY1!", "UCNY": "MOEX:UCNY1!"},
    "Товар": {"BR": "MOEX:BR1!", "CL": "MOEX:CL1!", "GOLD": "MOEX:GD1!",
              "GD": "MOEX:GD1!", "SILV": "MOEX:SV1!", "SV": "MOEX:SV1!",
              "PLD": "MOEX:PD1!", "PD": "MOEX:PD1!", "PLT": "MOEX:PT1!",
              "PT": "MOEX:PT1!", "ALMN": "MOEX:ALMN1!", "Co": "MOEX:CO1!",
              "Nl": "MOEX:NI1!", "Zn": "MOEX:ZN1!", "NG": "MOEX:NG1!",
              "WHEAT": "MOEX:WHEAT1!", "SUGR": "MOEX:SUGR1!"},
}


def resolve_tv_ticker(asset_code: str, asset_type_ui: str):
    return TV_TICKER_MAP.get(asset_type_ui, {}).get(asset_code)


# ================= Предустановленные стратегии =================
PREDEFINED_STRATEGIES = {
    "Long Call": {"category": "Одиночные", "description": "Покупка опциона Call",
                  "strike_order": [],
                  "legs": [{"label": "Страйк", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K"}]},
    "Long Put": {"category": "Одиночные", "description": "Покупка опциона Put",
                 "strike_order": [],
                 "legs": [{"label": "Страйк", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K"}]},
    "Short Call": {"category": "Одиночные", "description": "Продажа опциона Call",
                   "strike_order": [],
                   "legs": [{"label": "Страйк", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K"}]},
    "Short Put": {"category": "Одиночные", "description": "Продажа опциона Put",
                  "strike_order": [],
                  "legs": [{"label": "Страйк", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K"}]},
    "Bull Call Spread": {"category": "Вертикальные спреды", "description": "Buy Call (низ) + Sell Call (верх)",
                         "strike_order": ["K_low", "K_high"],
                         "legs": [{"label": "Buy Call", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K_low"},
                                  {"label": "Sell Call", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K_high"}]},
    "Bear Call Spread": {"category": "Вертикальные спреды", "description": "Sell Call + Buy Call",
                         "strike_order": ["K_low", "K_high"],
                         "legs": [{"label": "Sell Call", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K_low"},
                                  {"label": "Buy Call", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K_high"}]},
    "Bull Put Spread": {"category": "Вертикальные спреды", "description": "Sell Put (верх) + Buy Put (низ)",
                        "strike_order": ["K_low", "K_high"],
                        "legs": [{"label": "Buy Put", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K_low"},
                                 {"label": "Sell Put", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K_high"}]},
    "Bear Put Spread": {"category": "Вертикальные спреды", "description": "Buy Put (верх) + Sell Put (низ)",
                        "strike_order": ["K_low", "K_high"],
                        "legs": [{"label": "Sell Put", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K_low"},
                                 {"label": "Buy Put", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K_high"}]},
    "Long Butterfly (Call)": {"category": "Бабочки", "description": "Buy 1 + Sell 2 + Buy 1 (Call)",
                              "strike_order": ["K1", "K2", "K3"],
                              "legs": [{"label": "Buy Call K1", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K1"},
                                       {"label": "Sell Call K2", "option": "Call", "side": "Sell", "qty": 2, "strike_group": "K2"},
                                       {"label": "Buy Call K3", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K3"}]},
    "Short Butterfly (Call)": {"category": "Бабочки", "description": "Sell 1 + Buy 2 + Sell 1 (Call)",
                               "strike_order": ["K1", "K2", "K3"],
                               "legs": [{"label": "Sell Call K1", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K1"},
                                        {"label": "Buy Call K2", "option": "Call", "side": "Buy", "qty": 2, "strike_group": "K2"},
                                        {"label": "Sell Call K3", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K3"}]},
    "Long Butterfly (Put)": {"category": "Бабочки", "description": "Buy 1 + Sell 2 + Buy 1 (Put)",
                             "strike_order": ["K1", "K2", "K3"],
                             "legs": [{"label": "Buy Put K1", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K1"},
                                      {"label": "Sell Put K2", "option": "Put", "side": "Sell", "qty": 2, "strike_group": "K2"},
                                      {"label": "Buy Put K3", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K3"}]},
    "Short Cat": {"category": "Кошка", "description": "Buy Put + Sell Put + Sell Call + Buy Call",
                  "strike_order": ["K1", "K2", "K3", "K4"],
                  "legs": [{"label": "Buy Put K1", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K1"},
                           {"label": "Sell Put K2", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K2"},
                           {"label": "Sell Call K3", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K3"},
                           {"label": "Buy Call K4", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K4"}]},
    "Iron Condor": {"category": "Кондоры", "description": "Buy Put + Sell Put + Sell Call + Buy Call",
                    "strike_order": ["K1", "K2", "K3", "K4"],
                    "legs": [{"label": "Buy Put K1", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K1"},
                             {"label": "Sell Put K2", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K2"},
                             {"label": "Sell Call K3", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K3"},
                             {"label": "Buy Call K4", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K4"}]},
    "Long Straddle": {"category": "Straddle / Strangle", "description": "Buy Call + Buy Put",
                      "strike_order": [],
                      "legs": [{"label": "Buy Call", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K"},
                               {"label": "Buy Put", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K"}]},
    "Short Straddle": {"category": "Straddle / Strangle", "description": "Sell Call + Sell Put",
                       "strike_order": [],
                       "legs": [{"label": "Sell Call", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K"},
                                {"label": "Sell Put", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K"}]},
    "Long Strangle": {"category": "Straddle / Strangle", "description": "Buy OTM Put + Buy OTM Call",
                      "strike_order": ["K_low", "K_high"],
                      "legs": [{"label": "Buy Put", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K_low"},
                               {"label": "Buy Call", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K_high"}]},
    "Short Strangle": {"category": "Straddle / Strangle", "description": "Sell OTM Put + Sell OTM Call",
                       "strike_order": ["K_low", "K_high"],
                       "legs": [{"label": "Sell Put", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K_low"},
                                {"label": "Sell Call", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K_high"}]},
    "Call Ratio Spread": {"category": "Ratio / Backspread", "description": "Buy 1 Call + Sell 2 Call",
                          "strike_order": ["K_low", "K_high"],
                          "legs": [{"label": "Buy Call", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K_low"},
                                   {"label": "Sell Call ×2", "option": "Call", "side": "Sell", "qty": 2, "strike_group": "K_high"}]},
    "Put Ratio Spread": {"category": "Ratio / Backspread", "description": "Buy 1 Put + Sell 2 Put",
                         "strike_order": ["K_low", "K_high"],
                         "legs": [{"label": "Sell Put ×2", "option": "Put", "side": "Sell", "qty": 2, "strike_group": "K_low"},
                                  {"label": "Buy Put", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K_high"}]},
    "Synthetic Long Futures": {"category": "Синтетика", "description": "Buy Call + Sell Put",
                               "strike_order": [],
                               "legs": [{"label": "Buy Call", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K"},
                                        {"label": "Sell Put", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K"}]},
    "Synthetic Short Futures": {"category": "Синтетика", "description": "Sell Call + Buy Put",
                                "strike_order": [],
                                "legs": [{"label": "Sell Call", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K"},
                                         {"label": "Buy Put", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K"}]},
    "Strap": {"category": "Strap / Strip", "description": "Buy 2 Call + Buy 1 Put",
              "strike_order": [],
              "legs": [{"label": "Buy 2 Call", "option": "Call", "side": "Buy", "qty": 2, "strike_group": "K"},
                       {"label": "Buy Put", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K"}]},
    "Strip": {"category": "Strap / Strip", "description": "Buy 1 Call + Buy 2 Put",
              "strike_order": [],
              "legs": [{"label": "Buy Call", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K"},
                       {"label": "Buy 2 Put", "option": "Put", "side": "Buy", "qty": 2, "strike_group": "K"}]},
    "Ladder Call": {"category": "Ladder", "description": "Buy 1 + Sell + Sell (Call)",
                    "strike_order": ["K1", "K2", "K3"],
                    "legs": [{"label": "Buy Call K1", "option": "Call", "side": "Buy", "qty": 1, "strike_group": "K1"},
                             {"label": "Sell Call K2", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K2"},
                             {"label": "Sell Call K3", "option": "Call", "side": "Sell", "qty": 1, "strike_group": "K3"}]},
    "Ladder Put": {"category": "Ladder", "description": "Buy 1 + Sell + Sell (Put)",
                   "strike_order": ["K1", "K2", "K3"],
                   "legs": [{"label": "Buy Put K1", "option": "Put", "side": "Buy", "qty": 1, "strike_group": "K1"},
                            {"label": "Sell Put K2", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K2"},
                            {"label": "Sell Put K3", "option": "Put", "side": "Sell", "qty": 1, "strike_group": "K3"}]},
}


# ================= HTTP-клиент ISS =================
def _make_iss_session():
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.6,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "MOEX-Options-Calc/1.0",
                      "Accept": "application/json, */*"})
    return s


_ISS_SESSION = _make_iss_session()


def iss_get(url, params=None, timeout=20):
    for attempt in range(3):
        try:
            r = _ISS_SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException:
            if attempt == 2:
                return None
            time.sleep(0.7 * (attempt + 1))
    return None


def iss_get_json(url, params=None, timeout=20):
    r = iss_get(url, params=params, timeout=timeout)
    if r is None:
        return None
    try:
        return r.json()
    except Exception:
        return None


_FAILED_UNTIL = {}


def _is_failed_recently(key: str, cooldown_sec: int = 60) -> bool:
    ts = _FAILED_UNTIL.get(key)
    return ts is not None and time.time() < ts


def _mark_failed(key: str, cooldown_sec: int = 60):
    _FAILED_UNTIL[key] = time.time() + cooldown_sec


def resolve_canonical_asset_code(user_input: str) -> str:
    if not user_input:
        return user_input
    s = user_input.strip()
    if not s:
        return s
    for cat_items in MOEX_INSTRUMENTS.values():
        for code in cat_items.keys():
            if code.upper() == s.upper():
                return code
    return s.upper()


# ================= Комиссии =================
def calc_commission(premium, instrument_type="Опцион",
                    min_comm_options=0.02, comm_options_pct=3.0,
                    comm_futures_pct=0.1, comm_stocks_pct=0.3):
    if premium is None or premium <= 0:
        return 0.0
    t = (instrument_type or "").strip().lower()
    if t in ("опцион", "option"):
        return max((comm_options_pct / 100.0) * premium, min_comm_options)
    if t in ("фьючерс", "futures"):
        return (comm_futures_pct / 100.0) * premium
    if t in ("акция", "stock", "share", "облигация", "etf", "bond"):
        return (comm_stocks_pct / 100.0) * premium
    return 0.0


def _calc_comm_ui(premium, instr_type="Опцион"):
    cop = st.session_state.get("cop_inp", DEFAULT_COMM_OPTIONS_PCT)
    cmo = st.session_state.get("cmo_inp", DEFAULT_COMM_OPTIONS_MIN)
    cfp = st.session_state.get("cfp_inp", DEFAULT_COMM_FUTURES_PCT)
    csp = st.session_state.get("csp_inp", DEFAULT_COMM_STOCKS_PCT)
    return calc_commission(premium, instrument_type=instr_type,
                           min_comm_options=cmo, comm_options_pct=cop,
                           comm_futures_pct=cfp, comm_stocks_pct=csp)


# ================= Дивиденды =================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_dividends_smartlab() -> pd.DataFrame:
    url = "https://smart-lab.ru/dividends/index/order_by_ticker/desc/"
    headers = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0 Safari/537.36")}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception:
        return pd.DataFrame(columns=["ticker", "dividend_rub", "record_date", "stock_price"])
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, flags=re.DOTALL | re.IGNORECASE)
    records = []
    for row_html in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, flags=re.DOTALL | re.IGNORECASE)
        if len(cells) < 10:
            continue
        clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        ticker = clean[1].upper() if len(clean) > 1 else ""
        if not ticker or not re.match(r'^[A-Z0-9]+$', ticker):
            continue
        try:
            dividend = float(clean[3].replace(",", ".").replace(" ", ""))
        except Exception:
            continue
        date_str = None
        for idx in (7, 6, 8):
            if idx < len(clean) and re.match(r'\d{2}\.\d{2}\.\d{4}', clean[idx]):
                date_str = clean[idx]
                break
        if not date_str:
            continue
        try:
            record_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except Exception:
            continue
        stock_price = None
        try:
            price_str = clean[9].replace(",", ".").replace(" ", "").replace("₽", "")
            stock_price = float(price_str)
        except Exception:
            pass
        records.append({"ticker": ticker, "dividend_rub": dividend,
                        "record_date": record_date, "stock_price": stock_price})
    return pd.DataFrame(records)


def get_dividend_yield_for_ticker(ticker: str, expiry_str: str):
    df = fetch_dividends_smartlab()
    if df.empty:
        return None, None, None
    try:
        exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except Exception:
        return None, None, None
    candidates = df[(df["ticker"] == ticker.upper())
                    & (df["record_date"] <= exp_date)
                    & (df["record_date"] >= date.today())]
    if candidates.empty:
        return None, None, None
    row = candidates.sort_values("record_date").iloc[0]
    div = float(row["dividend_rub"])
    price = row["stock_price"]
    if price is None or price <= 0:
        return None, None, None
    return div / price, float(price), row["record_date"]


# ================= G-кривая ОФЗ =================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_g_curve_params():
    if _is_failed_recently("g_curve", cooldown_sec=120):
        return None
    url = "https://iss.moex.com/iss/engines/stock/zcyc/securities.json"
    data = iss_get_json(url, timeout=15)
    if data is None:
        _mark_failed("g_curve", cooldown_sec=120)
        return None
    params = data.get('params', {})
    columns = params.get('columns', [])
    values = params.get('data', [])
    if not columns or not values:
        _mark_failed("g_curve", cooldown_sec=120)
        return None
    df = pd.DataFrame(values, columns=columns)
    row = df.iloc[0]
    try:
        return {'beta0': float(row['B1']), 'beta1': float(row['B2']),
                'beta2': float(row['B3']), 'tau': float(row['T1']),
                'g': [float(row[f'G{i}']) for i in range(1, 10)]}
    except Exception:
        return None


_GC_A = [0.0, 0.4, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0]
_GC_B = [0.4, 0.6, 1.0, 1.6, 2.4, 4.0, 6.4, 9.6, 16.0]


def g_curve_yield(t_years: float, p: dict):
    if p is None or t_years <= 0:
        return None
    b0, b1, b2, tau = p['beta0'], p['beta1'], p['beta2'], p['tau']
    g = p['g']
    if tau <= 0:
        tau = 1.0
    exp_term = math.exp(-t_years / tau)
    frac = (1 - exp_term) * tau / t_years
    term1 = b0
    term2 = b1 * frac
    term3 = b2 * (frac - exp_term)
    term4 = 0.0
    for i in range(9):
        if _GC_B[i] != 0:
            term4 += g[i] * math.exp(-((t_years - _GC_A[i]) ** 2) / (_GC_B[i] ** 2))
    raw = term1 + term2 + term3 + term4
    rate_pct = raw / 10000.0
    if rate_pct < 0.5 or rate_pct > 50:
        rate_pct = raw / 100.0 if raw > 100 else raw
    return rate_pct


def get_risk_free_rate_for_expiry(expiry_str: str, current_str: str = None):
    params = fetch_g_curve_params()
    if params is None:
        return None
    try:
        exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        cur_date = (datetime.strptime(current_str, "%Y-%m-%d").date()
                    if current_str else date.today())
        days = (exp_date - cur_date).days
        if days <= 0:
            return None
        return round(g_curve_yield(days / 365.0, params), 4)
    except Exception:
        return None


# ================= Цены =================
@st.cache_data(ttl=10, show_spinner=False)
def fetch_last_price_from_iss(secid: str, asset_type_ui: str):
    if not secid:
        return {"last": None, "secid": secid, "source": "—"}
    if asset_type_ui in ("Фьючерс", "Валюта", "Товар"):
        engine, market = "futures", "forts"
    elif asset_type_ui == "Индекс":
        engine, market = "stock", "index"
    else:
        engine, market = "stock", "shares"
    url = (f"https://iss.moex.com/iss/engines/{engine}/markets/{market}"
           f"/securities/{secid}.json")
    data = iss_get_json(url, params={"iss.meta": "off", "iss.only": "marketdata"}, timeout=15)
    if data is None:
        return {"last": None, "secid": secid, "source": "ошибка"}
    md = data.get("marketdata", {})
    cols = md.get("columns", [])
    rows = md.get("data", [])
    if not rows or not cols:
        return {"last": None, "secid": secid, "source": "нет данных"}
    rd = dict(zip(cols, rows[0]))
    for key in ("LAST", "MARKETPRICE", "LCLOSEPRICE", "LASTTOPREVPRICE", "OPEN", "SETTLEPRICE"):
        val = rd.get(key)
        if val and val > 0:
            return {"last": float(val), "secid": secid, "source": key}
    return {"last": None, "secid": secid, "source": "нет цены"}


@st.cache_data(ttl=3600, show_spinner=False)
def resolve_underlying_secid(asset_code: str, asset_type_ui: str):
    if asset_type_ui == "Акция":
        return asset_code.upper()
    if asset_type_ui == "Индекс":
        idx_map = {"RTS": "RTSI", "MIX": "IMOEX"}
        return idx_map.get(asset_code.upper(), asset_code.upper())
    if asset_type_ui in ("Фьючерс", "Валюта", "Товар"):
        url = "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json"
        data = iss_get_json(url, params={"iss.meta": "off", "iss.only": "securities"}, timeout=20)
        if data is None:
            return None
        try:
            cols = data["securities"]["columns"]
            rows = data["securities"]["data"]
            df = pd.DataFrame(rows, columns=cols)
            if "ASSETCODE" not in df.columns:
                return None
            df = df[df["ASSETCODE"] == asset_code.upper()]
            if df.empty:
                return None
            today_str = date.today().isoformat()
            if "LASTTRADEDATE" in df.columns:
                df_live = df[df["LASTTRADEDATE"] >= today_str]
                df = df_live if not df_live.empty else df
                df = df.dropna(subset=["LASTTRADEDATE"]).sort_values("LASTTRADEDATE")
            return df.iloc[0]["SECID"] if not df.empty else None
        except Exception:
            return None
    return asset_code.upper()


@st.cache_data(ttl=600, show_spinner=False)
def fetch_futures_info_iss(secid: str):
    if not secid:
        return None
    url = (f"https://iss.moex.com/iss/engines/futures/markets/forts"
           f"/securities/{secid}.json")
    data = iss_get_json(url, params={"iss.meta": "off", "iss.only": "securities,marketdata"}, timeout=15)
    if data is None:
        return None
    result = {"last": None, "expiration": None, "go": None, "secid": secid}
    sec = data.get("securities", {})
    if sec.get("data"):
        rd = dict(zip(sec["columns"], sec["data"][0]))
        for key in ("LASTTRADEDATE", "LASTDELDATE"):
            if rd.get(key):
                try:
                    result["expiration"] = str(rd[key])
                except Exception:
                    pass
                break
    md = data.get("marketdata", {})
    if md.get("data"):
        rd = dict(zip(md["columns"], md["data"][0]))
        for key in ("LAST", "MARKETPRICE", "LCLOSEPRICE", "LASTTOPREVPRICE", "OPEN", "SETTLEPRICE"):
            v = rd.get(key)
            if v and v > 0:
                result["last"] = float(v)
                break
    return result


@st.cache_data(ttl=600, show_spinner=False)
def fetch_stock_info_iss(secid: str):
    if not secid:
        return None
    url = (f"https://iss.moex.com/iss/engines/stock/markets/shares"
           f"/securities/{secid}.json")
    data = iss_get_json(url, params={"iss.meta": "off", "iss.only": "securities,marketdata"}, timeout=15)
    if data is None:
        return None
    result = {"last": None, "shortname": None, "secid": secid}
    sec = data.get("securities", {})
    if sec.get("data"):
        rd = dict(zip(sec["columns"], sec["data"][0]))
        result["shortname"] = rd.get("SHORTNAME")
        for key in ("LAST", "PREVPRICE", "PREVLEGALCLOSEPRICE"):
            v = rd.get(key)
            if v and v > 0:
                result["last"] = float(v)
                break
    md = data.get("marketdata", {})
    if md.get("data"):
        rd = dict(zip(md["columns"], md["data"][0]))
        for key in ("LAST", "MARKETPRICE", "LCLOSEPRICE", "LASTTOPREVPRICE", "OPEN"):
            v = rd.get(key)
            if v and v > 0:
                result["last"] = float(v)
                break
    return result


@st.cache_data(ttl=300, show_spinner=False)
def fetch_index_info_iss(secid: str):
    if not secid:
        return None
    url = (f"https://iss.moex.com/iss/engines/stock/markets/index"
           f"/securities/{secid}.json")
    data = iss_get_json(url, params={"iss.meta": "off", "iss.only": "securities,marketdata"}, timeout=15)
    if data is None:
        return None
    result = {"last": None, "secid": secid, "expiration": None}
    md = data.get("marketdata", {})
    if md.get("data"):
        rd = dict(zip(md["columns"], md["data"][0]))
        for key in ("CURRENTVALUE", "LASTVALUE", "LAST", "LCLOSEPRICE", "OPEN"):
            v = rd.get(key)
            if v and v > 0:
                result["last"] = float(v)
                break
    return result


@st.cache_data(ttl=300, show_spinner=False)
def fetch_ba_iss_info(secid: str, asset_type_ui: str):
    if asset_type_ui in ("Фьючерс", "Валюта", "Товар"):
        return fetch_futures_info_iss(secid)
    elif asset_type_ui == "Индекс":
        return fetch_index_info_iss(secid)
    return fetch_stock_info_iss(secid)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_futures_contracts_list(asset_code: str):
    if not asset_code:
        return []
    url = "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json"
    data = iss_get_json(url, params={"iss.meta": "off", "iss.only": "securities"}, timeout=20)
    if data is None:
        return []
    try:
        cols = data["securities"]["columns"]
        rows = data["securities"]["data"]
        df = pd.DataFrame(rows, columns=cols)
        if "ASSETCODE" not in df.columns:
            return []
        df = df[df["ASSETCODE"] == asset_code.upper()]
        if df.empty:
            return []
        if "LASTTRADEDATE" in df.columns:
            df = df.dropna(subset=["LASTTRADEDATE"])
            today_str = date.today().isoformat()
            df = df[df["LASTTRADEDATE"] >= today_str]
        df = df.sort_values("LASTTRADEDATE")
        result = []
        for _, row in df.iterrows():
            secid = str(row.get("SECID", "")).strip()
            ltd = str(row.get("LASTTRADEDATE", "")).strip()
            shortname = str(row.get("SHORTNAME", secid)).strip()
            if secid and ltd and ltd >= "2000-01-01":
                result.append({"secid": secid, "expiration": ltd, "shortname": shortname})
        return result
    except Exception:
        return []


# ================= Паритет опционов =================
def apply_parity_delta(position: dict) -> dict:
    if position.get("Тип инструмента") == "БА" or position.get("Опцион") == "БА":
        qty = int(position.get("Кол-во", 0))
        sign = 1 if qty >= 0 else -1
        position["Дельта"] = float(sign)
        position["Гамма"] = 0.0
        position["Вега"] = 0.0
        position["Тета"] = 0.0
        position["Ро"] = 0.0
    return position


# ================= Оповещения =================
def find_alert_levels(ticker: str, category: str = None):
    df = st.session_state.get("alerts_df")
    if df is None or df.empty:
        return {"buy": None, "sell": None, "found": False}
    tk = ticker.upper().strip()
    try:
        mask = df["Тикер БА"].astype(str).str.upper().str.strip() == tk
        if category and "Категория БА" in df.columns:
            mask_cat = df["Категория БА"].astype(str).str.strip() == category
            rows = df[mask & mask_cat]
            if rows.empty:
                rows = df[mask]
        else:
            rows = df[mask]
        if rows.empty:
            return {"buy": None, "sell": None, "found": False}
        row = rows.iloc[0]
        return {"buy": float(row["Уровень покупок"]),
                "sell": float(row["Уровень продаж"]), "found": True}
    except Exception:
        return {"buy": None, "sell": None, "found": False}


def autoload_series_for(asset: str, asset_type_ui: str):
    if not asset:
        return False
    try:
        series = fetch_optionseries(asset, asset_type_ui)
        if series:
            st.session_state.series_list = series
            st.session_state.series_autoloaded_for = (asset, asset_type_ui)
            return True
    except Exception:
        pass
    return False


# ================= MOEX API: опционы =================
@st.cache_data(ttl=1800, show_spinner=False)
def get_asset_code_and_type(asset_input: str, asset_type_ui: str):
    moex_type = ASSET_TYPE_MAP.get(asset_type_ui, 'futures')
    code_to_fetch = asset_input
    if moex_type != 'futures':
        if _is_failed_recently("sec_list", cooldown_sec=120):
            return code_to_fetch, moex_type
        data = iss_get_json(SECURITIES_URL, timeout=20)
        if data is None:
            _mark_failed("sec_list", cooldown_sec=120)
            return code_to_fetch, moex_type
        try:
            securities = data.get('securities', {}).get('data', [])
            columns = data.get('securities', {}).get('columns', [])
            assetcode_idx = columns.index('ASSETCODE') if 'ASSETCODE' in columns else -1
            underlying_idx = columns.index('UNDERLYINGASSET') if 'UNDERLYINGASSET' in columns else -1
            type_idx = columns.index('UNDERLYINGTYPE') if 'UNDERLYINGTYPE' in columns else -1
            if assetcode_idx != -1 and underlying_idx != -1 and type_idx != -1:
                for row in securities:
                    if row[assetcode_idx] == asset_input:
                        if row[type_idx] != 'F':
                            code_to_fetch = row[underlying_idx]
                        break
        except Exception:
            pass
    return code_to_fetch, moex_type


@st.cache_data(ttl=300, show_spinner=False)
def fetch_optionseries(asset: str, asset_type_ui: str):
    asset_code, moex_type = get_asset_code_and_type(asset, asset_type_ui)
    url = f"{API_BASE_URL}/assets/{asset_code}/optionseries"
    data = iss_get_json(url, params={'asset_type': moex_type}, timeout=15)
    if data is None:
        return []
    series = []
    if isinstance(data, list):
        for item in data:
            if 'optionseries_code' in item and 'expiration_date' in item:
                series.append({'code': item['optionseries_code'], 'expiry': item['expiration_date']})
    elif isinstance(data, dict) and 'data' in data:
        for item in data['data']:
            if 'optionseries_code' in item and 'expiration_date' in item:
                series.append({'code': item['optionseries_code'], 'expiry': item['expiration_date']})
    return series


@st.cache_data(ttl=300, show_spinner=False)
def fetch_series_info(asset: str, asset_type_ui: str, series_code: str):
    asset_code, moex_type = get_asset_code_and_type(asset, asset_type_ui)
    url = f"{API_BASE_URL}/assets/{asset_code}/optionseries/{series_code}"
    r = iss_get(url, params={'asset_type': moex_type}, timeout=15)
    if r is None or r.status_code != 200:
        r = iss_get(url, timeout=15)
    if r is None:
        return {}
    try:
        data = r.json()
    except Exception:
        return {}
    translated = {
        "Опционная серия": data.get('optionseries_code', '—'),
        "Базовый актив": data.get('asset_code', '—'),
        "Тип БА": data.get('asset_type', '—'),
        "Тикер": data.get('futures_code', '—'),
        "Тип серии": data.get('series_type', '—'),
        "Дата экспирации": data.get('expiration_date', '—'),
        "Центральный страйк": data.get('central_strike', '—'),
    }
    for side_key, label in (('call', 'Опционы Call'), ('put', 'Опционы Put')):
        if side_key in data:
            s = data[side_key]
            translated[label] = {
                "Объем (руб.)": s.get('volume_rub', 0),
                "Контрактов": s.get('volume_contracts', 0),
                "Открытых позиций": s.get('openposition', 0),
                "ОИ изменение": s.get('oichange', 0)}
    return translated


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_optionboard_raw(asset_code: str, series_code: str, asset_type: str):
    for at in [asset_type, 'share', 'futures', 'index', 'currency', 'commodity']:
        url = f"{API_BASE_URL}/assets/{asset_code}/optionseries/{series_code}/optionboard"
        data = iss_get_json(url, params={'asset_type': at}, timeout=15)
        if data is not None:
            return data
    return None


def fetch_central_strike(asset_code, series_code, asset_type):
    url = f"{API_BASE_URL}/assets/{asset_code}/optionseries/{series_code}"
    data = iss_get_json(url, params={'asset_type': asset_type}, timeout=15)
    if data is not None:
        cs = data.get('central_strike')
        if cs:
            try:
                return float(cs)
            except (TypeError, ValueError):
                pass
    try:
        board = _fetch_optionboard_raw(asset_code, series_code, asset_type)
        if board:
            calls = board.get('call') or []
            puts = board.get('put') or []
            c_map = {c['strike']: c for c in calls if c.get('theorprice') and c.get('strike') is not None}
            p_map = {p['strike']: p for p in puts if p.get('theorprice') and p.get('strike') is not None}
            common = sorted(set(c_map.keys()) & set(p_map.keys()))
            fs_est = []
            for k in common:
                ct = c_map[k]['theorprice']; pt = p_map[k]['theorprice']
                if ct and pt and ct > 0 and pt > 0:
                    fs_est.append(ct - pt + float(k))
            if fs_est:
                fs_est.sort()
                f_current = fs_est[len(fs_est) // 2]
                all_strikes = list(c_map.keys()) | list(p_map.keys())
                if all_strikes:
                    return float(min(all_strikes, key=lambda s: abs(float(s) - f_current)))
    except Exception:
        pass
    return None


@st.cache_data(ttl=120, show_spinner=False)
def fetch_optionboard(asset: str, asset_type_ui: str, series_code: str):
    asset_code, _ = get_asset_code_and_type(asset, asset_type_ui)
    board_data, used_asset_type = None, None
    for at in ['share', 'futures', 'index', 'currency', 'commodity']:
        url = f"{API_BASE_URL}/assets/{asset_code}/optionseries/{series_code}/optionboard"
        data = iss_get_json(url, params={'asset_type': at}, timeout=15)
        if data is not None:
            board_data = data; used_asset_type = at
            break
    if not board_data:
        raise RuntimeError("Не удалось получить доску опционов")
    board_data['central_strike'] = fetch_central_strike(asset_code, series_code, used_asset_type)
    board_data['series_code'] = series_code
    return board_data


@st.cache_data(ttl=300, show_spinner=False)
def fetch_volatility_graph(asset: str, series_code: str, asset_type_ui: str):
    asset_code, moex_type = get_asset_code_and_type(asset, asset_type_ui)
    url = f"{API_BASE_URL}/assets/{asset_code}/optionseries/{series_code}/volatility_graph"
    data = iss_get_json(url, params={'asset_type': moex_type}, timeout=15)
    return data if data is not None else []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_bars(secid, interval=24, days=180, engine="futures", market="forts"):
    if not secid:
        return pd.DataFrame()
    end = datetime.now()
    start = end - timedelta(days=days)
    url = (f"https://iss.moex.com/iss/engines/{engine}/markets/{market}"
           f"/securities/{secid}/candles.json")
    params = {"from": start.strftime("%Y-%m-%d"), "till": end.strftime("%Y-%m-%d"),
              "interval": interval, "iss.meta": "off"}
    data = iss_get_json(url, params=params, timeout=20)
    if data is None:
        return pd.DataFrame()
    cols = data.get("candles", {}).get("columns", [])
    rows = data.get("candles", {}).get("data", [])
    if not rows or not cols:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=cols)
    df["begin"] = pd.to_datetime(df["begin"], errors="coerce")
    df = df.dropna(subset=["begin", "open", "high", "low", "close"])
    df = df[df["begin"] >= pd.Timestamp("2000-01-01")]
    df = df[(df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0)]
    return df.sort_values("begin").reset_index(drop=True)


@st.cache_data(ttl=10, show_spinner=False)
def get_last_close_price(secid: str, engine: str, market: str):
    if not secid:
        return None
    end = datetime.now()
    start = end - timedelta(days=7)
    url = (f"https://iss.moex.com/iss/engines/{engine}/markets/{market}"
           f"/securities/{secid}/candles.json")
    params = {"from": start.strftime("%Y-%m-%d"), "till": end.strftime("%Y-%m-%d"),
              "interval": 24, "iss.meta": "off"}
    data = iss_get_json(url, params=params, timeout=15)
    if data is None:
        return None
    cols = data.get("candles", {}).get("columns", [])
    rows = data.get("candles", {}).get("data", [])
    if not rows or not cols:
        return None
    df = pd.DataFrame(rows, columns=cols)
    if "close" not in df.columns:
        return None
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    if df.empty:
        return None
    try:
        return float(df.iloc[-1]["close"])
    except Exception:
        return None


# ================= Payoff-расчёты =================
def compute_payoff(positions, S_values, comm_func=None):
    S = np.asarray(S_values, dtype=float)
    pnl = np.zeros_like(S)
    for p in positions:
        if not p.get("visible", True):
            continue
        qty = int(p.get("Кол-во", 0))
        entry = float(p.get("Цена", 0))
        _instr = p.get("Тип инструмента", "Опцион")
        com = comm_func(entry, _instr) if comm_func else 0.0
        if p.get("Тип инструмента") == "БА" or p.get("Опцион") == "БА":
            pnl += (S - entry) * qty
            continue
        K = float(p["Страйк"]) if p.get("Страйк") is not None else 0
        if K == 0:
            continue
        if p["Опцион"] == "Call":
            intrinsic = np.maximum(0, S - K)
        else:
            intrinsic = np.maximum(0, K - S)
        pnl += (intrinsic - entry - com) * qty
    return pnl


def find_breakevens(positions, price_min, price_max, n=500, comm_func=None):
    prices = np.linspace(price_min, price_max, n)
    pnl = compute_payoff(positions, prices, comm_func=comm_func)
    be = []
    for i in range(1, len(prices)):
        if pnl[i-1] * pnl[i] < 0:
            denom = pnl[i] - pnl[i-1]
            if abs(denom) > 1e-12:
                x0 = prices[i-1] + (prices[i] - prices[i-1]) * (-pnl[i-1]) / denom
                be.append(float(x0))
    return be


# ================= Биржевой график (мобильная высота) =================
def render_exchange_chart(df, positions, buy_level, sell_level,
                          strikes, title, key, current_price=None, comm_func=None):
    if df is None or df.empty:
        st.info(f"Нет данных для {title}")
        return

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.04, row_heights=[0.78, 0.22])

    fig.add_trace(go.Ohlc(x=df["begin"], open=df["open"], high=df["high"],
                          low=df["low"], close=df["close"],
                          increasing_line_color="black",
                          decreasing_line_color="black",
                          name="Цена", showlegend=False), row=1, col=1)
    fig.add_trace(go.Bar(x=df["begin"], y=df["volume"], marker_color="black",
                         name="Объём", showlegend=False), row=2, col=1)

    price_min = float(df["low"].min()) * 0.97
    price_max = float(df["high"].max()) * 1.03

    if positions:
        be_points = find_breakevens(positions, price_min, price_max, n=500, comm_func=comm_func)
        segments = [price_min] + sorted(be_points) + [price_max]
        for i in range(len(segments) - 1):
            seg_start = segments[i]; seg_end = segments[i + 1]
            mid = (seg_start + seg_end) / 2
            mid_pnl = compute_payoff(positions, [mid], comm_func=comm_func)[0]
            color = ("rgba(0,220,80,0.28)" if mid_pnl > 0 else "rgba(255,40,40,0.22)")
            fig.add_shape(type="rect", xref="x domain", x0=0, x1=1,
                          yref="y", y0=seg_start, y1=seg_end,
                          fillcolor=color, line_width=0, layer="below", row=1, col=1)
    else:
        be_points = []

    if strikes:
        visible_strikes = sorted(float(s) for s in strikes if price_min <= float(s) <= price_max)
        for K in visible_strikes:
            fig.add_hline(y=K, line=dict(color="#9c00ff", width=1, dash="dot"),
                          opacity=0.45, row=1, col=1)
            _k_txt = f"{int(K)}" if float(K).is_integer() else f"{K:.2f}"
            fig.add_annotation(x=0.5, y=K, xref="paper", yref="y",
                               text=_k_txt, showarrow=False,
                               font=dict(size=9, color="#7f9bb3"),
                               bgcolor="rgba(255,255,255,0.78)", row=1, col=1)

    buy_markers = []; sell_markers = []
    for p in (positions or []):
        if not p.get("visible", True) or p.get("Опцион") not in ("Call", "Put"):
            continue
        qty = int(p.get("Кол-во", 0))
        if qty == 0:
            continue
        K = p.get("Страйк")
        if K is None:
            continue
        code = "C" if p["Опцион"] == "Call" else "P"
        color = "#00a651" if p["Опцион"] == "Call" else "#d32f2f"
        sign = "+" if qty > 0 else "-"
        Ks = f"{int(K)}" if float(K).is_integer() else f"{K:.2f}"
        entry = {"text": f"{sign}{abs(qty)}{code} {Ks}", "color": color}
        (buy_markers if qty > 0 else sell_markers).append(entry)

    def _add_level(level, label_txt, line_color, markers):
        fig.add_hline(y=level, line=dict(color=line_color, width=2.5), row=1, col=1)
        fig.add_annotation(x=0.5, y=level, xref="paper", yref="y",
                           text=label_txt, showarrow=False,
                           font=dict(size=10, color=line_color, family="Arial Black"),
                           bgcolor="rgba(255,255,255,0.85)", yshift=11, row=1, col=1)
        for i, m in enumerate(markers[:6]):
            fig.add_annotation(x=0.5, y=level, xref="paper", yref="y",
                               text=m["text"], showarrow=False,
                               font=dict(size=10, color=m["color"], family="Consolas, monospace"),
                               bgcolor="rgba(255,255,255,0.88)",
                               xshift=80 + i * 72, yshift=11, row=1, col=1)

    if buy_level and buy_level > 0:
        _add_level(buy_level, f"Покупка {buy_level:.2f}", "#9c00ff", buy_markers)
    if sell_level and sell_level > 0:
        _add_level(sell_level, f"Продажа {sell_level:.2f}", "#fb92f0", sell_markers)

    if current_price is not None and current_price > 0:
        fig.add_hline(y=current_price,
                      line=dict(color="#1e88e5", width=2, dash="dash"), row=1, col=1)
        fig.add_annotation(x=0.5, y=current_price, xref="paper", yref="y",
                           text=f"Текущая {current_price:.2f}", showarrow=False,
                           font=dict(size=10, color="#1e88e5", family="Arial Black"),
                           bgcolor="rgba(255,255,255,0.90)",
                           bordercolor="#1e88e5", borderwidth=1,
                           yshift=-11, row=1, col=1)

    for be in be_points:
        fig.add_hline(y=be, line=dict(color="#00a651", width=1.5, dash="dot"), row=1, col=1)
        fig.add_annotation(x=0.5, y=be, xref="paper", yref="y",
                           text=f"БУ {be:.2f}", showarrow=False,
                           font=dict(size=10, color="#00a651", family="Arial Black"),
                           bgcolor="rgba(255,255,255,0.90)",
                           bordercolor="#00a651", borderwidth=1,
                           yshift=10, row=1, col=1)

    # 🔧 Высота графика снижена для мобильного
    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        height=360,
        margin=dict(l=10, r=10, t=36, b=20),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", showlegend=False)

    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)", side="left",
                     row=1, col=1, showspikes=True, spikemode='across',
                     spikesnap='cursor', spikecolor='#888888',
                     spikethickness=1, spikedash='dot')
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)", side="left",
                     row=2, col=1, showspikes=True, spikemode='across',
                     spikesnap='cursor', spikecolor='#888888',
                     spikethickness=1, spikedash='dot')

    _x_min_val = df["begin"].min(); _x_max_val = df["begin"].max()
    if pd.notna(_x_min_val) and pd.notna(_x_max_val):
        if len(df) >= 2:
            _diffs = df["begin"].diff().dropna()
            _step = _diffs.median() if not _diffs.empty else pd.Timedelta(days=1)
        else:
            _step = pd.Timedelta(days=1)
        if pd.isna(_step) or _step <= pd.Timedelta(0):
            _step = pd.Timedelta(days=1)
        _x_max_extended = _x_max_val + _step * 15
        fig.update_xaxes(type='date', range=[_x_min_val, _x_max_extended],
                         showgrid=True, gridcolor="rgba(0,0,0,0.05)",
                         rangeslider_visible=False, row=1, col=1,
                         showspikes=True, spikemode='across', spikesnap='cursor',
                         spikecolor='#888888', spikethickness=1, spikedash='dot')
        fig.update_xaxes(type='date', range=[_x_min_val, _x_max_extended],
                         showgrid=True, gridcolor="rgba(0,0,0,0.05)", row=2, col=1,
                         showspikes=True, spikemode='across', spikesnap='cursor',
                         spikecolor='#888888', spikethickness=1, spikedash='dot')

    st.plotly_chart(fig, use_container_width=True, key=key,
                    config={'displayModeBar': False})


# ================= Вспомогательные =================
def _color_call_put(option: str) -> str:
    if option == "Call":
        return f"<span style='color:#00a651; font-weight:700;'>{option}</span>"
    if option == "Put":
        return f"<span style='color:#d32f2f; font-weight:700;'>{option}</span>"
    return option


def _side_from_qty(qty: int) -> str:
    if qty > 0:
        return "Buy"
    if qty < 0:
        return "Sell"
    return "—"


def _new_position_id() -> str:
    return uuid.uuid4().hex[:8]


def expiry_marker(expiry_str: str) -> str:
    try:
        d = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except Exception:
        return "⚪"
    today = date.today()
    monday_this_week = today - timedelta(days=today.weekday())
    end_next_week = monday_this_week + timedelta(days=13)
    end_week_after = monday_this_week + timedelta(days=20)
    if d <= end_next_week:
        return "🔴"
    if d <= end_week_after:
        return "🔵"
    return "🟢"


# ================= Матчинг стратегий =================
def _leg_matches_position(leg, pos):
    if not pos.get("visible", True):
        return False
    if pos.get("Опцион") != leg["option"]:
        return False
    pos_side = "Buy" if int(pos.get("Кол-во", 0)) >= 0 else "Sell"
    return pos_side == leg["side"]


def match_strategy_with_positions(strategy_def, positions):
    matched = {}; used_positions = set(); matched_strikes_by_group = {}
    total_required = 0; total_covered = 0
    for li, leg in enumerate(strategy_def["legs"]):
        req_qty = leg["qty"]; total_required += req_qty
        best_pi = None; best_cover = 0
        for pi, p in enumerate(positions):
            if pi in used_positions or not _leg_matches_position(leg, p):
                continue
            have = abs(int(p.get("Кол-во", 0)))
            cover = min(have, req_qty)
            if cover > best_cover:
                best_cover = cover; best_pi = pi
        if best_pi is not None:
            used_positions.add(best_pi)
            matched[li] = {"pos_index": best_pi, "qty_covered": best_cover,
                           "qty_required": req_qty, "full": best_cover >= req_qty}
            total_covered += best_cover
            grp = leg["strike_group"]
            if grp not in matched_strikes_by_group:
                matched_strikes_by_group[grp] = float(positions[best_pi]["Страйк"])
    missing = [i for i in range(len(strategy_def["legs"])) if i not in matched]
    weight = total_covered / total_required if total_required else 0.0
    all_full = all(m["full"] for m in matched.values()) if matched else False
    return {"matched": matched, "missing": missing,
            "matched_strikes_by_group": matched_strikes_by_group,
            "weight": weight, "is_full": all_full and not missing}


# ================= postMessage-мост =================
def _send_to_iframes(payload: dict, delays=(300, 1000, 2500)):
    delays_js = "\n".join([f"setTimeout(send, {d});" for d in delays])
    js = f"""
    <script>
    (function() {{
      const payload = {json.dumps(payload, ensure_ascii=False)};
      function send() {{
        try {{
          const frames = window.parent.document.querySelectorAll('iframe');
          frames.forEach(f => {{
            try {{ f.contentWindow.postMessage(payload, '*'); }} catch (e) {{}}
          }});
        }} catch (e) {{}}
      }}
      send();
      {delays_js}
    }})();
    </script>
    """
    components.html(js, height=0)


def push_expiry_to_calculator(expiry_str: str, series_code: str = ""):
    _send_to_iframes({"type": "setExpiry", "value": expiry_str, "series_code": series_code},
                     delays=(200, 500, 1000, 1500, 2200, 3000, 4000, 5500, 7000))


def push_tv_ticker(ticker_label: str, tv_symbol: str):
    _send_to_iframes({"type": "setTicker", "ticker": ticker_label, "symbol": tv_symbol},
                     delays=(300, 700, 1200, 2000, 3500, 5000))


def push_strikes_to_calculator(strikes_iv: list, central_strike):
    _send_to_iframes({"type": "setStrikes", "strikes": strikes_iv, "central": central_strike},
                     delays=(200, 500, 1000, 1500, 2200, 3000, 4000, 5500, 7000))


def push_calc_params(rf_buy=None, rf_sell=None, div_buy=None, div_sell=None,
                     vol_buy=None, vol_sell=None):
    _send_to_iframes({"type": "setCalcParams",
                      "rf_buy": float(rf_buy) if rf_buy is not None else 0.0,
                      "rf_sell": float(rf_sell) if rf_sell is not None else 0.0,
                      "div_buy": float(div_buy) if div_buy is not None else 0.0,
                      "div_sell": float(div_sell) if div_sell is not None else 0.0,
                      "vol_buy": float(vol_buy) if vol_buy is not None else 30.0,
                      "vol_sell": float(vol_sell) if vol_sell is not None else 30.0},
                     delays=(500, 1500, 3000))


def push_alert_levels(ticker: str, buy_lvl, sell_lvl):
    _send_to_iframes({"type": "setAlertLevels",
                      "ticker": ticker or "",
                      "buy": float(buy_lvl) if buy_lvl is not None else None,
                      "sell": float(sell_lvl) if sell_lvl is not None else None},
                     delays=(500, 1500, 3000))


# ==================================================================
# ===================== UI =========================================
# ==================================================================
st.markdown("<h2 style='margin-bottom:.2rem;'>MOEX Options</h2>", unsafe_allow_html=True)

def _safe_float_qp(key, default=0.0):
    try:
        return float(st.query_params.get(key, default) or default)
    except (TypeError, ValueError):
        return default

st.session_state["_calc_level_buy"]  = _safe_float_qp("level_buy", 0.0)
st.session_state["_calc_level_sell"] = _safe_float_qp("level_sell", 0.0)
st.session_state["_calc_riskfree"]   = _safe_float_qp("rf_buy", 0.0)
st.session_state["_calc_volatility"] = _safe_float_qp("vol_buy", 0.0)
st.session_state["_calc_dividend"]   = _safe_float_qp("div_buy", 0.0)

# ================= КОРОТКИЕ ИМЕНА ВКЛАДОК + МЕНЮ «⋮» =================
TAB_NAMES = ["Калькулятор", "Позиция", "Опционы", "Уведомления"]

if "target_tab" not in st.session_state:
    st.session_state.target_tab = None

_h1, _h2 = st.columns([5, 1])
with _h2:
    with st.popover("⋮"):
        st.markdown("**Навигация**")
        for _name in TAB_NAMES:
            if st.button(_name, use_container_width=True, key=f"nav_{_name}"):
                st.session_state.target_tab = _name
                st.rerun()

tab_calc, tab_position, tab_board, tab_alerts = st.tabs(TAB_NAMES)

# Swipe + программное переключение вкладок
components.html(
    f"""
    <script>
    (function() {{
      const parentDoc = window.parent.document;
      if (parentDoc.__swipeBound) return;
      parentDoc.__swipeBound = true;
      let _sx = 0, _ex = 0;
      parentDoc.addEventListener('touchstart', e => {{
        _sx = e.changedTouches[0].screenX;
      }}, {{passive: true}});
      parentDoc.addEventListener('touchend', e => {{
        _ex = e.changedTouches[0].screenX;
        const tabs = parentDoc.querySelectorAll('button[role="tab"]');
        if (tabs.length === 0) return;
        let activeIdx = -1;
        tabs.forEach((t, i) => {{
          if (t.getAttribute('aria-selected') === 'true') activeIdx = i;
        }});
        if (_ex < _sx - 60 && activeIdx > -1 && activeIdx < tabs.length - 1) {{
          tabs[activeIdx + 1].click();
        }} else if (_ex > _sx + 60 && activeIdx > 0) {{
          tabs[activeIdx - 1].click();
        }}
      }}, {{passive: true}});
    }})();
    </script>
    """, height=0, width=0)

_target = st.session_state.target_tab
if _target:
    components.html(
        f"""
        <script>
        (function() {{
          const tabs = window.parent.document.querySelectorAll('button[role="tab"]');
          tabs.forEach(t => {{
            if (t.innerText.trim() === "{_target}") t.click();
          }});
        }})();
        </script>
        """, height=0, width=0)
    st.session_state.target_tab = None


# ==================================================================
# ============ ВКЛАДКА 1: КАЛЬКУЛЯТОР =============================
# ==================================================================
with tab_calc:
    if "asset_input" not in st.session_state:
        st.session_state.asset_input = "RTS"
    if "asset_type_ui" not in st.session_state:
        st.session_state.asset_type_ui = "Фьючерс"

    _need_expand = not st.session_state.get("board_loaded", False)

    with st.expander("⚙️ Параметры инструмента", expanded=_need_expand):
        with st.expander("📖 Справочник инструментов MOEX", expanded=False):
            if not MOEX_INSTRUMENTS:
                st.warning("⚠ Справочник пуст.")
            else:
                filter_text = st.text_input("Поиск", key="dict_filter",
                                            placeholder="GAZP, Сбер…").strip().lower()
                dict_tabs = st.tabs(list(MOEX_INSTRUMENTS.keys()))
                for dtab, (category, items) in zip(dict_tabs, MOEX_INSTRUMENTS.items()):
                    with dtab:
                        filtered = {code: (atype, name) for code, (atype, name) in items.items()
                                    if not filter_text or filter_text in code.lower()
                                    or filter_text in name.lower()}
                        if not filtered:
                            st.caption("Ничего не найдено.")
                            continue
                        n_cols = 3
                        cols = st.columns(n_cols)
                        for i, (code, (asset_type, name)) in enumerate(filtered.items()):
                            with cols[i % n_cols]:
                                if st.button(code, key=f"dict_{category}_{code}",
                                             use_container_width=True, help=name):
                                    st.session_state.asset_input = code
                                    st.session_state.asset_type_ui = asset_type
                                    st.session_state.board_loaded = False
                                    st.rerun()

        pc1, pc2 = st.columns([2, 2])
        with pc1:
            _raw_asset = st.text_input("Базовый актив", key="asset_input",
                                       placeholder="RTS, Si, GAZP…").strip()
        with pc2:
            asset_type_ui = st.selectbox(
                "Категория БА",
                ["Фьючерс", "Акция", "Валюта", "Товар", "Индекс"],
                key="asset_type_ui")

        asset = resolve_canonical_asset_code(_raw_asset)

        _last_loaded = st.session_state.get("series_autoloaded_for", (None, None))
        if asset and (asset, asset_type_ui) != _last_loaded:
            autoload_series_for(asset, asset_type_ui)

        if st.button("🔄 Загрузить доску", use_container_width=True, type="primary"):
            with st.spinner("Загрузка серий..."):
                try:
                    st.session_state.series_list = fetch_optionseries(asset, asset_type_ui)
                    st.session_state.series_autoloaded_for = (asset, asset_type_ui)
                except Exception as e:
                    st.error(f"Ошибка: {e}")
                    st.session_state.series_list = []

        if st.session_state.get("series_list"):
            sorted_series = sorted(st.session_state.series_list, key=lambda x: x.get("expiry", ""))
            option_labels = [f"{expiry_marker(s['expiry'])} {s['expiry']} — {s['code']}"
                             for s in sorted_series]
            chosen = st.selectbox("Экспирация", option_labels, index=0)
            chosen_idx = option_labels.index(chosen)
            selected = sorted_series[chosen_idx]
            series_code = selected["code"]; expiry_str = selected["expiry"]

            st.session_state.selected_asset = asset
            st.session_state.selected_asset_type_ui = asset_type_ui
            st.session_state.selected_series_code = series_code
            st.session_state.selected_expiry = expiry_str
            st.session_state.board_loaded = True

            try:
                info = fetch_series_info(asset, asset_type_ui, series_code)
                with st.expander("ℹ️ О серии", expanded=False):
                    st.json(info, expanded=True)
            except Exception:
                pass

    if st.session_state.get("board_loaded") and "selected_series_code" in st.session_state:
        asset = st.session_state.get("selected_asset", "")
        asset_type_ui = st.session_state.get("selected_asset_type_ui", "")
        series_code = st.session_state.get("selected_series_code", "")
        expiry_str = st.session_state.get("selected_expiry", "")

        st.success(f"**{asset}** · {expiry_str} · `{series_code}`")

        _alert_levels = find_alert_levels(asset, category=asset_type_ui)
        if _alert_levels["found"]:
            st.info(f"🎯 Покупка = {_alert_levels['buy']:.2f} · "
                    f"Продажа = {_alert_levels['sell']:.2f}")
            push_alert_levels(asset, _alert_levels["buy"], _alert_levels["sell"])
        else:
            push_alert_levels(asset, None, None)

        if asset_type_ui == "Акция":
            rfr = get_risk_free_rate_for_expiry(expiry_str)
            if rfr is not None:
                st.caption(f"Безриск. ставка (G-кривая): **{rfr:.4f}%**")
            q, stock_price, rec_date = get_dividend_yield_for_ticker(asset, expiry_str)
            if q is not None and stock_price is not None:
                st.caption(f"Див. доходность: **{q*100:.2f}%** · цена: {stock_price:.2f}₽ · реестр: {rec_date.strftime('%d.%m.%Y')}")
        else:
            rfr = None; q = None

    st.markdown("---")

    # ---- Инъекция в index.html ----
    _inject = {"strikes": [], "central_strike": None, "expiry": "", "series_code": "",
               "rf_buy": None, "rf_sell": None, "div_buy": None, "div_sell": None,
               "vol_buy": 30.0, "vol_sell": 30.0,
               "alerts": {"ticker": "", "buy": None, "sell": None}, "market_price": None}
    _futures_contract_for_chart = None

    if st.session_state.get("board_loaded") and "selected_series_code" in st.session_state:
        _asset_inj = st.session_state.get("selected_asset", "")
        _atype_inj = st.session_state.get("selected_asset_type_ui", "")
        _series_inj = st.session_state.get("selected_series_code", "")
        _expiry_inj = st.session_state.get("selected_expiry", "")

        _inject["expiry"] = _expiry_inj; _inject["series_code"] = _series_inj

        try:
            _board_inj = fetch_optionboard(_asset_inj, _atype_inj, _series_inj)
            _calls_inj = _board_inj.get('call') or []
            _puts_inj = _board_inj.get('put') or []
            _central_inj = _board_inj.get('central_strike')
            if _central_inj is not None:
                try:
                    _inject["central_strike"] = float(_central_inj)
                except (TypeError, ValueError):
                    _inject["central_strike"] = None
            _strikes_set = set()
            _strikes_iv_inj = []
            for _c in _calls_inj:
                if _c.get('strike') is not None:
                    _strikes_set.add(_c['strike'])
            for _p in _puts_inj:
                if _p.get('strike') is not None:
                    _strikes_set.add(_p['strike'])
            for _k in sorted(_strikes_set):
                _c_iv = next((c.get('volatility') for c in _calls_inj if c.get('strike') == _k), None)
                _p_iv = next((p.get('volatility') for p in _puts_inj if p.get('strike') == _k), None)
                _iv = _c_iv or _p_iv
                _k_val = float(_k)
                _strikes_iv_inj.append({
                    "strike": int(_k_val) if _k_val.is_integer() else _k_val,
                    "iv": float(_iv) if _iv is not None else None})
            _inject["strikes"] = _strikes_iv_inj
        except Exception:
            pass

        try:
            _ser_info_inj = fetch_series_info(_asset_inj, _atype_inj, _series_inj)
            _futures_contract_for_chart = _ser_info_inj.get("Тикер", "")
            if _futures_contract_for_chart == "—":
                _futures_contract_for_chart = None
        except Exception:
            pass

        if _atype_inj == "Акция":
            try:
                _rf_inj = get_risk_free_rate_for_expiry(_expiry_inj)
                _inject["rf_buy"] = _rf_inj; _inject["rf_sell"] = _rf_inj
            except Exception:
                pass
            try:
                _q_inj, _sp_inj, _rd_inj = get_dividend_yield_for_ticker(_asset_inj, _expiry_inj)
                _inject["div_buy"] = _q_inj; _inject["div_sell"] = _q_inj
            except Exception:
                pass
        else:
            _inject["rf_buy"] = 0.0; _inject["rf_sell"] = 0.0
            _inject["div_buy"] = 0.0; _inject["div_sell"] = 0.0

        _alv = find_alert_levels(_asset_inj, category=_atype_inj)
        if _alv["found"]:
            _inject["alerts"]["ticker"] = _asset_inj
            _inject["alerts"]["buy"] = _alv["buy"]
            _inject["alerts"]["sell"] = _alv["sell"]

        try:
            if _atype_inj in ("Фьючерс", "Валюта", "Товар"):
                _eng_mkt, _mkt_mkt = "futures", "forts"
            elif _atype_inj == "Индекс":
                _eng_mkt, _mkt_mkt = "stock", "index"
            else:
                _eng_mkt, _mkt_mkt = "stock", "shares"
            if _futures_contract_for_chart:
                _mkt_secid = _futures_contract_for_chart
            else:
                _mkt_secid = resolve_underlying_secid(_asset_inj, _atype_inj)
            _close_price = get_last_close_price(_mkt_secid, _eng_mkt, _mkt_mkt)
            if _close_price is not None:
                _inject["market_price"] = _close_price
                st.session_state["quick_und_last_price"] = _close_price
                st.session_state["_current_market_price"] = _close_price
        except Exception:
            pass

    _calc_html_path = Path("index.html")
    calc_html = None
    if not _calc_html_path.exists():
        st.error("Файл `index.html` не найден.")
    else:
        try:
            calc_html = _calc_html_path.read_text(encoding="utf-8")
        except Exception as e:
            st.error(f"Не удалось прочитать index.html: {e}")
            calc_html = None

    if calc_html is not None:
        if HTML_PLACEHOLDER not in calc_html:
            st.warning("⚠ В index.html не найден плейсхолдер.")
        else:
            _inject_json = json.dumps(_inject, ensure_ascii=False, default=str)
            _inject_json = _inject_json.replace("</", "<\\/")
            calc_html = calc_html.replace(HTML_PLACEHOLDER, _inject_json)

    # 🔧 На мобильном колонки стакаются вертикально — Streamlit сам это делает при узком экране
    col_calc, col_charts = st.columns([1.05, 1])

    with col_calc:
        if calc_html is None:
            st.info("Калькулятор недоступен.")
        else:
            components.html(calc_html, height=1150, scrolling=True)

    with col_charts:
        st.markdown("#### 📈 Графики")
        if not st.session_state.get("board_loaded"):
            st.info("Выберите серию.")
        else:
            try:
                _asset_ch = st.session_state.get("selected_asset", "")
                _atype_ch = st.session_state.get("selected_asset_type_ui", "")
                _series_ch = st.session_state.get("selected_series_code", "")

                if _atype_ch in ("Фьючерс", "Валюта", "Товар"):
                    _eng, _mkt = "futures", "forts"
                elif _atype_ch == "Индекс":
                    _eng, _mkt = "stock", "index"
                else:
                    _eng, _mkt = "stock", "shares"

                if _futures_contract_for_chart:
                    _secid_ch = _futures_contract_for_chart
                else:
                    _secid_ch = resolve_underlying_secid(_asset_ch, _atype_ch) or _asset_ch

                _strikes_ch = []
                try:
                    _board_ch = fetch_optionboard(_asset_ch, _atype_ch, _series_ch)
                    _calls_ch = _board_ch.get('call') or []
                    _puts_ch = _board_ch.get('put') or []
                    _strikes_ch = sorted({float(c['strike']) for c in _calls_ch if c.get('strike') is not None}
                                         | {float(p['strike']) for p in _puts_ch if p.get('strike') is not None})
                except Exception:
                    pass

                _today_d = date.today()
                _year_start = date(_today_d.year, 1, 1)
                _d1_days = (_today_d - _year_start).days + 1
                _h1_days = 25

                _df_d1 = fetch_bars(_secid_ch, interval=24, days=_d1_days, engine=_eng, market=_mkt)
                _df_h1 = fetch_bars(_secid_ch, interval=60, days=_h1_days, engine=_eng, market=_mkt)

                _buy_ch = float(st.session_state.get("_calc_level_buy", 0) or 0)
                _sell_ch = float(st.session_state.get("_calc_level_sell", 0) or 0)

                _current_price_ch = None
                try:
                    _current_price_ch = get_last_close_price(_secid_ch, _eng, _mkt)
                except Exception:
                    pass

                _chart_label = _futures_contract_for_chart or _asset_ch

                render_exchange_chart(_df_d1, st.session_state.get("positions", []),
                                      _buy_ch, _sell_ch, _strikes_ch,
                                      f"D1 — {_chart_label}", "chart_d1_tab",
                                      current_price=_current_price_ch, comm_func=_calc_comm_ui)
                render_exchange_chart(_df_h1, st.session_state.get("positions", []),
                                      _buy_ch, _sell_ch, _strikes_ch,
                                      f"H1 — {_chart_label}", "chart_h1_tab",
                                      current_price=_current_price_ch, comm_func=_calc_comm_ui)
            except Exception as e:
                st.warning(f"Не удалось построить графики: {e}")

    if st.session_state.get("board_loaded") and "selected_expiry" in st.session_state:
        push_expiry_to_calculator(st.session_state.selected_expiry,
                                  st.session_state.selected_series_code)


# ==================================================================
# ============ ВКЛАДКА 2: ПОЗИЦИЯ ==================================
# ==================================================================
with tab_position:
    # ---- Компактная панель управления ----
    with st.container(border=True):
        cc1, cc2 = st.columns(2)
        with cc1:
            deposit = st.number_input("Депозит, ₽", min_value=0.0, value=100000.0,
                                      step=100.0, format="%.0f", key="dep_inp")
        with cc2:
            risk_pct = st.number_input("Риск, %", min_value=0.1, max_value=100.0,
                                       value=1.0, step=0.1, format="%.1f", key="rp_inp")

        with st.expander("⚙️ Комиссии", expanded=False):
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                comm_options_pct = st.number_input("Опц. %", min_value=0.0, max_value=20.0,
                                                   value=3.0, step=0.1, format="%.2f",
                                                   key="cop_inp")
            with cc2:
                comm_futures_pct = st.number_input("Фьюч. %", min_value=0.0, max_value=5.0,
                                                   value=0.1, step=0.01, format="%.3f",
                                                   key="cfp_inp")
            with cc3:
                comm_stocks_pct = st.number_input("Акц. %", min_value=0.0, max_value=5.0,
                                                  value=0.3, step=0.01, format="%.3f",
                                                  key="csp_inp")
            min_comm_options = st.number_input("Мин. комиссия опциона, ₽", min_value=0.0,
                                               max_value=100.0, value=0.02,
                                               step=0.01, format="%.4f", key="cmo_inp")

        risk_amount = deposit * risk_pct / 100.0
        st.caption(f"💰 Доступно: **{risk_amount:,.0f} ₽**")

    def _calc_comm(premium, instr_type="Опцион"):
        return calc_commission(premium, instrument_type=instr_type,
                               min_comm_options=min_comm_options,
                               comm_options_pct=comm_options_pct,
                               comm_futures_pct=comm_futures_pct,
                               comm_stocks_pct=comm_stocks_pct)

    def _norm_cdf_py(x):
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def black_scholes_py(S, K, T, r_pct, vol_pct, div_pct, opt_type):
        if T <= 0 or S <= 0 or K <= 0 or vol_pct <= 0:
            return max(0.0, S - K) if opt_type == "call" else max(0.0, K - S)
        r = r_pct / 100.0; q = div_pct / 100.0; sigma = vol_pct / 100.0
        d1 = (math.log(S / K) + (r - q + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if opt_type == "call":
            return S * math.exp(-q * T) * _norm_cdf_py(d1) - K * math.exp(-r * T) * _norm_cdf_py(d2)
        return K * math.exp(-r * T) * _norm_cdf_py(-d2) - S * math.exp(-q * T) * _norm_cdf_py(-d1)

    def _cb_qty_dec(key): st.session_state[key] = int(st.session_state.get(key, 1)) - 1
    def _cb_qty_inc(key): st.session_state[key] = int(st.session_state.get(key, 1)) + 1
    def _cb_price_dec(key): st.session_state[key] = round(float(st.session_state.get(key, 0.0)) - 0.01, 4)
    def _cb_price_inc(key): st.session_state[key] = round(float(st.session_state.get(key, 0.0)) + 0.01, 4)

    if "positions" not in st.session_state:
        st.session_state.positions = []

    # ---- Добавить позицию ----
    with st.expander("➕ Добавить позицию", expanded=not st.session_state.positions):
        can_build = (st.session_state.get("series_list")
                     and "selected_series_code" in st.session_state)
        if not can_build:
            st.warning("Выберите серию на вкладке «Калькулятор».")
        else:
            try:
                board = fetch_optionboard(
                    st.session_state.get("selected_asset", ""),
                    st.session_state.get("selected_asset_type_ui", ""),
                    st.session_state.get("selected_series_code", ""))
            except Exception as e:
                st.error(f"Не удалось загрузить доску: {e}")
                board = None

            if board:
                calls = board.get('call') or []
                puts = board.get('put') or []
                central = board.get('central_strike')
                c_map = {c['strike']: c for c in calls if c.get('strike') is not None}
                p_map = {p['strike']: p for p in puts if p.get('strike') is not None}
                all_strikes = sorted(set(c_map.keys()) | set(p_map.keys()))
                expiry_now = st.session_state.get("selected_expiry", "—")
                asset_type_ui_now = st.session_state.get("selected_asset_type_ui", "Фьючерс")
                asset_now = st.session_state.get("selected_asset", "")

                with st.form("add_position_form", clear_on_submit=False):
                    f1, f2 = st.columns([2, 2])
                    with f1:
                        _instr_options = ["Опцион"]
                        if asset_type_ui_now in ("Фьючерс", "Валюта", "Товар"):
                            _instr_options.append("Фьючерс")
                        elif asset_type_ui_now == "Акция":
                            _instr_options.append("Акция")
                        else:
                            _instr_options.append("Индекс")
                        instrument_type = st.selectbox("Тип", _instr_options, key="form_instrument_type")
                    with f2:
                        if instrument_type == "Опцион":
                            opt_type = st.selectbox("Опцион", ["Call", "Put"], key="form_opt_type")
                        else:
                            opt_type = "—"
                            st.markdown("<label>Опцион</label><div style='padding:8px;background:#f5f5f5;border-radius:10px;color:#999;text-align:center;'>—</div>", unsafe_allow_html=True)

                    f3, f4 = st.columns([2, 2])
                    with f3:
                        if instrument_type == "Опцион" and all_strikes:
                            default_idx = 0
                            if central is not None:
                                try:
                                    default_idx = all_strikes.index(min(all_strikes, key=lambda s: abs(float(s) - float(central))))
                                except ValueError:
                                    default_idx = 0
                            chosen_strike = st.selectbox("Страйк", all_strikes, index=default_idx, key="form_strike")
                        else:
                            chosen_strike = None
                            st.markdown("<label>Страйк</label><div style='padding:8px;background:#f5f5f5;border-radius:10px;color:#999;text-align:center;'>—</div>", unsafe_allow_html=True)
                    with f4:
                        side = st.selectbox("Направление", ["Buy", "Sell"], key="form_side")

                    _und_secid = None
                    _futures_secid_form = None
                    _futures_contracts = []

                    if instrument_type == "Фьючерс":
                        _futures_contracts = fetch_futures_contracts_list(asset_now)
                        if _futures_contracts:
                            _contract_labels = [f"{c['expiration']} — {c['secid']}" for c in _futures_contracts]
                            _chosen = st.selectbox("Контракт", _contract_labels, index=0,
                                                   key="form_futures_contract")
                            _chosen_contract = _futures_contracts[_contract_labels.index(_chosen)]
                            expiry_now_form = _chosen_contract["expiration"]
                            _futures_secid_form = _chosen_contract["secid"]
                        else:
                            expiry_now_form = expiry_now
                            _futures_secid_form = asset_now
                            st.caption(f"Экспирация: {expiry_now}")
                    elif instrument_type == "Опцион":
                        expiry_now_form = expiry_now
                        st.caption(f"Экспирация: {expiry_now}")
                    else:
                        expiry_now_form = "—"
                        st.caption("БА без экспирации")

                    if instrument_type == "Опцион" and chosen_strike is not None:
                        ref_opt_for_ticker = (c_map.get(chosen_strike, {}) if opt_type == "Call"
                                              else p_map.get(chosen_strike, {}))
                        ticker_val = ref_opt_for_ticker.get('secid', '—')
                    elif instrument_type == "Фьючерс" and _futures_secid_form:
                        ticker_val = _futures_secid_form
                    else:
                        ticker_val = resolve_underlying_secid(asset_now, asset_type_ui_now) or '—'
                    st.caption(f"Тикер: **{ticker_val}**")

                    qty_input = st.number_input("Кол-во", min_value=1, value=1, step=1, key="form_qty")

                    _alert_lv = find_alert_levels(asset_now, category=asset_type_ui_now)
                    _alerts_available = _alert_lv.get("found", False)
                    use_alert_price = False
                    _buy_lvl = _sell_lvl = None
                    _nearest_strike = lambda lvl, stk: (min(stk, key=lambda s: abs(float(s) - float(lvl)))
                                                        if lvl is not None and stk else None)
                    _K_buy = _K_sell = None
                    _buy_c = _buy_p = _sell_c = _sell_p = None

                    if _alerts_available:
                        _buy_lvl = _alert_lv["buy"]; _sell_lvl = _alert_lv["sell"]

                        def _opt_price(K, opt_type_chk):
                            if K is None:
                                return None
                            src = c_map if opt_type_chk == "Call" else p_map
                            row = src.get(K, {})
                            v = row.get('theorprice')
                            if v is None or v <= 0:
                                v = row.get('last')
                            return float(v) if v and v > 0 else None

                        _K_buy = _nearest_strike(_buy_lvl, all_strikes)
                        _K_sell = _nearest_strike(_sell_lvl, all_strikes)
                        _buy_c = _opt_price(_K_buy, "Call"); _buy_p = _opt_price(_K_buy, "Put")
                        _sell_c = _opt_price(_K_sell, "Call"); _sell_p = _opt_price(_K_sell, "Put")
                        _fmt = lambda v: f"{v:.2f}₽" if v is not None else "—"
                        _K_buy_s = f"{int(_K_buy)}" if _K_buy is not None else "—"
                        _K_sell_s = f"{int(_K_sell)}" if _K_sell is not None else "—"
                        st.markdown(
                            f"<div style='background:#eef6fb;border-radius:10px;padding:8px 12px;"
                            f"font-size:.8rem;color:#1c5a7a;margin:6px 0;'>"
                            f"<b>Покупка {_buy_lvl:.2f}₽</b> (K={_K_buy_s}): "
                            f"<span style='color:#00a651;font-weight:700;'>C={_fmt(_buy_c)}</span> · "
                            f"<span style='color:#d32f2f;font-weight:700;'>P={_fmt(_buy_p)}</span><br>"
                            f"<b>Продажа {_sell_lvl:.2f}₽</b> (K={_K_sell_s}): "
                            f"<span style='color:#00a651;font-weight:700;'>C={_fmt(_sell_c)}</span> · "
                            f"<span style='color:#d32f2f;font-weight:700;'>P={_fmt(_sell_p)}</span>"
                            f"</div>", unsafe_allow_html=True)
                        use_alert_price = st.checkbox("🎯 Взять цену из оповещений",
                                                      value=False, key="form_use_alert_price")

                    ref_opt = (c_map.get(chosen_strike, {}) if opt_type == "Call"
                               else p_map.get(chosen_strike, {})) if chosen_strike is not None else {}
                    _qs_last = st.session_state.get("quick_und_last_price", 0.0)
                    default_price = (float(_qs_last) if instrument_type != "Опцион" and _qs_last
                                     else (float(ref_opt.get('theorprice') or 0)
                                           or float(ref_opt.get('last') or 0) or 0.0))
                    price_input = st.number_input("Цена, ₽", min_value=0.0,
                                                  value=float(default_price), step=0.01,
                                                  format="%.4f", key="form_price")

                    submitted = st.form_submit_button("➕ Добавить", type="primary",
                                                      use_container_width=True)

                    if submitted:
                        if instrument_type == "Фьючерс":
                            _fut_info = fetch_futures_info_iss(_futures_secid_form or asset_now) or {}
                            _last_price = _fut_info.get("last")
                            _fut_exp = _fut_info.get("expiration") or expiry_now_form
                            final_price = float(price_input) if price_input > 0 else (float(_last_price) if _last_price else 0.0)
                            if final_price > 0:
                                signed_qty = int(qty_input) if side == "Buy" else -int(qty_input)
                                _pos = {"_id": _new_position_id(), "Конструкция": "Без названия",
                                        "Тип инструмента": "Фьючерс", "Опцион": "БА", "Направление": side,
                                        "Страйк": None, "Эксп.": _fut_exp, "Тикер": _futures_secid_form or asset_now,
                                        "Кол-во": signed_qty, "Цена": float(final_price),
                                        "Теор.цена": float(_last_price) if _last_price else float(final_price),
                                        "Дельта": None, "Гамма": None, "Вега": None, "Тета": None, "Ро": None,
                                        "visible": True}
                                _pos = apply_parity_delta(_pos)
                                st.session_state.positions.append(_pos); st.rerun()
                            else:
                                st.error("Не удалось определить цену фьючерса.")
                        elif instrument_type in ("Акция", "Индекс"):
                            _und_secid = resolve_underlying_secid(asset_now, asset_type_ui_now)
                            _ba_info = fetch_ba_iss_info(_und_secid, asset_type_ui_now) or {}
                            _last_price = _ba_info.get("last")
                            final_price = float(price_input) if price_input > 0 else (float(_last_price) if _last_price else 0.0)
                            if final_price > 0:
                                signed_qty = int(qty_input) if side == "Buy" else -int(qty_input)
                                _pos = {"_id": _new_position_id(), "Конструкция": "Без названия",
                                        "Тип инструмента": instrument_type, "Опцион": "БА",
                                        "Направление": side, "Страйк": None, "Эксп.": "—",
                                        "Тикер": _und_secid or '—', "Кол-во": signed_qty,
                                        "Цена": float(final_price),
                                        "Теор.цена": float(_last_price) if _last_price else float(final_price),
                                        "Дельта": None, "Гамма": None, "Вега": None, "Тета": None, "Ро": None,
                                        "visible": True}
                                _pos = apply_parity_delta(_pos)
                                st.session_state.positions.append(_pos); st.rerun()
                            else:
                                st.error("Не удалось определить цену БА.")
                        else:  # Опцион
                            if chosen_strike is None:
                                st.error("Укажите страйк.")
                            else:
                                ref = c_map.get(chosen_strike, {}) if opt_type == "Call" else p_map.get(chosen_strike, {})
                                final_pos_price = None
                                _src_label = ""
                                if use_alert_price:
                                    _lvl = (_buy_lvl if side == "Buy" else _sell_lvl) if opt_type == "Call" else (_sell_lvl if side == "Buy" else _buy_lvl)
                                    _K_alert = _nearest_strike(_lvl, all_strikes)
                                    _auto_p = _opt_price(_K_alert, opt_type)
                                    if _auto_p is not None:
                                        final_pos_price = float(_auto_p)
                                        _src_label = f" (K={int(_K_alert)}, из оповещений)"
                                if final_pos_price is None:
                                    final_pos_price = float(price_input)
                                if final_pos_price <= 0:
                                    st.error("Укажите цену > 0.")
                                else:
                                    signed_qty = int(qty_input) if side == "Buy" else -int(qty_input)
                                    st.session_state.positions.append({
                                        "_id": _new_position_id(), "Конструкция": "Без названия",
                                        "Тип инструмента": "Опцион", "Опцион": opt_type,
                                        "Направление": side, "Страйк": chosen_strike,
                                        "Эксп.": expiry_now, "Тикер": ref.get('secid', '—'),
                                        "Кол-во": signed_qty, "Цена": float(final_pos_price),
                                        "Теор.цена": float(ref.get('theorprice') or 0),
                                        "Дельта": ref.get('delta'), "Гамма": ref.get('gamma'),
                                        "Вега": ref.get('vega'), "Тета": ref.get('theta'),
                                        "Ро": ref.get('rho'), "visible": True})
                                    st.success(f"Добавлено: {side} {opt_type} {chosen_strike} × {qty_input}{_src_label}")
                                    st.rerun()

    # ==========================================================
    # ТЕКУЩИЕ ПОЗИЦИИ (мобильный компакт)
    # ==========================================================
    st.markdown("#### 📋 Позиции")

    if not st.session_state.positions:
        st.caption("Портфель пуст.")
    else:
        # 🔧 Сокращённый набор колонок для мобильного
        COL_W = [0.55, 1.4, 0.65, 1.05, 1.15, 1.1, 1.1, 1.0, 1.0, 2.0, 0.85]
        HEADERS = ["✕/👁", "Тип/Опц", "K", "Эксп", "Тикер", "Кол-во", "Цена",
                   "Теор", "P&L", "Греки (Δ Γ ν Θ ρ)", "Ком."]

        _hdr = st.columns(COL_W)
        for c, h in zip(_hdr, HEADERS):
            with c:
                st.markdown(f"<div style='font-size:.62rem;color:#2c506d;font-weight:700;"
                            f"text-transform:uppercase;letter-spacing:.02em;padding-top:2px;'>{h}</div>",
                            unsafe_allow_html=True)

        st.markdown("<hr style='margin:2px 0 4px 0;border:none;border-top:1px solid #e6edf4;'>",
                    unsafe_allow_html=True)

        _today = date.today()
        for idx, p in enumerate(st.session_state.positions):
            _id = p.get("_id", f"legacy_{idx}")
            visible = p.get("visible", True)
            gray = "opacity:0.45;" if not visible else ""

            row = st.columns(COL_W)

            # 0. del + vis
            with row[0]:
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("✖", key=f"del_{_id}", help="Удалить"):
                        st.session_state.positions.pop(idx)
                        for k in list(st.session_state.keys()):
                            if k.endswith(f"_{_id}"):
                                del st.session_state[k]
                        st.rerun()
                with bc2:
                    icon = "👁" if visible else "🚫"
                    if st.button(icon, key=f"vis_{_id}", help="Скрыть/показать"):
                        p["visible"] = not visible
                        st.rerun()

            # 1. Тип + Опцион
            with row[1]:
                _t = p.get("Тип инструмента", "Опцион")
                _short_t = {"Опцион": "Опц", "Фьючерс": "Фьюч", "Акция": "Акц", "Индекс": "Инд"}.get(_t, _t)
                _opt = p.get("Опцион", "—")
                _opt_html = _color_call_put(_opt) if _opt in ("Call", "Put") else _opt
                st.markdown(f"<div style='padding-top:6px;{gray};font-size:.75rem;'>"
                            f"{_short_t} {_opt_html}</div>", unsafe_allow_html=True)

            # 2. Страйк
            with row[2]:
                _k = p.get("Страйк")
                _k_txt = f"<b>{int(_k)}</b>" if _k is not None else "—"
                st.markdown(f"<div style='padding-top:6px;{gray};font-size:.8rem;'>{_k_txt}</div>",
                            unsafe_allow_html=True)

            # 3. Эксп + DTE
            with row[3]:
                _dte = "—"
                _exp_str = p.get("Эксп.", "—")
                if _exp_str and _exp_str != "—":
                    try:
                        _d = datetime.strptime(_exp_str, "%Y-%m-%d").date()
                        _dte = f"{(_d - _today).days}д"
                    except Exception:
                        pass
                st.markdown(f"<div style='padding-top:6px;{gray};font-size:.72rem;'>"
                            f"{_exp_str}<br><span style='color:#4a6f8a;'>({_dte})</span></div>",
                            unsafe_allow_html=True)

            # 4. Тикер
            with row[4]:
                st.markdown(f"<div style='padding-top:6px;{gray};font-size:.68rem;"
                            f"color:#4a6f8a;word-break:break-all;'>{p.get('Тикер', '—')}</div>",
                            unsafe_allow_html=True)

            # 5. Кол-во с +/-
            with row[5]:
                kq = f"qty_{_id}"
                if kq not in st.session_state:
                    st.session_state[kq] = int(p.get("Кол-во", 1))
                qc = st.columns([1, 2, 1])
                with qc[0]:
                    st.button("−", key=f"qm_{_id}", on_click=_cb_qty_dec,
                              args=(kq,), use_container_width=True)
                with qc[1]:
                    new_qty = st.number_input("qty", min_value=-10000, max_value=10000,
                                              step=1, key=kq, label_visibility="collapsed")
                with qc[2]:
                    st.button("+", key=f"qp_{_id}", on_click=_cb_qty_inc,
                              args=(kq,), use_container_width=True)
                if int(new_qty) != int(p.get("Кол-во", 0)):
                    p["Кол-во"] = int(new_qty)
                    p["Направление"] = _side_from_qty(int(new_qty))

            # 6. Цена с +/-
            with row[6]:
                kp = f"price_{_id}"
                if kp not in st.session_state:
                    st.session_state[kp] = float(p.get("Цена", 0.0))
                pc = st.columns([1, 2, 1])
                with pc[0]:
                    st.button("−", key=f"pm_{_id}", on_click=_cb_price_dec,
                              args=(kp,), use_container_width=True)
                with pc[1]:
                    new_price = st.number_input("price", min_value=0.0, step=0.01,
                                                format="%.4f", key=kp,
                                                label_visibility="collapsed")
                with pc[2]:
                    st.button("+", key=f"pp_{_id}", on_click=_cb_price_inc,
                              args=(kp,), use_container_width=True)
                if float(new_price) != float(p.get("Цена", 0)):
                    p["Цена"] = float(new_price)

            _theor = float(p.get("Теор.цена", 0))
            _instr = p.get("Тип инструмента", "Опцион")
            _isBA = (_instr == "БА" or p.get("Опцион") == "БА")
            _com = 0.0 if _isBA else _calc_comm(float(p.get("Цена", 0)), _instr)
            _qty = int(p.get("Кол-во", 0))
            _price = float(p.get("Цена", 0))
            _eff_price = _price + _com
            _pnl = ((_theor - _price) * _qty if _isBA else (_theor - _eff_price) * _qty)

            # 7. Теор
            with row[7]:
                st.markdown(f"<div style='padding-top:6px;{gray};font-size:.72rem;'>"
                            f"{_theor:.4f}</div>", unsafe_allow_html=True)

            # 8. P&L
            with row[8]:
                _color = "#00a651" if _pnl > 0 else ("#d32f2f" if _pnl < 0 else "#333")
                st.markdown(f"<div style='padding-top:6px;{gray};font-weight:700;"
                            f"color:{_color};font-size:.75rem;'>{_pnl:+,.2f}</div>",
                            unsafe_allow_html=True)

            # 9. Греки (одна строка)
            with row[9]:
                _fmt_g = lambda v, prec=2: (f"{v:+.{prec}f}" if isinstance(v, (int, float)) else "—")
                _g_line = (f"Δ{_fmt_g(p.get('Дельта'), 2)} "
                           f"Γ{_fmt_g(p.get('Гамма'), 2)} "
                           f"ν{_fmt_g(p.get('Вега'), 2)} "
                           f"Θ{_fmt_g(p.get('Тета'), 2)} "
                           f"ρ{_fmt_g(p.get('Ро'), 2)}")
                st.markdown(f"<div style='padding-top:6px;{gray};font-size:.68rem;"
                            f"font-family:Consolas,monospace;white-space:nowrap;"
                            f"overflow-x:auto;'>{_g_line}</div>", unsafe_allow_html=True)

            # 10. Комиссия
            with row[10]:
                st.markdown(f"<div style='padding-top:6px;{gray};font-size:.72rem;'>"
                            f"{_com:.4f}</div>", unsafe_allow_html=True)

        st.markdown("<hr style='margin:4px 0;border:none;border-top:1px solid #e6edf4;'>",
                    unsafe_allow_html=True)

        # ---- Итоги ----
        _tot_com = _tot_pnl = _tot_delta = _tot_gamma = 0.0
        _tot_vega = _tot_theta = _tot_rho = 0.0
        for p in st.session_state.positions:
            _q = int(p.get("Кол-во", 0)); _pr = float(p.get("Цена", 0))
            _th = float(p.get("Теор.цена", 0)); _instr = p.get("Тип инструмента", "Опцион")
            _isBA = (_instr == "БА" or p.get("Опцион") == "БА")
            if _isBA:
                _c = 0.0; _pl = (_th - _pr) * _q
            else:
                _c = _calc_comm(_pr, _instr); _pl = (_th - _pr - _c) * _q
            _tot_com += _c * abs(_q); _tot_pnl += _pl
            _tot_delta += (p.get("Дельта") or 0) * _q
            _tot_gamma += (p.get("Гамма") or 0) * _q
            _tot_vega += (p.get("Вега") or 0) * _q
            _tot_theta += (p.get("Тета") or 0) * _q
            _tot_rho += (p.get("Ро") or 0) * _q

        tot_row = st.columns(COL_W)
        with tot_row[0]:
            if st.button("🗑", key="clear_all_positions", help="Удалить все"):
                for k in list(st.session_state.keys()):
                    if k.startswith(("qty_", "price_", "qp_", "qm_", "pp_", "pm_")):
                        del st.session_state[k]
                st.session_state.positions = []
                st.rerun()
        with tot_row[1]:
            st.markdown("<div style='padding-top:6px;font-size:.75rem;color:#2c506d;font-weight:700;'>Итого:</div>",
                        unsafe_allow_html=True)
        _color_pnl_tot = "#00a651" if _tot_pnl > 0 else ("#d32f2f" if _tot_pnl < 0 else "#333")
        with tot_row[8]:
            st.markdown(f"<div style='padding-top:6px;font-weight:800;color:{_color_pnl_tot};"
                        f"font-size:.78rem;'>{_tot_pnl:+,.2f}</div>", unsafe_allow_html=True)
        with tot_row[9]:
            _g_tot = (f"Δ{_tot_delta:+.2f} Γ{_tot_gamma:+.3f} ν{_tot_vega:+.2f} "
                      f"Θ{_tot_theta:+.3f} ρ{_tot_rho:+.3f}")
            st.markdown(f"<div style='padding-top:6px;font-weight:700;font-size:.68rem;"
                        f"font-family:Consolas,monospace;white-space:nowrap;overflow-x:auto;'>"
                        f"{_g_tot}</div>", unsafe_allow_html=True)
        with tot_row[10]:
            st.markdown(f"<div style='padding-top:6px;font-weight:700;font-size:.72rem;'>"
                        f"{_tot_com:,.4f}</div>", unsafe_allow_html=True)

        # =========================================================
        # Определение стратегии
        # =========================================================
        try:
            _visible_positions = [p for p in st.session_state.positions
                                  if p.get("visible", True) and p.get("Опцион") in ("Call", "Put")]
            if _visible_positions:
                _best = None
                for _sname, _sdef in PREDEFINED_STRATEGIES.items():
                    _m = match_strategy_with_positions(_sdef, _visible_positions)
                    if _m["is_full"] and _m["weight"] >= 1.0:
                        if _best is None or _m["weight"] > _best["weight"]:
                            _best = {"name": _sname, "weight": _m["weight"], "def": _sdef}
                if _best is not None:
                    st.markdown(
                        f"<div style='background:#d4f7d8;border-radius:10px;"
                        f"padding:8px 12px;margin-top:6px;font-size:.85rem;color:#0a5d29;'>"
                        f"<b>Конструкция:</b> {_best['name']} "
                        f"<span style='color:#4a6f8a;font-size:.75rem;'>— {_best['def'].get('description','')}</span>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    _partials = []
                    for _sname, _sdef in PREDEFINED_STRATEGIES.items():
                        _m = match_strategy_with_positions(_sdef, _visible_positions)
                        if _m["weight"] >= 0.5:
                            _partials.append({"name": _sname, "w": _m["weight"]})
                    if _partials:
                        _partials.sort(key=lambda x: -x["w"])
                        _txt = ", ".join(f"{x['name']} ({int(x['w']*100)}%)" for x in _partials[:3])
                        st.caption(f"📐 Ближайшие: {_txt}")
        except Exception:
            pass

        # ---- Риск + экспорт ----
        _max_loss_prem = 0.0
        for p in st.session_state.positions:
            if p.get("Опцион") == "БА":
                continue
            _instr = p.get("Тип инструмента", "Опцион")
            _q = abs(int(p.get("Кол-во", 0))); _pr = float(p.get("Цена", 0))
            _c = _calc_comm(_pr, _instr); _max_loss_prem += (_pr + _c) * _q

        if _max_loss_prem > risk_amount:
            st.error(f"⚠ Риск: {_max_loss_prem:,.0f}₽ > {risk_amount:,.0f}₽")
        else:
            st.success(f"✓ Риск: {_max_loss_prem:,.0f}₽ / {risk_amount:,.0f}₽ ({_max_loss_prem / risk_amount * 100:.1f}%)")

        _export_rows = []
        for i, p in enumerate(st.session_state.positions):
            _q = int(p["Кол-во"]); _pr = float(p["Цена"]); _th = float(p["Теор.цена"])
            _instr = p.get("Тип инструмента", "Опцион")
            _isBA = (_instr == "БА" or p.get("Опцион") == "БА")
            if _isBA:
                _c = 0.0; _pl = (_th - _pr) * _q
            else:
                _c = _calc_comm(_pr, _instr); _pl = (_th - _pr - _c) * _q
            _export_rows.append({"#": i + 1, "Тип": _instr, "Опцион": p["Опцион"],
                                 "Направление": p.get("Направление", _side_from_qty(_q)),
                                 "Страйк": p.get("Страйк", "—"), "Эксп.": p.get("Эксп.", "—"),
                                 "Тикер": p.get("Тикер", "—"), "Кол-во": _q, "Цена": _pr,
                                 "Комиссия": _c, "Эфф.цена": _pr + _c, "Теор.цена": _th,
                                 "P&L": _pl, "Дельта": p.get("Дельта"), "Гамма": p.get("Гамма"),
                                 "Вега": p.get("Вега"), "Тета": p.get("Тета"), "Ро": p.get("Ро")})
        _df_export = pd.DataFrame(_export_rows)
        st.download_button("📤 Экспорт CSV",
                           data=_df_export.to_csv(index=False).encode("utf-8-sig"),
                           file_name="portfolio.csv", mime="text/csv",
                           use_container_width=True)

    # ==================================================================
    # ПРОФИЛЬ ПОЗИЦИИ (мобильный)
    # ==================================================================
    st.markdown("---")
    st.markdown("#### 📊 Профиль позиции")

    payoff_positions = [p for p in st.session_state.positions if p.get("visible", True)]

    if not payoff_positions:
        st.caption("Нет видимых позиций.")
    else:
        F_current = st.session_state.get("_current_market_price", None)
        if F_current is None:
            try:
                _atype_f = st.session_state.get("selected_asset_type_ui", "")
                if _atype_f in ("Фьючерс", "Валюта", "Товар"):
                    _eng_f, _mkt_f = "futures", "forts"
                elif _atype_f == "Индекс":
                    _eng_f, _mkt_f = "stock", "index"
                else:
                    _eng_f, _mkt_f = "stock", "shares"
                _ser_info_f = fetch_series_info(
                    st.session_state.get("selected_asset", ""), _atype_f,
                    st.session_state.get("selected_series_code", ""))
                _fut_ticker_f = _ser_info_f.get("Тикер", "")
                if _fut_ticker_f and _fut_ticker_f != "—":
                    _secid_f = _fut_ticker_f
                else:
                    _secid_f = resolve_underlying_secid(
                        st.session_state.get("selected_asset", ""), _atype_f)
                F_current = get_last_close_price(_secid_f, _eng_f, _mkt_f)
                if F_current is not None:
                    st.session_state["_current_market_price"] = F_current
            except Exception:
                pass

        all_pos_strikes = sorted({float(p["Страйк"]) for p in payoff_positions
                                  if p.get("Страйк") is not None})
        if not all_pos_strikes:
            _ba_prices = [float(p["Цена"]) for p in payoff_positions
                          if p.get("Тип инструмента") == "БА" or p.get("Опцион") == "БА"]
            if _ba_prices:
                all_pos_strikes = _ba_prices

        if not all_pos_strikes:
            st.caption("Нет данных для профиля.")
        else:
            _range_pts = list(all_pos_strikes)
            if F_current is not None:
                _range_pts.append(F_current)
            s_min = min(_range_pts) * 0.85; s_max = max(_range_pts) * 1.15
            S_arr = np.linspace(s_min, s_max, 500)

            def _payoff_at_expiry(S_vals, positions_subset):
                S_vals = np.asarray(S_vals, dtype=float)
                pnl_arr = np.zeros_like(S_vals)
                for p in positions_subset:
                    qty = int(p["Кол-во"]); price = float(p["Цена"])
                    _instr = p.get("Тип инструмента", "Опцион")
                    com = _calc_comm(price, _instr)
                    if p.get("Тип инструмента") == "БА" or p.get("Опцион") == "БА":
                        pnl_arr += (S_vals - price) * qty
                        continue
                    K = float(p["Страйк"])
                    intrinsic = (np.maximum(0.0, S_vals - K) if p["Опцион"] == "Call"
                                 else np.maximum(0.0, K - S_vals))
                    pnl_arr += (intrinsic - price - com) * qty
                return pnl_arr

            def _payoff_today(S_vals, positions_subset, T_years):
                S_vals = np.asarray(S_vals, dtype=float)
                pnl_arr = np.zeros_like(S_vals)
                if T_years <= 0:
                    return pnl_arr
                _r = float(st.session_state.get("_calc_riskfree", 0.0) or 0.0)
                _q = float(st.session_state.get("_calc_dividend", 0.0) or 0.0)
                _vol = float(st.session_state.get("_calc_volatility", 0.0) or 0.0)
                if _vol <= 0:
                    _vol = 20.0
                for p in positions_subset:
                    qty = int(p["Кол-во"]); entry = float(p["Цена"])
                    _instr = p.get("Тип инструмента", "Опцион")
                    com = _calc_comm(entry, _instr)
                    if p.get("Тип инструмента") == "БА" or p.get("Опцион") == "БА":
                        pnl_arr += (S_vals - entry) * qty
                        continue
                    K = float(p["Страйк"])
                    opt_type = "call" if p["Опцион"] == "Call" else "put"
                    price_now = np.array([black_scholes_py(S, K, T_years, _r, _vol, _q, opt_type) for S in S_vals])
                    pnl_arr += (price_now - entry - com) * qty
                return pnl_arr

            pnl_arr = _payoff_at_expiry(S_arr, payoff_positions)
            max_profit = float(np.max(pnl_arr)); max_loss_pf = float(np.min(pnl_arr))

            be_points = []
            for i in range(1, len(S_arr)):
                if pnl_arr[i - 1] * pnl_arr[i] < 0:
                    denom = pnl_arr[i] - pnl_arr[i - 1]
                    if abs(denom) > 1e-12:
                        x0 = S_arr[i - 1] + (S_arr[i] - S_arr[i - 1]) * (-pnl_arr[i - 1]) / denom
                        be_points.append(float(x0))

            fig_pf = go.Figure()
            fig_pf.add_trace(go.Scatter(x=S_arr, y=np.where(pnl_arr >= 0, pnl_arr, 0),
                                        fill='tozeroy', fillcolor='rgba(0,255,12,0.20)',
                                        line=dict(width=0), mode='lines',
                                        name='Прибыль', hoverinfo='skip'))
            fig_pf.add_trace(go.Scatter(x=S_arr, y=np.where(pnl_arr <= 0, pnl_arr, 0),
                                        fill='tozeroy', fillcolor='rgba(255,0,0,0.20)',
                                        line=dict(width=0), mode='lines',
                                        name='Убыток', hoverinfo='skip'))
            fig_pf.add_trace(go.Scatter(x=S_arr, y=pnl_arr, mode='lines',
                                        line=dict(color='#1e5a7a', width=3),
                                        name='Экспирация',
                                        hovertemplate='БА: %{x:.2f}<br>P&L: %{y:.2f}<extra></extra>'))

            _cur_pnl_today = None
            try:
                _exp_date_pt = datetime.strptime(st.session_state.get("selected_expiry", ""), "%Y-%m-%d").date()
                _T_now = max((_exp_date_pt - date.today()).days, 1) / 365.0
                pnl_today = _payoff_today(S_arr, payoff_positions, _T_now)
                fig_pf.add_trace(go.Scatter(x=S_arr, y=pnl_today, mode='lines',
                                            line=dict(color='#1e88e5', width=2, dash='dash'),
                                            name='Сегодня',
                                            hovertemplate='БА: %{x:.2f}<br>P&L: %{y:.2f}<extra></extra>'))
                if F_current is not None:
                    _cur_pnl_today = float(_payoff_today(np.array([F_current]), payoff_positions, _T_now)[0])
                    _marker_color = "#00a651" if _cur_pnl_today > 0 else ("#d32f2f" if _cur_pnl_today < 0 else "#1e88e5")
                    fig_pf.add_trace(go.Scatter(x=[F_current], y=[_cur_pnl_today], mode='markers',
                                                marker=dict(size=14, color=_marker_color, symbol='circle',
                                                            line=dict(color='white', width=2)),
                                                name='Тек',
                                                hovertemplate='Тек: %{x:.2f}<br>P&L: %{y:+,.2f}<extra></extra>'))
                    fig_pf.add_annotation(x=F_current, y=_cur_pnl_today,
                                          text=f"  {_cur_pnl_today:+,.0f} ₽", showarrow=False,
                                          font=dict(size=10, color=_marker_color, family="Arial Black"),
                                          bgcolor="rgba(255,255,255,0.92)",
                                          bordercolor=_marker_color, borderwidth=1,
                                          xanchor='left', yanchor='middle')
            except Exception:
                pass

            fig_pf.add_hline(y=0, line_dash='dot', line_color='#7f9bb3', line_width=1)
            for k in all_pos_strikes:
                fig_pf.add_vline(x=k, line_dash='dash', line_color='#9c00ff',
                                 line_width=1, opacity=0.5,
                                 annotation_text=f"{k:.0f}", annotation_position="top",
                                 annotation_font_size=9)
            if F_current is not None:
                fig_pf.add_vline(x=F_current, line_dash='dot', line_color='#1e88e5',
                                 line_width=2, annotation_text=f"Тек {F_current:.0f}",
                                 annotation_position="bottom right", annotation_font_size=10)
            for be in be_points:
                fig_pf.add_vline(x=be, line_dash='dot', line_color='#00a651',
                                 line_width=1.5, opacity=0.8)

            # 🔧 Высота снижена для мобильного
            fig_pf.update_layout(
                title=dict(text="Профиль позиции", font=dict(size=13)),
                xaxis_title="Цена БА, ₽", yaxis_title="P&L, ₽",
                height=380, margin=dict(l=10, r=10, t=40, b=20),
                xaxis=dict(tickformat=".0f", hoverformat=".2f"),
                yaxis=dict(tickformat=".2f", hoverformat=".2f"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="left", x=0, font=dict(size=10)),
                hovermode='x unified')

            fig_pf.update_xaxes(showspikes=True, spikemode='across', spikesnap='cursor',
                                spikecolor='#888888', spikethickness=1, spikedash='dot')
            fig_pf.update_yaxes(showspikes=True, spikemode='across', spikesnap='cursor',
                                spikecolor='#888888', spikethickness=1, spikedash='dot')

            st.plotly_chart(fig_pf, use_container_width=True,
                            config={'displayModeBar': False})

            pm1, pm2, pm3 = st.columns(3)
            with pm1:
                st.metric("Макс. +", f"{max_profit:+,.0f}₽")
            with pm2:
                st.metric("Макс. −", f"{max_loss_pf:+,.0f}₽")
            with pm3:
                if _cur_pnl_today is not None:
                    st.metric("Тек. P&L", f"{_cur_pnl_today:+,.0f}₽")
                else:
                    st.metric("Тек. P&L", "—")

            if be_points:
                be_str = " · ".join(f"**{be:,.2f}**" for be in be_points)
                st.caption(f"ТБ: {be_str}")
            else:
                st.caption("ТБ в диапазоне не найдены.")


# ==================================================================
# ============ ВКЛАДКА 3: ДОСКА ОПЦИОНОВ ===========================
# ==================================================================
with tab_board:
    if not st.session_state.get("series_list"):
        st.info("Выберите серию на вкладке «Калькулятор».")
    elif "selected_series_code" not in st.session_state:
        st.info("Выберите дату экспирации.")
    else:
        asset = st.session_state.get("selected_asset", "")
        asset_type_ui = st.session_state.get("selected_asset_type_ui", "")
        series_code = st.session_state.get("selected_series_code", "")
        expiry_str = st.session_state.get("selected_expiry", "")

        buy_level = float(st.session_state.get("_calc_level_buy", 0) or 0)
        sell_level = float(st.session_state.get("_calc_level_sell", 0) or 0)

        st.markdown(f"**{asset}** · `{series_code}` · {expiry_str}")

        try:
            _board_for_price = fetch_optionboard(asset, asset_type_ui, series_code)
            _calls_p = _board_for_price.get('call') or []
            _puts_p = _board_for_price.get('put') or []
            _c_map_p = {c['strike']: c for c in _calls_p if c.get('theorprice') and c.get('strike') is not None}
            _p_map_p = {p2['strike']: p2 for p2 in _puts_p if p2.get('theorprice') and p2.get('strike') is not None}
            _common_p = sorted(set(_c_map_p.keys()) & set(_p_map_p.keys()))
            _fs_est = []
            for k in _common_p:
                ct = _c_map_p[k]['theorprice']; pt = _p_map_p[k]['theorprice']
                if ct and pt and ct > 0 and pt > 0:
                    _fs_est.append(ct - pt + float(k))
            _f_current = None
            if _fs_est:
                _fs_est.sort()
                _f_current = _fs_est[len(_fs_est) // 2]
            _central_p = _board_for_price.get('central_strike')
            _strikes_p = sorted({c['strike'] for c in _calls_p if c.get('strike') is not None}
                                | {p2['strike'] for p2 in _puts_p if p2.get('strike') is not None})
            _k_min = _strikes_p[0] if _strikes_p else None
            _k_max = _strikes_p[-1] if _strikes_p else None

            _info_parts = []
            if _f_current is not None:
                _info_parts.append(f"<span style='color:#1c5a7a;font-weight:700;'>БА: {_f_current:,.2f}₽</span>")
            if _central_p is not None:
                _info_parts.append(f"<span style='color:#4a6f8a;'>Центр: <b>{int(_central_p)}</b></span>")
            if _k_min is not None and _k_max is not None:
                _info_parts.append(f"<span style='color:#4a6f8a;'>Диапазон: <b>{int(_k_min)}…{int(_k_max)}</b> ({len(_strikes_p)} шт.)</span>")
            if _info_parts:
                st.markdown("<div style='background:#eef6fb;border-radius:10px;"
                            "padding:8px 12px;margin-bottom:8px;font-size:.8rem;"
                            "display:flex;gap:16px;flex-wrap:wrap;align-items:center;'>"
                            + " · ".join(_info_parts) + "</div>", unsafe_allow_html=True)
        except Exception:
            pass

        highlight_on = st.toggle("Раскрасить по грекам/ликвидности", value=False,
                                 key="board_highlight")

        try:
            board = fetch_optionboard(asset, asset_type_ui, series_code)
        except Exception as e:
            st.error(f"Не удалось загрузить доску: {e}")
            board = None

        if board:
            calls = board.get('call') or []
            puts = board.get('put') or []
            central = board.get('central_strike')
            strikes = sorted({c['strike'] for c in calls} | {p['strike'] for p in puts})
            c_map = {c['strike']: c for c in calls}
            p_map = {p['strike']: p for p in puts}

            def nearest_strike(level, strikes_list):
                if level is None or level <= 0 or not strikes_list:
                    return None
                return min(strikes_list, key=lambda s: abs(float(s) - float(level)))

            buy_strike_match = nearest_strike(buy_level, strikes)
            sell_strike_match = nearest_strike(sell_level, strikes)

            strikes_iv = []
            for k in strikes:
                c = c_map.get(k, {}); p = p_map.get(k, {})
                iv = c.get('volatility') or p.get('volatility')
                strikes_iv.append({"strike": int(k) if float(k).is_integer() else k,
                                   "iv": float(iv) if iv is not None else None})
            push_strikes_to_calculator(strikes_iv, central)

            rows = []
            for k in strikes:
                c = c_map.get(k, {}); p = p_map.get(k, {})
                iv = c.get('volatility') or p.get('volatility')
                rows.append({
                    "Call_Ticker": c.get('secid', '—'),
                    "Call_Rho": c.get('rho'), "Call_Theta": c.get('theta'),
                    "Call_Vega": c.get('vega'), "Call_Gamma": c.get('gamma'),
                    "Call_Delta": c.get('delta'), "Call_Theor": c.get('theorprice'),
                    "Call_Last": c.get('last'), "Call_Offer": c.get('offer'),
                    "Call_Bid": c.get('bid'), "Strike": k, "IV_%": iv,
                    "Put_Bid": p.get('bid'), "Put_Offer": p.get('offer'),
                    "Put_Last": p.get('last'), "Put_Theor": p.get('theorprice'),
                    "Put_Delta": p.get('delta'), "Put_Gamma": p.get('gamma'),
                    "Put_Vega": p.get('vega'), "Put_Theta": p.get('theta'),
                    "Put_Rho": p.get('rho'), "Put_Ticker": p.get('secid', '—')})
            df = pd.DataFrame(rows)

            def _delta_color(delta):
                if not isinstance(delta, (int, float)): return None
                d = abs(delta)
                if 0.25 <= d <= 0.45: return "#00ff0c"
                if (0.15 <= d < 0.25) or (0.45 < d <= 0.55): return "#fcff00"
                return "#ff0000"

            def _theta_color(theta, vega):
                if not isinstance(theta, (int, float)) or not isinstance(vega, (int, float)):
                    return None
                if abs(vega) < 1e-9: return None
                ratio = abs(theta) / abs(vega)
                if ratio > 1.0: return "#00ff0c"
                if ratio > 0.5: return "#fcff00"
                return "#ff0000"

            def _liquidity_color(bid, ask, theor):
                if not all(isinstance(x, (int, float)) for x in (bid, ask, theor)):
                    return None
                if bid <= 0 or ask <= 0 or theor <= 0: return None
                spread_pct = (ask - bid) / theor * 100
                if spread_pct < 5: return "#00ff0c"
                if spread_pct < 15: return "#fcff00"
                return "#ff0000"

            def style_row(row):
                strike = float(row["Strike"])
                is_central = central is not None and abs(strike - float(central)) < 0.01
                is_buy_strike = (buy_strike_match is not None and abs(strike - float(buy_strike_match)) < 0.01)
                is_sell_strike = (sell_strike_match is not None and abs(strike - float(sell_strike_match)) < 0.01)
                call_bg = "#e1e3fb" if is_central else "#dbf3df"
                put_bg = "#fee5cd" if is_central else "#ffcdce"
                styles = []
                for col in row.index:
                    style = ""
                    if col.startswith("Call_"): style = f"background-color: {call_bg}"
                    elif col.startswith("Put_"): style = f"background-color: {put_bg}"
                    if col == "Strike":
                        if is_sell_strike:
                            style = "background-color:#fb92f0;color:white;font-weight:bold"
                        elif is_buy_strike:
                            style = "background-color:#9c00ff;color:white;font-weight:bold"
                        elif is_central:
                            style = "background-color:#e3e7ec;font-weight:bold"
                    elif col == "IV_%" and is_central:
                        style = "background-color:#e3e7ec;font-weight:bold"
                    if highlight_on:
                        if col in ("Call_Delta", "Put_Delta"):
                            c = _delta_color(row[col])
                            if c: style = f"background-color:{c};font-weight:600"
                        elif col in ("Call_Theta", "Put_Theta"):
                            vega_col = "Call_Vega" if col.startswith("Call_") else "Put_Vega"
                            c = _theta_color(row[col], row.get(vega_col))
                            if c: style = f"background-color:{c};font-weight:600"
                        elif col in ("Call_Bid", "Call_Offer", "Put_Bid", "Put_Offer"):
                            theor_col = "Call_Theor" if col.startswith("Call_") else "Put_Theor"
                            pair_col = col.replace("_Bid", "_Offer") if col.endswith("_Bid") else col.replace("_Offer", "_Bid")
                            c = _liquidity_color(row[col], row.get(pair_col), row.get(theor_col))
                            if c: style = f"background-color:{c}"
                    styles.append(style)
                return styles

            column_display = {
                "Call_Ticker": "Тк", "Call_Rho": "ρ", "Call_Theta": "Θ",
                "Call_Vega": "ν", "Call_Gamma": "Γ", "Call_Delta": "Δ",
                "Call_Theor": "Теор", "Call_Last": "Посл", "Call_Offer": "Оф",
                "Call_Bid": "Бид", "Strike": "K", "IV_%": "IV%",
                "Put_Bid": "Бид", "Put_Offer": "Оф", "Put_Last": "Посл",
                "Put_Theor": "Теор", "Put_Delta": "Δ", "Put_Gamma": "Γ",
                "Put_Vega": "ν", "Put_Theta": "Θ", "Put_Rho": "ρ", "Put_Ticker": "Тк"}

            caption_extra = ""
            if buy_strike_match is not None:
                caption_extra += f" · покуп.≈**{buy_strike_match}**"
            if sell_strike_match is not None:
                caption_extra += f" · продаж.≈**{sell_strike_match}**"
            st.caption(f"Центр: **{central if central is not None else '—'}** · "
                       f"страйков: {len(df)}{caption_extra}")

            st.dataframe(
                df.style.apply(style_row, axis=1).format(
                    {"Strike": "{:.0f}", "IV_%": "{:.2f}"},
                    precision=4, na_rep="—"),
                column_config=column_display,
                use_container_width=True, height=420)

            # ---- Улыбка волатильности ----
            st.markdown("#### 🌀 Улыбка IV")
            try:
                points = fetch_volatility_graph(asset, series_code, asset_type_ui)
            except Exception:
                points = []
            if points:
                strikes_g = [p['strike'] for p in points]
                vols_g = [p['volatility'] for p in points]
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=strikes_g, y=vols_g, mode='lines+markers',
                                         line=dict(color='#2c7da0', width=2),
                                         fill='tozeroy', fillcolor='rgba(44,125,160,0.1)',
                                         name='IV, %'))
                fig.update_layout(title=dict(text="Улыбка волатильности", font=dict(size=13)),
                                  xaxis_title="Страйк", yaxis_title="IV, %",
                                  height=300,
                                  margin=dict(l=10, r=10, t=40, b=20),
                                  xaxis=dict(tickformat=".0f", hoverformat=".0f"),
                                  yaxis=dict(tickformat=".2f", hoverformat=".2f"))
                st.plotly_chart(fig, use_container_width=True,
                                config={'displayModeBar': False})
            else:
                st.info("Данные улыбки недоступны.")


# ==================================================================
# ============ ВКЛАДКА 4: ОПОВЕЩЕНИЯ ===============================
# ==================================================================
with tab_alerts:
    st.markdown("Загрузите Excel. Колонки: **Тикер БА · Категория БА · "
                "Уровень покупок · Уровень продаж**. "
                "Сигнал покупки: цена ≤ уровня покупок. "
                "Сигнал продажи: цена ≥ уровня продаж.")

    uploaded = st.file_uploader("Excel (.xlsx)", type=["xlsx", "xls"],
                                key="alerts_xlsx_uploader")

    if "alerts_df" not in st.session_state:
        st.session_state.alerts_df = None

    if uploaded is not None:
        try:
            _xls = pd.read_excel(uploaded)
            _col_map = {}
            for c in _xls.columns:
                c_str = str(c).strip().lower()
                if "тикер" in c_str: _col_map[c] = "Тикер БА"
                elif "категор" in c_str: _col_map[c] = "Категория БА"
                elif "покуп" in c_str or "bid" in c_str: _col_map[c] = "Уровень покупок"
                elif "продаж" in c_str or "ask" in c_str: _col_map[c] = "Уровень продаж"
            _xls = _xls.rename(columns=_col_map)
            required = ["Тикер БА", "Категория БА", "Уровень покупок", "Уровень продаж"]
            missing = [c for c in required if c not in _xls.columns]
            if missing:
                st.error(f"Нет колонок: {', '.join(missing)}")
            else:
                _xls["Уровень покупок"] = pd.to_numeric(_xls["Уровень покупок"], errors="coerce")
                _xls["Уровень продаж"] = pd.to_numeric(_xls["Уровень продаж"], errors="coerce")
                _xls = _xls.dropna(subset=["Тикер БА", "Уровень покупок", "Уровень продаж"])
                st.session_state.alerts_df = _xls
                st.success(f"Загружено {len(_xls)} строк.")
        except Exception as e:
            st.error(f"Ошибка чтения: {e}")

    if st.session_state.alerts_df is not None:
        if st.button("Очистить таблицу", key="alerts_clear_btn"):
            st.session_state.alerts_df = None
            st.rerun()

    if st.session_state.alerts_df is None:
        st.info("Загрузите Excel-файл.")
    else:
        @st.fragment(run_every="10s")
        def _render_alerts_live():
            df_alerts = st.session_state.alerts_df.copy()

            def _get_price_for_alert(ticker, category):
                secid = resolve_underlying_secid(ticker.upper(), category)
                return fetch_last_price_from_iss(secid, category)

            out_rows = []
            for _, row in df_alerts.iterrows():
                ticker = str(row["Тикер БА"]).strip()
                category = str(row["Категория БА"]).strip()
                lvl_buy = float(row["Уровень покупок"])
                lvl_sell = float(row["Уровень продаж"])
                info = _get_price_for_alert(ticker, category)
                last = info.get("last") if info else None
                if last and last > 0:
                    buy_dev_pct = (lvl_buy - last) / last * 100.0
                    sell_dev_pct = (lvl_sell - last) / last * 100.0
                    buy_active = (last <= lvl_buy)
                    sell_active = (last >= lvl_sell)
                else:
                    buy_dev_pct = sell_dev_pct = None
                    buy_active = sell_active = False
                out_rows.append({
                    "Тикер БА": ticker, "Категория БА": category,
                    "Уровень покупок": lvl_buy, "Откл. покупок, %": buy_dev_pct,
                    "Уровень продаж": lvl_sell, "Откл. продаж, %": sell_dev_pct,
                    "Рыночная цена": last,
                    "Покупка активна": buy_active,
                    "Продажа активна": sell_active})

            df_out = pd.DataFrame(out_rows)

            def _style_alert_row(row):
                styles = []
                for col in row.index:
                    style = ""
                    if col in ("Покупка активна", "Продажа активна"):
                        if row[col] is True:
                            style = "background-color:#00ff0c;color:#0a3d0e;font-weight:700"
                    elif col == "Откл. покупок, %" and row[col] is not None:
                        style = "color:#00a651;font-weight:700" if row[col] <= 0 else "color:#d32f2f"
                    elif col == "Откл. продаж, %" and row[col] is not None:
                        style = "color:#00a651;font-weight:700" if row[col] >= 0 else "color:#d32f2f"
                    styles.append(style)
                return styles

            st.dataframe(
                df_out.style.apply(_style_alert_row, axis=1).format({
                    "Уровень покупок": "{:,.2f}", "Уровень продаж": "{:,.2f}",
                    "Откл. покупок, %": "{:+.2f}%", "Откл. продаж, %": "{:+.2f}%",
                    "Рыночная цена": "{:,.2f}",
                    "Покупка активна": lambda v: "АКТИВНО" if v is True else "—",
                    "Продажа активна": lambda v: "АКТИВНО" if v is True else "—"},
                    na_rep="—"),
                use_container_width=True, hide_index=True, height=400)

            n_buy = int((df_out["Покупка активна"] == True).sum())
            n_sell = int((df_out["Продажа активна"] == True).sum())
            n_total = len(df_out)
            s1, s2, s3 = st.columns(3)
            with s1: st.metric("Всего", n_total)
            with s2: st.metric("Покупка", n_buy)
            with s3: st.metric("Продажа", n_sell)

            st.download_button("📤 Экспорт CSV",
                               data=df_out.to_csv(index=False).encode("utf-8-sig"),
                               file_name="alerts.csv", mime="text/csv",
                               use_container_width=True)

        _render_alerts_live()
