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
# ABA 1: PLANEJADOR DE ROTA
# ==========================================
with aba_rota:
    st.subheader("Para onde vamos?")

    if not CHAVE_GOOGLE:
        st.markdown(
            '<div class="alerta-inline">⚠️ <strong>Chave Google Maps não configurada.</strong> '
            'Adicione <code>CHAVE_GOOGLE</code> em <code>.streamlit/secrets.toml</code> para usar esta aba.</div>',
            unsafe_allow_html=True
        )

    c_orig, c_dest = st.columns(2)
    with c_orig:
        tipo_origem = st.radio(
            "Origem:", ["📍 Usar meu GPS", "⌨️ Digitar Endereço"],
            horizontal=True, key="orig_type"
        )
        if tipo_origem == "📍 Usar meu GPS":
            origem_final = f"{lat_u},{lon_u}" if lat_u else None
            st.text_input("Saindo de:", value="Minha localização atual", disabled=True)
        else:
            origem_final = st.text_input(
                "Saindo de:", placeholder="Ex: Av. Paulista, 1000", key="orig_text"
            )

    with c_dest:
        destino_final = st.text_input(
            "Indo para:", placeholder="Ex: Estação da Luz", key="dest_text"
        )

    with st.expander("⚙️ Preferências de Trajeto"):
        col_m, col_p, col_h = st.columns(3)
        with col_m:
            modo = st.selectbox(
                "Transporte:", ["transit", "walking", "driving"],
                format_func=lambda x: {"transit": "🚌 Ônibus/Metrô", "walking": "🚶 A pé", "driving": "🚗 Carro"}[x]
            )
        with col_p:
            prioridade = st.selectbox(
                "Prioridade:", ["best_guess", "fewer_transfers", "less_walking"],
                format_func=lambda x: {"best_guess": "⚡ Mais Rápido", "fewer_transfers": "🔄 Menos Trocas", "less_walking": "🚶 Menos Caminhada"}[x]
            )
        with col_h:
            quando = st.radio("Quando:", ["Sair Agora", "Escolher Horário"], horizontal=True)
            ts = "now"
            if quando == "Escolher Horário":
                h_e = st.time_input("Horário de Saída:", value=datetime.now().time())
                dt = datetime.combine(datetime.today(), h_e)
                ts = int(time_lib.mktime(dt.timetuple()))

    if st.button("🚀 Calcular Melhor Rota", type="primary"):
        if not CHAVE_GOOGLE:
            st.error("Configure a chave da API Google Maps para usar esta função.")
        elif not origem_final or "None" in str(origem_final):
            st.error("Origem não definida. Ative o GPS ou digite o endereço de partida.")
        elif not destino_final:
            st.warning("Por favor, digite o destino.")
        else:
            with st.spinner("Consultando rotas..."):
                try:
                    url = (
                        f"https://maps.googleapis.com/maps/api/directions/json"
                        f"?origin={origem_final}&destination={destino_final}"
                        f"&mode={modo}&transit_routing_preference={prioridade}"
                        f"&departure_time={ts}&language=pt-BR&key={CHAVE_GOOGLE}"
                    )
                    res = requests.get(url, timeout=10).json()

                    if res.get('status') == 'OK':
                        r = res['routes'][0]
                        lg = r['legs'][0]

                        # Métricas da rota
                        mc1, mc2, mc3 = st.columns(3)
                        mc1.metric("⏱️ Duração", lg['duration']['text'])
                        mc2.metric("📏 Distância", lg['distance']['text'])
                        mc3.metric("🚏 Partida", lg.get('departure_time', {}).get('text', 'Agora'))

                        col_txt, col_map = st.columns([1, 1])
                        with col_txt:
                            st.markdown("#### 📋 Instruções de Viagem")
                            for i, step in enumerate(lg['steps'], 1):
                                txt = (step['html_instructions']
                                       .replace('<b>', '**').replace('</b>', '**')
                                       .replace('<div style="font-size:0.9em">', ' (')
                                       .replace('</div>', ')'))
                                st.markdown(
                                    f'<div class="instrucao-passo"><strong>{i}.</strong> {txt}</div>',
                                    unsafe_allow_html=True
                                )

                        with col_map:
                            pts = decode_poly(r['overview_polyline']['points'])
                            m_r = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB Positron')
                            folium.PolyLine(pts, color="#004a99", weight=6, opacity=0.85).add_to(m_r)
                            folium.Marker(pts[0], tooltip="Início", icon=folium.Icon(color='green', icon='play')).add_to(m_r)
                            folium.Marker(pts[-1], tooltip="Destino", icon=folium.Icon(color='red', icon='flag')).add_to(m_r)
                            st_folium(m_r, width=600, height=500, key="mapa_planeador")
                    else:
                        status = res.get('status', 'UNKNOWN')
                        msgs = {
                            'ZERO_RESULTS': 'Nenhuma rota encontrada entre os pontos informados.',
                            'NOT_FOUND': 'Um dos endereços não foi encontrado. Tente ser mais específico.',
                            'REQUEST_DENIED': 'Chave da API inválida ou sem permissão.',
                            'OVER_DAILY_LIMIT': 'Limite diário da API Google atingido.',
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
                opcoes = {
                    f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l
                    for l in res_l
                }
                l_sel = opcoes[st.selectbox("Selecione o sentido:", list(opcoes.keys()))]

                with st.spinner("Buscando posição da frota..."):
                    frota_res = sessao.get(
                        f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}",
                        timeout=8
                    ).json()

                vs = frota_res.get('vs', [])

                if vs:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🚌 Frota na Rua", len(vs))
                    m2.metric("♿ Acessíveis", sum(1 for v in vs if v.get('a')))
                    m3.metric("🚫 Não Acessíveis", sum(1 for v in vs if not v.get('a')))
                    m4.metric("🕒 Atualizado", frota_res.get('hr', '—'))

                    m_f = folium.Map(
                        location=[vs[0]['py'], vs[0]['px']],
                        zoom_start=13,
                        tiles='CartoDB Positron'
                    )

                    # Trajeto oficial (bug fix: agora carrega o .gz corretamente)
                    chave_t = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl']}"
                    if chave_t in dados_trajetos:
                        folium.PolyLine(
                            dados_trajetos[chave_t],
                            color="#00A1FF", weight=4, opacity=0.6,
                            tooltip="Trajeto oficial"
                        ).add_to(m_f)

                    # Ícones diferenciados: acessível (azul) vs não acessível (laranja)
                    for v in vs:
                        cor = 'blue' if v.get('a') else 'orange'
                        folium.Marker(
                            [v['py'], v['px']],
                            popup=folium.Popup(
                                f"<b>Prefixo:</b> {v['p']}<br>"
                                f"<b>Acessível:</b> {'Sim' if v.get('a') else 'Não'}",
                                max_width=200
                            ),
                            icon=folium.Icon(color=cor, icon='bus', prefix='fa')
                        ).add_to(m_f)

                    # Legenda simples
                    st.caption("🔵 Acessível  🟠 Não acessível")
                    st_folium(m_f, width=1000, height=480, key="mapa_monitor")
                else:
                    st.info("Nenhum ônibus detectado para esta linha no momento.")

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

                        linhas = prev.get('p', {}).get('l', []) if prev else []
                        if linhas:
                            for lin in linhas:
                                vs_prev = lin.get('vs', [])
                                if vs_prev:
                                    chegada = vs_prev[0].get('t', '?')
                                    prefixo = vs_prev[0].get('p', '?')
                                    st.write(
                                        f"🚌 **Linha {lin['c']}** — chegada prevista: `{chegada}` "
                                        f"(prefixo {prefixo})"
                                    )
                        else:
                            st.caption("Sem ônibus a caminho deste ponto agora.")
                    except requests.RequestException:
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
