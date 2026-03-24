import streamlit as st
import pandas as pd  # <--- ESSA É A LINHA QUE ESTÁ FALTANDO!
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
from streamlit_geolocation import streamlit_geolocation
from folium.plugins import LocateControl
import googlemaps

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="D23 Mobilidade", layout="wide")

# --- CONFIGURAÇÃO DE GPS GLOBAL NA SIDEBAR ---
with st.sidebar:
    st.header("📍 Localização em Tempo Real")
    st.write("Ative o GPS para usar as funções de 'Minha Posição'.")
    
    # AGORA SIM: Sem nenhum parâmetro dentro, para não dar erro!
    gps_global = streamlit_geolocation() 
    
    if gps_global and gps_global.get('latitude'):
        st.success("✅ GPS Conectado!")
    else:
        st.warning("Aguardando sinal...")
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
# ABA 1: PLANEJADOR DE ROTAS (VERSÃO CLARA)
# ==========================================
with aba_rota:
    st.subheader("🗺️ Traçar Nova Rota")
    
    # Limpando a memória de busca se necessário
    if 'resultado_busca' not in st.session_state:
        st.session_state['resultado_busca'] = None

    # --- 1. CONFIGURAÇÕES DE VIAGEM ---
    col_m, col_f = st.columns(2)
    with col_m:
        modo_v = st.radio("Como quer ir?", ["🚌 Transporte Público", "🚗 Carro", "🚶 A Pé"], horizontal=True, key="radio_modo_v1")
    with col_f:
        criterio = st.selectbox("Prioridade:", ["⚡ Mais Rápida", "🔄 Menos Baldeações", "🚶 Menos Caminhada"], key="select_ordem_v1")
    
    st.divider()

    # --- 2. DEFINIÇÃO DE ORIGEM E DESTINO ---
    col_origem_config, col_destino_config = st.columns(2)
    
    with col_origem_config:
        st.markdown("**📍 Ponto de Partida**")
        # Criamos uma escolha clara para não haver dúvida
        tipo_origem = st.radio("Definir origem por:", ["⌨️ Digitar Endereço", "🌍 Usar meu GPS"], horizontal=True, key="tipo_origem_v1")
        
        origem_final = None
        
        if tipo_origem == "⌨️ Digitar Endereço":
            origem_txt = st.text_input("Endereço de saída:", placeholder="Ex: Av. Paulista, 1500", key="txt_origem_v1")
            origem_final = origem_txt
        else:
            # Verifica se o GPS na barra lateral foi ativado
            if gps_global and gps_global.get('latitude'):
                origem_final = f"{gps_global['latitude']},{gps_global['longitude']}"
                st.success("✅ GPS capturado com sucesso!")
                st.caption(f"Coordenadas: {origem_final}")
            else:
                st.warning("⚠️ Ative o GPS na barra lateral (menu à esquerda) primeiro!")

    with col_destino_config:
        st.markdown("**🏁 Destino Final**")
        destino_final = st.text_input("Para onde você vai?", placeholder="Ex: Parque Ibirapuera", key="txt_destino_v1")
        st.write("") # Espaçador visual

    # --- 3. DATA E HORÁRIO ---
    st.markdown("### ⏱️ Quando você vai?")
    col_dt, col_hr = st.columns(2)
    with col_dt:
        data_v = st.date_input("Data da viagem:", value=datetime.now(), format="DD/MM/YYYY", key="date_viagem_v1")
    with col_hr:
        hora_v = st.time_input("Horário planejado:", value=datetime.now().time(), key="time_viagem_v1")

    st.divider()

    # --- 4. BOTÃO DE BUSCA E LÓGICA ---
    if st.button("🚀 Buscar Melhores Rotas", type="primary", use_container_width=True, key="btn_busca_v1"):
        if origem_final and destino_final:
            with st.spinner("Analisando mapas e rastreando frotas..."):
                dt_obj = datetime.combine(data_v, hora_v)
                ts = int(dt_obj.timestamp())
                m_google = {"🚌 Transporte Público": "transit", "🚗 Carro": "driving", "🚶 A Pé": "walking"}[modo_v]
                
                # Chamada API Google
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origem_final}&destination={destino_final}&mode={m_google}&departure_time={ts}&alternatives=true&language=pt-BR&key={CHAVE_GOOGLE}"
                res = requests.get(url).json()
                
                if res['status'] == 'OK':
                    st.session_state['resultado_busca'] = res['routes']
                else:
                    st.error("O Google não encontrou essa rota. Verifique se o endereço ou o GPS estão corretos.")
        else:
            st.warning("Preencha o destino e defina a origem para continuar.")

    # --- 5. EXIBIÇÃO DOS RESULTADOS (MEMÓRIA PERSISTENTE) ---
    if st.session_state['resultado_busca']:
        rotas_encontradas = st.session_state['resultado_busca']
        
        # Algoritmo de Triagem para os Expanders
        for i, r in enumerate(rotas_encontradas):
            leg = r['legs'][0]
            with st.expander(f"Opção {i+1}: {leg['duration']['text']} ({lg['distance']['text'] if 'lg' in locals() else ''})", expanded=(i==0)):
                c1, c2 = st.columns([4, 6])
                with c1:
                    st.write("**Instruções detalhadas:**")
                    for p in leg['steps']:
                        inst = p['html_instructions'].replace('<b>','**').replace('</b>','**').replace('<div style="font-size:0.9em">',' (').replace('</div>',')')
                        
                        if p['travel_mode'] == "TRANSIT":
                            det = p.get('transit_details', {})
                            n_lin = det.get('line', {}).get('short_name') or det.get('line', {}).get('name') or "???"
                            st.info(f"🚌 **Linha {n_lin}**\n\n{inst}")
                            
                            # RASTREIO DE PREFIXO EM TEMPO REAL
                            try:
                                s_st = requests.Session()
                                s_st.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
                                l_info = s_st.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={n_lin}").json()
                                if l_info:
                                    fr = s_st.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_info[0]['cl']}").json()
                                    if fr and fr['vs']:
                                        prefixos = [v['p'] for v in fr['vs'][:3]]
                                        st.success(f"📡 **Radar:** Veículos {', '.join(prefixos)} na linha.")
                            except: pass
                        else:
                            st.write(f"- {inst}")
                            
                with c2:
                    # Mapa da Rota
                    def decode_v1(p):
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
                    
                    pts = decode_v1(r['overview_polyline']['points'])
                    m_v1 = folium.Map(location=pts[0], zoom_start=13, tiles='CartoDB positron')
                    folium.PolyLine(pts, color="#00A1FF", weight=5).add_to(m_v1)
                    folium.Marker(pts[0], icon=folium.Icon(color='green', icon='play')).add_to(m_v1)
                    folium.Marker(pts[-1], icon=folium.Icon(color='red', icon='stop')).add_to(m_v1)
                    st_folium(m_v1, width=500, height=350, key=f"mapa_final_v1_{i}")

# ==========================================
# ABA 2: MONITOR DE FROTA (CENTRO DE COMANDO)
# ==========================================
with aba_monitor:
    st.subheader("🚌 Monitor de Frota ao Vivo")
    
    # --- 1. CONFIGURAÇÕES E RADAR ---
    col_a, col_t = st.columns([7, 3])
    with col_a:
        auto_v2 = st.checkbox("🔄 Radar Automático (30s)", value=False, key="check_auto_v2_definitivo")
        if auto_v2: 
            st_autorefresh(interval=30000, key="refresh_v2_definitivo")
    
    # --- 2. ENTRADA DE DADOS ---
    c_lin, c_pref = st.columns(2)
    with c_lin:
        lin_id = st.text_input("🔍 Linha (Número):", placeholder="Ex: 8000", key="in_lin_v2_final")
    with c_pref:
        prefixo_alvo = st.text_input("🎯 Destacar Ônibus (Prefixo):", placeholder="Ex: 12345", key="in_pref_v2_final")

    if lin_id:
        # Autenticação e Busca na SPTrans
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            sel_v2 = st.selectbox("Sentido da Operação:", list(opcoes.keys()), key="sel_lin_v2_final")
            l_sel = opcoes[sel_v2]
            
            # Puxando posições em tempo real
            frota_res = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota_res.get('vs', [])
            
            # --- 3. DASHBOARD DE MÉTRICAS ---
            st.divider()
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("🚌 Frota na Rua", len(vs))
            c_m2.metric("♿ Acessíveis", sum(1 for v in vs if v.get('a')))
            c_m3.metric("🕒 Relógio SPTrans", frota_res.get('hr', '--:--'))

            # --- 4. MAPA DE MONITORAMENTO ---
            # Define o centro do mapa (frota ou centro de SP)
            centro_mapa = [vs[0]['py'], vs[0]['px']] if vs else [-23.55, -46.63]
            
            # Escolha automática do tema (Dia/Noite)
            h_atual = datetime.now(pytz.timezone('America/Sao_Paulo')).hour
            tema_mapa = 'CartoDB dark_matter' if (h_atual >= 18 or h_atual < 6) else 'CartoDB positron'
            
            m_frota = folium.Map(location=centro_mapa, zoom_start=13, tiles=tema_mapa)
            
            # Marcador do seu GPS (Vindo da Sidebar)
            if gps_global and gps_global.get('latitude'):
                folium.Marker(
                    [gps_global['latitude'], gps_global['longitude']],
                    popup="Você está aqui",
                    icon=folium.Icon(color='green', icon='user', prefix='fa')
                ).add_to(m_frota)

            if vs:
                lats, lons = [], []
                for v in vs:
                    prefixo_atual = str(v['p'])
                    lats.append(v['py']); lons.append(v['px'])
                    
                    # Lógica de cores do monitor
                    if prefixo_alvo and prefixo_alvo in prefixo_atual:
                        cor_icon = 'orange'  # Ônibus que você está procurando
                    else:
                        cor_icon = 'blue' if v.get('a') else 'red'

                    folium.Marker(
                        [v['py'], v['px']],
                        tooltip=f"Prefixo: {prefixo_atual}",
                        popup=f"🚌 <b>Veículo {prefixo_atual}</b><br>Sinal: {v.get('t', 'Real')}",
                        icon=folium.Icon(color=cor_icon, icon='bus', prefix='fa')
                    ).add_to(m_frota)
                
                # Ajusta o zoom automaticamente para abraçar todos os ônibus
                m_frota.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
            
            st_folium(m_frota, width=1000, height=500, key="mapa_v2_final_corrigido")
            
            # --- 5. RAIO-X DA FROTA (VERSÃO BLINDADA CONTRA ERROS) ---
            st.markdown("### 📋 Detalhamento dos Veículos")
            if vs:
                df_raw = pd.DataFrame(vs)
                
                # O reindex impede o KeyError se uma coluna sumir da API
                df_view = df_raw.reindex(columns=['p', 't', 'a'], fill_value="N/D")
                df_view.columns = ['Prefixo', 'Último Sinal', 'Acessível']
                
                # Formatação visual da acessibilidade
                df_view['Acessível'] = df_view['Acessível'].apply(
                    lambda x: "✅ Sim" if x is True else "❌ Não" if x is False else "N/D"
                )
                
                # Se houver busca por prefixo, filtra a tabela também
                if prefixo_alvo:
                    df_view = df_view[df_view['Prefixo'].astype(str).str.contains(prefixo_alvo)]
                
                st.dataframe(df_view, use_container_width=True, hide_index=True)
            else:
                st.info("Aguardando sinal dos veículos para listar a frota.")
        else:
            st.error("Linha não encontrada na base da SPTrans.")

# ==========================================
# ABA 3: PAINEL DO PONTO (CHEGADA EM TEMPO REAL)
# ==========================================
with aba_ponto:
    st.subheader("🚏 Próximas Chegadas no Ponto")
    st.write("Saiba exatamente quanto tempo falta para o ônibus chegar até você.")

    # --- 1. BUSCA DO PONTO ---
    c_busca, c_gps = st.columns([7, 3])
    with c_busca:
        termo_ponto = st.text_input("🔍 Nome da Rua ou Código do Ponto:", placeholder="Ex: Av. Paulista ou 2600123", key="in_ponto_v3")
    
    with c_gps:
        st.write("Distância:")
        raio_busca = st.slider("Raio (metros):", 200, 1000, 500, key="slider_raio_v3")

    if termo_ponto:
        s_p = requests.Session()
        s_p.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        
        # Busca os pontos por nome ou código
        pontos = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/Buscar?termosBusca={termo_ponto}").json()
        
        if pontos:
            dict_pontos = {f"{p['np']} ({p['ed']})": p for p in pontos}
            sel_ponto = st.selectbox("Selecione o ponto exato:", list(dict_pontos.keys()), key="sel_ponto_v3")
            ponto_f = dict_pontos[sel_ponto]
            cp_ponto = ponto_f['cp'] # Código da Parada
            
            st.divider()
            
            # --- 2. BUSCA DE PREVISÕES ---
            with st.spinner("Consultando horários em tempo real..."):
                previsao = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={cp_ponto}").json()
                
            if previsao and 'p' in previsao:
                info_ponto = previsao['p']
                linhas_chegando = info_ponto.get('l', [])
                
                if linhas_chegando:
                    st.markdown(f"### ⏱️ Chegadas para: **{info_ponto['np']}**")
                    
                    # Layout em cards para as previsões
                    for linha in linhas_chegando:
                        with st.container(border=True):
                            col_icon, col_txt, col_tempo = st.columns([1, 6, 3])
                            
                            with col_icon:
                                st.title("🚌")
                            
                            with col_txt:
                                st.markdown(f"**Linha {linha['c']}**")
                                st.caption(f"Sentido: {linha['lt0']} ➔ {linha['lt1']}")
                            
                            with col_tempo:
                                # Pega a previsão do veículo mais próximo (v[0])
                                prox_veiculo = linha['vs'][0]
                                tempo_chegada = prox_veiculo['t']
                                st.metric("Chega em", f"{tempo_chegada}")
                                st.caption(f"Prefixo: {prox_veiculo['p']}")

                    # --- 3. MAPA DO PONTO ---
                    st.markdown("### 📍 Localização do Ponto")
                    m_ponto = folium.Map(location=[ponto_f['py'], ponto_f['px']], zoom_start=16, tiles='CartoDB positron')
                    
                    # Marcador do Ponto
                    folium.Marker(
                        [ponto_f['py'], ponto_f['px']],
                        popup=ponto_f['np'],
                        icon=folium.Icon(color='darkblue', icon='map-pin', prefix='fa')
                    ).add_to(m_ponto)
                    
                    # Marcador do Usuário (GPS Global)
                    if gps_global and gps_global.get('latitude'):
                        folium.Marker(
                            [gps_global['latitude'], gps_global['longitude']],
                            popup="Você",
                            icon=folium.Icon(color='green', icon='user', prefix='fa')
                        ).add_to(m_ponto)
                    
                    # Mostra os ônibus que estão chegando no mapa
                    for linha in linhas_chegando:
                        for v in linha['vs']:
                            folium.Marker(
                                [v['py'], v['px']],
                                popup=f"Linha {linha['c']} - Prefixo {v['p']}",
                                icon=folium.Icon(color='orange', icon='bus', prefix='fa')
                            ).add_to(m_ponto)

                    st_folium(m_ponto, width=1000, height=400, key="mapa_ponto_v3")
                else:
                    st.info("Nenhum ônibus com previsão de chegada para este ponto no momento.")
            else:
                st.warning("Não há dados de previsão para este ponto agora.")
        else:
            st.error("Nenhum ponto encontrado com esse nome ou código.")