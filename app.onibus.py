import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime
import math
import json
import os
from streamlit_autorefresh import st_autorefresh
from streamlit_geolocation import streamlit_geolocation

# ==========================================
# 1. CONFIGURAÇÕES
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")

st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

# CSS para pílulas e layout
st.markdown("""
    <style>
    .stButton>button { border-radius: 8px; background-color: #004a99; color: white; font-weight: bold; width: 100%; }
    .horario-pills { display: inline-block; background-color: #f1f3f5; border-radius: 4px; padding: 2px 6px; margin: 2px; font-size: 11px; border: 1px solid #dee2e6; font-family: monospace; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---
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

@st.cache_data
def carregar_json(nome_arquivo):
    if os.path.exists(nome_arquivo):
        with open(nome_arquivo, "r", encoding="utf-8") as f: return json.load(f)
    return {}

dados_trajetos = carregar_json("trajetos.json")
dados_paradas = carregar_json("paradas.json")
dados_horarios = carregar_json("horarios.json")

# --- SIDEBAR ---
with st.sidebar:
    st.header("🌦️ Status")
    gps = streamlit_geolocation()
    if gps and gps.get('latitude'): st.success("📍 GPS Ativo")
    st.caption("BusRadar Pro v4.8")

aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs(["🗺️ Planeador", "🚌 Monitor", "📍 Radar", "🇬🇧 Londres"])

# ==========================================
# ABA 1: PLANEADOR (RESTAURADA)
# ==========================================
with aba_rota:
    st.subheader("Traçar Viagem")
    c1, c2 = st.columns(2)
    with c1: dest = st.text_input("Para onde?", placeholder="Ex: Parque Ibirapuera", key="dest_v48")
    with c2: modo = st.selectbox("Transporte:", ["transit", "walking", "driving"], key="modo_v48")
    
    if st.button("🚀 Ver Rota", key="btn_rota"):
        if gps and gps.get('latitude') and dest and CHAVE_GOOGLE:
            with st.spinner("Calculando..."):
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={gps['latitude']},{gps['longitude']}&destination={dest}&mode={modo}&language=pt-BR&key={CHAVE_GOOGLE}"
                res = requests.get(url).json()
                if res['status'] == 'OK':
                    r = res['routes'][0]
                    lg = r['legs'][0]
                    st.info(f"🏁 {lg['duration']['text']} ({lg['distance']['text']})")
                    pts = decode_poly(r['overview_polyline']['points'])
                    m = folium.Map(location=pts[0], zoom_start=14)
                    folium.PolyLine(pts, color="#004a99", weight=5).add_to(m)
                    st_folium(m, width=1000, height=400)
                else: st.error("Rota não encontrada.")

# ==========================================
# ABA 2: MONITOR + HORÁRIOS (CORRIGIDA)
# ==========================================
with aba_monitor:
    lin_id = st.text_input("🔍 Buscar Linha:", key="mon_lin_v48")
    if lin_id and TOKEN_SPTRANS:
        s = requests.Session()
        s.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        linhas = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        if linhas:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in linhas}
            l_sel = opcoes[st.selectbox("Sentido:", list(opcoes.keys()))]
            
            # --- LÓGICA DE HORÁRIOS CORRIGIDA ---
            # A chave agora usa o route_id (lt-tl) + direction_id (sl-1)
            chave_h = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl'] - 1}"
            
            if chave_h in dados_horarios:
                with st.expander("📅 Quadro de Horários Oficial"):
                    prog = dados_horarios[chave_h]
                    cols = st.columns(3)
                    for col, dia, tit in zip(cols, ["Útil", "Sábado", "Domingo"], ["📅 Úteis", "🌅 Sábados", "⛪ Domingos"]):
                        with col:
                            st.markdown(f"**{tit}**")
                            lista = prog.get(dia, [])
                            if lista: 
                                html = "".join([f'<span class="horario-pills">{h}</span>' for h in lista])
                                st.markdown(html, unsafe_allow_html=True)
                            else: st.caption("Sem dados")
            else:
                st.caption(f"Quadro não encontrado para chave: {chave_h}")

            # Mapa em tempo real
            pos = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = pos.get('vs', [])
            if vs:
                st.metric("🚌 Frota", len(vs))
                m_f = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13)
                for v in vs: folium.Marker([v['py'], v['px']], icon=folium.Icon(color='blue', icon='bus', prefix='fa')).add_to(m_f)
                st_folium(m_f, width=1000, height=400)
        else: st.error("Linha não encontrada.")

# ==========================================
# ABA 3: RADAR
# ==========================================
with aba_ponto:
    st.subheader("📍 Radar de Área")
    if gps and gps.get('latitude') and dados_paradas:
        st.info("Buscando paradas próximas (400m)...")

with aba_londres:
    st.title("🇬🇧 Londres")
    st.write("Pronto para a Maratona?")
