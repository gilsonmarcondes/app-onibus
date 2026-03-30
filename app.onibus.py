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
# 1. CONFIGURAÇÕES E ESTILO (V6.1)
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")

st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

# Estilos CSS (Mantendo seu visual premium v6.0)
st.markdown("""
    <style>
    .main { background-color: #f0f4f8; }
    .stButton>button { border-radius: 10px; background: linear-gradient(135deg, #004a99, #0066cc); color: white; font-weight: 600; }
    .instrucao-passo { padding: 12px 16px; border-left: 4px solid #004a99; background: white; margin-bottom: 8px; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); font-size: 14px; }
    .horario-pills { display: inline-block; background-color: #f1f3f5; border-radius: 4px; padding: 2px 6px; margin: 2px; font-size: 11px; border: 1px solid #dee2e6; color: #333; font-family: monospace; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES ---
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
def carregar_json(nome_arquivo):
    if os.path.exists(nome_arquivo):
        with open(nome_arquivo, "r", encoding="utf-8") as f: return json.load(f)
    return {}

dados_paradas = carregar_json("paradas.json")
dados_horarios = carregar_json("horarios.json")
# Carregamento do trajeto comprimido
if os.path.exists("trajetos.json.gz"):
    with gzip.open("trajetos.json.gz", "rt", encoding="utf-8") as f: dados_trajetos = json.load(f)
else: dados_trajetos = {}

# ==========================================
# 2. INICIALIZAÇÃO DE MEMÓRIA (SESSION STATE)
# ==========================================
if 'rota_fixa' not in st.session_state: st.session_state['rota_fixa'] = None

# ==========================================
# 3. SIDEBAR — GPS
# ==========================================
with st.sidebar:
    st.markdown('<p style="font-size:22px; font-weight:800; color:white;">🚌 BusRadar Pro</p>', unsafe_allow_html=True)
    gps = streamlit_geolocation()
    lat_u, lon_u = (gps['latitude'], gps['longitude']) if gps and gps.get('latitude') else (None, None)
    if lat_u: st.success(f"📍 GPS Ativo")
    else: st.warning("🛰️ Aguardando sinal...")

aba_rota, aba_monitor, aba_ponto, aba_london = st.tabs(["🗺️ Planejador", "🚌 Monitor", "📍 Radar", "🇬🇧 Londres"])

# ==========================================
# ABA 1: PLANEJADOR (COM PERSISTÊNCIA)
# ==========================================
with aba_rota:
    col_in, col_opt = st.columns([2, 1])
    
    with col_in:
        t_orig = st.radio("Origem:", ["📍 GPS", "⌨️ Manual"], horizontal=True)
        origem = f"{lat_u},{lon_u}" if t_orig == "📍 GPS" and lat_u else st.text_input("De:", placeholder="Endereço de saída")
        destino = st.text_input("Para:", placeholder="Destino final")
    
    with col_opt:
        modo = st.selectbox("Modal:", ["transit", "walking", "driving"])
        quando = st.selectbox("Horário:", ["Sair Agora", "Chegar às..."])
        ts_param = "&departure_time=now"
        if quando == "Chegar às...":
            h_c = st.time_input("Hora:", value=datetime.now().time())
            dt_c = datetime.combine(datetime.today(), h_c)
            ts_param = f"&arrival_time={int(time_lib.mktime(dt_c.timetuple()))}"

    if st.button("🔍 Calcular Rota", type="primary"):
        if origem and destino and CHAVE_GOOGLE:
            with st.spinner("Traçando caminho..."):
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origem}&destination={destino}&mode={modo}&language=pt-BR{ts_param}&key={CHAVE_GOOGLE}"
                res = requests.get(url).json()
                if res['status'] == 'OK':
                    st.session_state['rota_fixa'] = res['routes'][0]
                else: st.error("Rota não encontrada.")

    # EXIBIÇÃO PERSISTENTE (Não some no refresh)
    if st.session_state['rota_fixa']:
        r = st.session_state['rota_fixa']
        lg = r['legs'][0]
        st.success(f"⏱️ {lg['duration']['text']} | 🏁 Chegada: {lg.get('arrival_time', {}).get('text', 'N/D')}")
        
        c_inst, c_map = st.columns([1, 1])
        with c_inst:
            for s in lg['steps']:
                txt = s['html_instructions'].replace('<b>', '**').replace('</b>', '**')
                st.markdown(f'<div class="instrucao-passo">{txt}</div>', unsafe_allow_html=True)
            if st.button("🗑️ Limpar Rota"):
                st.session_state['rota_fixa'] = None
                st.rerun()
        with c_map:
            pts = decode_poly(r['overview_polyline']['points'])
            m = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB Positron')
            folium.PolyLine(pts, color="#004a99", weight=6).add_to(m)
            st_folium(m, width=500, height=400, key="mapa_fixo")

# ==========================================
# ABA 2: MONITOR + QUADRO DE HORÁRIOS
# ==========================================
with aba_monitor:
    lin_id = st.text_input("🔍 Linha (ex: 675A):", key="mon_lin_v61")
    if lin_id and TOKEN_SPTRANS:
        s = requests.Session()
        s.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            l_sel = opcoes[st.selectbox("Sentido:", list(opcoes.keys()))]
            
            # --- QUADRO DE HORÁRIOS (Ajuste de Chave) ---
            chave_h = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl'] - 1}"
            if chave_h in dados_horarios:
                with st.expander("📅 Programação Oficial"):
                    prog = dados_horarios[chave_h]
                    cols = st.columns(3)
                    for col, dia, tit in zip(cols, ["Útil", "Sábado", "Domingo"], ["📅 Úteis", "🌅 Sábados", "⛪ Domingos"]):
                        with col:
                            st.markdown(f"**{tit}**")
                            h_list = prog.get(dia, [])
                            if h_list: st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in h_list]), unsafe_allow_html=True)
                            else: st.caption("Sem dados")

            # Mapa Tempo Real
            pos = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = pos.get('vs', [])
            if vs:
                m_f = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13, tiles='CartoDB Positron')
                for v in vs: folium.Marker([v['py'], v['px']], icon=folium.Icon(color='blue' if v.get('a') else 'red', icon='bus', prefix='fa')).add_to(m_f)
                st_folium(m_f, width=1000, height=400, key="mapa_frota_v61")