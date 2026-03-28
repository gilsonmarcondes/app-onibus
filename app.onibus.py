import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime, time
import math
import json
import os
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
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; width: 100%; transition: 0.3s; }
    .stButton>button:hover { background-color: #003366; border: 1px solid #fff; }
    .horario-pills { display: inline-block; background-color: #f1f3f5; border-radius: 4px; padding: 2px 6px; margin: 2px; font-size: 11px; border: 1px solid #dee2e6; color: #333; font-family: monospace; }
    .instrucao-passo { padding: 12px; border-left: 5px solid #28a745; background: white; margin-bottom: 8px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); font-size: 14px; }
    .metric-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES TÉCNICAS (NÃO MEXER) ---
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

# ==========================================
# 2. GPS E BARRA LATERAL
# ==========================================
with st.sidebar:
    st.header("🌦️ Status do GPS")
    gps = streamlit_geolocation()
    if gps and gps.get('latitude'):
        st.success("📍 GPS Conectado")
        lat_u, lon_u = gps['latitude'], gps['longitude']
    else:
        st.warning("📍 Aguardando sinal GPS...")
        lat_u, lon_u = None, None
    st.divider()
    st.caption("BusRadar Pro v5.5 - Engine Completa")

aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs([
    "🗺️ Planeador", "🚌 Monitor de Frota", "📍 Radar de Área", "🇬🇧 Londres"
])

# ==========================================
# ABA 1: PLANEADOR (VERSÃO GOOGLE FULL)
# ==========================================
with aba_rota:
    st.subheader("Para onde vamos?")
    
    c_orig, c_dest = st.columns(2)
    with c_orig:
        tipo_origem = st.radio("Origem:", ["📍 Usar meu GPS", "⌨️ Digitar Endereço"], horizontal=True, key="orig_type")
        if tipo_origem == "📍 Usar meu GPS":
            origem_final = f"{lat_u},{lon_u}" if lat_u else None
            st.text_input("Saindo de:", value="Minha localização atual", disabled=True)
        else:
            origem_final = st.text_input("Saindo de:", placeholder="Ex: Av. Paulista, 1000", key="orig_text")
            
    with c_dest:
        destino_final = st.text_input("Indo para:", placeholder="Ex: Estação da Luz", key="dest_text")

    # --- FILTROS AVANÇADOS DO GOOGLE ---
    with st.expander("⚙️ Preferências de Trajeto (Filtros Avançados)"):
        col_m, col_p, col_h = st.columns(3)
        with col_m:
            modo = st.selectbox("Transporte:", ["transit", "walking", "driving"], 
                               format_func=lambda x: "🚌 Ônibus/Metrô" if x=="transit" else ("🚶 A pé" if x=="walking" else "🚗 Carro"))
        with col_p:
            prioridade = st.selectbox("Prioridade:", ["best_guess", "fewer_transfers", "less_walking"], 
                                     format_func=lambda x: "⚡ Mais Rápido" if x=="best_guess" else ("🔄 Menos Trocas" if x=="fewer_transfers" else "🚶 Menos Caminhada"))
        with col_h:
            quando = st.radio("Quando:", ["Sair Agora", "Escolher Horário"], horizontal=True)
            ts = "now"
            if quando == "Escolher Horário":
                h_e = st.time_input("Horário de Saída:", value=datetime.now().time())
                dt = datetime.combine(datetime.today(), h_e)
                ts = int(time_lib.mktime(dt.timetuple()))

    if st.button("🚀 Calcular Melhor Rota", type="primary"):
        if not origem_final or "None" in str(origem_final):
            st.error("Erro: Origem não definida. Ative o GPS ou digite o endereço de partida.")
        elif not destino_final:
            st.warning("Por favor, digite o destino.")
        else:
            with st.spinner("Consultando rotas inteligentes..."):
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origem_final}&destination={destino_final}&mode={modo}&transit_routing_preference={prioridade}&departure_time={ts}&language=pt-BR&key={CHAVE_GOOGLE}"
                res = requests.get(url).json()
                
                if res['status'] == 'OK':
                    r = res['routes'][0]
                    lg = r['legs'][0]
                    
                    st.success(f"✅ Rota encontrada! Tempo: **{lg['duration']['text']}** | Distância: **{lg['distance']['text']}**")
                    
                    col_txt, col_map = st.columns([1, 1])
                    with col_txt:
                        st.markdown("### 📋 Instruções de Viagem")
                        for step in lg['steps']:
                            txt = step['html_instructions'].replace('<b>', '**').replace('</b>', '**').replace('<div style="font-size:0.9em">', ' (').replace('</div>', ')')
                            st.markdown(f'<div class="instrucao-passo">{txt}</div>', unsafe_allow_html=True)
                    
                    with col_map:
                        pts = decode_poly(r['overview_polyline']['points'])
                        m_r = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB Positron')
                        folium.PolyLine(pts, color="#004a99", weight=6, opacity=0.8).add_to(m_r)
                        folium.Marker(pts[0], tooltip="Início", icon=folium.Icon(color='green', icon='play')).add_to(m_r)
                        folium.Marker(pts[-1], tooltip="Fim", icon=folium.Icon(color='red', icon='flag')).add_to(m_r)
                        st_folium(m_r, width=600, height=500, key="mapa_planeador_full")
                else:
                    st.error(f"Erro ao traçar rota: {res.get('status')}. Verifique os nomes das ruas.")

# ==========================================
# ABA 2: MONITOR (MANTIDO O MAPA OK)
# ==========================================
with aba_monitor:
    st.subheader("Radar da Frota (Tempo Real)")
    lin_id = st.text_input("🔍 Digite a Linha (ex: 675A ou 8000):", key="mon_lin_full")
    
    if lin_id and TOKEN_SPTRANS:
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            l_sel = opcoes[st.selectbox("Selecione o sentido:", list(opcoes.keys()))]
            
            # Busca posição
            frota_res = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota_res.get('vs', [])
            
            if vs:
                m1, m2, m3 = st.columns(3)
                m1.metric("🚌 Frota na Rua", len(vs))
                m2.metric("♿ Acessíveis", sum(1 for v in vs if v.get('a')))
                m3.metric("🕒 Atualizado em", frota_res.get('hr'))
                
                # Mapa
                m_f = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13, tiles='CartoDB Positron')
                
                # Trajeto oficial (JSON)
                chave_t = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl']}"
                if chave_t in dados_trajetos:
                    folium.PolyLine(dados_trajetos[chave_t], color="#00A1FF", weight=4, opacity=0.5).add_to(m_f)
                
                for v in vs:
                    folium.Marker(
                        [v['py'], v['px']], 
                        popup=f"Prefixo: {v['p']}",
                        icon=folium.Icon(color='blue' if v.get('a') else 'red', icon='bus', prefix='fa')
                    ).add_to(m_f)
                st_folium(m_f, width=1000, height=450, key="mapa_mon_full")
            else:
                st.warning("Nenhum ônibus detectado para esta linha no momento.")

# ==========================================
# ABA 3: RADAR DE ÁREA (RESTAURADA)
# ==========================================
with aba_ponto:
    st.subheader("📍 Ônibus vindo para perto de você")
    if st.checkbox("🔄 Atualizar Painel Automaticamente (30s)", value=True):
        st_autorefresh(interval=30000, key="auto_radar_full")

    if lat_u and dados_paradas:
        s_p = requests.Session()
        s_p.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        
        # Encontrar pontos num raio de 400m
        paradas_perto = []
        for p in dados_paradas:
            lat_p = p.get('py') or p.get('stop_lat')
            lon_p = p.get('px') or p.get('stop_lon')
            id_p = p.get('cp') or p.get('stop_id')
            if lat_p and lon_p and id_p:
                dist = calcular_distancia(lat_u, lon_u, float(lat_p), float(lon_p))
                if dist <= 400:
                    paradas_perto.append({'cp': id_p, 'np': p.get('np') or p.get('stop_name'), 'dist': int(dist)})
        
        paradas_perto = sorted(paradas_perto, key=lambda x: x['dist'])[:5]
        
        if paradas_perto:
            for p in paradas_perto:
                with st.expander(f"🚏 {p['np']} ({p['dist']}m de distância)"):
                    prev = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={p['cp']}").json()
                    if prev and prev.get('p') and 'l' in prev['p']:
                        for lin in prev['p']['l']:
                            vs_prev = lin['vs']
                            st.write(f"🚌 **{lin['c']}** ➔ {vs_prev[0]['t']} (Prefixo: {vs_prev[0]['p']})")
                    else:
                        st.caption("Sem ônibus a caminho deste ponto agora.")
        else:
            st.info("Nenhuma parada de ônibus encontrada no raio de 400m do seu GPS.")
    else:
        st.warning("📍 Ative o GPS para ver os ônibus ao seu redor.")

# ==========================================
# ABA 4: LONDRES (O PRÓXIMO PASSO)
# ==========================================
with aba_londres:
    st.title("🇬🇧 London Transport (TfL)")
    st.write("Aba reservada para monitorar o seu trajeto na Maratona de Londres.")
