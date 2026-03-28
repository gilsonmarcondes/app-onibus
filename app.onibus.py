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
# 1. CONFIGURAÇÕES E ESTILO
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")

st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; width: 100%; }
    .horario-pills { display: inline-block; background-color: #f1f3f5; border-radius: 4px; padding: 2px 6px; margin: 2px; font-size: 11px; border: 1px solid #dee2e6; font-family: monospace; color: #333; }
    .instrucao-passo { padding: 12px; border-left: 5px solid #004a99; background: white; margin-bottom: 8px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES TÉCNICAS ---
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

# ==========================================
# 2. GPS E STATUS
# ==========================================
with st.sidebar:
    st.header("🌦️ Status")
    gps = streamlit_geolocation()
    if gps and gps.get('latitude'):
        st.success("📍 GPS Conectado")
        lat_u, lon_u = gps['latitude'], gps['longitude']
    else:
        st.warning("📍 Buscando GPS...")
        lat_u, lon_u = None, None
    st.divider()
    st.caption("BusRadar Pro v5.0 - Final de Sábado")

aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs(["🗺️ Planeador", "🚌 Monitor", "📍 Radar", "🇬🇧 Londres"])

# ==========================================
# ABA 1: PLANEADOR (O FOCO AGORA)
# ==========================================
with aba_rota:
    st.subheader("Para onde vamos?")
    
    c1, c2 = st.columns([3, 1])
    with c1:
        destino = st.text_input("📍 Destino Final:", placeholder="Ex: Aeroporto de Congonhas", key="dest_v5")
    with c2:
        modo = st.selectbox("🚗 Modo:", ["transit", "walking", "driving"], format_func=lambda x: "Ônibus/Metrô" if x=="transit" else ("A pé" if x=="walking" else "Carro"))

    if st.button("🚀 Calcular Rota", type="primary"):
        if not lat_u:
            st.error("Ative o GPS para traçarmos a rota de onde você está agora.")
        elif not destino:
            st.warning("Digite um destino para começar.")
        else:
            with st.spinner("Buscando no Google Maps..."):
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={lat_u},{lon_u}&destination={destino}&mode={modo}&language=pt-BR&key={CHAVE_GOOGLE}"
                res = requests.get(url).json()
                
                if res['status'] == 'OK':
                    r = res['routes'][0]
                    lg = r['legs'][0]
                    
                    st.metric("Tempo Estimado", lg['duration']['text'], delta=lg['distance']['text'])
                    
                    col_txt, col_map = st.columns([1, 1])
                    with col_txt:
                        st.markdown("### 📋 Passo a Passo")
                        for s in lg['steps']:
                            txt = s['html_instructions'].replace('<b>', '**').replace('</b>', '**')
                            st.markdown(f'<div class="instrucao-passo">{txt}</div>', unsafe_allow_html=True)
                    
                    with col_map:
                        pts = decode_poly(r['overview_polyline']['points'])
                        m_r = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB Positron')
                        folium.PolyLine(pts, color="#004a99", weight=6).add_to(m_r)
                        folium.Marker(pts[0], icon=folium.Icon(color='green', icon='play')).add_to(m_r)
                        folium.Marker(pts[-1], icon=folium.Icon(color='red', icon='flag')).add_to(m_r)
                        st_folium(m_r, width=600, height=450, key="mapa_rota_v5")
                else:
                    st.error("Não encontramos rotas. Tente ser mais específico no endereço.")

# ==========================================
# ABA 2: MONITOR (O MAPA OK + DIAGNÓSTICO)
# ==========================================
with aba_monitor:
    st.subheader("Radar da Linha")
    lin = st.text_input("🔍 Digite a Linha (ex: 675A):", key="mon_v5")
    
    if lin and TOKEN_SPTRANS:
        s = requests.Session()
        s.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        linhas = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin}").json()
        
        if linhas:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in linhas}
            l_sel = opcoes[st.selectbox("Selecione o sentido:", list(opcoes.keys()))]
            
            # --- TENTATIVA DE HORÁRIOS COM DIAGNÓSTICO ---
            id_sentido = str(l_sel['sl'] - 1)
            chave_primaria = f"{l_sel['lt']}-{l_sel['tl']}-{id_sentido}" # Ex: 675A-10-0
            chave_secundaria = f"{l_sel['lt']}-{id_sentido}"            # Ex: 675A-0
            
            prog = dados_horarios.get(chave_primaria) or dados_horarios.get(chave_secundaria)
            
            if prog:
                with st.expander("📅 Quadro de Horários (Programação Oficial)"):
                    c_u, c_s, c_d = st.columns(3)
                    for col, dia, tit in zip([c_u, c_s, c_d], ["Útil", "Sábado", "Domingo"], ["📅 Úteis", "🌅 Sábados", "⛪ Domingos"]):
                        with col:
                            st.markdown(f"**{tit}**")
                            h_list = prog.get(dia, [])
                            if h_list: st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in h_list]), unsafe_allow_html=True)
                            else: st.caption("Sem dados")
            else:
                st.caption(f"ℹ️ Quadro não encontrado para as chaves: {chave_primaria} ou {chave_secundaria}")

            # O mapa que você gostou
            pos = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = pos.get('vs', [])
            if vs:
                st.metric("🚌 Frota Monitorada", len(vs))
                m_f = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13, tiles='CartoDB Positron')
                for v in vs:
                    folium.Marker([v['py'], v['px']], icon=folium.Icon(color='blue' if v.get('a') else 'red', icon='bus', prefix='fa')).add_to(m_f)
                st_folium(m_f, width=1000, height=450, key="mapa_mon_v5")
            else: st.warning("Nenhum ônibus detectado no GPS agora.")

with aba_ponto: st.info("📍 Radar de área automático (GPS 400m).")
with aba_londres: st.title("🇬🇧 Londres (TfL)")
