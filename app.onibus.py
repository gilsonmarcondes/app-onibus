import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import json
import gzip
from streamlit_geolocation import streamlit_geolocation
import googlemaps
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
import xml.etree.ElementTree as ET 

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="D23 Mobilidade", layout="wide")

# --- CONFIGURAÇÃO DE GPS GLOBAL NA SIDEBAR ---
with st.sidebar:
    st.header("📍 Localização em Tempo Real")
    st.write("Ative o GPS para usar as funções de 'Minha Posição'.")
    # Chamada ÚNICA da biblioteca (evita erros de chave duplicada)
    gps_global = streamlit_geolocation(key="gps_unico_do_app")
    
    if gps_global and gps_global.get('latitude'):
        st.success(f"GPS Ativo: {gps_global['latitude']:.4f}, {gps_global['longitude']:.4f}")
    else:
        st.warning("GPS aguardando ativação...")
    st.divider()

# --- O BANHO DE LOJA (INJEÇÃO DE CSS) ---
st.markdown("""
    <style>
    /* Ocultar as marcas do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Estilizar os botões principais */
    div.stButton > button:first-child {
        background-color: #1E1E1E;
        color: white;
        border-radius: 8px;
        border: 1px solid #333333;
        padding: 10px 24px;
        font-weight: bold;
        transition: all 0.3s ease;
        width: 100%;
    }
    div.stButton > button:first-child:hover {
        background-color: #0066cc; /* Azul vibrante ao passar o mouse */
        border-color: #0066cc;
        color: white;
        transform: translateY(-2px); /* Pequeno efeito de elevação */
    }
    </style>
""", unsafe_allow_html=True)

st.title("🌍 D23 Transporte")

# --- AS SUAS CHAVES DE ACESSO ---
TOKEN_SPTRANS = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'
CHAVE_GOOGLE = 'AIzaSyAtp5jarrnwyy3_JWVfoWGbKlfEd4NjSKk' 
CHAVE_CLIMA = '1fb1b9310c7e1e3192d52f5821b0c1ab'

# --- AS CHAVES INTERNACIONAIS ---
CHAVE_TFL = 'd4fcd31a062a4b1dab6ea40cf1896241'           
CHAVE_BODS = '76765b7adeb5b7e231139229df66db24b94a12d7' # <-- Sua chave do interior da Inglaterra
CHAVE_SCOTLAND = 'CHAVE_TRAVELINE_AQUI'                  
CHAVE_RAIL = 'CHAVE_DARWIN_AQUI' 

gmaps = googlemaps.Client(key=CHAVE_GOOGLE)

def obter_clima_destino(lat, lon, api_key):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=pt_br"
    try:
        resposta = requests.get(url).json()
        if resposta.get('main'):
            temp = round(resposta['main']['temp'])
            descricao = resposta['weather'][0]['description'].capitalize()
            icone = "☀️" if "limpo" in descricao.lower() else "☁️" if "nublado" in descricao.lower() else "🌧️" if "chuva" in descricao.lower() else "⛅"
            return f"{icone} **{temp}°C** - {descricao}"
    except:
        pass
    return None

@st.cache_data
def carregar_gtfs():
    try:
        with gzip.open('trajetos.json.gz', 'rt', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}
trajetos_sp = carregar_gtfs()

# --- INICIALIZAR A MEMÓRIA DO APLICATIVO ---
if 'memoria_origem' not in st.session_state:
    st.session_state.memoria_origem = ""
if 'memoria_destino' not in st.session_state:
    st.session_state.memoria_destino = ""

aba_rota, aba_monitor, aba_ponto = st.tabs(["🗺️ Planejar Rota", "🚌 Monitor Clássico", "🚏 Painel do Ponto"])

# ==========================================
# ABA 1: PLANEJADOR DE ROTAS (GPS GLOBAL)
# ==========================================
with aba_rota:
    st.subheader("🗺️ Traçar Nova Rota")
    
    if 'resultado_busca' not in st.session_state:
        st.session_state['resultado_busca'] = None

    col_m, col_f = st.columns(2)
    with col_m:
        modo_v = st.radio("Como quer ir?", ["🚌 Transporte Público", "🚗 Carro", "🚶 A Pé"], horizontal=True, key="r_modo_v1")
    with col_f:
        criterio = st.selectbox("Prioridade:", ["⚡ Mais Rápida", "🔄 Menos Baldeações", "🚶 Menos Caminhada"], key="s_ordem_v1")
    
    col_o, col_d = st.columns(2)
    with col_o:
        origem_txt = st.text_input("📍 Origem:", placeholder="Endereço ou deixe vazio para usar GPS", key="in_orig_v1")
        # Lógica inteligente de origem
        origem_final = origem_txt
        if not origem_txt and gps_global and gps_global.get('latitude'):
            origem_final = f"{gps_global['latitude']},{gps_global['longitude']}"
            st.caption("✅ Usando sua localização atual via GPS.")
            
    with col_d:
        destino = st.text_input("🏁 Destino:", placeholder="Ex: Estação da Luz", key="in_dest_v1")

    col_dt, col_hr = st.columns(2)
    with col_dt:
        data_v = st.date_input("Data:", value=datetime.now(), format="DD/MM/YYYY", key="d_v1")
    with col_hr:
        hora_v = st.time_input("Horário:", value=datetime.now().time(), key="h_v1")

    if st.button("🚀 Buscar Rotas e Rastrear Ônibus", type="primary", use_container_width=True, key="btn_rota_v1"):
        if origem_final and destino:
            with st.spinner("Conectando aos satélites e frota..."):
                dt_obj = datetime.combine(data_v, hora_v)
                ts = int(dt_obj.timestamp())
                m_google = {"🚌 Transporte Público": "transit", "🚗 Carro": "driving", "🚶 A Pé": "walking"}[modo_v]
                
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origem_final}&destination={destino}&mode={m_google}&departure_time={ts}&alternatives=true&language=pt-BR&key={CHAVE_GOOGLE}"
                res = requests.get(url).json()
                if res['status'] == 'OK':
                    st.session_state['resultado_busca'] = res['routes']
                else: st.error("Não encontramos rotas. Verifique os endereços.")
        else: st.warning("Por favor, informe o destino e ative o GPS ou digite a origem.")

    if st.session_state['resultado_busca']:
        for i, r in enumerate(st.session_state['resultado_busca']):
            lg = r['legs'][0]
            with st.expander(f"Opção {i+1}: {lg['duration']['text']} ({lg['distance']['text']})", expanded=(i==0)):
                c1, c2 = st.columns([4, 6])
                with c1:
                    for p in lg['steps']:
                        inst = p['html_instructions'].replace('<b>','**').replace('</b>','**').replace('<div style="font-size:0.9em">',' (').replace('</div>',')')
                        if p['travel_mode'] == "TRANSIT":
                            det = p.get('transit_details', {})
                            n_lin = det.get('line', {}).get('short_name') or det.get('line', {}).get('name') or "---"
                            st.info(f"🚌 **Linha {n_lin}**\n\n{inst}")
                            # --- RADAR DE PREFIXOS (PLACA DO UBER) ---
                            try:
                                s = requests.Session()
                                s.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
                                l_info = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={n_lin}").json()
                                if l_info:
                                    frota = s.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_info[0]['cl']}").json()
                                    if frota and frota['vs']:
                                        pre = [v['p'] for v in frota['vs'][:3]]
                                        st.success(f"📡 **No Radar:** Veículos {', '.join(pre)}")
                            except: pass
                        else: st.write(f"- {inst}")
                with c2:
                    # Função de decodificação de linha (interna para evitar imports)
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
                    
                    pts = decode_poly(r['overview_polyline']['points'])
                    m_r = folium.Map(location=pts[0], zoom_start=13, tiles='CartoDB positron')
                    folium.PolyLine(pts, color="#00A1FF", weight=5).add_to(m_r)
                    folium.Marker(pts[0], icon=folium.Icon(color='green')).add_to(m_r)
                    folium.Marker(pts[-1], icon=folium.Icon(color='red')).add_to(m_r)
                    st_folium(m_r, width=500, height=300, key=f"mapa_r_{i}")



# ==========================================
# ABA 2: MONITOR DE FROTA (DADOS & MAPA)
# ==========================================
with aba_monitor:
    st.subheader("🚌 Monitor de Frota ao Vivo")
    
    col_a, col_t = st.columns([7, 3])
    with col_a:
        auto = st.checkbox("🔄 Atualizar Radar Sozinho (30s)", value=False, key="check_auto_v2")
        if auto: st_autorefresh(interval=30000, key="refresh_v2")
    
    lin_id = st.text_input("🔍 Digite a linha para monitorar:", placeholder="Ex: 8000", key="in_lin_v2")
    
    if lin_id:
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            sel = st.selectbox("Escolha o sentido:", list(opcoes.keys()), key="sel_lin_v2")
            l_sel = opcoes[sel]
            
            # Posição dos ônibus
            frota = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota.get('vs', [])
            
            # Dashboard
            st.divider()
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("🚌 Ônibus na Rua", len(vs))
            c_m2.metric("♿ Com Acessibilidade", sum(1 for v in vs if v.get('a')))
            c_m3.metric("🕒 Atualização API", frota.get('hr', '--:--'))

            # Mapa
            centro = [vs[0]['py'], vs[0]['px']] if vs else [-23.55, -46.63]
            m_f = folium.Map(location=centro, zoom_start=13, tiles='CartoDB positron')
            
            # MARCADOR DO USUÁRIO (Vindo do GPS Global)
            if gps_global and gps_global.get('latitude'):
                folium.Marker(
                    [gps_global['latitude'], gps_global['longitude']],
                    popup="Você está aqui",
                    icon=folium.Icon(color='green', icon='user', prefix='fa')
                ).add_to(m_f)

            if vs:
                for v in vs:
                    cor = 'blue' if v.get('a') else 'red'
                    folium.Marker(
                        [v['py'], v['px']],
                        popup=f"Prefixo: {v['p']}<br>Sinal: {v.get('t', 'Real')}",
                        icon=folium.Icon(color=cor, icon='bus', prefix='fa')
                    ).add_to(m_f)
            
            st_folium(m_f, width=1000, height=500, key="mapa_frota_v2")
            
            # Tabela de Dados
            if vs:
                st.markdown("### 📋 Raio-X da Frota")
                df = pd.DataFrame(vs)[['p', 't', 'a']]
                df.columns = ['Prefixo', 'Último Sinal', 'Acessível']
                df['Acessível'] = df['Acessível'].map({True: "✅ Sim", False: "❌ Não"})
                st.dataframe(df, use_container_width=True, hide_index=True)
        else: st.error("Linha não encontrada.")

# ==========================================
# ABA 3: PAINEL DO PONTO (UX PREMIUM)
# ==========================================
with aba_ponto:
    st.subheader("🚏 Painel Expresso do Ponto")
    st.write("Encontre seu ponto e acompanhe as chegadas em tempo real.")
    
    col_r1, col_r2 = st.columns([8, 2])
    auto_refresh_ponto = col_r2.checkbox("🔄 Radar (30s)", value=False, key="refresh_ponto")
    
    if auto_refresh_ponto:
        st_autorefresh(interval=30000, limit=None, key="radar_paradas")

    # --- MEMÓRIA DE CURTO PRAZO (Histórico) ---
    if 'historico_pontos' not in st.session_state:
        st.session_state['historico_pontos'] = []
        
    def salvar_no_historico(nome, codigo, lat, lon):
        novo_ponto = {"nome": nome, "codigo": codigo, "lat": lat, "lon": lon}
        if novo_ponto not in st.session_state['historico_pontos']:
            st.session_state['historico_pontos'].insert(0, novo_ponto)
        # Mantém apenas os 3 últimos na memória
        st.session_state['historico_pontos'] = st.session_state['historico_pontos'][:3]

    # Variáveis globais da aba
    codigo_da_parada = None
    nome_exibicao = ""
    lat_exibicao = None
    lon_exibicao = None

    # --- A NOVA INTERFACE (ABAS INTERNAS) ---
    tab_fav, tab_linha, tab_gps, tab_nome = st.tabs([
        "⭐ Favoritos & Histórico", 
        "🚌 Por Linha", 
        "🗺️ Radar GPS", 
        "🔍 Por Nome"
    ])
    
    # 1. ABA DE FAVORITOS & HISTÓRICO
    with tab_fav:
        st.markdown("### Seus Pontos Salvos")
        pontos_vip = {
            "Parada 1 - Sabesp (Sentido Centro)": {"cp": 7203277, "lat": -23.5927, "lon": -46.6728}, 
            "Américo Brasiliense (Sentido Bairro)": {"cp": 7203285, "lat": -23.632, "lon": -46.705}
        }
        
        opcoes_dropdown = ["(Selecione um ponto abaixo)"] + [f"🌟 {nome}" for nome in pontos_vip.keys()]
        
        if st.session_state['historico_pontos']:
            opcoes_dropdown += ["--- ÚLTIMAS BUSCAS NESTA SESSÃO ---"]
            opcoes_dropdown += [f"🕒 {p['nome']}" for p in st.session_state['historico_pontos']]
            
        escolha_fav = st.selectbox("Escolha um ponto rápido:", opcoes_dropdown, key="sel_fav")
        
        if escolha_fav.startswith("🌟"):
            nome_limpo = escolha_fav.replace("🌟 ", "")
            codigo_da_parada = pontos_vip[nome_limpo]["cp"]
            nome_exibicao = nome_limpo
            lat_exibicao = pontos_vip[nome_limpo].get("lat")
            lon_exibicao = pontos_vip[nome_limpo].get("lon")
        elif escolha_fav.startswith("🕒"):
            nome_limpo = escolha_fav.replace("🕒 ", "")
            for p in st.session_state['historico_pontos']:
                if p['nome'] == nome_limpo:
                    codigo_da_parada = p['codigo']
                    nome_exibicao = p['nome']
                    lat_exibicao = p['lat']
                    lon_exibicao = p['lon']

    # 2. ABA DE RASTREIO DE LINHA
    with tab_linha:
        st.info("Acha todos os pontos do trajeto (Ida e Volta).")
        busca_linha = st.text_input("Linha (ex: 6450, 5300):", key="input_linha")
        if busca_linha:
            session = requests.Session()
            session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
            linhas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={busca_linha}").json()
            
            if linhas:
                opcoes_linhas = {}
                for l in linhas:
                    sentido = l.get('sl', 1)
                    if sentido == 1:
                        nome_rota = f"{l.get('c', 'Linha')} (IDA) - {l.get('tp', 'Term 1')} ➔ {l.get('ts', 'Term 2')} [ID: {l.get('cl')}]"
                    else:
                        nome_rota = f"{l.get('c', 'Linha')} (VOLTA) - {l.get('ts', 'Term 2')} ➔ {l.get('tp', 'Term 1')} [ID: {l.get('cl')}]"
                    opcoes_linhas[nome_rota] = l.get('cl')
                
                escolha_linha = st.selectbox("Selecione o sentido:", list(opcoes_linhas.keys()), key="sel_linha")
                codigo_da_linha = opcoes_linhas[escolha_linha]
                paradas_da_linha = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/BuscarParadasPorLinha?codigoLinha={codigo_da_linha}").json()
                
                if paradas_da_linha:
                    st.success(f"Encontramos {len(paradas_da_linha)} paradas!")
                    opcoes_paradas = {f"{p['np']} (Endereço: {p.get('ed', 'S/N')}) - ID: {p['cp']}": p for p in paradas_da_linha}
                    escolha_parada = st.selectbox("Escolha seu ponto:", list(opcoes_paradas.keys()), key="sel_ponto_linha")
                    
                    dados_p = opcoes_paradas[escolha_parada]
                    codigo_da_parada = dados_p['cp']
                    nome_exibicao = escolha_parada.split('(')[0].strip()
                    lat_exibicao = dados_p.get('py')
                    lon_exibicao = dados_p.get('px')
                    
                    salvar_no_historico(nome_exibicao, codigo_da_parada, lat_exibicao, lon_exibicao)
                else:
                    st.warning("Trajeto indisponível para esta linha.")
            else:
                st.error("Nenhuma linha encontrada.")

    # 3. ABA RADAR GOOGLE
    with tab_gps:
        st.info("O Google acha a rua, a SPTrans acha o ponto.")
        local_atual = st.text_input("Onde você está? (Ex: 'MASP'):", key="input_gps")
        if local_atual:
            url_google = f"https://maps.googleapis.com/maps/api/geocode/json?address={local_atual}&key={CHAVE_GOOGLE}"
            res_google = requests.get(url_google).json()
            if res_google['status'] == 'OK':
                rua_oficial = ""
                for comp in res_google['results'][0]['address_components']:
                    if 'route' in comp['types']:
                        rua_oficial = comp['long_name']
                        break
                if rua_oficial:
                    st.success(f"📍 Região: **{rua_oficial}**")
                    session = requests.Session()
                    session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
                    paradas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/Buscar?termosBusca={rua_oficial}").json()
                    if paradas:
                        opcoes_paradas = {f"{p['np']} ({p.get('ed','S/N')})": p for p in paradas}
                        escolha_parada = st.selectbox("Selecione a parada:", list(opcoes_paradas.keys()), key="sel_ponto_gps")
                        
                        dados_p = opcoes_paradas[escolha_parada]
                        codigo_da_parada = dados_p['cp']
                        nome_exibicao = escolha_parada.split('(')[0].strip()
                        lat_exibicao = dados_p.get('py')
                        lon_exibicao = dados_p.get('px')
                        salvar_no_historico(nome_exibicao, codigo_da_parada, lat_exibicao, lon_exibicao)
                    else:
                        st.warning("Nenhum ponto SPTrans nessa rua.")
                else:
                    st.warning("Rua não identificada pelo Google.")

    # 4. ABA BUSCA POR NOME
    with tab_nome:
        st.info("A busca raiz (use apenas a palavra-chave principal).")
        busca_ponto = st.text_input("Palavra-chave (ex: Bela Vista):", key="input_nome")
        if busca_ponto:
            session = requests.Session()
            session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
            paradas = session.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/Buscar?termosBusca={busca_ponto}").json()
            if paradas:
                opcoes_paradas = {f"{p['np']} ({p.get('ed','S/N')})": p for p in paradas}
                escolha_parada = st.selectbox("Selecione a parada:", list(opcoes_paradas.keys()), key="sel_ponto_nome")
                
                dados_p = opcoes_paradas[escolha_parada]
                codigo_da_parada = dados_p['cp']
                nome_exibicao = escolha_parada.split('(')[0].strip()
                lat_exibicao = dados_p.get('py')
                lon_exibicao = dados_p.get('px')
                salvar_no_historico(nome_exibicao, codigo_da_parada, lat_exibicao, lon_exibicao)
            else:
                st.error("Nenhum ponto encontrado.")

    # ==========================================
    # O MOTOR DO LETREIRO DIGITAL & MAPA VISUAL
    # ==========================================
    st.divider()
    
    if codigo_da_parada:
        col_info, col_mapa = st.columns([6, 4])
        
        with col_info:
            st.markdown(f"### 🚥 Chegadas em: {nome_exibicao}")
            filtro_linha = st.text_input("Filtrar linha (ex: 6500):", placeholder="Deixe em branco para ver todas", key="filtro_aba3")
            
            session = requests.Session()
            session.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
            previsao_url = f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={codigo_da_parada}"
            dados_previsao = session.get(previsao_url).json()
            
            if dados_previsao and 'p' in dados_previsao and 'l' in dados_previsao['p']:
                linhas_chegando = dados_previsao['p']['l']
                painel = []
                
                for linha in linhas_chegando:
                    numero_linha = linha.get('c', '')
                    if filtro_linha and filtro_linha not in numero_linha:
                        continue 
                        
                    letreiro = f"{numero_linha} - {linha.get('lt0', 'Destino')} ➔ {linha.get('lt1', 'Origem')}"
                    for veiculo in linha['vs']:
                        painel.append({"linha": letreiro, "hora_chegada": veiculo['t'], "prefixo": veiculo['p']})
                
                painel = sorted(painel, key=lambda x: x['hora_chegada'])
                
                if painel:
                    for item in painel:
                        st.info(f"🕒 **{item['hora_chegada']}** | 🚌 **{item['linha']}** (Carro: {item['prefixo']})")
                else:
                    st.warning("Nenhum ônibus correspondente ao seu filtro no momento.")
            else:
                st.warning("Não há nenhum ônibus no radar para este ponto.")
        
        with col_mapa:
            if lat_exibicao and lon_exibicao:
                st.markdown("**📍 Radar ao Vivo**")
                import pandas as pd
                
                # 1. Cria a lista de GPS começando por você (O ponto vermelho maior)
                coordenadas = [{"lat": lat_exibicao, "lon": lon_exibicao, "cor": "#FF0000", "tamanho": 100}]
                
                # 2. Caça o GPS de cada ônibus que está vindo na previsão
                if dados_previsao and 'p' in dados_previsao and 'l' in dados_previsao['p']:
                    for linha in dados_previsao['p']['l']:
                        numero_linha = linha.get('c', '')
                        
                        # Se você filtrou uma linha, só mostra os ônibus dela no mapa
                        if filtro_linha and filtro_linha not in numero_linha:
                            continue
                            
                        for veiculo in linha['vs']:
                            lat_bus = veiculo.get('py')
                            lon_bus = veiculo.get('px')
                            
                            # Se o GPS do ônibus estiver funcionando, adiciona como ponto azul
                            if lat_bus and lon_bus:
                                coordenadas.append({
                                    "lat": lat_bus, 
                                    "lon": lon_bus, 
                                    "cor": "#0000FF", # Azul
                                    "tamanho": 30     # Menorzinho
                                })
                
                # 3. Desenha o mapa final com as cores e tamanhos
                df_mapa = pd.DataFrame(coordenadas)
                try:
                    # Tenta desenhar com cores (Versões novas do Streamlit)
                    st.map(df_mapa, latitude="lat", longitude="lon", color="cor", size="tamanho", zoom=14)
                except:
                    # Plano B (Versões antigas do Streamlit aceitam só os pontos puros)
                    st.map(df_mapa, latitude="lat", longitude="lon", zoom=14)
            else:
                st.caption("Mapa indisponível (SPTrans não forneceu coordenadas para este ponto).")