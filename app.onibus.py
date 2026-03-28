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
# 1. CONFIGURAÇÕES E CHAVES (COFRE SEGURO)
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")
CHAVE_CLIMA = st.secrets.get("CHAVE_CLIMA", "")

# ==========================================
# 2. DESIGN PREMIUM (CSS) E CONFIGURAÇÃO
# ==========================================
st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; width: 100%; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    [data-testid="stExpander"] { border-radius: 12px; background-color: white; border: 1px solid #dce4ec; }
    .horario-pills { display: inline-block; background-color: #e9ecef; border-radius: 5px; padding: 2px 8px; margin: 2px; font-size: 12px; color: #333; border: 1px solid #dee2e6; font-family: monospace; }
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
dados_horarios = carregar_json("horarios.json")

# ==========================================
# 3. BARRA LATERAL (GPS E CLIMA)
# ==========================================
with st.sidebar:
    st.header("🌦️ Status do Sistema")
    gps_global = streamlit_geolocation()
    
    if gps_global and gps_global.get('latitude'):
        st.success("📍 GPS Conectado")
        try:
            url_clima = f"https://api.open-meteo.com/v1/forecast?latitude={gps_global['latitude']}&longitude={gps_global['longitude']}&current_weather=true"
            clima = requests.get(url_clima).json()['current_weather']
            st.metric("Temperatura", f"{clima['temperature']}°C")
        except: st.caption("Clima indisponível.")
    else: st.warning("📍 Aguardando sinal GPS...")
    
    st.divider()
    st.caption("BusRadar Pro v4.5 - Edição UNESP")

# ==========================================
# 4. SISTEMA DE ABAS
# ==========================================
aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs([
    "🗺️ Planeador", "🚌 Monitor de Frota", "📍 Radar de Área", "🇬🇧 Londres"
])

# --- ABA 1 (PLANEADOR) ---
with aba_rota:
    st.subheader("Planeie a sua Rota")
    destino_v = st.text_input("Para onde deseja ir?", placeholder="Ex: Estação da Luz")
    if st.button("🚀 Buscar Rotas"):
        st.info("Funcionalidade de rotas integrada com Google Maps.")

# ==========================================
# ABA 2: MONITOR DE FROTA + HORÁRIOS
# ==========================================
with aba_monitor:
    st.subheader("Monitoramento da Linha")
    
    c_lin, c_pref = st.columns(2)
    with c_lin: lin_id = st.text_input("🔍 Linha (ex: 675A):", key="monitor_lin_v45")
    with c_pref: pref_alvo = st.text_input("🎯 Destacar Prefixo:", key="monitor_pref_v45")

    if lin_id and TOKEN_SPTRANS:
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            l_sel = opcoes[st.selectbox("Selecione o sentido:", list(opcoes.keys()))]
            
            # --- BLOCO DE HORÁRIOS (v4.5) ---
            sentido_gtfs = str(l_sel['sl'] - 1)
            chave_horario = f"{l_sel['lt']}-{l_sel['tl']}-{sentido_gtfs}"
            
            if chave_horario in dados_horarios:
                with st.expander("📅 Quadro de Horários Oficial (Saídas do Terminal)"):
                    prog = dados_horarios[chave_horario]
                    col_u, col_s, col_d = st.columns(3)
                    
                    with col_u:
                        st.markdown("**📅 Dias Úteis**")
                        if prog.get("Útil"):
                            html_pills = "".join([f'<span class="horario-pills">{h}</span>' for h in prog["Útil"]])
                            st.markdown(html_pills, unsafe_allow_html=True)
                        else: st.caption("Sem dados")
                    
                    with col_s:
                        st.markdown("**🌅 Sábados**")
                        if prog.get("Sábado"):
                            html_pills = "".join([f'<span class="horario-pills">{h}</span>' for h in prog["Sábado"]])
                            st.markdown(html_pills, unsafe_allow_html=True)
                        else: st.caption("Sem dados")
                        
                    with col_d:
                        st.markdown("**⛪ Domingos**")
                        if prog.get("Domingo"):
                            html_pills = "".join([f'<span class="horario-pills">{h}</span>' for h in prog["Domingo"]])
                            st.markdown(html_pills, unsafe_allow_html=True)
                        else: st.caption("Sem dados")
            else:
                st.caption(f"Quadro de horários ({chave_horario}) não disponível no JSON.")

            # --- MAPA E FROTA ---
            frota_res = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota_res.get('vs', [])
            
            st.divider()
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("🚌 Frota", len(vs))
            c_m2.metric("♿ Acessíveis", sum(1 for v in vs if v.get('a')))
            c_m3.metric("🕒 Atualização", frota_res.get('hr', '--:--'))

            m_frota = folium.Map(location=[vs[0]['py'], vs[0]['px']] if vs else [-23.55, -46.63], zoom_start=13, tiles='CartoDB positron')
            
            chave_trajeto = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl']}"
            if chave_trajeto in dados_trajetos:
                folium.PolyLine(dados_trajetos[chave_trajeto], color="#00A1FF", weight=5, opacity=0.7).add_to(m_frota)

            for v in vs:
                cor = 'orange' if pref_alvo and pref_alvo in str(v['p']) else ('blue' if v.get('a') else 'red')
                folium.Marker([v['py'], v['px']], popup=f"Prefixo: {v['p']}", icon=folium.Icon(color=cor, icon='bus', prefix='fa')).add_to(m_frota)
            
            st_folium(m_frota, width=1000, height=450, key="mapa_monitor_v45")
        else: st.error("Linha não encontrada.")

# ==========================================
# ABA 3: RADAR DE ÁREA (INTELIGENTE)
# ==========================================
with aba_ponto:
    st.subheader("📍 Radar de Área (A sua Volta)")
    
    if st.checkbox("🔄 Atualização Automática (30s)", value=True):
        st_autorefresh(interval=30000, key="refresh_radar_v45")

    if gps_global and gps_global.get('latitude') and isinstance(dados_paradas, list) and len(dados_paradas) > 0:
        lat_u, lon_u = gps_global['latitude'], gps_global['longitude']
        s_p = requests.Session()
        s_p.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        
        paradas_perto = []
        for p in dados_paradas:
            lat_p = p.get('py') or p.get('stop_lat')
            lon_p = p.get('px') or p.get('stop_lon')
            id_p = p.get('cp') or p.get('stop_id')
            if lat_p and lon_p and id_p:
                dist = calcular_distancia(lat_u, lon_u, float(lat_p), float(lon_p))
                if dist <= 400:
                    paradas_perto.append({'cp': str(id_p), 'np': p.get('np') or p.get('stop_name'), 'dist': int(dist)})
        
        paradas_perto = sorted(paradas_perto, key=lambda x: x['dist'])[:5]

        if paradas_perto:
            st.success(f"📡 Monitorizando {len(paradas_perto)} paragens próximas.")
            for p in paradas_perto:
                with st.expander(f"🚏 {p['np']} ({p['dist']}m)"):
                    prev = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={p['cp']}").json()
                    if prev and prev.get('p') and isinstance(prev['p'], dict) and 'l' in prev['p']:
                        for lin in prev['p']['l']:
                            vs = lin['vs']
                            st.write(f"**{lin['c']}** ➔ {vs[0]['t']} (Pref: {vs[0]['p']}) {'♿' if vs[0].get('a') else ''}")
                            if len(vs) > 1:
                                st.caption(f"Próximos: {', '.join([v['t'] for v in vs[1:]])}")
                    else: st.caption("Nenhuma previsão para esta paragem agora.")
        else: st.info("Nenhuma paragem encontrada num raio de 400m.")
    else: st.warning("Ative o GPS ou carregue o 'paradas.json' para usar o radar.")

# ==========================================
# ABA 4: LONDRES (MARATHON PREP)
# ==========================================
with aba_londres:
    st.title("🇬🇧 London Transport (TfL)")
    st.info("Próxima etapa: integração com os ônibus vermelhos e o Tube para a sua viagem!")
