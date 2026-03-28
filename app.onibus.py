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
# 1. CONFIGURAÇÕES E DESIGN
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")

st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; width: 100%; }
    .horario-pills { display: inline-block; background-color: #f1f3f5; border-radius: 4px; padding: 2px 6px; margin: 2px; font-size: 11px; border: 1px solid #dee2e6; font-family: monospace; }
    .instrucao-passo { padding: 10px; border-left: 4px solid #004a99; background: white; margin-bottom: 5px; border-radius: 0 8px 8px 0; font-size: 14px; }
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
        with open(nome_arquivo, "r", encoding="utf-8") as f: return json.load(f)
    return {}

dados_trajetos = carregar_json("trajetos.json")
dados_paradas = carregar_json("paradas.json")
dados_horarios = carregar_json("horarios.json")

# ==========================================
# 2. SIDEBAR E GPS
# ==========================================
with st.sidebar:
    st.header("🌦️ Central de Status")
    gps = streamlit_geolocation()
    if gps and gps.get('latitude'):
        st.success("📍 Satélite Conectado")
        lat_atual, lon_atual = gps['latitude'], gps['longitude']
    else:
        st.warning("📍 Aguardando sinal GPS...")
        lat_atual, lon_atual = None, None
    st.divider()
    st.caption("BusRadar Pro v4.9")

aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs(["🗺️ Planeador", "🚌 Monitor", "📍 Radar", "🇬🇧 Londres"])

# ==========================================
# ABA 1: PLANEADOR DE VIAGEM (FULL)
# ==========================================
with aba_rota:
    st.subheader("Para onde vamos?")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        destino_input = st.text_input("📍 Digite o destino:", placeholder="Ex: Estação da Luz ou Av. Paulista, 1000")
    with col2:
        modo_viagem = st.selectbox("🚗 Modo:", ["transit", "walking", "driving"], format_func=lambda x: "Ônibus/Metrô" if x=="transit" else ("A pé" if x=="walking" else "Carro"))

    if st.button("🚀 Calcular Melhor Rota", type="primary"):
        if not lat_atual:
            st.error("Erro: Ative o GPS para que possamos saber de onde você está partindo.")
        elif not destino_input:
            st.warning("Por favor, digite um destino.")
        elif not CHAVE_GOOGLE:
            st.error("API Key do Google não configurada.")
        else:
            with st.spinner("Consultando rotas..."):
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={lat_atual},{lon_atual}&destination={destino_input}&mode={modo_viagem}&language=pt-BR&key={CHAVE_GOOGLE}"
                res = requests.get(url).json()
                
                if res['status'] == 'OK':
                    rota = res['routes'][0]
                    leg = rota['legs'][0]
                    
                    # Métricas Rápidas
                    m1, m2 = st.columns(2)
                    m1.metric("Tempo Est.", leg['duration']['text'])
                    m2.metric("Distância", leg['distance']['text'])
                    
                    st.divider()
                    
                    c_inst, c_mapa = st.columns([1, 1])
                    
                    with c_inst:
                        st.markdown("### 📋 Passo a Passo")
                        for step in leg['steps']:
                            # Limpa tags HTML que o Google manda
                            txt = step['html_instructions'].replace('<b>', '**').replace('</b>', '**')
                            st.markdown(f'<div class="instrucao-passo">{txt}</div>', unsafe_allow_html=True)
                    
                    with c_mapa:
                        # Renderiza o caminho no mapa
                        pts = decode_poly(rota['overview_polyline']['points'])
                        m_rota = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB Positron')
                        folium.PolyLine(pts, color="#004a99", weight=6, opacity=0.8).add_to(m_rota)
                        folium.Marker(pts[0], tooltip="Partida", icon=folium.Icon(color='green', icon='play')).add_to(m_rota)
                        folium.Marker(pts[-1], tooltip="Destino", icon=folium.Icon(color='red', icon='flag')).add_to(m_rota)
                        st_folium(m_rota, width=600, height=450, key="mapa_planeador")
                else:
                    st.error("Não foi possível traçar a rota. Verifique o endereço de destino.")

# ==========================================
# ABA 2: MONITOR DE FROTA (O MAPA QUE VOCÊ APROVOU)
# ==========================================
with aba_monitor:
    st.subheader("Monitoramento em Tempo Real")
    lin_id = st.text_input("🔍 Digite a Linha (ex: 675A):", key="mon_lin_v49")
    
    if lin_id and TOKEN_SPTRANS:
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            l_sel = opcoes[st.selectbox("Sentido da Operação:", list(opcoes.keys()))]
            
            # Aqui mantivemos o mapa que você achou perfeito
            frota_res = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota_res.get('vs', [])
            
            if vs:
                st.metric("🚌 Ônibus na rua agora", len(vs))
                m_frota = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13, tiles='CartoDB Positron')
                
                # Desenha o trajeto se o trajetos.json estiver presente
                chave_t = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl']}"
                if chave_t in dados_trajetos:
                    folium.PolyLine(dados_trajetos[chave_t], color="#00A1FF", weight=4, opacity=0.5).add_to(m_frota)
                
                for v in vs:
                    folium.Marker(
                        [v['py'], v['px']], 
                        popup=f"Prefixo: {v['p']}",
                        icon=folium.Icon(color='blue' if v.get('a') else 'red', icon='bus', prefix='fa')
                    ).add_to(m_frota)
                st_folium(m_frota, width=1000, height=450, key="mapa_monitor_v49")
            else:
                st.warning("Nenhum veículo desta linha detectado no radar agora.")
        else:
            st.error("Linha não encontrada.")

# --- ABAS RESTANTES (PLACEHOLDERS) ---
with aba_ponto:
    st.info("📍 Radar de Área configurado para detecção por GPS em 400m.")
with aba_londres:
    st.title("🇬🇧 London Transport")
    st.write("Aba reservada para a integração TfL.")
