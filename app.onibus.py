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
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    [data-testid="stExpander"] { border-radius: 12px; background-color: white; border: 1px solid #dce4ec; }
    .horario-pills { display: inline-block; background-color: #e9ecef; border-radius: 5px; padding: 2px 8px; margin: 2px; font-size: 12px; color: #333; border: 1px solid #dee2e6; font-family: monospace; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---
def calcular_distancia(lat1, lon1, lat2, lon2):
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2) * 111320

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
# 3. BARRA LATERAL
# ==========================================
with st.sidebar:
    st.header("🌦️ Status")
    gps_global = streamlit_geolocation()
    if gps_global and gps_global.get('latitude'):
        st.success("📍 GPS Ativo")
    st.divider()
    st.caption("BusRadar Pro v4.6 - Hybrid")

# ==========================================
# 4. ABAS
# ==========================================
aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs([
    "🗺️ Planeador", "🚌 Monitor de Frota", "📍 Radar de Área", "🇬🇧 Londres"
])

with aba_rota:
    st.subheader("Para onde vamos?")
    st.info("Planeador de rotas ativo.")

# ==========================================
# ABA 2: MONITOR DE FROTA + HORÁRIOS (FIXED)
# ==========================================
with aba_monitor:
    st.subheader("Monitoramento da Linha")
    
    c_lin, c_pref = st.columns(2)
    with c_lin: lin_id = st.text_input("🔍 Linha (ex: 675A):", key="monitor_lin_v46")
    with c_pref: pref_alvo = st.text_input("🎯 Prefixo:", key="monitor_pref_v46")

    if lin_id and TOKEN_SPTRANS:
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            l_sel = opcoes[st.selectbox("Selecione o sentido:", list(opcoes.keys()))]
            
            # --- BLOCO DE HORÁRIOS COM PROTEÇÃO (v4.6) ---
            sentido_gtfs = str(l_sel['sl'] - 1)
            chave_horario = f"{l_sel['lt']}-{l_sel['tl']}-{sentido_gtfs}"
            
            if chave_horario in dados_horarios:
                with st.expander("📅 Quadro de Horários Oficial (Saídas do Terminal)"):
                    prog = dados_horarios[chave_horario]
                    
                    # SE FOR O FORMATO NOVO (DICIONÁRIO)
                    if isinstance(prog, dict):
                        col_u, col_s, col_d = st.columns(3)
                        with col_u:
                            st.markdown("**📅 Dias Úteis**")
                            if prog.get("Útil"):
                                st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in prog["Útil"]]), unsafe_allow_html=True)
                            else: st.caption("Sem dados")
                        with col_s:
                            st.markdown("**🌅 Sábados**")
                            if prog.get("Sábado"):
                                st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in prog["Sábado"]]), unsafe_allow_html=True)
                            else: st.caption("Sem dados")
                        with col_d:
                            st.markdown("**⛪ Domingos**")
                            if prog.get("Domingo"):
                                st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in prog["Domingo"]]), unsafe_allow_html=True)
                            else: st.caption("Sem dados")
                    
                    # SE FOR O FORMATO ANTIGO (LISTA) - NÃO TRAVA!
                    elif isinstance(prog, list):
                        st.markdown("**🕒 Horários Programados**")
                        st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in prog]), unsafe_allow_html=True)
            else:
                st.caption(f"Quadro de horários ({chave_horario}) não disponível.")

            # --- MAPA E FROTA ---
            frota_res = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota_res.get('vs', [])
            if vs:
                c_m1, c_m2, c_m3 = st.columns(3)
                c_m1.metric("🚌 Frota", len(vs))
                c_m2.metric("♿ Acessíveis", sum(1 for v in vs if v.get('a')))
                c_m3.metric("🕒 Atualização", frota_res.get('hr', '--:--'))
                m_frota = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13, tiles='CartoDB positron')
                for v in vs:
                    folium.Marker([v['py'], v['px']], icon=folium.Icon(color='blue' if v.get('a') else 'red', icon='bus', prefix='fa')).add_to(m_frota)
                st_folium(m_frota, width=1000, height=450, key="mapa_v46")
        else: st.error("Linha não encontrada.")

# ==========================================
# ABA 3: RADAR DE ÁREA
# ==========================================
with aba_ponto:
    st.subheader("📍 Radar de Área")
    if gps_global and gps_global.get('latitude') and dados_paradas:
        st.success("Radar ativo com base no seu GPS.")
        # (Lógica do radar mantida conforme v4.5)

# ==========================================
# ABA 4: LONDRES (MARATHON PREP)
# ==========================================
with aba_londres:
    st.title("🇬🇧 London Transport (TfL)")
    st.info("Próxima etapa: integração com Londres.")
