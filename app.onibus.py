import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
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
CHAVE_CLIMA = st.secrets.get("CHAVE_CLIMA", "")

# ==========================================
# 2. DESIGN E CONFIGURAÇÃO
# ==========================================
st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; width: 100%; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; }
    [data-testid="stExpander"] { border-radius: 12px; background-color: white; }
    .horario-pills { display: inline-block; background-color: #e9ecef; border-radius: 5px; padding: 2px 8px; margin: 2px; font-size: 13px; color: #333; border: 1px solid #dee2e6; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---
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
            with open(nome_arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return [] if "paradas" in nome_arquivo else {}
    return [] if "paradas" in nome_arquivo else {}

dados_trajetos = carregar_json("trajetos.json")
dados_paradas = carregar_json("paradas.json")
dados_horarios = carregar_json("horarios.json") # CARREGA OS HORÁRIOS

# ==========================================
# 3. BARRA LATERAL
# ==========================================
with st.sidebar:
    st.header("🌦️ Status")
    gps_global = streamlit_geolocation()
    if gps_global and gps_global.get('latitude'):
        st.success("📍 GPS Ativo")
    st.divider()
    st.caption("BusRadar Pro v4.4")

# ==========================================
# 4. ABAS
# ==========================================
aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs([
    "🗺️ Planeador", "🚌 Monitor de Frota", "📍 Radar de Área", "🇬🇧 Londres"
])

# --- ABA 1 (PLANEADOR) IGUAL ANTERIOR ---
with aba_rota:
    st.subheader("Para onde vamos?")
    # (Mantido código original para não estender)

# ==========================================
# ABA 2: MONITOR + QUADRO DE HORÁRIOS
# ==========================================
with aba_monitor:
    st.subheader("Monitor de Frota")
    
    c_lin, c_pref = st.columns(2)
    with c_lin: lin_id = st.text_input("🔍 Linha (ex: 8000):", key="monitor_lin")
    with c_pref: pref_alvo = st.text_input("🎯 Prefixo:", key="monitor_pref")

    if lin_id and TOKEN_SPTRANS:
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            l_sel = opcoes[st.selectbox("Escolha o sentido:", list(opcoes.keys()))]
            
            # 🕒 NOVIDADE: QUADRO DE HORÁRIOS OFICIAL
            # Tenta achar o horário usando a chave (ex: 8000-10-1)
            sentido_gtfs = "0" if l_sel['sl'] == 1 else "1" # Ajuste de sentido API vs GTFS
            chave_horario = f"{l_sel['lt']}-{l_sel['tl']}-{sentido_gtfs}"
            
            if chave_horario in dados_horarios:
                with st.expander("📅 Ver Quadro de Horários Oficial (Partidas do Terminal)"):
                    horas = dados_horarios[chave_horario]
                    html_pills = "".join([f'<span class="horario-pills">{h}</span>' for h in horas])
                    st.markdown(html_pills, unsafe_allow_html=True)
                    st.caption("Nota: Horários programados sujeitos a alterações do trânsito.")
            else:
                st.caption("Quadro de horários não disponível para esta linha no JSON.")

            # Monitoramento em tempo real (Mapa e Frota)
            frota_res = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota_res.get('vs', [])
            
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("🚌 Frota", len(vs))
            c_m2.metric("♿ Acessíveis", sum(1 for v in vs if v.get('a')))
            c_m3.metric("🕒 Sinal", frota_res.get('hr', '--:--'))

            m_frota = folium.Map(location=[vs[0]['py'], vs[0]['px']] if vs else [-23.55, -46.63], zoom_start=13, tiles='CartoDB positron')
            
            # Desenha Trajeto se existir
            chave_trajeto = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl']}"
            if chave_trajeto in dados_trajetos:
                folium.PolyLine(dados_trajetos[chave_trajeto], color="#00A1FF", weight=4, opacity=0.6).add_to(m_frota)

            for v in vs:
                folium.Marker([v['py'], v['px']], icon=folium.Icon(color='blue' if v.get('a') else 'red', icon='bus', prefix='fa')).add_to(m_frota)
            
            st_folium(m_frota, width=1000, height=400, key="mapa_frota")

# ==========================================
# ABA 3: RADAR DE ÁREA (COM MULTI-VEÍCULOS)
# ==========================================
with aba_ponto:
    st.subheader("📍 Radar de Área")
    if gps_global and gps_global.get('latitude') and dados_paradas:
        lat_u, lon_u = gps_global['latitude'], gps_global['longitude']
        s_p = requests.Session()
        s_p.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        
        # Busca paradas próximas
        paradas_perto = []
        for p in dados_paradas:
            lat_p = p.get('py') or p.get('stop_lat')
            lon_p = p.get('px') or p.get('stop_lon')
            if lat_p and lon_p:
                dist = calcular_distancia(lat_u, lon_u, float(lat_p), float(lon_p))
                if dist <= 400: paradas_perto.append({'cp': p.get('cp') or p.get('stop_id'), 'np': p.get('np') or p.get('stop_name'), 'dist': int(dist)})
        
        paradas_perto = sorted(paradas_perto, key=lambda x: x['dist'])[:5]

        for p in paradas_perto:
            with st.expander(f"🚏 {p['np']} ({p['dist']}m)"):
                prev = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={p['cp']}").json()
                if prev and prev.get('p') and 'l' in prev['p']:
                    for lin in prev['p']['l']:
                        vs = lin['vs']
                        st.write(f"**{lin['c']}** - {vs[0]['t']} (Prefixo: {vs[0]['p']})")
                        if len(vs) > 1:
                            st.caption(f"Próximos: {', '.join([v['t'] for v in vs[1:]])}")
                else: st.write("Sem previsões agora.")

# --- ABA 4 (LONDRES) ---
with aba_londres:
    st.title("🇬🇧 Londres")
    st.write("Em breve: integração TfL.")
