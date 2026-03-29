import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime, time
import math
import json
import os
import gzip
import time as time_lib
from streamlit_autorefresh import st_autorefresh
from streamlit_geolocation import streamlit_geolocation

# ==========================================
# 1. CONFIGURAÇÕES, CHAVES E ESTILO
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")

st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Fundo e container */
    .main { background-color: #f0f4f8; }
    section[data-testid="stSidebar"] { background-color: #0a1628; }
    section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    section[data-testid="stSidebar"] .stSuccess { background: #1a3a2a; border-color: #2d6a4f; }
    section[data-testid="stSidebar"] .stWarning { background: #3a2a0a; border-color: #b7791f; }

    /* Botão principal */
    .stButton>button {
        border-radius: 10px;
        height: 3em;
        background: linear-gradient(135deg, #004a99, #0066cc);
        color: white;
        font-weight: 600;
        width: 100%;
        border: none;
        box-shadow: 0 4px 14px rgba(0,74,153,0.35);
        transition: all 0.2s ease;
        letter-spacing: 0.3px;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #003780, #004a99);
        box-shadow: 0 6px 20px rgba(0,74,153,0.5);
        transform: translateY(-1px);
    }
    .stButton>button:active { transform: translateY(0); }

    /* Cards de passo de instrução */
    .instrucao-passo {
        padding: 12px 16px;
        border-left: 4px solid #004a99;
        background: white;
        margin-bottom: 8px;
        border-radius: 6px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        font-size: 14px;
        line-height: 1.6;
        transition: box-shadow 0.2s;
    }
    .instrucao-passo:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    div[data-testid="metric-container"] label { color: #64748b !important; font-size: 13px !important; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] { color: #0a1628 !important; font-weight: 700 !important; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: white;
        border-radius: 12px;
        padding: 4px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        font-weight: 500;
        color: #64748b;
    }
    .stTabs [aria-selected="true"] {
        background: #004a99 !important;
        color: white !important;
    }

    /* Inputs */
    .stTextInput input, .stSelectbox select {
        border-radius: 8px;
        border-color: #cbd5e1;
        background: white;
    }
    .stTextInput input:focus { border-color: #004a99; box-shadow: 0 0 0 3px rgba(0,74,153,0.1); }

    /* Expander */
    .streamlit-expanderHeader {
        background: white;
        border-radius: 10px;
        font-weight: 600;
        color: #0a1628;
    }

    /* Badge de status GPS */
    .badge-gps-on {
        display: inline-block;
        background: #d1fae5;
        color: #065f46;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-gps-off {
        display: inline-block;
        background: #fef3c7;
        color: #92400e;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }

    /* Cabeçalho da sidebar */
    .sidebar-logo {
        font-size: 22px;
        font-weight: 800;
        color: white !important;
        letter-spacing: -0.5px;
        margin-bottom: 4px;
    }
    .sidebar-subtitle {
        font-size: 11px;
        color: #94a3b8 !important;
        margin-bottom: 16px;
    }

    /* Aviso inline */
    .alerta-inline {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 13px;
        color: #9a3412;
        margin: 8px 0;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. FUNÇÕES UTILITÁRIAS
# ==========================================

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    """Cálculo correto de distância usando fórmula de Haversine."""
    R = 6371000  # raio da Terra em metros
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def decode_poly(p):
    """Decodifica polyline do Google Maps."""
    index, lat, lng = 0, 0, 0
    coords = []
    while index < len(p):
        for unit in ['lat', 'lng']:
            shift, result = 0, 0
            while True:
                byte = ord(p[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if not byte >= 0x20:
                    break
            change = ~(result >> 1) if (result & 1) else (result >> 1)
            if unit == 'lat':
                lat += change
            else:
                lng += change
        coords.append([lat / 100000.0, lng / 100000.0])
    return coords

@st.cache_data(show_spinner=False)
def carregar_json(nome_arquivo):
    """Carrega JSON simples com cache."""
    if os.path.exists(nome_arquivo):
        try:
            with open(nome_arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

@st.cache_data(show_spinner=False)
def carregar_json_gz(nome_arquivo):
    """
    BUG CORRIGIDO: carrega arquivos .json.gz (comprimidos).
    O código original tentava abrir 'trajetos.json' sem descomprimir.
    """
    gz_path = nome_arquivo + ".gz"
    # Tenta primeiro o .gz, depois o .json plano
    if os.path.exists(gz_path):
        try:
            with gzip.open(gz_path, "rt", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    elif os.path.exists(nome_arquivo):
        try:
            with open(nome_arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

@st.cache_resource(show_spinner=False)
def criar_sessao_sptrans():
    """
    BUG CORRIGIDO: sessão SPTrans reutilizável (cache_resource).
    O código original criava uma nova sessão em cada aba, causando
    múltiplas autenticações e possível rate-limiting.
    """
    s = requests.Session()
    if TOKEN_SPTRANS:
        try:
            s.post(
                f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}",
                timeout=5
            )
        except requests.RequestException:
            pass
    return s

# Carregamento dos dados com feedback visual
with st.spinner("Carregando dados das linhas..."):
    dados_trajetos = carregar_json_gz("trajetos.json")
    dados_paradas = carregar_json("paradas.json")
    dados_horarios = carregar_json("horarios.json")

# ==========================================
# 3. SIDEBAR — GPS E IDENTIDADE
# ==========================================
with st.sidebar:
    st.markdown('<p class="sidebar-logo">🚌 BusRadar Pro</p>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-subtitle">v6.0 · São Paulo Transit</p>', unsafe_allow_html=True)
    st.divider()

    st.markdown("**📡 GPS do Dispositivo**")
    gps = streamlit_geolocation()

    if gps and gps.get('latitude'):
        lat_u, lon_u = gps['latitude'], gps['longitude']
        st.markdown(
            f'<span class="badge-gps-on">✅ Conectado · {lat_u:.4f}, {lon_u:.4f}</span>',
            unsafe_allow_html=True
        )
        precisao = gps.get('accuracy', '?')
        st.caption(f"Precisão: ±{precisao}m")
    else:
        lat_u, lon_u = None, None
        st.markdown('<span class="badge-gps-off">⏳ Aguardando sinal...</span>', unsafe_allow_html=True)
        st.caption("Permita o acesso à localização no navegador.")

    st.divider()

    # Estatísticas rápidas dos dados carregados
    st.markdown("**📊 Base de Dados Local**")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Paradas", f"{len(dados_paradas):,}".replace(",", "."))
    col_s2.metric("Linhas", f"{len(dados_horarios):,}".replace(",", "."))
    st.caption("Fonte: GTFS SPTrans")

# ==========================================
# 4. ABAS PRINCIPAIS
# ==========================================
aba_rota, aba_monitor, aba_ponto, aba_london = st.tabs([
    "🗺️ Planejador", "🚌 Monitor de Frota", "📍 Radar de Área", "🇬🇧 Londres"
])

# ==========================================
# ABA 1: PLANEJADOR — ESTILO GOOGLE MAPS
# ==========================================
with aba_rota:

    # CSS extra específico para o planejador
    st.markdown("""
    <style>
    /* Painel de origem/destino */
    .painel-rota {
        background: white;
        border-radius: 14px;
        padding: 20px 24px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        margin-bottom: 16px;
    }
    /* Botões de modo de transporte (chips) */
    .transport-row { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0 4px 0; }
    .transport-chip {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 7px 16px; border-radius: 20px; font-size: 13px; font-weight: 500;
        border: 2px solid #e2e8f0; background: white; color: #475569; cursor: pointer;
        transition: all 0.15s;
    }
    .transport-chip.ativo {
        border-color: #004a99; background: #eff6ff; color: #004a99; font-weight: 600;
    }
    /* Linha de entrada (origem/destino) */
    .linha-input { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
    .dot-verde { width:12px; height:12px; background:#22c55e; border-radius:50%; flex-shrink:0; }
    .dot-vermelho { width:12px; height:12px; background:#ef4444; border-radius:50%; flex-shrink:0; }
    .linha-tracejada { width:2px; height:20px; background:repeating-linear-gradient(to bottom,#cbd5e1 0,#cbd5e1 4px,transparent 4px,transparent 8px); margin-left:5px; }

    /* Card de resultado de rota */
    .rota-card {
        background: white; border-radius: 12px; padding: 16px 20px;
        border-left: 5px solid #004a99; margin-bottom: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06);
        cursor: pointer; transition: box-shadow 0.2s, transform 0.15s;
    }
    .rota-card:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.1); transform: translateY(-2px); }
    .rota-card-melhor { border-left-color: #16a34a; }
    .rota-badge {
        display:inline-block; font-size:10px; font-weight:700; padding:2px 8px;
        border-radius:10px; background:#dcfce7; color:#15803d; margin-left:8px;
        vertical-align: middle;
    }

    /* Etapas de transporte */
    .step-transit { display:flex; align-items:flex-start; gap:12px; padding:12px 0; border-bottom:1px solid #f1f5f9; }
    .step-icon { font-size:22px; min-width:32px; text-align:center; }
    .step-info { flex:1; }
    .step-linha-tag {
        display:inline-block; padding:2px 10px; border-radius:4px;
        font-size:12px; font-weight:700; color:white; margin-bottom:4px;
    }
    .step-detalhe { font-size:13px; color:#64748b; margin-top:2px; }

    /* Quando: chips de horário */
    .quando-row { display:flex; gap:8px; flex-wrap: wrap; margin: 8px 0; }
    .quando-chip {
        padding:6px 16px; border-radius:16px; font-size:13px; font-weight:500;
        border:2px solid #e2e8f0; background:white; color:#475569; cursor:pointer;
    }
    .quando-chip.ativo { border-color:#004a99; background:#eff6ff; color:#004a99; }

    /* Filtros de modal de transporte */
    .filtro-section { margin-top:12px; }
    .filtro-label { font-size:12px; font-weight:600; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }
    </style>
    """, unsafe_allow_html=True)

    if not CHAVE_GOOGLE:
        st.markdown(
            '<div class="alerta-inline">⚠️ <strong>Chave Google Maps não configurada.</strong> '
            'Adicione <code>CHAVE_GOOGLE</code> em <code>.streamlit/secrets.toml</code>.</div>',
            unsafe_allow_html=True
        )

    # ── PAINEL ORIGEM / DESTINO ──────────────────────────────────
    st.markdown('<div class="painel-rota">', unsafe_allow_html=True)

    col_inputs, col_troca = st.columns([10, 1])
    with col_inputs:
        # Origem
        st.markdown('<div class="linha-input"><span class="dot-verde"></span></div>', unsafe_allow_html=True)
        tipo_origem = st.radio("", ["📍 Minha localização", "⌨️ Digitar"], horizontal=True, key="orig_type", label_visibility="collapsed")
        if tipo_origem == "📍 Minha localização":
            origem_final = f"{lat_u},{lon_u}" if lat_u else None
            st.text_input("Saindo de", value="Minha localização atual", disabled=True, label_visibility="collapsed")
        else:
            origem_final = st.text_input("Saindo de", placeholder="Ponto de partida", key="orig_text", label_visibility="collapsed")

        st.markdown('<div class="linha-tracejada" style="margin:4px 0 4px 5px"></div>', unsafe_allow_html=True)

        # Destino
        st.markdown('<div class="linha-input"><span class="dot-vermelho"></span></div>', unsafe_allow_html=True)
        destino_final = st.text_input("Indo para", placeholder="Destino", key="dest_text", label_visibility="collapsed")

    st.markdown('</div>', unsafe_allow_html=True)

    # ── MODO DE TRANSPORTE (multi-select com checkboxes) ─────────
    st.markdown("**Modo de transporte**")
    st.caption("Selecione um ou mais meios — rotas que combinem os marcados serão consideradas.")

    transit_opcoes = {"🚌 Ônibus": "bus", "🚇 Metrô": "subway", "🚆 Trem": "train", "🚊 VLT": "tram"}
    outros_opcoes  = {"🚶 A pé": "walking", "🚗 Carro": "driving"}

    col_tr, col_out = st.columns([3, 1])

    with col_tr:
        st.markdown("<span style=\'font-size:12px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:.5px\'>Transporte público</span>", unsafe_allow_html=True)
        cols_t = st.columns(len(transit_opcoes))
        transit_selecionados = []
        for col, (label, val) in zip(cols_t, transit_opcoes.items()):
            if col.checkbox(label, value=True, key=f"modo_{val}"):
                transit_selecionados.append(val)

    with col_out:
        st.markdown("<span style=\'font-size:12px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:.5px\'>Outros</span>", unsafe_allow_html=True)
        cols_o = st.columns(len(outros_opcoes))
        outros_selecionados = []
        for col, (label, val) in zip(cols_o, outros_opcoes.items()):
            if col.checkbox(label, value=False, key=f"modo_{val}"):
                outros_selecionados.append(val)

    # Decide modo e transit_mode para a API
    tem_transit = len(transit_selecionados) > 0
    so_walking   = outros_selecionados == ["walking"] and not tem_transit
    so_driving   = outros_selecionados == ["driving"] and not tem_transit

    if so_walking:
        modo_api, transit_mode = "walking", None
    elif so_driving:
        modo_api, transit_mode = "driving", None
    elif tem_transit:
        modo_api = "transit"
        transit_mode = "|".join(transit_selecionados)  # ex: "bus|subway|train"
    else:
        modo_api, transit_mode = "transit", None

    st.markdown("---")

    # ── PREFERÊNCIAS (só mostra se for transit) ───────────────────
    col_pref, col_quando = st.columns([1, 1])

    with col_pref:
        if modo_api == "transit":
            st.markdown("**Preferência de rota**")
            prioridade_map = {
                "⚡ Mais rápida":       "best_guess",
                "🔄 Menos baldeações":  "fewer_transfers",
                "🚶 Menos caminhada":   "less_walking",
            }
            pref_sel = st.radio(
                "pref", list(prioridade_map.keys()),
                horizontal=False, key="pref_rota", label_visibility="collapsed"
            )
            prioridade = prioridade_map[pref_sel]
        else:
            prioridade = "best_guess"

    with col_quando:
        st.markdown("**Quando**")
        quando_opcoes = ["🟢 Sair agora", "🕐 Horário de saída", "🏁 Horário de chegada"]
        quando_sel = st.radio(
            "quando", quando_opcoes,
            horizontal=False, key="quando_rota", label_visibility="collapsed"
        )

        ts = "now"
        arrival_time = None

        if quando_sel == "🕐 Horário de saída":
            col_d, col_h = st.columns(2)
            with col_d:
                data_sel = st.date_input("Data", value=datetime.today(), key="data_saida", label_visibility="collapsed")
            with col_h:
                hora_sel = st.time_input("Hora", value=datetime.now().time(), key="hora_saida", label_visibility="collapsed")
            dt = datetime.combine(data_sel, hora_sel)
            ts = int(time_lib.mktime(dt.timetuple()))

        elif quando_sel == "🏁 Horário de chegada":
            col_d, col_h = st.columns(2)
            with col_d:
                data_arr = st.date_input("Data", value=datetime.today(), key="data_chegada", label_visibility="collapsed")
            with col_h:
                hora_arr = st.time_input("Hora", value=datetime.now().time(), key="hora_chegada", label_visibility="collapsed")
            dt_arr = datetime.combine(data_arr, hora_arr)
            arrival_time = int(time_lib.mktime(dt_arr.timetuple()))
            ts = "now"  # departure_time ignorado quando arrival_time está presente

    # ── BOTÃO ─────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔍 Buscar rotas", type="primary", key="btn_buscar_rota"):
        if not CHAVE_GOOGLE:
            st.error("Configure a chave da API Google Maps para usar esta função.")
        elif not origem_final or "None" in str(origem_final):
            st.error("Origem não definida. Ative o GPS ou digite o endereço de partida.")
        elif not destino_final:
            st.warning("Digite o destino.")
        else:
            with st.spinner("Buscando rotas..."):
                try:
                    # Monta URL com parâmetros corretos
                    params = {
                        "origin": origem_final,
                        "destination": destino_final,
                        "mode": modo_api,
                        "language": "pt-BR",
                        "key": CHAVE_GOOGLE,
                        "alternatives": "true",   # pede múltiplas rotas
                    }
                    if modo_api == "transit":
                        params["transit_routing_preference"] = prioridade
                        if transit_mode:
                            params["transit_mode"] = transit_mode
                    if arrival_time:
                        params["arrival_time"] = arrival_time
                    elif ts != "now":
                        params["departure_time"] = ts
                    else:
                        params["departure_time"] = "now"

                    res = requests.get(
                        "https://maps.googleapis.com/maps/api/directions/json",
                        params=params, timeout=12
                    ).json()

                    if res.get('status') == 'OK':
                        rotas = res['routes']

                        # ── CARDS DE OPÇÕES DE ROTA ──────────────────────
                        st.markdown(f"### {len(rotas)} rota(s) encontrada(s)")

                        opcoes_label = []
                        for i, r in enumerate(rotas):
                            lg = r['legs'][0]
                            dur = lg['duration']['text']
                            dist = lg['distance']['text']
                            label = f"Rota {i+1} · {dur} · {dist}"
                            opcoes_label.append(label)

                        rota_escolhida_idx = st.radio(
                            "Selecione a rota:", opcoes_label,
                            key="rota_sel", label_visibility="collapsed"
                        )
                        idx = opcoes_label.index(rota_escolhida_idx)
                        r_sel = rotas[idx]
                        lg = r_sel['legs'][0]

                        # ── RESUMO DA ROTA SELECIONADA ────────────────────
                        mc1, mc2, mc3, mc4 = st.columns(4)
                        mc1.metric("⏱️ Duração", lg['duration']['text'])
                        mc2.metric("📏 Distância", lg['distance']['text'])
                        dep = lg.get('departure_time', {}).get('text', '—')
                        arr = lg.get('arrival_time', {}).get('text', '—')
                        mc3.metric("🚀 Saída", dep)
                        mc4.metric("🏁 Chegada", arr)

                        col_txt, col_map = st.columns([1, 1])

                        with col_txt:
                            st.markdown("#### 📋 Passo a passo")
                            for i, step in enumerate(lg['steps'], 1):
                                modo_step = step.get('travel_mode', '')
                                transit = step.get('transit_details', {})

                                if modo_step == 'TRANSIT' and transit:
                                    line = transit.get('line', {})
                                    nome_linha = line.get('short_name') or line.get('name', '?')
                                    vehicle = line.get('vehicle', {})
                                    tipo_veiculo = vehicle.get('name', 'Ônibus')
                                    icone_v = vehicle.get('local_icon') or ''
                                    cor_linha = line.get('color', '#004a99')
                                    dep_stop = transit.get('departure_stop', {}).get('name', '?')
                                    arr_stop = transit.get('arrival_stop', {}).get('name', '?')
                                    n_paradas = transit.get('num_stops', '?')
                                    h_saida = transit.get('departure_time', {}).get('text', '')
                                    h_cheg = transit.get('arrival_time', {}).get('text', '')

                                    emoji_v = {"Bus": "🚌", "Subway": "🚇", "Heavy Rail": "🚆",
                                               "Commuter Train": "🚆", "Tram": "🚊"}.get(tipo_veiculo, "🚌")

                                    st.markdown(f"""
                                    <div class="instrucao-passo">
                                        <div style="margin-bottom:6px">
                                            {emoji_v}
                                            <span class="step-linha-tag" style="background:{cor_linha}">{nome_linha}</span>
                                            <strong>{tipo_veiculo}</strong>
                                        </div>
                                        <div style="font-size:13px;color:#374151">
                                            📍 <strong>{dep_stop}</strong> → <strong>{arr_stop}</strong>
                                        </div>
                                        <div class="step-detalhe">
                                            {n_paradas} parada(s) &nbsp;·&nbsp; {h_saida} → {h_cheg}
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)

                                else:
                                    # Passo a pé ou carro
                                    txt = (step['html_instructions']
                                           .replace('<b>', '<strong>').replace('</b>', '</strong>')
                                           .replace('<div style="font-size:0.9em">', '<br><span style="color:#64748b;font-size:12px">')
                                           .replace('</div>', '</span>'))
                                    dur_step = step.get('duration', {}).get('text', '')
                                    dist_step = step.get('distance', {}).get('text', '')
                                    emoji_step = "🚶" if modo_step == "WALKING" else "🚗"
                                    st.markdown(f"""
                                    <div class="instrucao-passo" style="border-left-color:#94a3b8">
                                        {emoji_step} {txt}
                                        <div class="step-detalhe">{dur_step} · {dist_step}</div>
                                    </div>
                                    """, unsafe_allow_html=True)

                        with col_map:
                            pts = decode_poly(r_sel['overview_polyline']['points'])
                            m_r = folium.Map(location=pts[0], zoom_start=13, tiles='CartoDB Positron')
                            folium.PolyLine(pts, color="#004a99", weight=6, opacity=0.85).add_to(m_r)
                            folium.Marker(pts[0], tooltip="Partida", icon=folium.Icon(color='green', icon='play')).add_to(m_r)
                            folium.Marker(pts[-1], tooltip="Chegada", icon=folium.Icon(color='red', icon='flag')).add_to(m_r)

                            # Marca pontos de embarque/desembarque
                            for step in lg['steps']:
                                if step.get('travel_mode') == 'TRANSIT':
                                    td = step.get('transit_details', {})
                                    dep_loc = td.get('departure_stop', {}).get('location', {})
                                    arr_loc = td.get('arrival_stop', {}).get('location', {})
                                    if dep_loc:
                                        folium.CircleMarker(
                                            [dep_loc['lat'], dep_loc['lng']],
                                            radius=6, color='#004a99', fill=True,
                                            tooltip=td.get('departure_stop', {}).get('name', '')
                                        ).add_to(m_r)
                                    if arr_loc:
                                        folium.CircleMarker(
                                            [arr_loc['lat'], arr_loc['lng']],
                                            radius=6, color='#ef4444', fill=True,
                                            tooltip=td.get('arrival_stop', {}).get('name', '')
                                        ).add_to(m_r)

                            st_folium(m_r, width=620, height=520, key="mapa_planeador")

                    else:
                        status = res.get('status', 'UNKNOWN')
                        msgs = {
                            'ZERO_RESULTS': 'Nenhuma rota encontrada. Tente outros endereços ou modo de transporte.',
                            'NOT_FOUND': 'Endereço não encontrado. Seja mais específico.',
                            'REQUEST_DENIED': 'Chave da API inválida ou sem permissão.',
                            'OVER_DAILY_LIMIT': 'Limite diário da API Google atingido.',
                            'INVALID_REQUEST': 'Parâmetros inválidos. Verifique origem e destino.',
                        }
                        st.error(f"Erro: {msgs.get(status, status)}")

                except requests.RequestException as e:
                    st.error(f"Falha de conexão com a API Google: {e}")

# ==========================================
# ABA 2: MONITOR DE FROTA
# ==========================================
with aba_monitor:
    st.subheader("🚌 Radar da Frota em Tempo Real")

    if not TOKEN_SPTRANS:
        st.markdown(
            '<div class="alerta-inline">⚠️ <strong>Token SPTrans não configurado.</strong> '
            'Adicione <code>TOKEN_SPTRANS</code> em <code>.streamlit/secrets.toml</code>.</div>',
            unsafe_allow_html=True
        )

    lin_id = st.text_input("🔍 Número da Linha (ex: 675A, 8000):", key="mon_lin")

    if lin_id and TOKEN_SPTRANS:
        sessao = criar_sessao_sptrans()  # sessão reutilizada (bug fix)
        try:
            res_l = sessao.get(
                f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}",
                timeout=8
            ).json()

            if not res_l:
                st.warning("Nenhuma linha encontrada. Verifique o número digitado.")
            else:
                # Agrupa as linhas encontradas por número (lt), separando os sentidos
                # A API retorna uma entrada por sentido (sl=1 e sl=2)
                # Mostramos TODOS os sentidos no mesmo mapa — sem forçar escolha

                # Checkboxes para selecionar quais sentidos exibir
                st.markdown("**Sentidos disponíveis — selecione os que deseja ver:**")
                sentidos_cols = st.columns(min(len(res_l), 4))
                sentidos_ativos = {}
                for i, l in enumerate(res_l):
                    label = f"{l['lt']}-{l['tl']} · {l['tp']} ➔ {l['ts']}"
                    with sentidos_cols[i % len(sentidos_cols)]:
                        ativo = st.checkbox(label, value=True, key=f"sentido_{l['cl']}")
                    sentidos_ativos[l['cl']] = (ativo, l)

                linhas_ativas = [(cl, l) for cl, (ativo, l) in sentidos_ativos.items() if ativo]

                if not linhas_ativas:
                    st.info("Selecione pelo menos um sentido para ver a frota.")
                else:
                    # Cores por sentido: azul para sentido 1, verde para sentido 2, roxo para demais
                    paleta_sentido = ["blue", "green", "purple", "red"]
                    paleta_trajeto = ["#0066cc", "#16a34a", "#7c3aed", "#dc2626"]

                    todos_vs = []       # todos os ônibus de todos os sentidos ativos
                    total_acessiveis = 0
                    hr_atualizacao = "—"
                    primeiro_vs = None

                    with st.spinner("Buscando posição da frota..."):
                        frota_por_sentido = {}
                        for idx_s, (cl, l) in enumerate(linhas_ativas):
                            try:
                                frota_res = sessao.get(
                                    f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={cl}",
                                    timeout=8
                                ).json()
                                vs_s = frota_res.get('vs') or []
                                frota_por_sentido[cl] = (vs_s, l, idx_s, frota_res.get('hr', '—'))
                                todos_vs.extend(vs_s)
                                total_acessiveis += sum(1 for v in vs_s if v.get('a'))
                                if vs_s and primeiro_vs is None:
                                    primeiro_vs = vs_s[0]
                                hr_atualizacao = frota_res.get('hr', hr_atualizacao)
                            except requests.RequestException:
                                st.warning(f"Falha ao buscar sentido {l.get('tp')} ➔ {l.get('ts')}")

                    # Métricas consolidadas
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🚌 Total na Rua", len(todos_vs))
                    m2.metric("♿ Acessíveis", total_acessiveis)
                    m3.metric("🚫 Não Acessíveis", len(todos_vs) - total_acessiveis)
                    m4.metric("🕒 Atualizado", hr_atualizacao)

                    if not todos_vs:
                        st.info("Nenhum ônibus detectado nos sentidos selecionados.")
                    else:
                        centro = [primeiro_vs['py'], primeiro_vs['px']]
                        m_f = folium.Map(location=centro, zoom_start=13, tiles='CartoDB Positron')

                        # Plota cada sentido com sua cor
                        for cl, (vs_s, l, idx_s, _) in frota_por_sentido.items():
                            cor_bus = paleta_sentido[idx_s % len(paleta_sentido)]
                            cor_traj = paleta_trajeto[idx_s % len(paleta_trajeto)]
                            nome_sentido = f"{l['tp']} ➔ {l['ts']}"

                            # Trajeto oficial no mapa
                            chave_t = f"{l['lt']}-{l['tl']}-{l['sl']}"
                            if chave_t in dados_trajetos:
                                folium.PolyLine(
                                    dados_trajetos[chave_t],
                                    color=cor_traj, weight=4, opacity=0.55,
                                    tooltip=f"Trajeto: {nome_sentido}"
                                ).add_to(m_f)

                            # Ônibus do sentido
                            for v in vs_s:
                                cor_icon = cor_bus if v.get('a') else 'orange'
                                folium.Marker(
                                    [v['py'], v['px']],
                                    popup=folium.Popup(
                                        f"<b>Sentido:</b> {nome_sentido}<br>"
                                        f"<b>Prefixo:</b> {v['p']}<br>"
                                        f"<b>Acessível:</b> {'Sim' if v.get('a') else 'Não'}",
                                        max_width=220
                                    ),
                                    icon=folium.Icon(color=cor_icon, icon='bus', prefix='fa'),
                                    tooltip=f"{nome_sentido} · {v['p']}"
                                ).add_to(m_f)

                        # Legenda dinâmica
                        legenda_items = []
                        icones_cor = {"blue": "🔵", "green": "🟢", "purple":"🟣", "red":"🔴"}
                        for cl, (vs_s, l, idx_s, _) in frota_por_sentido.items():
                            emoji = icones_cor.get(paleta_sentido[idx_s % len(paleta_sentido)], "⚫")
                            legenda_items.append(f"{emoji} {l['tp']} ➔ {l['ts']} ({len(vs_s)} ônibus)")
                        legenda_items.append("🟠 = não acessível (qualquer sentido)")
                        st.caption("  ·  ".join(legenda_items))

                        st_folium(m_f, width=1000, height=480, key="mapa_monitor")

        except requests.RequestException as e:
            st.error(f"Falha de conexão com a API SPTrans: {e}")

# ==========================================
# ABA 3: RADAR DE ÁREA
# ==========================================
with aba_ponto:
    st.subheader("📍 Ônibus chegando perto de você")

    col_opt1, col_opt2 = st.columns([2, 1])
    with col_opt1:
        if st.checkbox("🔄 Atualizar automaticamente (30s)", value=True):
            st_autorefresh(interval=30000, key="auto_radar")
    with col_opt2:
        raio = st.slider("Raio de busca (m)", min_value=200, max_value=800, value=400, step=100)

    if not lat_u:
        st.warning("📍 Ative o GPS na barra lateral para ver os ônibus ao seu redor.")
    elif not dados_paradas:
        st.error("Base de paradas não carregada. Verifique o arquivo paradas.json.")
    elif not TOKEN_SPTRANS:
        st.markdown(
            '<div class="alerta-inline">⚠️ Token SPTrans necessário para previsões em tempo real.</div>',
            unsafe_allow_html=True
        )
    else:
        sessao = criar_sessao_sptrans()  # sessão reutilizada (bug fix)

        # Encontrar paradas no raio configurado (usando Haversine — bug fix)
        paradas_perto = []
        for p in dados_paradas:
            lat_p = p.get('py') or p.get('stop_lat')
            lon_p = p.get('px') or p.get('stop_lon')
            id_p = p.get('cp') or p.get('stop_id')
            if lat_p and lon_p and id_p:
                dist = calcular_distancia_haversine(lat_u, lon_u, float(lat_p), float(lon_p))
                if dist <= raio:
                    paradas_perto.append({
                        'cp': id_p,
                        'np': p.get('np') or p.get('stop_name', 'Parada'),
                        'lat': float(lat_p),
                        'lon': float(lon_p),
                        'dist': int(dist)
                    })

        paradas_perto = sorted(paradas_perto, key=lambda x: x['dist'])[:6]

        if not paradas_perto:
            st.info(f"Nenhuma parada encontrada no raio de {raio}m. Tente aumentar o raio.")
        else:
            st.success(f"✅ {len(paradas_perto)} parada(s) encontrada(s) no raio de {raio}m")

            # Mini mapa com as paradas próximas
            m_area = folium.Map(location=[lat_u, lon_u], zoom_start=16, tiles='CartoDB Positron')
            folium.Marker(
                [lat_u, lon_u],
                tooltip="Você está aqui",
                icon=folium.Icon(color='green', icon='user', prefix='fa')
            ).add_to(m_area)
            folium.Circle(
                [lat_u, lon_u], radius=raio,
                color='#004a99', fill=True, fill_opacity=0.08
            ).add_to(m_area)
            for p in paradas_perto:
                folium.Marker(
                    [p['lat'], p['lon']],
                    tooltip=f"🚏 {p['np']} ({p['dist']}m)",
                    icon=folium.Icon(color='blue', icon='bus', prefix='fa')
                ).add_to(m_area)
            st_folium(m_area, width=900, height=280, key="mapa_area")

            st.markdown("---")
            for p in paradas_perto:
                with st.expander(f"🚏 {p['np']}  ·  {p['dist']}m de você"):
                    try:
                        prev = sessao.get(
                            f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={p['cp']}",
                            timeout=8
                        ).json()

                        # Extração defensiva: a API pode retornar None, lista ou dict
                        linhas = []
                        if isinstance(prev, dict):
                            p_val = prev.get('p')
                            if isinstance(p_val, dict):
                                linhas = p_val.get('l') or []
                            elif isinstance(p_val, list):
                                linhas = p_val  # alguns endpoints retornam lista direto

                        if linhas:
                            for lin in linhas:
                                if not isinstance(lin, dict):
                                    continue
                                vs_prev = lin.get('vs') or []
                                if vs_prev:
                                    chegada = vs_prev[0].get('t', '?')
                                    prefixo = vs_prev[0].get('p', '?')
                                    st.write(
                                        f"🚌 **Linha {lin.get('c', '?')}** — chegada prevista: `{chegada}` "
                                        f"(prefixo {prefixo})"
                                    )
                        else:
                            st.caption("Sem ônibus a caminho deste ponto agora.")
                    except (requests.RequestException, ValueError):
                        st.caption("⚠️ Falha ao consultar previsões para esta parada.")

# ==========================================
# ABA 4: LONDRES (TfL)
# ==========================================
with aba_london:
    st.title("🇬🇧 London Transport — TfL")

    st.info(
        "Esta aba monitora linhas do transporte de Londres via **API pública do TfL** "
        "(Transport for London). Não requer chave de API para consultas básicas."
    )

    col_ln1, col_ln2 = st.columns(2)
    with col_ln1:
        linha_tfl = st.text_input(
            "Número da linha (ônibus):",
            placeholder="Ex: 15, 48, 390",
            key="tfl_line"
        )
    with col_ln2:
        parada_tfl = st.text_input(
            "Código da parada (NaptanId):",
            placeholder="Ex: 490000173RB",
            key="tfl_stop"
        )

    if st.button("🔍 Buscar no TfL", key="tfl_buscar"):
        if linha_tfl:
            with st.spinner("Consultando TfL..."):
                try:
                    url_tfl = f"https://api.tfl.gov.uk/line/{linha_tfl}/arrivals"
                    res_tfl = requests.get(url_tfl, timeout=10).json()

                    if isinstance(res_tfl, list) and res_tfl:
                        df_tfl = pd.DataFrame([{
                            "Parada": a.get("stationName", ""),
                            "Destino": a.get("destinationName", ""),
                            "Chegada (s)": a.get("timeToStation", 0),
                            "Chegada": f"{a.get('timeToStation', 0) // 60} min",
                            "Veículo": a.get("vehicleId", ""),
                        } for a in res_tfl])
                        df_tfl = df_tfl.sort_values("Chegada (s)").drop(columns=["Chegada (s)"])
                        st.success(f"✅ {len(df_tfl)} chegadas encontradas para a linha **{linha_tfl}**")
                        st.dataframe(df_tfl, use_container_width=True, hide_index=True)
                    elif isinstance(res_tfl, dict) and res_tfl.get('message'):
                        st.error(f"Erro TfL: {res_tfl.get('message')}")
                    else:
                        st.warning("Nenhuma chegada encontrada. Verifique o número da linha.")
                except requests.RequestException as e:
                    st.error(f"Falha de conexão com a API TfL: {e}")
        else:
            st.warning("Digite o número de uma linha para buscar.")
