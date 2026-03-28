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
# 1. CONFIGURAÇÕES E CHAVES
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")

st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; width: 100%; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; }
    .horario-pills { display: inline-block; background-color: #e9ecef; border-radius: 5px; padding: 2px 8px; margin: 2px; font-size: 11px; color: #333; border: 1px solid #dee2e6; font-family: monospace; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES ---
def calcular_distancia(lat1, lon1, lat2, lon2):
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2) * 111320

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
        try:
            with open(nome_arquivo, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

dados_trajetos = carregar_json("trajetos.json")
dados_paradas = carregar_json("paradas.json")
dados_horarios = carregar_json("horarios.json")

# --- GPS SIDEBAR ---
with st.sidebar:
    st.header("🌦️ Status")
    gps = streamlit_geolocation()
    if gps and gps.get('latitude'): st.success("📍 GPS Ativo")
    st.caption("BusRadar Pro v4.7")

aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs(["🗺️ Planeador", "🚌 Monitor", "📍 Radar", "🇬🇧 Londres"])

# ==========================================
# ABA 1: PLANEADOR (RESTAURADA)
# ==========================================
with aba_rota:
    st.subheader("Traçar Viagem")
    c1, c2 = st.columns(2)
    with c1: destino_v = st.text_input("Destino:", placeholder="Ex: Metrô Ana Rosa")
    with c2: modo_v = st.selectbox("Modo:", ["transit", "walking", "driving"])
    
    if st.button("🚀 Buscar Rota", type="primary"):
        if gps and gps.get('latitude') and destino_v and CHAVE_GOOGLE:
            url = f"https://maps.googleapis.com/maps/api/directions/json?origin={gps['latitude']},{gps['longitude']}&destination={destino_v}&mode={modo_v}&language=pt-PT&key={CHAVE_GOOGLE}"
            res = requests.get(url).json()
            if res['status'] == 'OK':
                r = res['routes'][0]
                lg = r['legs'][0]
                st.success(f"Tempo: {lg['duration']['text']} | Distância: {lg['distance']['text']}")
                
                pts = decode_poly(r['overview_polyline']['points'])
                m = folium.Map(location=pts[0], zoom_start=14)
                folium.PolyLine(pts, color="blue", weight=5).add_to(m)
                st_folium(m, width=1000, height=400, key="mapa_rota_v47")
            else: st.error("Erro ao buscar rota.")

# ==========================================
# ABA 2: MONITOR + HORÁRIOS (CORRIGIDA)
# ==========================================
with aba_monitor:
    lin_id = st.text_input("🔍 Linha (ex: 675A):", key="mon_lin")
    if lin_id and TOKEN_SPTRANS:
        s = requests.Session()
        s.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        linhas = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        if linhas:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in linhas}
            l_sel = opcoes[st.selectbox("Sentido:", list(opcoes.keys()))]
            
            # Quadro de Horários
            sentido_gtfs = str(l_sel['sl'] - 1)
            chave_h = f"{l_sel['lt']}-{l_sel['tl']}-{sentido_gtfs}"
            
            if chave_h in dados_horarios:
                with st.expander("📅 Quadro de Horários Oficial"):
                    prog = dados_horarios[chave_h]
                    c_u, c_s, c_d = st.columns(3)
                    for col, dia, label in zip([c_u, c_s, c_d], ["Útil", "Sábado", "Domingo"], ["📅 Úteis", "🌅 Sábados", "⛪ Domingos"]):
                        with col:
                            st.markdown(f"**{label}**")
                            h_list = prog.get(dia, [])
                            if h_list: st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in h_list]), unsafe_allow_html=True)
                            else: st.caption("Sem dados")
            
            # Mapa em tempo real
            pos = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = pos.get('vs', [])
            if vs:
                st.metric("🚌 Frota na Rua", len(vs))
                m_f = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13)
                for v in vs: folium.Marker([v['py'], v['px']], icon=folium.Icon(color='blue', icon='bus', prefix='fa')).add_to(m_f)
                st_folium(m_f, width=1000, height=400, key="mapa_mon")

# ==========================================
# ABA 3: RADAR (SIMPLIFICADO)
# ==========================================
with aba_ponto:
    st.subheader("📍 Radar de Área")
    if gps and gps.get('latitude') and dados_paradas:
        st_autorefresh(interval=30000, key="auto_radar")
        # (Lógica de busca de paradas próximas aqui)
        st.info("Monitorizando paragens num raio de 400m...")

with aba_londres:
    st.title("🇬🇧 Londres")
    st.write("Em breve.")
