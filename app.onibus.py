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
# 1. CONFIGURAÇÕES, CHAVES E IDENTIDADE VISUAL
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")

st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main { background-color: #f0f4f8; }
    
    /* Estilo dos Botões e Cards */
    .stButton>button {
        border-radius: 10px; background: linear-gradient(135deg, #004a99, #0066cc);
        color: white; font-weight: 600; width: 100%; border: none;
        box-shadow: 0 4px 12px rgba(0,74,153,0.2); transition: 0.2s;
    }
    .stButton>button:hover { transform: translateY(-1px); box-shadow: 0 6px 15px rgba(0,74,153,0.3); }
    
    .instrucao-passo {
        padding: 12px 16px; border-left: 4px solid #004a99; background: white;
        margin-bottom: 8px; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        font-size: 14px;
    }
    
    .horario-pills {
        display: inline-block; background-color: #f1f3f5; border-radius: 4px;
        padding: 2px 8px; margin: 2px; font-size: 11px; border: 1px solid #dee2e6;
        color: #333; font-family: monospace;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. FUNÇÕES TÉCNICAS E DE DADOS
# ==========================================

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def decode_poly(p):
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
                if not byte >= 0x20: break
            change = ~(result >> 1) if (result & 1) else (result >> 1)
            if unit == 'lat': lat += change
            else: lng += change
        coords.append([lat/100000.0, lng/100000.0])
    return coords

@st.cache_data(show_spinner=False)
def carregar_dados_locais():
    paradas = []
    if os.path.exists("paradas.json"):
        with open("paradas.json", "r", encoding="utf-8") as f: paradas = json.load(f)
    
    horarios = {}
    if os.path.exists("horarios.json"):
        with open("horarios.json", "r", encoding="utf-8") as f: horarios = json.load(f)
        
    trajetos = {}
    if os.path.exists("trajetos.json.gz"):
        with gzip.open("trajetos.json.gz", "rt", encoding="utf-8") as f: trajetos = json.load(f)
        
    return paradas, horarios, trajetos

def buscar_lugares_google(query):
    if not query or len(query) < 3: return {}
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={CHAVE_GOOGLE}&language=pt-BR"
    try:
        res = requests.get(url).json()
        if res['status'] == 'OK':
            return {item['formatted_address']: item['geometry']['location'] for item in res['results']}
    except: pass
    return {}

@st.cache_resource(show_spinner=False)
def criar_sessao_sptrans():
    s = requests.Session()
    if TOKEN_SPTRANS:
        s.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
    return s

dados_paradas, dados_horarios, dados_trajetos = carregar_dados_locais()

# ==========================================
# 3. GESTÃO DE ESTADO (PERSISTÊNCIA)
# ==========================================
if 'rota_ativa' not in st.session_state: st.session_state['rota_ativa'] = None
if 'origem_sel' not in st.session_state: st.session_state['origem_sel'] = None
if 'destino_sel' not in st.session_state: st.session_state['destino_sel'] = None
if 'busca_o_res' not in st.session_state: st.session_state['busca_o_res'] = None
if 'busca_d_res' not in st.session_state: st.session_state['busca_d_res'] = None

# ==========================================
# 4. SIDEBAR E GPS
# ==========================================
with st.sidebar:
    st.markdown('<p style="font-size:24px; font-weight:800; color:white;">🚌 BusRadar Pro</p>', unsafe_allow_html=True)
    st.caption("v6.4 · Autocomplete Edition")
    st.divider()
    gps = streamlit_geolocation()
    lat_u, lon_u = (gps['latitude'], gps['longitude']) if gps and gps.get('latitude') else (None, None)
    if lat_u: st.success(f"🛰️ GPS Conectado")
    else: st.warning("📡 Aguardando sinal de satélite...")
    st.divider()
    st.info(f"Dados: {len(dados_paradas)} paradas e {len(dados_horarios)} linhas carregadas.")

aba_rota, aba_monitor, aba_ponto, aba_london = st.tabs([
    "🗺️ Planejador", "🚌 Monitor", "📍 Radar de Área", "🇬🇧 Londres"
])

# ==========================================
# ABA 1: PLANEJADOR (ESTILO GOOGLE + PERSISTÊNCIA)
# ==========================================
with aba_rota:
    st.subheader("Para onde vamos hoje?")
    
    col_a, col_b = st.columns(2)
    
    # --- BLOCO DA ORIGEM ---
    with col_a:
        st.markdown("**1. Ponto de Partida**")
        t_o = st.radio("Origem:", ["📍 Meu GPS", "🔍 Buscar Endereço"], horizontal=True, key="opt_o")
        
        if t_o == "📍 Meu GPS":
            if lat_u:
                st.session_state['origem_sel'] = {"nome": "Sua localização atual", "coord": f"{lat_u},{lon_u}"}
                st.success("📍 GPS selecionado!")
            else:
                st.warning("GPS não detectado.")
                
        elif t_o == "🔍 Buscar Endereço":
            q_o = st.text_input("Local de saída:", placeholder="Ex: Metrô Ana Rosa", key="in_o")
            if st.button("🔍 Buscar Origem", key="btn_o"):
                res = buscar_lugares_google(q_o)
                if res: st.session_state['busca_o_res'] = res
                else: st.error("Nenhum local encontrado ou verifique o Faturamento da API.")

            if st.session_state['busca_o_res']:
                opcoes = st.session_state['busca_o_res']
                sel_o = st.selectbox("Escolha o local correto:", list(opcoes.keys()), key="res_o")
                
                if st.button("✅ Confirmar Origem", key="conf_o"):
                    st.session_state['origem_sel'] = {"nome": sel_o, "coord": f"{opcoes[sel_o]['lat']},{opcoes[sel_o]['lng']}"}
                    st.session_state['busca_o_res'] = None 
                    st.rerun()

        if st.session_state['origem_sel'] and t_o == "🔍 Buscar Endereço":
            st.info(f"Origem: {st.session_state['origem_sel']['nome']}")
    
    # --- BLOCO DO DESTINO ---
    with col_b:
        st.markdown("**2. Destino**")
        q_d = st.text_input("Para onde vai:", placeholder="Ex: Aeroporto Congonhas", key="in_d")
        if st.button("🔍 Buscar Destino", key="btn_d"):
            res = buscar_lugares_google(q_d)
            if res: st.session_state['busca_d_res'] = res
            else: st.error("Nenhum local encontrado ou erro na API.")

        if st.session_state['busca_d_res']:
            opcoes_d = st.session_state['busca_d_res']
            sel_d = st.selectbox("Escolha o local correto:", list(opcoes_d.keys()), key="res_d")
            
            if st.button("✅ Confirmar Destino", key="conf_d"):
                st.session_state['destino_sel'] = {"nome": sel_d, "coord": f"{opcoes_d[sel_d]['lat']},{opcoes_d[sel_d]['lng']}"}
                st.session_state['busca_d_res'] = None
                st.rerun()

        if st.session_state['destino_sel']:
            st.info(f"Destino: {st.session_state['destino_sel']['nome']}")

    # --- BOTÃO DE TRAÇAR ROTA ---
    if st.session_state['origem_sel'] and st.session_state['destino_sel']:
        st.divider()
        if st.button("🚀 TRAÇAR ROTA AGORA", type="primary"):
            with st.spinner("Consultando Google Maps..."):
                o, d = st.session_state['origem_sel']['coord'], st.session_state['destino_sel']['coord']
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={o}&destination={d}&mode=transit&language=pt-BR&key={CHAVE_GOOGLE}"
                resp = requests.get(url).json()
                if resp['status'] == 'OK': 
                    st.session_state['rota_ativa'] = resp['routes'][0]
                else: 
                    st.error(f"Erro do Google: {resp['status']}. Verifique a API.")

    # --- EXIBIÇÃO INDEPENDENTE DO MAPA ---
    if st.session_state.get('rota_ativa'):
        st.divider()
        r = st.session_state['rota_ativa']
        leg = r['legs'][0]
        st.success(f"⏱️ Tempo: **{leg['duration']['text']}** | 🏁 Chegada: **{leg.get('arrival_time', {}).get('text', 'N/D')}**")
        
        c1, c2 = st.columns([4, 6])
        with c1:
            for s in leg['steps']:
                txt = s['html_instructions'].replace('<b>', '**').replace('</b>', '**')
                st.markdown(f'<div class="instrucao-passo">{txt}</div>', unsafe_allow_html=True)
            if st.button("🗑️ Nova Busca"):
                st.session_state['rota_ativa'] = None
                st.session_state['origem_sel'] = None
                st.session_state['destino_sel'] = None
                st.rerun()
        with c2:
            pts = decode_poly(r['overview_polyline']['points'])
            m = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB Positron')
            folium.PolyLine(pts, color="#004a99", weight=6, opacity=0.8).add_to(m)
            folium.Marker(pts[0], icon=folium.Icon(color='green', icon='play')).add_to(m)
            folium.Marker(pts[-1], icon=folium.Icon(color='red', icon='flag')).add_to(m)
            st_folium(m, width=700, height=500, key="mapa_planejador_v64")

# ==========================================
# ABA 2: MONITOR DE FROTA + QUADRO DE HORÁRIOS
# ==========================================
with aba_monitor:
    st.subheader("🚌 Radar da Linha em Tempo Real")
    lin_id = st.text_input("🔍 Número da Linha (ex: 675A):", key="mon_in")
    
    if lin_id and TOKEN_SPTRANS:
        sessao = criar_sessao_sptrans()
        res_l = sessao.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            l_sel = opcoes[st.selectbox("Escolha o sentido:", list(opcoes.keys()))]
            
            # --- QUADRO DE HORÁRIOS ---
            chave_h = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl'] - 1}"
            if chave_h in dados_horarios:
                with st.expander("📅 Horários Programados (Saídas do Terminal)"):
                    prog = dados_horarios[chave_h]
                    cu, cs, cd = st.columns(3)
                    for col, dia, tit in zip([cu, cs, cd], ["Útil", "Sábado", "Domingo"], ["📅 Úteis", "🌅 Sábados", "⛪ Domingos"]):
                        with col:
                            st.markdown(f"**{tit}**")
                            h_l = prog.get(dia, [])
                            if h_l: st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in h_l]), unsafe_allow_html=True)
                            else: st.caption("Sem dados")

            # --- POSIÇÃO DA FROTA ---
            pos = sessao.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = pos.get('vs', [])
            if vs:
                st.metric("🚌 Frota Monitorada", len(vs), delta=f"{sum(1 for v in vs if v.get('a'))} acessíveis")
                m_f = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13, tiles='CartoDB Positron')
                
                ch_traj = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl']}"
                if ch_traj in dados_trajetos:
                    folium.PolyLine(dados_trajetos[ch_traj], color="#00A1FF", weight=4, opacity=0.5).add_to(m_f)
                
                for v in vs:
                    folium.Marker([v['py'], v['px']], icon=folium.Icon(color='blue' if v.get('a') else 'red', icon='bus', prefix='fa')).add_to(m_f)
                st_folium(m_f, width=1000, height=450, key="mapa_frota_v64")
        else: st.error("Linha não encontrada.")

# ==========================================
# ABA 3: RADAR DE ÁREA (AUTO-REFRESH)
# ==========================================
with aba_ponto:
    st.subheader("📍 O que está chegando perto de você?")
    if st.checkbox("🔄 Atualizar radar automaticamente (30s)", value=True):
        st_autorefresh(interval=30000, key="refresh_radar")

    if lat_u and dados_paradas:
        sessao = criar_sessao_sptrans()
        pontos = []
        for p in dados_paradas:
            dist = calcular_distancia_haversine(lat_u, lon_u, float(p.get('py', 0)), float(p.get('px', 0)))
            if dist <= 400: pontos.append({'cp': p['cp'], 'np': p['np'], 'dist': int(dist)})
        
        pontos = sorted(pontos, key=lambda x: x['dist'])[:5]
        for p in pontos:
            with st.expander(f"🚏 {p['np']} ({p['dist']}m)"):
                prev = sessao.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={p['cp']}").json()
                if prev and prev.get('p') and 'l' in prev['p']:
                    for lin in prev['p']['l']:
                        st.write(f"🚌 **{lin['c']}** ➔ {lin['vs'][0]['t']} (Prefixo: {lin['vs'][0]['p']})")
                else: st.caption("Nenhuma previsão agora.")
    else: st.warning("Ative o GPS para ver paradas próximas.")

# ==========================================
# ABA 4: LONDRES (TfL REAL-TIME)
# ==========================================
with aba_london:
    st.title("🇬🇧 London Marathon Prep")
    l_tfl = st.text_input("Número da Linha em Londres:", placeholder="Ex: 15, 390, 11")
    if l_tfl:
        with st.spinner("Consultando TfL API..."):
            res_tfl = requests.get(f"https://api.tfl.gov.uk/line/{l_tfl}/arrivals").json()
            if isinstance(res_tfl, list) and res_tfl:
                df = pd.DataFrame([{
                    "Destino": a['destinationName'], 
                    "Minutos": a['timeToStation'] // 60,
                    "Localização": a['stationName']
                } for a in res_tfl]).sort_values("Minutos")
                st.table(df)
            else: st.warning("Linha não encontrada em Londres.")