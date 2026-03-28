import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
import math
from streamlit_autorefresh import st_autorefresh
from streamlit_geolocation import streamlit_geolocation
from folium.plugins import LocateControl
import googlemaps

# ==========================================
# 1. CONFIGURAÇÕES E CHAVES (COFRE SEGURO)
# ==========================================
# --- AS SUAS CHAVES DE ACESSO (SÃO PAULO E CLIMA) ---
TOKEN_SPTRANS = st.secrets["TOKEN_SPTRANS"]
CHAVE_GOOGLE = st.secrets["CHAVE_GOOGLE"]
CHAVE_CLIMA = st.secrets.get("CHAVE_CLIMA", "") # Usando get para evitar erro se não existir ainda

# --- AS CHAVES INTERNACIONAIS (REINO UNIDO) ---
CHAVE_TFL = st.secrets.get("CHAVE_TFL", "")
CHAVE_BODS = st.secrets.get("CHAVE_BODS", "")
CHAVE_SCOTLAND = st.secrets.get("CHAVE_SCOTLAND", "")
CHAVE_RAIL = st.secrets.get("CHAVE_RAIL", "")

# ==========================================
# 2. DESIGN PREMIUM (CSS) E CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { border-radius: 8px; height: 3em; background-color: #004a99; color: white; font-weight: bold; transition: 0.3s; }
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

# ==========================================
# 3. BARRA LATERAL (GPS GLOBAL E CLIMA)
# ==========================================
with st.sidebar:
    st.header("🌦️ Central de Status")
    
    st.write("Sua Posição (GPS):")
    gps_global = streamlit_geolocation()
    
    if gps_global and gps_global.get('latitude'):
        lat, lon = gps_global['latitude'], gps_global['longitude']
        st.success("📍 Satélite Conectado")
        
        # MÓDULO DE CLIMA (Open-Meteo)
        try:
            url_clima = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            clima = requests.get(url_clima).json()['current_weather']
            icones = {0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️", 45: "🌫️", 51: "🌧️", 61: "🌧️", 71: "❄️", 95: "⚡"}
            icone_atual = icones.get(clima['weathercode'], "🌡️")
            
            st.metric("Clima Local", f"{icone_atual} {clima['temperature']}°C")
            if clima['weathercode'] >= 51: 
                st.warning("☔ Possibilidade de chuva detectada.")
        except:
            st.caption("🌤️ Clima indisponível no momento.")
    else:
        st.warning("📍 Ative o GPS para previsões locais.")
    
    st.divider()
    st.caption("BusRadar Pro v2.5")

# ==========================================
# 4. SISTEMA DE ABAS
# ==========================================
aba_rota, aba_monitor, aba_ponto, aba_londres = st.tabs([
    "🗺️ Planejador de Rotas", "🚌 Monitor de Frota", "🚏 Painel do Ponto", "🇬🇧 Londres (Em Breve)"
])

# ==========================================
# ABA 1: PLANEJADOR DE ROTAS
# ==========================================
with aba_rota:
    st.subheader("Traçar Nova Viagem")
    
    if 'resultado_busca' not in st.session_state:
        st.session_state['resultado_busca'] = None

    c1, c2 = st.columns(2)
    with c1:
        modo_v = st.radio("Modo de Viagem:", ["🚌 Transporte Público", "🚗 Carro", "🚶 A Pé"], horizontal=True)
        tipo_origem = st.radio("Origem:", ["🌍 Usar meu GPS", "⌨️ Digitar Endereço"], horizontal=True)
    with c2:
        criterio = st.selectbox("Prioridade:", ["⚡ Mais Rápida", "🔄 Menos Baldeações", "🚶 Menos Caminhada"])
        destino_v = st.text_input("Destino Final:", placeholder="Ex: Parque Ibirapuera")

    origem_final = None
    if tipo_origem == "🌍 Usar meu GPS":
        if gps_global and gps_global.get('latitude'):
            origem_final = f"{gps_global['latitude']},{gps_global['longitude']}"
        else:
            st.warning("⚠️ Ative o GPS na barra lateral primeiro.")
    else:
        origem_final = st.text_input("Endereço de partida:", placeholder="Ex: Av. Paulista, 1500")

    if st.button("🚀 Buscar Melhores Rotas", type="primary"):
        if origem_final and destino_v:
            with st.spinner("Calculando rotas e tarifas..."):
                dt_obj = datetime.now()
                ts = int(dt_obj.timestamp())
                m_g = {"🚌 Transporte Público": "transit", "🚗 Carro": "driving", "🚶 A Pé": "walking"}[modo_v]
                
                url_rota = f"https://maps.googleapis.com/maps/api/directions/json?origin={origem_final}&destination={destino_v}&mode={m_g}&departure_time={ts}&alternatives=true&language=pt-BR&key={CHAVE_GOOGLE}"
                res = requests.get(url_rota).json()
                
                if res['status'] == 'OK':
                    st.session_state['resultado_busca'] = res['routes']
                else:
                    st.error("Rota não encontrada. Verifique os locais.")
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
                            
                            try:
                                s_st = requests.Session()
                                s_st.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
                                l_info = s_st.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={n_lin}").json()
                                if l_info:
                                    fr = s_st.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_info[0]['cl']}").json()
                                    if fr and fr['vs']:
                                        prefixos = [v['p'] for v in fr['vs'][:3]]
                                        st.success(f"📡 Veículos na rua agora: {', '.join(prefixos)}")
                            except: pass
                        else:
                            st.write(f"- {inst}")
                with col_map:
                    pts = decode_poly(r['overview_polyline']['points'])
                    m_v1 = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB positron')
                    folium.PolyLine(pts, color="#00A1FF", weight=5).add_to(m_v1)
                    folium.Marker(pts[0], icon=folium.Icon(color='green', icon='play')).add_to(m_v1)
                    folium.Marker(pts[-1], icon=folium.Icon(color='red', icon='stop')).add_to(m_v1)
                    st_folium(m_v1, width=500, height=350, key=f"mapa_r_{i}")

# ==========================================
# ABA 2: MONITOR DE FROTA
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

    if lin_id:
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            # CORREÇÃO: Lê o 'sl' (sentido) para garantir que Ida e Volta apareçam
            opcoes = {}
            for l in res_l:
                origem = l['tp'] if l['sl'] == 1 else l['ts']
                destino = l['ts'] if l['sl'] == 1 else l['tp']
                nome_opcao = f"{l['lt']}-{l['tl']} | {origem} ➔ {destino}"
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
            
            st.markdown("### 📋 Raio-X da Frota")
            if vs:
                df_view = pd.DataFrame(vs).reindex(columns=['p', 't', 'a'], fill_value="N/D")
                df_view.columns = ['Prefixo', 'Último Sinal', 'Acessível']
                df_view['Acessível'] = df_view['Acessível'].apply(lambda x: "✅ Sim" if x is True else "❌ Não" if x is False else "N/D")
                if pref_alvo: df_view = df_view[df_view['Prefixo'].astype(str).str.contains(pref_alvo)]
                st.dataframe(df_view, use_container_width=True, hide_index=True)
            else: st.info("Aguardando sinal dos veículos.")
        else: st.error("Linha não encontrada.")

# ==========================================
# ABA 3: PAINEL DO PONTO
# ==========================================
with aba_ponto:
    st.subheader("🚏 Painel de Chegada")
    
    col_b, col_f = st.columns([6, 4])
    with col_b: termo_ponto = st.text_input("🔍 Buscar ponto (Rua ou Código):", placeholder="Ex: Av. Paulista")
    with col_f:
        so_acessivel = st.toggle("♿ Apenas Acessíveis", value=False)
        if st.checkbox("🔄 Atualizar Painel (30s)", value=True): 
            st_autorefresh(interval=30000, key="refresh_ponto")

    s_p = requests.Session()
    s_p.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
    ponto_selecionado = None

    if termo_ponto:
        pontos_busca = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/Buscar?termosBusca={termo_ponto}").json()
        
        if isinstance(pontos_busca, list) and len(pontos_busca) > 0:
            dict_busca = {}
            for p in pontos_busca:
                nome_format = f"{p['np']} ({p['ed']})"
                if gps_global and gps_global.get('latitude'):
                    dist = calcular_distancia(gps_global['latitude'], gps_global['longitude'], p['py'], p['px'])
                    nome_format += f" 🚶 a {int(dist)}m"
                dict_busca[nome_format] = p
                
            ponto_selecionado = dict_busca[st.selectbox("Selecione o ponto exato:", list(dict_busca.keys()))]
        else:
            st.warning("Nenhum ponto encontrado. Tente outro nome ou código.")
    else:
        st.info("Digite o nome de uma rua (ex: Augusta) ou o código do ponto para começar.")

    if ponto_selecionado:
        cp = ponto_selecionado['cp']

        with st.spinner("Consultando cronômetro da SPTrans..."):
            previsao = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={cp}").json()
        
        if previsao and 'p' in previsao:
            linhas = previsao['p'].get('l', [])
            if not linhas: 
                st.warning("Nenhum ônibus a caminho no momento.")
            else:
                for lin in linhas:
                    vs_filt = [v for v in lin['vs'] if not so_acessivel or v.get('a')]
                    if vs_filt:
                        v_prox = vs_filt[0]
                        tempo = v_prox['t']
                        perto = "min" in tempo and int(tempo.replace(" min", "")) <= 5
                        
                        with st.chat_message("bus"):
                            c1, c2, c3 = st.columns([2, 5, 3])
                            with c1: st.markdown(f"### {lin['c']}")
                            with c2: 
                                st.write(f"**{lin['lt0']} ➔ {lin['lt1']}**")
                                st.caption(f"Prefixo: {v_prox['p']} {'♿' if v_prox.get('a') else ''}")
                            with c3:
                                if perto:
                                    st.error(f"⏱️ {tempo}")
                                    st.caption("Corre que está vindo!")
                                else: 
                                    st.subheader(f"⏱️ {tempo}")

                st.divider()
                st.markdown("### 🗺️ Radar do Ponto")
                m_v3 = folium.Map(location=[ponto_selecionado['py'], ponto_selecionado['px']], zoom_start=16, tiles='CartoDB positron')
                
                folium.Marker([ponto_selecionado['py'], ponto_selecionado['px']], icon=folium.Icon(color='darkblue', icon='map-pin', prefix='fa'), popup="Ponto").add_to(m_v3)
                
                if gps_global and gps_global.get('latitude'):
                    folium.Marker([gps_global['latitude'], gps_global['longitude']], icon=folium.Icon(color='green', icon='user', prefix='fa'), popup="Você").add_to(m_v3)
                
                for lin in linhas:
                    for v in lin['vs']:
                        folium.Marker([v['py'], v['px']], popup=f"Linha {lin['c']}", icon=folium.Icon(color='orange', icon='bus', prefix='fa')).add_to(m_v3)
                
                st_folium(m_v3, width=1000, height=400, key="mapa_ponto_final_corrigido")

# ==========================================
# ABA 4: LONDRES (EM BREVE)
# ==========================================
with aba_londres:
    st.title("🇬🇧 Preparando os motores...")
    st.info("A integração com a TfL (Transport for London) será construída aqui em breve.")
