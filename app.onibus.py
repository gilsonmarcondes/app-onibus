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

CHAVE_TFL = st.secrets.get("CHAVE_TFL", "")
CHAVE_BODS = st.secrets.get("CHAVE_BODS", "")
CHAVE_SCOTLAND = st.secrets.get("CHAVE_SCOTLAND", "")
CHAVE_RAIL = st.secrets.get("CHAVE_RAIL", "")

# ==========================================
# 2. DESIGN PREMIUM (CSS) E CONFIGURAÇÃO
# ==========================================
st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; transition: 0.3s; width: 100%; }
    .stButton>button:hover { background-color: #003366; border: 1px solid #fff; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #eee; }
    [data-testid="stExpander"] { border: 1px solid #dce4ec; border-radius: 12px; background-color: white; margin-bottom: 10px; }
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

def calcular_distancia(lat1, lon1, lat2, lon2):
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2) * 111320

@st.cache_data
def carregar_json(nome_arquivo):
    if os.path.exists(nome_arquivo):
        try:
            with open(nome_arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.decoder.JSONDecodeError:
            return [] if nome_arquivo == "paradas.json" else {}
    return [] if nome_arquivo == "paradas.json" else {}

dados_trajetos = carregar_json("trajetos.json")
dados_paradas = carregar_json("paradas.json")

# ==========================================
# 3. BARRA LATERAL (GPS E CLIMA)
# ==========================================
with st.sidebar:
    st.header("🌦️ Central de Status")
    st.write("A sua Posição (GPS):")
    gps_global = streamlit_geolocation()
    
    if gps_global and gps_global.get('latitude'):
        lat, lon = gps_global['latitude'], gps_global['longitude']
        st.success("📍 Satélite Conectado")
        try:
            url_clima = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            clima = requests.get(url_clima).json()['current_weather']
            icones = {0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️", 45: "🌫️", 51: "🌧️", 61: "🌧️", 71: "❄️", 95: "⚡"}
            icone_atual = icones.get(clima['weathercode'], "🌡️")
            st.metric("Clima Local", f"{icone_atual} {clima['temperature']}°C")
        except:
            st.caption("🌤️ Clima indisponível no momento.")
    else:
        st.warning("📍 Ative o GPS para previsões locais.")
    
    st.divider()
    st.caption("BusRadar Pro v4.2 - Radar Flexível")

# ==========================================
# 4. SISTEMA DE ABAS
# ==========================================
aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs([
    "🗺️ Planeador", "🚌 Monitor de Frota", "📍 Radar de Área", "🇬🇧 Londres (Soon)"
])

# ==========================================
# ABA 1: PLANEADOR DE ROTAS
# ==========================================
with aba_rota:
    st.subheader("Traçar Nova Viagem")
    if 'resultado_busca' not in st.session_state: st.session_state['resultado_busca'] = None

    c1, c2 = st.columns(2)
    with c1:
        modo_v = st.radio("Modo de Viagem:", ["🚌 Transportes Públicos", "🚗 Carro", "🚶 A Pé"], horizontal=True)
        tipo_origem = st.radio("Origem:", ["🌍 Usar o meu GPS", "⌨️ Digitar Morada"], horizontal=True)
    with c2:
        criterio = st.selectbox("Prioridade:", ["⚡ Mais Rápida", "🔄 Menos Transbordos", "🚶 Menos Caminhada"])
        destino_v = st.text_input("Destino Final:", placeholder="Ex: Parque Ibirapuera")

    origem_final = None
    if tipo_origem == "🌍 Usar o meu GPS":
        if gps_global and gps_global.get('latitude'):
            origem_final = f"{gps_global['latitude']},{gps_global['longitude']}"
        else: st.warning("⚠️ Ative o GPS na barra lateral primeiro.")
    else:
        origem_final = st.text_input("Morada de partida:", placeholder="Ex: Av. Paulista, 1500")

    if st.button("🚀 Buscar Melhores Rotas", type="primary"):
        if origem_final and destino_v and CHAVE_GOOGLE:
            with st.spinner("A calcular rotas e tarifas..."):
                ts = int(datetime.now().timestamp())
                m_g = {"🚌 Transportes Públicos": "transit", "🚗 Carro": "driving", "🚶 A Pé": "walking"}[modo_v]
                url_rota = f"https://maps.googleapis.com/maps/api/directions/json?origin={origem_final}&destination={destino_v}&mode={m_g}&departure_time={ts}&alternatives=true&language=pt-PT&key={CHAVE_GOOGLE}"
                res = requests.get(url_rota).json()
                
                if res['status'] == 'OK': st.session_state['resultado_busca'] = res['routes']
                else: st.error("Rota não encontrada.")
        elif not CHAVE_GOOGLE:
            st.error("Chave do Google Maps não configurada.")
        else:
            st.warning("Preencha a origem e o destino.")

    if st.session_state['resultado_busca']:
        for i, r in enumerate(st.session_state['resultado_busca']):
            lg = r['legs'][0]
            custo = sum(4.40 for p in lg['steps'] if p['travel_mode'] == "TRANSIT")
            custo = min(custo, 7.65) if custo > 0 else 0
            txt_custo = f" | 💰 Est. R$ {custo:.2f}" if custo > 0 else " | 🚶 Grátis"
            
            with st.expander(f"Opção {i+1}: {lg['duration']['text']}{txt_custo}", expanded=(i==0)):
                col_inst, col_map = st.columns([4, 6])
                with col_inst:
                    for p in lg['steps']:
                        inst = p['html_instructions'].replace('<b>','**').replace('</b>','**').replace('<div style="font-size:0.9em">',' (').replace('</div>',')')
                        if p['travel_mode'] == "TRANSIT":
                            n_lin = p.get('transit_details', {}).get('line', {}).get('short_name', "Bus")
                            st.info(f"🚌 **Linha {n_lin}**\n\n{inst}")
                        else: st.write(f"- {inst}")
                with col_map:
                    pts = decode_poly(r['overview_polyline']['points'])
                    m_v1 = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB positron')
                    folium.PolyLine(pts, color="#00A1FF", weight=5).add_to(m_v1)
                    folium.Marker(pts[0], icon=folium.Icon(color='green', icon='play')).add_to(m_v1)
                    folium.Marker(pts[-1], icon=folium.Icon(color='red', icon='stop')).add_to(m_v1)
                    st_folium(m_v1, width=500, height=350, key=f"mapa_r_{i}")

# ==========================================
# ABA 2: MONITOR DE FROTA + TRAJETOS JSON
# ==========================================
with aba_monitor:
    st.subheader("Centro de Comando de Frota")
    
    col_a, col_t = st.columns([7, 3])
    with col_a:
        if st.checkbox("🔄 Radar Automático (30s)", value=False):
            st_autorefresh(interval=30000, key="refresh_frota")
            
    c_lin, c_pref = st.columns(2)
    with c_lin: lin_id = st.text_input("🔍 Buscar Linha:", placeholder="Ex: 8000")
    with c_pref: pref_alvo = st.text_input("🎯 Destacar Prefixo:", placeholder="Ex: 12345")

    if lin_id and TOKEN_SPTRANS:
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {}
            for l in res_l:
                origem = l['tp'] if l['sl'] == 1 else l['ts']
                destino = l['ts'] if l['sl'] == 1 else l['tp']
                nome_opcao = f"{l['lt']}-{l['tl']} | {origem} ➔ {destino} (Sentido {l['sl']})"
                opcoes[nome_opcao] = l
                
            l_sel = opcoes[st.selectbox("Sentido da Operação:", list(opcoes.keys()))]
            
            frota_res = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota_res.get('vs', [])
            
            st.divider()
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("🚌 Frota na Rua", len(vs))
            c_m2.metric("♿ Acessíveis", sum(1 for v in vs if v.get('a')))
            c_m3.metric("🕒 Atualizado", frota_res.get('hr', '--:--'))

            centro_mapa = [vs[0]['py'], vs[0]['px']] if vs else [-23.55, -46.63]
            m_frota = folium.Map(location=centro_mapa, zoom_start=13, tiles='CartoDB positron')
            
            if isinstance(dados_trajetos, dict):
                chave_json = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl']}"
                if chave_json in dados_trajetos:
                    rota_oficial = dados_trajetos[chave_json]
                    folium.PolyLine(rota_oficial, color="#00A1FF", weight=5, opacity=0.7, tooltip="Trajeto Oficial").add_to(m_frota)
                else:
                    st.caption(f"Trajeto oficial não encontrado no ficheiro JSON.")

            if gps_global and gps_global.get('latitude'):
                folium.Marker([gps_global['latitude'], gps_global['longitude']], popup="Você", icon=folium.Icon(color='green', icon='user', prefix='fa')).add_to(m_frota)

            if vs:
                lats, lons = [], []
                for v in vs:
                    lats.append(v['py']); lons.append(v['px'])
                    cor_icon = 'orange' if pref_alvo and pref_alvo in str(v['p']) else ('blue' if v.get('a') else 'red')
                    folium.Marker(
                        [v['py'], v['px']], tooltip=f"Prefixo: {v['p']}",
                        popup=f"🚌 Veículo {v['p']}<br>Sinal: {v.get('t', 'Real')}",
                        icon=folium.Icon(color=cor_icon, icon='bus', prefix='fa')
                    ).add_to(m_frota)
                m_frota.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
            
            st_folium(m_frota, width=1000, height=450, key="mapa_monitor")
        else: st.error("Linha não encontrada.")

# ==========================================
# ABA 3: RADAR DE ÁREA (AUTOMÁTICO)
# ==========================================
with aba_ponto:
    st.subheader("📍 Radar de Área (A sua Volta)")
    
    col_f1, col_f2 = st.columns([6, 4])
    with col_f1: so_acessivel = st.toggle("♿ Apenas Acessíveis", value=False)
    with col_f2:
        if st.checkbox("🔄 Atualizar Painel (30s)", value=True): st_autorefresh(interval=30000, key="refresh_radar")

    if TOKEN_SPTRANS:
        s_p = requests.Session()
        s_p.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        
        # Se tiver o GPS e o ficheiro de paragens estiver a funcionar
        if gps_global and gps_global.get('latitude') and isinstance(dados_paradas, list) and len(dados_paradas) > 0:
            lat_u, lon_u = gps_global['latitude'], gps_global['longitude']
            
            paradas_perto = []
            for p in dados_paradas:
                if isinstance(p, dict):
                    # TENTA LER NO FORMATO SPTRANS OU NO FORMATO GTFS ORIGINAL
                    lat_p = p.get('py') or p.get('stop_lat')
                    lon_p = p.get('px') or p.get('stop_lon')
                    id_p = p.get('cp') or p.get('stop_id')
                    nome_p = p.get('np') or p.get('stop_name', 'Paragem sem nome')
                    
                    if lat_p and lon_p and id_p:
                        dist = calcular_distancia(lat_u, lon_u, float(lat_p), float(lon_p))
                        if dist <= 400:
                            paradas_perto.append({
                                'cp': str(id_p), 
                                'np': str(nome_p), 
                                'dist': int(dist)
                            })
            
            paradas_perto = sorted(paradas_perto, key=lambda x: x['dist'])[:5]

            if paradas_perto:
                st.success(f"📡 A monitorizar {len(paradas_perto)} paragens à sua volta.")
                todas_previsoes = {} 
                
                with st.spinner("A sondar autocarros na região..."):
                    for p in paradas_perto:
                        prev = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={p['cp']}").json()
                        if prev and prev.get('p') and isinstance(prev['p'], dict) and 'l' in prev['p']:
                            for lin in prev['p']['l']:
                                vs_filt = [v for v in lin['vs'] if not so_acessivel or v.get('a')]
                                if vs_filt:
                                    chave_linha = f"{lin['c']} | {lin['lt0']} ➔ {lin['lt1']}"
                                    t_str = vs_filt[0]['t']
                                    minutos = int(''.join(filter(str.isdigit, str(t_str))) or 999) if "min" in str(t_str).lower() else 999
                                    
                                    if chave_linha not in todas_previsoes or minutos < todas_previsoes[chave_linha]['minutos']:
                                        todas_previsoes[chave_linha] = {
                                            "linha": lin,
                                            "veiculos": vs_filt,
                                            "minutos": minutos,
                                            "nome_ponto": f"{p['np']} ({p['dist']}m)"
                                        }

                if todas_previsoes:
                    st.markdown("### 🚍 A entrar na sua área:")
                    linhas_ordenadas = sorted(todas_previsoes.values(), key=lambda x: x['minutos'])
                    
                    for info in linhas_ordenadas:
                        lin = info["linha"]
                        vs_filt = info["veiculos"]
                        v_prox = vs_filt[0]
                        v_segundo = vs_filt[1] if len(vs_filt) > 1 else None
                        
                        def formatar_tempo(t_str):
                            if "min" in str(t_str).lower():
                                min_val = int(''.join(filter(str.isdigit, str(t_str))) or 0)
                                if min_val <= 5: return f"🟢 {t_str}", "#d4edda", "#155724" 
                                elif min_val <= 10: return f"🟡 {t_str}", "#fff3cd", "#856404" 
                                else: return f"⚪ {t_str}", "#e2e3e5", "#383d41" 
                            else: return f"⏰ {t_str}", "#dce4ec", "#004a99"

                        texto1, bg1, cor1 = formatar_tempo(v_prox['t'])
                        html_badge1 = f"<span style='background-color: {bg1}; color: {cor1}; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 14px;'>{texto1} (Prefixo: {v_prox['p']}) {'♿' if v_prox.get('a') else ''}</span>"
                        html_badge2 = f"<span style='color: #6c757d; font-size: 13px; margin-left: 10px;'>Próximo: {v_segundo['t']}</span>" if v_segundo else ""
                        html_local = f"<span style='color: #004a99; font-size: 12px; margin-left: 10px;'>📍 {info['nome_ponto']}</span>"

                        st.markdown(f"""
                        <div style="margin-bottom: 12px; border-bottom: 1px solid #eee; padding-bottom: 8px;">
                            <div style="font-size: 15px; font-weight: bold; margin-bottom: 4px; color: #333;">
                                🚌 {lin['c']} <span style="font-weight: normal; color: #555;">| {lin['lt0']} ➔ {lin['lt1']}</span>
                            </div>
                            <div>{html_badge1}{html_badge2}{html_local}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning("Nenhum autocarro a caminho das paragens ao seu redor.")
            else:
                st.info("Nenhuma paragem encontrada num raio de 400m do seu GPS.")
                
        # MODO MANUAL (Se não houver GPS ou o ficheiro paradas.json estiver vazio/com erro)
        else:
            if not isinstance(dados_paradas, list) or len(dados_paradas) == 0:
                st.warning("⚠️ O ficheiro 'paradas.json' não foi carregado corretamente. A usar o modo manual.")
            
            termo_ponto = st.text_input("🔍 Buscar paragem (Rua ou Código):", placeholder="Ex: Av. Paulista")
            if termo_ponto:
                pontos_busca = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/Buscar?termosBusca={termo_ponto}").json()
                if isinstance(pontos_busca, list) and len(pontos_busca) > 0:
                    dict_busca = {f"{p['np']} ({p['ed']})": p for p in pontos_busca}
                    ponto_selecionado = dict_busca[st.selectbox("Selecione a paragem:", list(dict_busca.keys()))]
                    
                    if ponto_selecionado:
                        cp = ponto_selecionado['cp']
                        with st.spinner("A consultar cronómetro da SPTrans..."):
                            previsao = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={cp}").json()
                        
                        if previsao and 'p' in previsao:
                            linhas = previsao['p'].get('l', [])
                            if not linhas: 
                                st.warning("Nenhum autocarro a caminho no momento.")
                            else:
                                st.markdown("### 🚍 Próximas Chegadas")
                                for lin in linhas:
                                    vs_filt = [v for v in lin['vs'] if not so_acessivel or v.get('a')]
                                    if vs_filt:
                                        v_prox = vs_filt[0]
                                        v_segundo = vs_filt[1] if len(vs_filt) > 1 else None
                                        
                                        def formatar_tempo(t_str):
                                            if "min" in str(t_str).lower():
                                                min_val = int(''.join(filter(str.isdigit, str(t_str))) or 0)
                                                if min_val <= 5: return f"🟢 {t_str}", "#d4edda", "#155724" 
                                                elif min_val <= 10: return f"🟡 {t_str}", "#fff3cd", "#856404" 
                                                else: return f"⚪ {t_str}", "#e2e3e5", "#383d41" 
                                            else: return f"⏰ {t_str}", "#dce4ec", "#004a99"

                                        texto1, bg1, cor1 = formatar_tempo(v_prox['t'])
                                        html_badge1 = f"<span style='background-color: {bg1}; color: {cor1}; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 14px;'>{texto1} (Prefixo: {v_prox['p']}) {'♿' if v_prox.get('a') else ''}</span>"
                                        html_badge2 = f"<span style='color: #6c757d; font-size: 13px; margin-left: 10px;'>Próximo: {v_segundo['t']}</span>" if v_segundo else ""

                                        st.markdown(f"""
                                        <div style="margin-bottom: 12px; border-bottom: 1px solid #eee; padding-bottom: 8px;">
                                            <div style="font-size: 15px; font-weight: bold; margin-bottom: 4px; color: #333;">
                                                🚌 {lin['c']} <span style="font-weight: normal; color: #555;">| {lin['lt0']} ➔ {lin['lt1']}</span>
                                            </div>
                                            <div>{html_badge1}{html_badge2}</div>
                                        </div>
                                        """, unsafe_allow_html=True)
                else:
                    st.warning("Nenhuma paragem encontrada com esse nome.")

# ==========================================
# ABA 4: LONDRES (EM BREVE)
# ==========================================
with aba_londres:
    st.title("🇬🇧 A preparar os motores...")
    st.info("A integração com a TfL (Transport for London) será construída aqui em breve.")
